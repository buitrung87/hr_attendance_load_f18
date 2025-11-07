# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta, time
import pytz
from odoo import models, fields, api, _
import pytz
from datetime import datetime
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class HrOvertime(models.Model):
    _name = 'hr.overtime'
    _description = 'Employee Overtime Record'
    _order = 'date desc'
    _rec_name = 'display_name'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        index=True
    )
    date = fields.Date(
        string='Date',
        required=True,
        index=True
    )
    worked_hours = fields.Float(
        string='Worked Hours',
        digits=(16, 2),
        help='Total hours worked on this date'
    )
    standard_hours = fields.Float(
        string='Standard Hours',
        digits=(16, 2),
        help='Standard working hours for this date'
    )
    overtime_hours = fields.Float(
        string='Overtime Hours',
        digits=(16, 2),
        compute='_compute_overtime_hours',
        store=True,
        help='Total overtime hours'
    )
    ot_seconds = fields.Integer(
        string='OT Seconds',
        compute='_compute_ot_fields',
        store=True,
        help='Overtime duration in seconds per business rules'
    )
    ot_str = fields.Char(
        string='OT',
        compute='_compute_ot_fields',
        store=True,
        help='Overtime formatted as HH:MM:SS'
    )
    weekday_overtime = fields.Float(
        string='Weekday Overtime',
        digits=(16, 2),
        help='Overtime hours on weekdays (1.0x rate)'
    )
    weekend_overtime = fields.Float(
        string='Weekend Overtime',
        digits=(16, 2),
        help='Overtime hours on weekends (1.5x rate)'
    )
    holiday_overtime = fields.Float(
        string='Holiday Overtime',
        digits=(16, 2),
        help='Overtime hours on holidays (2.0x rate)'
    )
    overtime_type = fields.Selection([
        ('weekday', 'Weekday'),
        ('weekend', 'Weekend'),
        ('holiday', 'Holiday')
    ], string='Overtime Type', compute='_compute_overtime_type', store=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid')
    ], string='State', default='draft', tracking=True)
    
    approved_by = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True
    )
    approval_date = fields.Datetime(
        string='Approval Date',
        readonly=True
    )
    rejection_reason = fields.Text(string='Rejection Reason')
    
    attendance_ids = fields.One2many(
        'hr.attendance',
        'overtime_id',
        string='Related Attendances'
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        readonly=True
    )
    
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name'
    )
    
    notes = fields.Text(string='Notes')
    
    # Color coding for kanban view
    color = fields.Integer(
        string='Color',
        compute='_compute_color',
        help='Color for kanban view based on state'
    )
    
    # Computed fields for reporting
    overtime_amount = fields.Float(
        string='Overtime Amount',
        compute='_compute_overtime_amount',
        store=True,
        help='Calculated overtime payment amount'
    )
    
    @api.depends('employee_id', 'date')
    def _compute_display_name(self):
        for record in self:
            if record.employee_id and record.date:
                record.display_name = _('%s - %s') % (
                    record.employee_id.name,
                    record.date.strftime('%Y-%m-%d')
                )
            else:
                record.display_name = _('New Overtime Record')

    @api.depends('attendance_ids', 'date', 'employee_id')
    def _compute_ot_fields(self):
        for record in self:
            record.ot_seconds = 0
            record.ot_str = '00:00:00'
            if not record.employee_id or not record.date:
                continue

            # Resolve timezone
            tz_name = record.employee_id.tz or self.env.user.tz or 'Asia/Ho_Chi_Minh'
            try:
                tz = pytz.timezone(tz_name)
            except Exception:
                tz = pytz.utc

            weekday = record.date.weekday()  # 0=Mon .. 6=Sun
            ot_secs = 0

            if weekday <= 4:
                # Weekday: OT starts at 18:00 local; only count if checkout after 18:00 and >= 30 minutes
                overtime_start_local = tz.localize(datetime(record.date.year, record.date.month, record.date.day, 18, 0, 0))
                # Find latest checkout among attendances of the day
                latest_out_local = None
                for att in record.attendance_ids:
                    if att.check_out:
                        out_utc = pytz.utc.localize(fields.Datetime.from_string(att.check_out))
                        out_local = out_utc.astimezone(tz)
                        # Ensure same local date
                        if out_local.date() == record.date:
                            if latest_out_local is None or out_local > latest_out_local:
                                latest_out_local = out_local
                if latest_out_local and latest_out_local > overtime_start_local:
                    delta = (latest_out_local - overtime_start_local).total_seconds()
                    if delta >= 1800:
                        ot_secs = int(delta)
            else:
                # Weekend: sum all worked time of the day and cap at 4 hours
                total = 0
                for att in record.attendance_ids:
                    if att.check_in and att.check_out:
                        # Use UTC naive difference; timezone doesn't affect duration
                        # Ensure attendance belongs to the same local date
                        in_utc = pytz.utc.localize(fields.Datetime.from_string(att.check_in))
                        out_utc = pytz.utc.localize(fields.Datetime.from_string(att.check_out))
                        in_local = in_utc.astimezone(tz)
                        # Count only if local check-in date matches
                        if in_local.date() == record.date:
                            diff = (out_utc - in_utc).total_seconds()
                            if diff > 0:
                                total += diff
                if total > 0:
                    ot_secs = int(min(total, 14400))

            record.ot_seconds = ot_secs
            h = ot_secs // 3600
            m = (ot_secs % 3600) // 60
            s = ot_secs % 60
            record.ot_str = f"{h:02d}:{m:02d}:{s:02d}"

    @api.depends('ot_seconds')
    def _compute_overtime_hours(self):
        for record in self:
            record.overtime_hours = (record.ot_seconds or 0) / 3600.0

    @api.depends('date')
    def _compute_overtime_type(self):
        for record in self:
            if not record.date:
                record.overtime_type = 'weekday'
                continue
            
            # Check if it's a holiday
            if self._is_holiday(record.date, record.employee_id):
                record.overtime_type = 'holiday'
            # Check if it's weekend
            elif record.date.weekday() >= 5:  # Saturday = 5, Sunday = 6
                record.overtime_type = 'weekend'
            else:
                record.overtime_type = 'weekday'

    @api.depends('overtime_hours', 'overtime_type', 'employee_id')
    def _compute_overtime_amount(self):
        for record in self:
            if not record.overtime_hours or not record.employee_id:
                record.overtime_amount = 0.0
                continue
            
            # Get hourly rate from employee contract
            hourly_rate = record._get_hourly_rate()
            
            # Calculate overtime amount based on type
            if record.overtime_type == 'weekday':
                rate_multiplier = 1.5  # 1.5x for weekday overtime
            elif record.overtime_type == 'weekend':
                rate_multiplier = 2.0   # 2.0x for weekend overtime
            elif record.overtime_type == 'holiday':
                rate_multiplier = 3.0   # 3.0x for holiday overtime
            else:
                rate_multiplier = 1.5
            
            record.overtime_amount = record.overtime_hours * hourly_rate * rate_multiplier

    @api.depends('state')
    def _compute_color(self):
        """Compute color for kanban view based on state"""
        color_map = {
            'draft': 0,      # No color (default)
            'submitted': 1,  # Red
            'approved': 10,  # Green
            'rejected': 2,   # Orange
            'paid': 8        # Blue
        }
        for record in self:
            record.color = color_map.get(record.state, 0)

    def _get_hourly_rate(self):
        """Get employee hourly rate from current contract"""
        self.ensure_one()
        
        contract = self.env['hr.contract'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'open'),
            ('date_start', '<=', self.date),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', self.date)
        ], limit=1)
        
        if contract and contract.wage:
            # Assume monthly wage, convert to hourly
            # Standard: 22 working days * 8 hours = 176 hours per month
            return contract.wage / 176.0
        
        # Default hourly rate if no contract found
        return 50.0  # Default rate

    def _is_holiday(self, date, employee):
        """Check if the date is a public holiday for the employee.

        Be resilient across Odoo versions/modules:
        - Prefer modern models if available.
        - Fall back gracefully when public holiday models are not installed.
        """
        env = self.env
        company_id = employee.company_id.id if employee and employee.company_id else False

        # 1) Legacy/community installations may use 'hr.leave.public'
        try:
            if 'hr.leave.public' in env:
                holiday = env['hr.leave.public'].search([
                    ('date', '=', date),
                    '|',
                    ('company_id', '=', False),
                    ('company_id', '=', company_id)
                ], limit=1)
                if holiday:
                    return True
        except Exception:
            # If the model exists but fields differ, ignore and try other models
            _logger.debug('hr.leave.public lookup failed; trying alternative models')

        # 2) Newer Odoo versions commonly have 'hr.holidays.public' with lines
        try:
            if 'hr.holidays.public.line' in env:
                line_domain = [('date', '=', date)]
                # Some implementations include company on the line; if present, domain will still be valid
                if company_id:
                    line_domain = ['|', ('company_id', '=', False), ('company_id', '=', company_id), ('date', '=', date)]
                lines = env['hr.holidays.public.line'].search(line_domain, limit=1)
                if lines:
                    return True
        except Exception:
            _logger.debug('hr.holidays.public.line lookup failed; continuing')

        # 3) Alternative naming found in certain forks: 'hr.public.holiday'
        try:
            if 'hr.public.holiday' in env:
                domain = [('date', '=', date)]
                if company_id:
                    domain.append(('company_id', '=', company_id))
                alt = env['hr.public.holiday'].search(domain, limit=1)
                if alt:
                    return True
        except Exception:
            _logger.debug('hr.public.holiday lookup failed; continuing')

        # 4) If none of the models are available, treat as a non-holiday
        return False

    @api.model
    def calculate_daily_overtime(self, date=None):
        """Calculate overtime for all employees for a specific date"""
        if not date:
            date = fields.Date.today() - timedelta(days=1)  # Yesterday
        
        _logger.info('Calculating overtime for date: %s', date)
        
        # Get all employees
        employees = self.env['hr.employee'].search([
            ('active', '=', True)
        ])
        
        for employee in employees:
            try:
                self._calculate_employee_overtime(employee, date)
            except Exception as e:
                _logger.error('Error calculating overtime for employee %s: %s', 
                            employee.name, str(e))

    def _calculate_employee_overtime(self, employee, date):
        """Calculate/Update overtime per new business rules for a specific employee and date"""
        # Find existing overtime record (include all hours)
        overtime = self.with_context(overtime_any=True).search([
            ('employee_id', '=', employee.id),
            ('date', '=', date)
        ], limit=1)

        # Gather attendances of that local date (based on check_in)
        attendances = self.env['hr.attendance'].search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', date),
            ('check_in', '<', date + timedelta(days=1)),
        ])

        if not attendances:
            return overtime or None

        # Pre-compute daily OT seconds according to business rules
        ot_secs = self._compute_daily_ot_seconds(employee, date, attendances)
        ot_hours = ot_secs / 3600.0

        # Threshold rules:
        # - Weekday: keep/create OT only when >= 0.5 hours
        # - Weekend/Holiday: keep/create OT when there is any worked time (>0 seconds)
        weekday_num = date.weekday()
        if (weekday_num <= 4 and ot_secs < 1800) or (weekday_num >= 5 and ot_secs <= 0):
            # Ensure attendances are not linked to a non-OT record
            attendances.write({'overtime_id': False})
            # Clean up draft empty record to avoid clutter
            if overtime and overtime.state == 'draft':
                try:
                    overtime.unlink()
                except Exception:
                    pass
            return None

        # Resolve timezone for worked_hours aggregation
        tz_name = (employee and employee.tz) or self.env.user.tz or 'Asia/Ho_Chi_Minh'
        try:
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.utc

        # Aggregate worked hours for the local date
        total_worked_hours = 0.0
        for att in attendances:
            if not att.check_in or not att.check_out:
                continue
            try:
                in_utc = pytz.utc.localize(fields.Datetime.from_string(att.check_in))
                out_utc = pytz.utc.localize(fields.Datetime.from_string(att.check_out))
            except Exception:
                continue
            in_local = in_utc.astimezone(tz)
            # Only count if local check-in date matches the target date
            if in_local.date() != date:
                continue
            seconds = (out_utc - in_utc).total_seconds()
            if seconds > 0:
                total_worked_hours += seconds / 3600.0

        # Planned standard hours from resource calendar
        planned_hours = self._get_standard_hours(employee, date)

        # Determine overtime type for the date
        if self._is_holiday(date, employee):
            ot_type = 'holiday'
        elif date.weekday() >= 5:
            ot_type = 'weekend'
        else:
            ot_type = 'weekday'

        vals = {
            'employee_id': employee.id,
            'date': date,
            'state': overtime.state if overtime else 'draft',
            'worked_hours': total_worked_hours,
            'standard_hours': planned_hours,
            'weekday_overtime': ot_hours if ot_type == 'weekday' else 0.0,
            'weekend_overtime': ot_hours if ot_type == 'weekend' else 0.0,
            'holiday_overtime': ot_hours if ot_type == 'holiday' else 0.0,
        }

        if overtime:
            overtime.write(vals)
        else:
            overtime = self.create(vals)

        # Link attendances to overtime record
        attendances.write({'overtime_id': overtime.id})

        _logger.info('Overtime recalculated for %s on %s: OT=%s, Hours=%.2f',
                     employee.name, date, overtime.ot_str, overtime.overtime_hours)

        return overtime

    def _compute_daily_ot_seconds(self, employee, date, attendances):
        """Compute daily OT seconds without requiring an overtime record."""
        # Resolve timezone
        tz_name = (employee and employee.tz) or self.env.user.tz or 'Asia/Ho_Chi_Minh'
        try:
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.utc

        weekday = date.weekday()  # 0=Mon .. 6=Sun
        ot_secs = 0

        if weekday <= 4:
            # Weekday: OT starts at 18:00 local; only count if checkout after 18:00 and >= 30 minutes
            overtime_start_local = tz.localize(datetime(date.year, date.month, date.day, 18, 0, 0))
            latest_out_local = None
            for att in attendances:
                if att.check_out:
                    out_utc = pytz.utc.localize(fields.Datetime.from_string(att.check_out))
                    out_local = out_utc.astimezone(tz)
                    if out_local.date() == date:
                        if latest_out_local is None or out_local > latest_out_local:
                            latest_out_local = out_local
            if latest_out_local and latest_out_local > overtime_start_local:
                delta = (latest_out_local - overtime_start_local).total_seconds()
                if delta >= 1800:
                    ot_secs = int(delta)
        else:
            # Weekend: sum all worked time of the day and cap at 4 hours
            total = 0
            for att in attendances:
                if att.check_in and att.check_out:
                    in_utc = pytz.utc.localize(fields.Datetime.from_string(att.check_in))
                    out_utc = pytz.utc.localize(fields.Datetime.from_string(att.check_out))
                    in_local = in_utc.astimezone(tz)
                    if in_local.date() == date:
                        diff = (out_utc - in_utc).total_seconds()
                        if diff > 0:
                            total += diff
            if total > 0:
                ot_secs = int(min(total, 14400))

        return ot_secs

    def _get_standard_hours(self, employee, date):
        """Return planned working hours for the given employee and date.
        Uses the employee's resource calendar if available; otherwise falls back
        to 8 hours on weekdays and 0 on weekends.
        """
        calendar = employee.resource_calendar_id if employee else False
        fallback = 8.0 if date.weekday() < 5 else 0.0
        if not calendar:
            return fallback

        # Resource calendar attendance lines: dayofweek '0'..'6' (Mon..Sun), hour_from/hour_to float
        weekday_str = str(date.weekday())
        try:
            lines = calendar.attendance_ids.filtered(lambda l: l.dayofweek == weekday_str)
        except Exception:
            # In case attendance_ids or fields differ, use fallback
            return fallback
        if not lines:
            return fallback
        total = 0.0
        for l in lines:
            try:
                total += float(l.hour_to) - float(l.hour_from)
            except Exception:
                continue
        return total if total > 0 else fallback

    def action_submit(self):
        """Submit overtime for approval"""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft overtime can be submitted'))
            record.state = 'submitted'

    def action_approve(self):
        """Approve overtime"""
        for record in self:
            if record.state != 'submitted':
                raise UserError(_('Only submitted overtime can be approved'))
            record.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approval_date': fields.Datetime.now()
            })

    def action_reject(self):
        """Reject overtime"""
        for record in self:
            if record.state != 'submitted':
                raise UserError(_('Only submitted overtime can be rejected'))
            record.state = 'rejected'

    def action_reset_to_draft(self):
        """Reset to draft"""
        for record in self:
            record.write({
                'state': 'draft',
                'approved_by': False,
                'approval_date': False,
                'rejection_reason': False
            })

    @api.model
    def cron_calculate_overtime(self):
        """Cron job to calculate overtime daily"""
        yesterday = fields.Date.today() - timedelta(days=1)
        self.calculate_daily_overtime(yesterday)

    @api.constrains('date', 'employee_id')
    def _check_unique_date_employee(self):
        for record in self:
            existing = self.search([
                ('employee_id', '=', record.employee_id.id),
                ('date', '=', record.date),
                ('id', '!=', record.id)
            ])
            if existing:
                raise ValidationError(
                    _('Overtime record already exists for %s on %s') % 
                    (record.employee_id.name, record.date)
                )


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    overtime_id = fields.Many2one(
        'hr.overtime',
        string='Overtime Record',
        readonly=True
    )
    
    attendance_status = fields.Selection([
        ('normal', 'Normal'),
        ('late_in', 'Late Check-In'),
        ('early_out', 'Early Check-Out'),
        ('missing_out', 'Missing Check-Out'),
        ('missing_in', 'Missing Check-In'),
        ('overtime', 'Overtime'),
        ('both_issues', 'Late In & Early Out')
    ], string='Status', compute='_compute_attendance_status', store=True)
    
    late_minutes = fields.Float(
        string='Late Minutes',
        compute='_compute_late_early',
        store=True
    )
    early_minutes = fields.Float(
        string='Early Minutes',
        compute='_compute_late_early',
        store=True
    )
    
    @api.depends('check_in', 'check_out', 'employee_id')
    def _compute_attendance_status(self):
        config = self.env['attendance.enhanced.config'].get_config()
        grace_period = config.get('grace_period_minutes', 15.0)

        for record in self:
            if not record.check_in or not record.employee_id:
                record.attendance_status = 'normal'
                continue
            
            # Get standard work schedule (may be missing on weekends/holidays)
            schedule = record._get_work_schedule()
            if not schedule:
                # Still evaluate missing-out and overtime even without a schedule
                if not record.check_out:
                    record.attendance_status = 'missing_out'
                    continue
                if record.overtime_id and (
                    record.overtime_id.overtime_hours >= 0.5 or
                    record.overtime_id.overtime_type in ('weekend', 'holiday')
                ):
                    record.attendance_status = 'overtime'
                    continue
                record.attendance_status = 'normal'
                continue
            
            # Missing check-in takes precedence
            if getattr(record, 'missing_check_in', False):
                record.attendance_status = 'missing_in'
                continue

            # Check for missing check-out
            if not record.check_out:
                record.attendance_status = 'missing_out'
                continue
            
            # Check for late check-in
            if record._is_late_checkin(schedule, grace_period):
                record.attendance_status = 'late_in'
                continue
            
            # Check for early check-out
            # Grace applies ONLY to check-in; early-out is strict
            if record._is_early_checkout(schedule):
                record.attendance_status = 'early_out'
                continue
            
            # Check for overtime
            # - Weekdays: require OT >= 0.5h
            # - Weekends/Holidays: any OT shows as overtime
            if record.overtime_id and (
                record.overtime_id.overtime_hours >= 0.5 or
                record.overtime_id.overtime_type in ('weekend', 'holiday')
            ):
                record.attendance_status = 'overtime'
                continue
            
            record.attendance_status = 'normal'

    @api.depends('check_in', 'check_out', 'employee_id')
    def _compute_late_early(self):
        for record in self:
            record.late_minutes = 0.0
            record.early_minutes = 0.0
            
            if not record.check_in or not record.employee_id:
                continue
            
            schedule = record._get_work_schedule()
            if not schedule:
                continue
            
            # Calculate late minutes
            if record._is_late_checkin(schedule):
                expected_in = record._get_expected_checkin_time(schedule)
                if expected_in:
                    late_delta = record.check_in - expected_in
                    record.late_minutes = late_delta.total_seconds() / 60.0
            
            # Calculate early minutes
            if record.check_out and record._is_early_checkout(schedule):
                expected_out = record._get_expected_checkout_time(schedule)
                if expected_out:
                    early_delta = expected_out - record.check_out
                    record.early_minutes = early_delta.total_seconds() / 60.0

    def _get_work_schedule(self):
        """Get work schedule for the attendance date"""
        if not self.employee_id.resource_calendar_id:
            return None
        
        calendar = self.employee_id.resource_calendar_id
        weekday = self.check_in.weekday()
        
        return calendar.attendance_ids.filtered(
            lambda l: int(l.dayofweek) == weekday
        )

    def _is_late_checkin(self, schedule, grace_minutes=0.0):
        """Check if check-in is late"""
        if not schedule:
            return False
        
        expected_time = self._get_expected_checkin_time(schedule)
        if not expected_time:
            return False
        if grace_minutes and grace_minutes > 0:
            return self.check_in > (expected_time + timedelta(minutes=grace_minutes))
        return self.check_in > expected_time

    def _is_early_checkout(self, schedule):
        """Check if check-out is early"""
        if not schedule or not self.check_out:
            return False
        
        expected_time = self._get_expected_checkout_time(schedule)
        return expected_time and self.check_out < expected_time

    def _get_expected_checkin_time(self, schedule):
        """Get expected check-in time"""
        if not schedule:
            return None
        
        # Get the earliest start time for the day
        earliest = min(schedule.mapped('hour_from'))
        
        # Convert to datetime
        check_date = self.check_in.date()
        expected_time = datetime.combine(check_date, time(int(earliest), int((earliest % 1) * 60)))
        
        return expected_time

    def _get_expected_checkout_time(self, schedule):
        """Get expected check-out time"""
        if not schedule:
            return None
        
        # Get the latest end time for the day
        latest = max(schedule.mapped('hour_to'))
        
        # Convert to datetime
        check_date = self.check_in.date()
        expected_time = datetime.combine(check_date, time(int(latest), int((latest % 1) * 60)))
        
        return expected_time