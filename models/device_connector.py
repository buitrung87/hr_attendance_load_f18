from odoo import models, fields
from datetime import datetime, timedelta
import pytz
from odoo.exceptions import UserError


class AttendanceDevice(models.Model):
    _name = 'attendance.device'
    _description = 'Attendance Device'

    name = fields.Char(required=True)
    ip_address = fields.Char(required=True)
    port = fields.Integer(default=4370)
    comm_key = fields.Integer(default=0, help="Numeric communication password (CommKey) if set on device")
    timeout = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    auto_pull = fields.Boolean(default=True, help="If enabled, cron will pull from this device")

    # Pull range selection
    pull_start = fields.Datetime(help="Chọn thời điểm bắt đầu để tải log (theo giờ hiển thị)")
    pull_end = fields.Datetime(help="Chọn thời điểm kết thúc để tải log (theo giờ hiển thị)")

    # Device timezone for proper conversion (default UTC+7)
    timezone = fields.Char(default='Asia/Ho_Chi_Minh', help="Múi giờ của máy chấm công, ví dụ: Asia/Ho_Chi_Minh")

    last_pull_at = fields.Datetime()
    last_log_timestamp = fields.Datetime(help="Last processed log timestamp to avoid duplicates")
    last_pull_success = fields.Boolean()
    last_error_message = fields.Text()

    def action_pull_attendance(self):
        try:
            from zk import ZK
        except Exception:
            raise UserError("Thiếu thư viện 'zk'. Vui lòng cài đặt trên môi trường Odoo: pip install zk")

        Attendance = self.env['hr.attendance']
        Employee = self.env['hr.employee']

        for device in self:
            # Resolve device timezone
            tz_name = device.timezone or 'Asia/Ho_Chi_Minh'
            try:
                tz = pytz.timezone(tz_name)
            except Exception:
                try:
                    tz = pytz.timezone('Asia/Ho_Chi_Minh')
                    tz_name = 'Asia/Ho_Chi_Minh'
                except Exception:
                    tz = pytz.utc
                    tz_name = 'UTC'
            # When user specifies a pull range, treat it as a forced reload
            # to allow re-importing previously processed days and overwriting old data
            force_reload = bool(device.pull_start or device.pull_end)
            zk = ZK(
                device.ip_address,
                port=device.port or 4370,
                timeout=device.timeout or 10,
                password=device.comm_key or 0,
                force_udp=True,
                ommit_ping=True,
            )

            conn = False
            try:
                conn = zk.connect()
                conn.disable_device()

                users = conn.get_users() or []
                logs = conn.get_attendance() or []

                # Map user_id on device -> Employee in Odoo
                # Prefer Odoo's standard field 'barcode' first, then include F18 fields
                mapping_candidates = ['barcode', 'rfid', 'employee_number', 'pin', 'identification_id', 'badge_id']
                mapping_field = next((f for f in mapping_candidates if f in Employee._fields), None)
                employee_map = {}
                for u in users:
                    user_id = str(getattr(u, 'user_id', getattr(u, 'uid', '')))
                    if not user_id:
                        continue
                    emp = None
                    if mapping_field:
                        emp = Employee.search([(mapping_field, '=', user_id)], limit=1)
                    if emp:
                        employee_map[user_id] = emp.id

                # Helper: convert device timestamp to UTC-naive for storage/comparison
                def to_utc_naive(dt):
                    if not dt:
                        return None
                    if getattr(dt, 'tzinfo', None) is None:
                        # Device timestamp is naive in local device time; localize then convert to UTC
                        dt_local = tz.localize(dt)
                    else:
                        dt_local = dt.astimezone(tz)
                    return dt_local.astimezone(pytz.utc).replace(tzinfo=None)

                # Helper to check if a log is new against last processed UTC-naive timestamp
                def is_new(ts):
                    ts_utc = to_utc_naive(ts)
                    if not ts_utc:
                        return False
                    # In forced reload mode, ignore last_log_timestamp to reprocess
                    if force_reload:
                        return True
                    if not device.last_log_timestamp:
                        return True
                    last_ts = fields.Datetime.from_string(device.last_log_timestamp)
                    return ts_utc > last_ts

                # Sort logs by timestamp
                logs_sorted = sorted(logs, key=lambda l: l.timestamp)

                # Optional: filter by user-selected range (interpreted in device local time)
                def within_range(ts):
                    if not device.pull_start and not device.pull_end:
                        return True
                    # User inputs are stored as UTC-naive; convert to device local tz
                    start_local = None
                    end_local = None
                    if device.pull_start:
                        start_local = pytz.utc.localize(device.pull_start).astimezone(tz)
                    if device.pull_end:
                        end_local = pytz.utc.localize(device.pull_end).astimezone(tz)
                    # Normalize ts to device local aware
                    if getattr(ts, 'tzinfo', None) is None:
                        ts_local = tz.localize(ts)
                    else:
                        ts_local = ts.astimezone(tz)
                    if start_local and ts_local < start_local:
                        return False
                    if end_local and ts_local > end_local:
                        return False
                    return True

                # Process logs individually to handle missing check-in/check-out properly
                def to_local_aware(dt):
                    if getattr(dt, 'tzinfo', None) is None:
                        return tz.localize(dt)
                    return dt.astimezone(tz)

                # Auto-detect punch type based on time if not available
                def auto_detect_punch_type(ts_local):
                    """Auto-detect: before 12:00 = check-in, after 12:00 = check-out"""
                    return 'check_in' if ts_local.hour < 12 else 'check_out'

                # Group logs per employee per day to track all punches
                groups = {}  # (emp_id, local_date) -> [{'ts_local': ts, 'type': 'check_in'/'check_out'}, ...]
                last_processed_utc = None

                for att in logs_sorted:
                    ts = att.timestamp
                    if not within_range(ts):
                        continue
                    if not is_new(ts):
                        continue
                    user_id = str(getattr(att, 'user_id', ''))
                    emp_id = employee_map.get(user_id)
                    if not emp_id:
                        # Skip if we cannot map this device user to an employee
                        continue

                    ts_local = to_local_aware(ts)
                    day_key = ts_local.date()
                    key = (emp_id, day_key)
                    
                    # Auto-detect punch type (can be enhanced if device provides punch_type info)
                    punch_type = auto_detect_punch_type(ts_local)
                    
                    if key not in groups:
                        groups[key] = []
                    groups[key].append({'ts_local': ts_local, 'type': punch_type})
                    
                    # Track last processed
                    ts_utc_naive = to_utc_naive(ts)
                    if ts_utc_naive and (not last_processed_utc or ts_utc_naive > last_processed_utc):
                        last_processed_utc = ts_utc_naive

                # Process each employee's daily punches
                for (emp_id, day_local), punches in groups.items():
                    # Sort punches by time
                    punches.sort(key=lambda p: p['ts_local'])
                    
                    # Determine check-in and check-out based on punch logic
                    check_in_punch = None
                    check_out_punch = None

                    first_punch = punches[0] if punches else None
                    last_punch = punches[-1] if punches else None

                    if not first_punch:
                        # No punches at all, should not happen if groups is not empty
                        pass
                    elif len(punches) == 1:
                        # Only one punch. Determine if it's check-in or check-out based on its type.
                        if first_punch['type'] == 'check_in':
                            check_in_punch = first_punch
                            check_out_punch = None  # Explicitly missing check-out
                        else:  # 'check_out'
                            check_in_punch = None  # Explicitly missing check-in
                            check_out_punch = first_punch
                    else:
                        # Multiple punches. First is check-in, last is check-out.
                        check_in_punch = first_punch
                        check_out_punch = last_punch
                    
                    # Convert to UTC-naive for storage
                    check_in_utc = check_in_punch['ts_local'].astimezone(pytz.utc).replace(tzinfo=None) if check_in_punch else None
                    check_out_utc = check_out_punch['ts_local'].astimezone(pytz.utc).replace(tzinfo=None) if check_out_punch else None
                    
                    # Compute day window in local tz, then convert to UTC-naive for search
                    day_start_local = tz.localize(datetime(day_local.year, day_local.month, day_local.day, 0, 0, 0))
                    day_end_local = day_start_local + timedelta(days=1)
                    start_utc = day_start_local.astimezone(pytz.utc).replace(tzinfo=None)
                    end_utc = day_end_local.astimezone(pytz.utc).replace(tzinfo=None)
                    
                    # Overwrite-by-day: if forced reload, delete all prior device-imported
                    # attendances for this employee and local day, then write fresh data
                    if force_reload:
                        # Fetch all prior device-imported attendances for the employee/day
                        old_day_records = Attendance.search([
                            ('employee_id', '=', emp_id),
                            ('import_source', '=', 'f18_machine'),
                            '|',
                            '&', ('check_in', '>=', fields.Datetime.to_string(start_utc)),
                                 ('check_in', '<', fields.Datetime.to_string(end_utc)),
                            '&', ('check_out', '>=', fields.Datetime.to_string(start_utc)),
                                 ('check_out', '<', fields.Datetime.to_string(end_utc)),
                        ])

                        # Choose a target record to overwrite:
                        # Prefer a record that cannot be deleted (has leave_deduction) to keep references intact
                        non_deletable = old_day_records.filtered(lambda r: bool(getattr(r, 'leave_deduction_id', False)))
                        existing = non_deletable[0] if non_deletable else (old_day_records[0] if old_day_records else False)

                        # Safely delete other records that have no external references
                        unlinkable = old_day_records.filtered(lambda r: not getattr(r, 'leave_deduction_id', False))
                        if existing:
                            unlinkable = unlinkable.filtered(lambda r: r.id != existing.id)
                        if unlinkable:
                            # Unlink only those without leave_deduction to avoid FK violations
                            unlinkable.unlink()
                    else:
                        # Find any existing record in that local day window
                        existing = Attendance.search([
                            ('employee_id', '=', emp_id),
                            '|',
                            '&', ('check_in', '>=', fields.Datetime.to_string(start_utc)),
                                 ('check_in', '<', fields.Datetime.to_string(end_utc)),
                            '&', ('check_out', '>=', fields.Datetime.to_string(start_utc)),
                                 ('check_out', '<', fields.Datetime.to_string(end_utc)),
                        ], limit=1)

                    # KHÔNG tự đóng bản ghi mở: giữ nguyên Missing Out/ Missing In
                    # Tránh làm sai trạng thái Attendance; việc bỏ qua ràng buộc sẽ xử lý ở model hr.attendance
                    
                    # Prepare attendance data
                    attendance_data = {
                        'import_source': 'f18_machine',
                    }
                    if check_in_utc:
                        attendance_data['check_in'] = fields.Datetime.to_string(check_in_utc)
                    if check_out_utc:
                        attendance_data['check_out'] = fields.Datetime.to_string(check_out_utc)
                    
                    try:
                        if existing:
                            existing.write(attendance_data)
                        else:
                            attendance_data['employee_id'] = emp_id
                            Attendance.create(attendance_data)
                    except Exception as err:
                        # Ghi lại lỗi nhưng không tự đóng bản ghi trước đó để tránh sai trạng thái
                        device.last_pull_success = False
                        device.last_error_message = str(err)
                        # Bỏ qua ngày này, tiếp tục các bản ghi khác
                        continue

                # Update device timestamps
                if last_processed_utc:
                    device.last_log_timestamp = fields.Datetime.to_string(last_processed_utc)
                device.last_pull_at = fields.Datetime.now()
                device.last_pull_success = True
                # Informative message about mapping field
                if not mapping_field:
                    device.last_error_message = "Không tìm thấy trường map nhân viên (thử: barcode/pin/identification_id/badge_id). Vui lòng cấu hình hoặc thêm trường phù hợp."
                else:
                    if device.pull_start or device.pull_end:
                        device.last_error_message = (
                            f"Đã map theo trường: {mapping_field}. Khoảng thời gian áp dụng: "
                            f"{fields.Datetime.to_string(device.pull_start) if device.pull_start else '-'} đến "
                            f"{fields.Datetime.to_string(device.pull_end) if device.pull_end else '-'} (so sánh theo múi giờ {tz_name})."
                        )
                    else:
                        device.last_error_message = f"Đã map theo trường: {mapping_field}."

            except Exception as e:
                # Record error on device but do not raise to allow cron/UI to continue
                device.last_pull_success = False
                device.last_error_message = str(e)
            finally:
                if conn:
                    try:
                        conn.enable_device()
                        conn.disconnect()
                    except Exception:
                        # Ignore disconnect errors
                        pass