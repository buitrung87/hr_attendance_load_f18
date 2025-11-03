# -*- coding: utf-8 -*-

import socket
import struct
import logging
import base64
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AttendanceImport(models.Model):
    _name = 'attendance.import'
    _description = 'Attendance Import from F18 Machine'
    _order = 'import_date desc'
    _rec_name = 'import_date'

    import_date = fields.Datetime(
        string='Import Date',
        default=fields.Datetime.now,
        required=True
    )
    machine_ip = fields.Char(
        string='Machine IP',
        required=True,
        help='IP address of the F18 attendance machine'
    )
    machine_port = fields.Integer(
        string='Machine Port',
        default=4370,
        required=True
    )
    import_type = fields.Selection([
        ('auto', 'Automatic Import'),
        ('manual', 'Manual Import'),
        ('csv', 'CSV Import')
    ], string='Import Type', default='auto', required=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('connecting', 'Connecting'),
        ('importing', 'Importing'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('error', 'Error')
    ], string='State', default='draft', tracking=True)
    
    total_records = fields.Integer(string='Total Records', readonly=True)
    processed_records = fields.Integer(string='Processed Records', readonly=True)
    failed_records = fields.Integer(string='Failed Records', readonly=True)
    skipped_records = fields.Integer(string='Skipped Records', readonly=True)
    
    import_log = fields.Text(string='Import Log', readonly=True)
    error_message = fields.Text(string='Error Message', readonly=True)
    
    attendance_line_ids = fields.One2many(
        'attendance.import.line',
        'import_id',
        string='Attendance Lines'
    )
    
    csv_file = fields.Binary(string='CSV File')
    csv_filename = fields.Char(string='CSV Filename')
    auto_import = fields.Boolean(
        string='Auto Import',
        default=False,
        help='Indicates if this import was triggered automatically'
    )

    def action_connect_machine(self):
        """Connect to F18 machine and test connection"""
        self.ensure_one()
        try:
            self.state = 'connecting'
            self._log_message(_('Connecting to machine at %s:%s') % (self.machine_ip, self.machine_port))
            
            # Test connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            result = sock.connect_ex((self.machine_ip, self.machine_port))
            sock.close()
            
            if result == 0:
                self._log_message(_('Connection successful'))
                return True
            else:
                raise UserError(_('Cannot connect to machine at %s:%s') % (self.machine_ip, self.machine_port))
                
        except Exception as e:
            self.state = 'error'
            self.error_message = str(e)
            self._log_message(_('Connection failed: %s') % str(e))
            raise UserError(_('Connection failed: %s') % str(e))

    def action_import_attendance(self):
        """Import attendance data from F18 machine"""
        self.ensure_one()
        
        if self.import_type == 'csv':
            return self._import_from_csv()
        else:
            return self._import_from_machine()

    def _import_from_machine(self):
        """Import attendance data directly from F18 machine via TCP/IP"""
        try:
            self.state = 'importing'
            self._log_message(_('Starting attendance import from machine'))
            
            # Connect to machine
            if not self.action_connect_machine():
                return False
            
            # Get attendance records from machine
            attendance_data = self._fetch_attendance_from_machine()
            
            if not attendance_data:
                self._log_message(_('No attendance data found on machine'))
                self.state = 'done'
                return True
            
            # Process the data
            self._process_attendance_data(attendance_data)
            
            self.state = 'done'
            self._log_message(_('Import completed successfully'))
            return True
            
        except Exception as e:
            self.state = 'error'
            self.error_message = str(e)
            self._log_message(_('Import failed: %s') % str(e))
            return False

    def _import_from_csv(self):
        """Import attendance data from CSV file"""
        if not self.csv_file:
            raise UserError(_('Please upload a CSV file'))
        
        try:
            self.state = 'importing'
            self._log_message(_('Starting CSV import'))
            
            # Decode CSV file
            csv_data = base64.b64decode(self.csv_file).decode('utf-8')
            lines = csv_data.strip().split('\n')
            
            if not lines:
                raise UserError(_('CSV file is empty'))
            
            # Parse CSV data
            attendance_data = []
            headers = lines[0].split(',')
            
            for line_num, line in enumerate(lines[1:], 2):
                try:
                    values = line.split(',')
                    if len(values) >= 3:
                        attendance_data.append({
                            'user_id': values[0].strip(),
                            'check_time': values[1].strip(),
                            'check_type': values[2].strip() if len(values) > 2 else '1',
                            'line_number': line_num
                        })
                except Exception as e:
                    self._log_message(_('Error parsing line %s: %s') % (line_num, str(e)))
            
            # Process the data
            self._process_attendance_data(attendance_data)
            
            self.state = 'done'
            self._log_message(_('CSV import completed successfully'))
            return True
            
        except Exception as e:
            self.state = 'error'
            self.error_message = str(e)
            self._log_message(_('CSV import failed: %s') % str(e))
            return False

    def _fetch_attendance_from_machine(self):
        """Fetch attendance data from F18 machine using ZKTeco protocol"""
        # This is a simplified implementation
        # In a real scenario, you would use the ZKTeco SDK or implement the full protocol
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)
            sock.connect((self.machine_ip, self.machine_port))
            
            # Send command to get attendance logs
            # This is a simplified command structure
            command = struct.pack('<HHI', 1001, 0, 0)  # CMD_GET_ATTENDANCE
            sock.send(command)
            
            # Receive response
            response = sock.recv(1024)
            sock.close()
            
            # Parse response (simplified)
            # In real implementation, you would parse the actual ZKTeco protocol response
            attendance_data = []
            
            # Mock data for demonstration
            # Replace this with actual protocol parsing
            self._log_message(_('Received %d bytes from machine') % len(response))
            
            return attendance_data
            
        except Exception as e:
            _logger.error('Error fetching data from machine: %s', str(e))
            raise

    def _process_attendance_data(self, attendance_data):
        """Process attendance data and create attendance records"""
        self.state = 'processing'
        self.total_records = len(attendance_data)
        processed = 0
        failed = 0
        skipped = 0
        
        for data in attendance_data:
            try:
                # Find employee by RFID or barcode
                employee = self._find_employee(data.get('user_id'))
                
                if not employee:
                    self._log_message(_('Employee not found for user_id: %s') % data.get('user_id'))
                    skipped += 1
                    continue
                
                # Parse check time
                check_time = self._parse_datetime(data.get('check_time'))
                if not check_time:
                    self._log_message(_('Invalid check time: %s') % data.get('check_time'))
                    failed += 1
                    continue
                
                # Create attendance import line
                line_vals = {
                    'import_id': self.id,
                    'employee_id': employee.id,
                    'check_time': check_time,
                    'check_type': data.get('check_type', '1'),
                    'raw_data': str(data),
                    'state': 'draft'
                }
                
                line = self.env['attendance.import.line'].create(line_vals)
                
                # Process the line to create actual attendance
                if line.action_process():
                    processed += 1
                else:
                    failed += 1
                    
            except Exception as e:
                failed += 1
                self._log_message(_('Error processing record: %s') % str(e))
        
        self.processed_records = processed
        self.failed_records = failed
        self.skipped_records = skipped
        
        self._log_message(_('Processing completed: %d processed, %d failed, %d skipped') % 
                         (processed, failed, skipped))

    def _find_employee(self, user_id):
        """Find employee by RFID or barcode"""
        if not user_id:
            return None
        
        # Try to find by RFID first
        employee = self.env['hr.employee'].sudo().search([
            ('rfid', '=', user_id)
        ], limit=1)
        
        if not employee:
            # Try to find by barcode
            employee = self.env['hr.employee'].sudo().search([
                ('barcode', '=', user_id)
            ], limit=1)
        
        if not employee:
            # Try to find by employee number
            employee = self.env['hr.employee'].sudo().search([
                ('employee_number', '=', user_id)
            ], limit=1)

        if not employee:
            # Try to find by F18 user id if field exists
            Employee = self.env['hr.employee']
            if 'f18_user_id' in Employee._fields:
                employee = Employee.sudo().search([
                    ('f18_user_id', '=', user_id)
                ], limit=1)
        
        return employee

    def _parse_datetime(self, datetime_str):
        """Parse datetime string from various formats"""
        if not datetime_str:
            return None
        
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%d/%m/%Y %H:%M:%S',
            '%m/%d/%Y %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%d/%m/%Y %H:%M',
            '%m/%d/%Y %H:%M'
        ]
        
        parsed = None
        for fmt in formats:
            try:
                parsed = datetime.strptime(datetime_str, fmt)
                break
            except ValueError:
                continue

        if not parsed:
            return None

        # Diễn giải thời gian máy chấm công theo múi giờ UTC+7 (Asia/Ho_Chi_Minh),
        # sau đó chuyển sang UTC-naive để lưu vào Odoo.
        try:
            local_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        except Exception:
            local_tz = pytz.utc
        localized = local_tz.localize(parsed)
        return localized.astimezone(pytz.utc).replace(tzinfo=None)

    def _log_message(self, message):
        """Add message to import log"""
        timestamp = fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = '[%s] %s\n' % (timestamp, message)
        
        if self.import_log:
            self.import_log += log_entry
        else:
            self.import_log = log_entry

    @api.model
    def cron_auto_import(self):
        """Cron job to automatically import attendance"""
        config = self.env['attendance.enhanced.config'].get_config()

        # Respect auto import setting from business configuration
        if not config.get('auto_import_enabled', False):
            return

        # Delegate to Attendance Devices connector for pulling logs
        try:
            devices = self.env['attendance.device'].search([('active', '=', True), ('auto_pull', '=', True)])
            if devices:
                devices.action_pull_attendance()
                _logger.info('Automatic attendance pull via devices completed successfully')
            else:
                _logger.warning('No active auto-pull devices found for attendance import')
        except Exception as e:
            _logger.error('Automatic attendance pull via devices failed: %s', str(e))

    def action_process_import(self):
        """Process the import - start importing attendance data"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft imports can be processed'))
        
        return self.action_import_attendance()

    def action_retry_failed(self):
        """Retry processing failed import lines"""
        self.ensure_one()
        if self.state != 'error':
            raise UserError(_('Only failed imports can be retried'))
        
        # Reset failed lines to draft
        failed_lines = self.attendance_line_ids.filtered(lambda l: l.state == 'error')
        failed_lines.write({'state': 'draft', 'error_message': False})
        
        # Reset import state and counters
        self.write({
            'state': 'draft',
            'error_message': False,
            'failed_records': 0,
        })
        
        # Reprocess the import
        return self.action_import_attendance()

    def action_cancel(self):
        """Cancel the import"""
        self.ensure_one()
        if self.state in ['done']:
            raise UserError(_('Cannot cancel completed imports'))
        
        # Delete all draft lines
        self.attendance_line_ids.filtered(lambda l: l.state == 'draft').unlink()
        
        # Set state to cancelled (we need to add this state)
        self.state = 'draft'
        self._log_message(_('Import cancelled by user'))
        
        return True


class AttendanceImportLine(models.Model):
    _name = 'attendance.import.line'
    _description = 'Attendance Import Line'
    _order = 'check_time desc'

    import_id = fields.Many2one(
        'attendance.import',
        string='Import',
        required=True,
        ondelete='cascade'
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True
    )
    check_time = fields.Datetime(
        string='Check Time',
        required=True
    )
    check_type = fields.Selection([
        ('1', 'Check In'),
        ('0', 'Check Out'),
        ('2', 'Break Out'),
        ('3', 'Break In')
    ], string='Check Type', default='1')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('error', 'Error'),
        ('skipped', 'Skipped')
    ], string='State', default='draft')
    
    attendance_id = fields.Many2one(
        'hr.attendance',
        string='Created Attendance',
        readonly=True
    )
    raw_data = fields.Text(string='Raw Data')
    error_message = fields.Text(string='Error Message')

    def action_process(self):
        """Process the import line and create attendance record"""
        self.ensure_one()
        
        try:
            # Check if attendance already exists
            existing = self.env['hr.attendance'].with_context(attendance_importing=True).search([
                ('employee_id', '=', self.employee_id.id),
                ('check_in', '=', self.check_time)
            ], limit=1)
            
            if existing:
                self.state = 'skipped'
                self.error_message = _('Attendance already exists')
                return False
            
            # Determine if this is check-in or check-out
            if self.check_type in ['1', '3']:  # Check In or Break In
                # Create new attendance record
                attendance_vals = {
                    'employee_id': self.employee_id.id,
                    'check_in': self.check_time,
                }
                attendance = self.env['hr.attendance'].create(attendance_vals)
                self.attendance_id = attendance.id
                
            elif self.check_type in ['0', '2']:  # Check Out or Break Out
                # Find the last open attendance
                last_attendance = self.env['hr.attendance'].with_context(attendance_importing=True).search([
                    ('employee_id', '=', self.employee_id.id),
                    ('check_out', '=', False)
                ], order='check_in desc', limit=1)
                
                if last_attendance:
                    last_attendance.check_out = self.check_time
                    self.attendance_id = last_attendance.id
                else:
                    # Only check-out exists: mark as missing check-in
                    # We still need a check_in value (required) – use a safe placeholder
                    # Choose 8 hours prior to check_out to avoid overlaps, but flag missing_check_in
                    check_in_time = self.check_time - timedelta(hours=8)
                    attendance_vals = {
                        'employee_id': self.employee_id.id,
                        'check_in': check_in_time,
                        'check_out': self.check_time,
                        'missing_check_in': True,
                        'notes': _('Imported check-out only; flagged as missing check-in')
                    }
                    attendance = self.env['hr.attendance'].create(attendance_vals)
                    self.attendance_id = attendance.id
            
            self.state = 'processed'
            return True
            
        except Exception as e:
            self.state = 'error'
            self.error_message = str(e)
            return False

    def action_reprocess(self):
        """Reprocess failed import line"""
        self.ensure_one()
        self.state = 'draft'
        self.error_message = False
        return self.action_process()

    def action_retry_process(self):
        """Retry processing this line (alias for action_reprocess)"""
        return self.action_reprocess()