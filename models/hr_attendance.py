# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta
from odoo import models, fields, api, _
import pytz
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    # Enhanced status tracking
    attendance_status = fields.Selection([
        ('normal', 'Normal'),
        ('late_in', 'Late Check-In'),
        ('early_out', 'Early Check-Out'),
        ('missing_out', 'Missing Check-Out'),
        ('missing_in', 'Missing Check-In'),
        ('late_missing_out', 'Late Check-In + Missing Check-Out'),
        ('early_missing_in', 'Early Check-Out + Missing Check-In'),
        ('overtime', 'Overtime'),
        ('both_issues', 'Late In & Early Out')
    ], string='Attendance Status',
       compute='_compute_attendance_status',
       store=True,
       help='Status based on working schedule and attendance times')
    
    # Time calculations
    late_minutes = fields.Float(
        string='Late Minutes',
        compute='_compute_time_deviations',
        store=True,
        digits=(16, 2),
        help='Minutes late for check-in'
    )
    early_minutes = fields.Float(
        string='Early Minutes',
        compute='_compute_time_deviations',
        store=True,
        digits=(16, 2),
        help='Minutes early for check-out'
    )
    
    # Schedule information
    scheduled_check_in = fields.Datetime(
        string='Scheduled Check-In',
        compute='_compute_schedule_times',
        store=True,
        help='Expected check-in time based on work schedule'
    )
    scheduled_check_out = fields.Datetime(
        string='Scheduled Check-Out',
        compute='_compute_schedule_times',
        store=True,
        help='Expected check-out time based on work schedule'
    )
    scheduled_hours = fields.Float(
        string='Scheduled Hours',
        compute='_compute_schedule_times',
        store=True,
        digits=(16, 2),
        help='Scheduled working hours for the day'
    )
    
    # Overtime integration
    overtime_id = fields.Many2one(
        'hr.overtime',
        string='Related Overtime',
        help='Related overtime record if applicable'
    )
    overtime_hours = fields.Float(
        string='Overtime Hours',
        related='overtime_id.overtime_hours',
        store=True,
        digits=(16, 2),
        help='Overtime hours for this attendance'
    )
    
    # Leave deduction integration
    leave_deduction_id = fields.Many2one(
        'leave.deduction',
        string='Leave Deduction',
        help='Related leave deduction record'
    )
    deduction_days = fields.Float(
        string='Deduction Days',
        related='leave_deduction_id.deduction_days',
        store=True,
        digits=(16, 3),
        help='Leave days deducted for this attendance'
    )
    
    # Import information
    import_source = fields.Selection([
        ('manual', 'Manual Entry'),
        ('f18_machine', 'F18 Machine'),
        ('csv_import', 'CSV Import'),
        ('api', 'API Import')
    ], string='Import Source',
       default='manual',
       help='Source of this attendance record')
    
    import_id = fields.Many2one(
        'attendance.import',
        string='Import Record',
        help='Related import record'
    )
    
    # Additional fields
    notes = fields.Text(
        string='Notes',
        help='Additional notes about this attendance'
    )

    # Missing check-in/out handling and approval
    missing_check_in = fields.Boolean(
        string='Missing Check-In',
        help='Flag when only check-out exists (employee forgot to check in)'
    )
    missing_request_state = fields.Selection([
        ('none', 'No Request'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], string='Missing Approval State', default='none', tracking=True)
    missing_approval_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    missing_approval_date = fields.Datetime(string='Approval Date', readonly=True)
    missing_request_note = fields.Text(string='Missing Reason/Note')
    
    # Color coding for list view
    color = fields.Integer(
        string='Color',
        compute='_compute_color',
        help='Color for kanban/list view based on status'
    )

    # Display-only fields for overview
    attendance_date = fields.Date(
        string='Date',
        compute='_compute_display_fields',
        help='Attendance date in user timezone'
    )
    check_in_time = fields.Char(
        string='Check In',
        compute='_compute_display_fields',
        help='Check-in time (HH:MM:SS) in user timezone'
    )
    check_out_time = fields.Char(
        string='Check Out',
        compute='_compute_display_fields',
        help='Check-out time (HH:MM:SS) in user timezone'
    )

    # Daily overtime per attendance based on local business rules
    daily_ot_seconds = fields.Integer(
        string='OT Seconds',
        compute='_compute_daily_ot',
        store=True,
        help='Daily overtime in seconds based on weekday/weekend rules'
    )
    daily_ot_str = fields.Char(
        string='OT',
        compute='_compute_daily_ot',
        store=True,
        help='Daily overtime formatted as HH:MM:SS'
    )

    @api.depends('check_in', 'check_out')
    def _compute_display_fields(self):
        for att in self:
            att.attendance_date = False
            att.check_in_time = False
            att.check_out_time = False

            # Resolve display timezone: prefer employee.tz, then user.tz, else Asia/Ho_Chi_Minh
            tz_name = (att.employee_id and att.employee_id.tz) or self.env.user.tz or 'Asia/Ho_Chi_Minh'
            try:
                tz = pytz.timezone(tz_name)
            except Exception:
                tz = pytz.timezone('UTC')

            # Convert stored UTC-naive datetimes to local timezone for display
            if att.check_in:
                in_utc = pytz.utc.localize(fields.Datetime.from_string(att.check_in))
                in_local = in_utc.astimezone(tz)
                att.attendance_date = in_local.date()
                att.check_in_time = in_local.strftime('%H:%M:%S')
            elif att.check_out:
                out_utc_tmp = pytz.utc.localize(fields.Datetime.from_string(att.check_out))
                out_local_tmp = out_utc_tmp.astimezone(tz)
                att.attendance_date = out_local_tmp.date()

            if att.check_out:
                out_utc = pytz.utc.localize(fields.Datetime.from_string(att.check_out))
                out_local = out_utc.astimezone(tz)
                att.check_out_time = out_local.strftime('%H:%M:%S')

    @api.depends('check_in', 'check_out', 'employee_id')
    def _compute_daily_ot(self):
        for att in self:
            att.daily_ot_seconds = 0
            att.daily_ot_str = '00:00:00'
            if not att.check_in or not att.check_out:
                continue
            # Resolve business timezone (prefer employee.tz, fallback to user.tz, else Asia/Ho_Chi_Minh)
            tz_name = (att.employee_id and att.employee_id.tz) or self.env.user.tz or 'Asia/Ho_Chi_Minh'
            try:
                tz = pytz.timezone(tz_name)
            except Exception:
                tz = pytz.timezone('UTC')
            # Convert naive UTC to aware UTC then to local tz
            in_utc = pytz.utc.localize(fields.Datetime.from_string(att.check_in))
            out_utc = pytz.utc.localize(fields.Datetime.from_string(att.check_out))
            in_local = in_utc.astimezone(tz)
            out_local = out_utc.astimezone(tz)
            # Determine weekday and compute OT
            weekday = in_local.weekday()  # 0=Mon .. 6=Sun
            ot_seconds = 0
            if weekday <= 4:
                # Weekdays: OT starts at 18:00 if checkout is after
                overtime_start_local = tz.localize(datetime(in_local.year, in_local.month, in_local.day, 18, 0, 0))
                if out_local > overtime_start_local:
                    delta = (out_local - overtime_start_local).total_seconds()
                    if delta >= 1800:  # only count if >= 30 minutes
                        ot_seconds = int(delta)
            else:
                # Weekends: entire working time capped at 4 hours
                delta = (out_local - in_local).total_seconds()
                if delta > 0:
                    ot_seconds = int(min(delta, 14400))
            att.daily_ot_seconds = int(ot_seconds)
            # Format HH:MM:SS
            h = ot_seconds // 3600
            m = (ot_seconds % 3600) // 60
            s = ot_seconds % 60
            att.daily_ot_str = f"{h:02d}:{m:02d}:{s:02d}"

    @api.depends('check_in', 'check_out', 'employee_id')
    def _compute_schedule_times(self):
        """Compute scheduled times based on employee's work schedule"""
        for attendance in self:
            if not attendance.check_in or not attendance.employee_id:
                attendance.scheduled_check_in = False
                attendance.scheduled_check_out = False
                attendance.scheduled_hours = 0.0
                continue
            
            # Get employee's resource calendar
            calendar = attendance.employee_id.resource_calendar_id
            if not calendar:
                # Use company default
                calendar = attendance.employee_id.company_id.resource_calendar_id
            
            if not calendar:
                attendance.scheduled_check_in = False
                attendance.scheduled_check_out = False
                attendance.scheduled_hours = 0.0
                continue
            
            # Get work intervals for the day
            check_in_date = attendance.check_in.date()
            day_start = datetime.combine(check_in_date, datetime.min.time())
            day_end = day_start + timedelta(days=1)
            
            # Convert local day bounds to TZ-aware datetimes for calendar computation
            # Ưu tiên timezone của nhân viên hoặc người dùng; mặc định UTC+7 (Asia/Ho_Chi_Minh)
            tz_name = attendance.employee_id.tz or self.env.user.tz or 'Asia/Ho_Chi_Minh'
            try:
                tz = pytz.timezone(tz_name)
            except Exception:
                # Fallback về UTC+7 nếu tên timezone không hợp lệ, sau cùng mới về UTC
                try:
                    tz = pytz.timezone('Asia/Ho_Chi_Minh')
                    tz_name = 'Asia/Ho_Chi_Minh'
                except Exception:
                    tz = pytz.utc
                    tz_name = 'UTC'
            day_start_local = tz.localize(day_start)
            day_end_local = tz.localize(day_end)
            # Keep tzinfo; resource calendar requires tz-aware datetimes
            day_start_aware = day_start_local
            day_end_aware = day_end_local

            # Ensure employee has a resource; otherwise schedule is undefined
            if not attendance.employee_id.resource_id:
                attendance.scheduled_check_in = False
                attendance.scheduled_check_out = False
                attendance.scheduled_hours = 0.0
                continue

            work_intervals = calendar._work_intervals_batch(
                day_start_aware, day_end_aware, resources=attendance.employee_id.resource_id, tz=tz
            )[attendance.employee_id.resource_id.id]
            
            if work_intervals:
                # Get first and last work intervals
                first_interval = min(work_intervals, key=lambda x: x[0])
                last_interval = max(work_intervals, key=lambda x: x[1])
                
                # Store as UTC naive datetimes as required by Odoo datetime fields
                attendance.scheduled_check_in = first_interval[0].astimezone(pytz.utc).replace(tzinfo=None)
                attendance.scheduled_check_out = last_interval[1].astimezone(pytz.utc).replace(tzinfo=None)
                
                # Calculate total scheduled hours
                total_minutes = sum(
                    (interval[1] - interval[0]).total_seconds() / 60
                    for interval in work_intervals
                )
                attendance.scheduled_hours = total_minutes / 60.0
            else:
                attendance.scheduled_check_in = False
                attendance.scheduled_check_out = False
                attendance.scheduled_hours = 0.0

    @api.depends('check_in', 'check_out', 'scheduled_check_in', 'scheduled_check_out')
    def _compute_time_deviations(self):
        """Compute late and early minutes"""
        for attendance in self:
            attendance.late_minutes = 0.0
            attendance.early_minutes = 0.0
            
            # Calculate late minutes (requires scheduled_check_in and actual check_in)
            if attendance.scheduled_check_in and attendance.check_in:
                if attendance.check_in > attendance.scheduled_check_in:
                    late_delta = attendance.check_in - attendance.scheduled_check_in
                    attendance.late_minutes = late_delta.total_seconds() / 60.0

            # Calculate early minutes (requires scheduled_check_out and actual check_out)
            if attendance.scheduled_check_out and attendance.check_out:
                if attendance.check_out < attendance.scheduled_check_out:
                    early_delta = attendance.scheduled_check_out - attendance.check_out
                    attendance.early_minutes = early_delta.total_seconds() / 60.0

    @api.depends('late_minutes', 'early_minutes', 'check_out', 'check_in', 'daily_ot_seconds', 'overtime_id', 'worked_hours', 'missing_check_in')
    def _compute_attendance_status(self):
        """Compute attendance status strictly following OT rules.

        - Weekdays: Overtime only when OT >= 0.5 hours (after 18:00).
        - Weekdays also count OT when worked_hours > 9.5 hours.
        - Weekends/Holidays: Any worked time counts as overtime.
        - Missing in/out take precedence.
        - Late/Early evaluated only when a schedule exists, and only when not overtime.
        """
        config = self.env['attendance.enhanced.config'].get_config()
        grace_period = config.get('grace_period_minutes', 15.0)

        for attendance in self:
            # Missing check-in/out handling with combined display rules
            if not attendance.check_in and not attendance.check_out:
                # No attendance data at all
                attendance.attendance_status = 'missing_in'
                continue
            elif not attendance.check_in and attendance.check_out:
                # Only check-out exists (missing check-in)
                # If also early check-out, display both
                is_early = attendance.early_minutes > 0.0
                attendance.attendance_status = 'early_missing_in' if is_early else 'missing_in'
                continue
            elif attendance.check_in and not attendance.check_out:
                # Only check-in exists (missing check-out)
                # If also late check-in (beyond grace), display both
                is_late = False
                if attendance.scheduled_check_in:
                    is_late = attendance.late_minutes > grace_period
                attendance.attendance_status = 'late_missing_out' if is_late else 'missing_out'
                continue

            # Determine if weekend/holiday via overtime record when available
            ot_type = attendance.overtime_id and attendance.overtime_id.overtime_type or False
            is_weekend_or_holiday = ot_type in ('weekend', 'holiday')

            # Fallback weekend detection when no overtime record
            if not ot_type and attendance.check_in:
                weekday_num = attendance.check_in.weekday()
                is_weekend_or_holiday = weekday_num in (5, 6)

            # Compute overtime status per rules (OT takes precedence over late/early)
            has_ot_record = bool(attendance.overtime_id)
            ot_hours = attendance.overtime_id.overtime_hours if has_ot_record else 0.0
            ot_secs = attendance.daily_ot_seconds or 0
            worked_hours = attendance.worked_hours or 0.0

            is_overtime = False
            if is_weekend_or_holiday:
                # Any worked time counts as overtime on weekends/holidays
                is_overtime = (worked_hours > 0) or (ot_hours > 0) or (ot_secs > 0)
            else:
                # Weekday: require >= 0.5h after 18:00 OR worked_hours > 9.5h
                is_overtime = (ot_hours >= 0.5) or (ot_secs >= 1800) or (worked_hours > 9.5)

            if is_overtime:
                attendance.attendance_status = 'overtime'
                continue

            # Not overtime: evaluate schedule-dependent deviations when schedule exists
            schedule_exists = bool(attendance.scheduled_check_in and attendance.scheduled_check_out)
            if schedule_exists:
                is_late = attendance.late_minutes > grace_period
                # Grace applies ONLY to check-in; early-out is strict
                is_early = attendance.early_minutes > 0.0
                if is_late and is_early:
                    attendance.attendance_status = 'both_issues'
                elif is_late:
                    attendance.attendance_status = 'late_in'
                elif is_early:
                    attendance.attendance_status = 'early_out'
                else:
                    attendance.attendance_status = 'normal'
            else:
                attendance.attendance_status = 'normal'

    @api.depends('attendance_status')
    def _compute_color(self):
        """Compute color for list/kanban view"""
        color_map = {
            'normal': 0,      # No color (default)
            'late_in': 3,     # Yellow
            'early_out': 1,   # Red
            'missing_out': 9, # Pink
            'missing_in': 9,  # Pink
            'late_missing_out': 2, # Orange
            'early_missing_in': 2, # Orange
            'overtime': 4,    # Blue
            'both_issues': 2, # Orange
        }
        
        for attendance in self:
            attendance.color = color_map.get(attendance.attendance_status, 0)

    @api.model_create_multi
    def create(self, vals_list):
        # Tạo bình thường, sau đó xử lý OT và deduction; ràng buộc hợp lệ sẽ được override bên dưới
        attendances = super().create(vals_list)
        for attendance in attendances:
            attendance._process_overtime()
            attendance._process_leave_deduction()
        return attendances

    # Bỏ qua ràng buộc "chưa check out" cho dữ liệu import từ F18
    # để có thể tạo bản ghi mới mà vẫn giữ trạng thái Missing In/Out.
    @api.constrains('employee_id', 'check_in', 'check_out')
    def _check_validity(self):
        # Chỉ áp dụng kiểm tra mặc định cho bản ghi KHÔNG phải từ F18
        non_f18 = self.filtered(lambda r: r.import_source != 'f18_machine')
        if non_f18:
            super(HrAttendance, non_f18)._check_validity()
        # Với F18: bỏ qua ràng buộc để không chặn tạo bản ghi khi ngày trước đó còn mở.
        return True

    def write(self, vals):
        """Override write to reprocess when relevant fields change"""
        result = super().write(vals)
        
        # If check_in or check_out changed, reprocess
        if 'check_in' in vals or 'check_out' in vals:
            for attendance in self:
                # Auto-set missing_check_in flag for consistency
                if not attendance.check_in and attendance.check_out:
                    if not attendance.missing_check_in:
                        super(HrAttendance, attendance).write({'missing_check_in': True})
                elif attendance.check_in and attendance.missing_check_in:
                    super(HrAttendance, attendance).write({'missing_check_in': False})
                attendance._process_overtime()
                attendance._process_leave_deduction()
        
        return result

    def _process_overtime(self):
        """Process overtime calculation for this attendance"""
        if not self.check_in:
            return

        # Recalculate/Update OT record for employee on local day of this attendance
        overtime_model = self.env['hr.overtime']
        overtime = overtime_model._calculate_employee_overtime(self.employee_id, self.check_in.date())
        if overtime:
            self.overtime_id = overtime.id

    def _process_leave_deduction(self):
        """Process leave deduction for this attendance"""
        if self.leave_deduction_id:
            return
        
        # Get configuration
        config = self.env['attendance.enhanced.config'].get_config()
        grace_period = config.get('grace_period_minutes', 15.0)
        
        # Skip deduction completely if missing check-in/out and approved
        if (self.missing_check_in or (not self.check_out)) and self.missing_request_state == 'approved':
            return

        # Handle missing_out with possible late_in deduction
        if self.attendance_status in ('missing_out', 'late_missing_out'):
            late_minutes = 0
            if self.late_minutes and self.scheduled_check_in:
                late_minutes = max(0, self.late_minutes - grace_period)
            if late_minutes > 0:
                deduction_vals = {
                    'employee_id': self.employee_id.id,
                    'date': (self.check_in or self.check_out).date(),
                    'attendance_id': self.id,
                    'late_minutes': late_minutes,
                    'early_minutes': 0.0,
                    'deduction_type': 'late_in',
                }
            else:
                # Dashboard-only record for pure missing_out
                deduction_vals = {
                    'employee_id': self.employee_id.id,
                    'date': (self.check_in or self.check_out).date(),
                    'attendance_id': self.id,
                    'deduction_type': 'missing_out',
                    'late_minutes': 0.0,
                    'early_minutes': 0.0,
                    'grace_period_minutes': grace_period,
                }
            deduction = self.env['leave.deduction'].create(deduction_vals)
            self.leave_deduction_id = deduction.id
            return

        # Handle missing_in with possible early_out deduction
        if self.attendance_status in ('missing_in', 'early_missing_in'):
            early_minutes = 0
            if self.early_minutes and self.scheduled_check_out and self.check_out:
                early_minutes = max(0, self.early_minutes)
            if early_minutes > 0:
                deduction_vals = {
                    'employee_id': self.employee_id.id,
                    'date': (self.check_in or self.check_out).date(),
                    'attendance_id': self.id,
                    'late_minutes': 0.0,
                    'early_minutes': early_minutes,
                    'deduction_type': 'early_out',
                }
            else:
                # Dashboard-only record for pure missing_in
                deduction_vals = {
                    'employee_id': self.employee_id.id,
                    'date': (self.check_in or self.check_out).date(),
                    'attendance_id': self.id,
                    'deduction_type': 'missing_in',
                    'late_minutes': 0.0,
                    'early_minutes': 0.0,
                    'grace_period_minutes': grace_period,
                }
            deduction = self.env['leave.deduction'].create(deduction_vals)
            self.leave_deduction_id = deduction.id
            return

        # Check if deduction is needed
        late_minutes = max(0, self.late_minutes - grace_period)
        # Grace does NOT apply to early-out; count all early minutes
        early_minutes = max(0, self.early_minutes)
        
        if late_minutes > 0 or early_minutes > 0:
            # Create deduction record
            deduction_vals = {
                'employee_id': self.employee_id.id,
                'date': self.check_in.date(),
                'attendance_id': self.id,
                'late_minutes': late_minutes,
                'early_minutes': early_minutes,
                'deduction_type': self._get_deduction_type(late_minutes, early_minutes)
            }
            
            deduction = self.env['leave.deduction'].create(deduction_vals)
            self.leave_deduction_id = deduction.id

    # Simple approval flow for missing check-in/out
    def action_request_missing_approval(self):
        for att in self:
            # Allow request when auto-detected missing check-in (no check_in but has check_out)
            if att.missing_check_in or (not att.check_in and att.check_out) or not att.check_out:
                att.missing_request_state = 'pending'
        return True

    def action_approve_missing(self):
        for att in self:
            if att.missing_request_state in ['pending']:
                att.write({
                    'missing_request_state': 'approved',
                    'missing_approval_by': self.env.user.id,
                    'missing_approval_date': fields.Datetime.now(),
                })
        return True

    def action_reject_missing(self):
        for att in self:
            if att.missing_request_state in ['pending']:
                att.missing_request_state = 'rejected'
        return True

    def _get_deduction_type(self, late_minutes, early_minutes):
        """Determine deduction type based on late and early minutes"""
        if late_minutes > 0 and early_minutes > 0:
            return 'both'
        elif late_minutes > 0:
            return 'late_in'
        else:
            return 'early_out'

    def action_view_overtime(self):
        """View related overtime record"""
        if not self.overtime_id:
            return
        
        return {
            'name': _('Overtime Record'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.overtime',
            'res_id': self.overtime_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_leave_deduction(self):
        """View related leave deduction record"""
        if not self.leave_deduction_id:
            return
        
        return {
            'name': _('Leave Deduction'),
            'type': 'ir.actions.act_window',
            'res_model': 'leave.deduction',
            'res_id': self.leave_deduction_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def get_attendance_summary(self, date_from=None, date_to=None, employee_ids=None):
        """Get attendance summary for dashboard/reports"""
        if not date_from:
            date_from = fields.Date.today().replace(day=1)  # Start of month
        if not date_to:
            date_to = fields.Date.today()
        
        domain = [
            ('check_in', '>=', date_from),
            ('check_in', '<=', date_to)
        ]
        
        if employee_ids:
            domain.append(('employee_id', 'in', employee_ids))
        
        attendances = self.search(domain)
        
        # Group by status
        status_counts = {}
        for status in ['normal', 'late_in', 'early_out', 'missing_out', 'overtime', 'both_issues']:
            status_counts[status] = len(attendances.filtered(lambda a: a.attendance_status == status))
        
        # Calculate totals
        total_attendances = len(attendances)
        total_worked_hours = sum(attendances.mapped('worked_hours'))
        total_overtime_hours = sum(attendances.mapped('overtime_hours'))
        
        return {
            'total_attendances': total_attendances,
            'total_worked_hours': total_worked_hours,
            'total_overtime_hours': total_overtime_hours,
            'status_counts': status_counts,
            'date_from': date_from,
            'date_to': date_to
        }