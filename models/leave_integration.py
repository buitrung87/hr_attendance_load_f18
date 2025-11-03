# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class LeaveDeduction(models.Model):
    _name = 'leave.deduction'
    _description = 'Leave Deduction for Late/Early Attendance'
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
    attendance_id = fields.Many2one(
        'hr.attendance',
        string='Related Attendance',
        required=True
    )
    deduction_type = fields.Selection([
        ('late_in', 'Late Check-In'),
        ('early_out', 'Early Check-Out'),
        ('both', 'Both Late In and Early Out'),
        ('missing_in', 'Missing Check-In'),
        ('missing_out', 'Missing Check-Out')
    ], string='Deduction Type', required=True)
    
    late_minutes = fields.Float(
        string='Late Minutes',
        digits=(16, 2),
        help='Minutes late for check-in'
    )
    early_minutes = fields.Float(
        string='Early Minutes',
        digits=(16, 2),
        help='Minutes early for check-out'
    )
    total_minutes = fields.Float(
        string='Total Minutes',
        compute='_compute_total_minutes',
        store=True,
        help='Total minutes to deduct'
    )
    # Optional field for missing check-in/out minutes (some flows may set this)
    missing_minutes = fields.Float(
        string='Missing Minutes',
        default=0.0,
        help='Minutes associated with missing check-in/out incidents (for reporting only)'
    )
    deduction_days = fields.Float(
        string='Deduction Days',
        compute='_compute_deduction_days',
        store=True,
        digits=(16, 3),
        help='Leave days to deduct (based on 8-hour workday)'
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('deducted', 'Deducted'),
        ('cancelled', 'Cancelled')
    ], string='State', default='draft', tracking=True)
    
    leave_allocation_id = fields.Many2one(
        'hr.leave.allocation',
        string='Leave Allocation',
        help='Leave allocation from which days were deducted'
    )
    
    notes = fields.Text(string='Notes')
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
    
    # Configuration fields
    grace_period_minutes = fields.Float(
        string='Grace Period (Minutes)',
        default=10.0,
        help='Grace period in minutes before deduction starts'
    )

    @api.depends('employee_id', 'date', 'deduction_type')
    def _compute_display_name(self):
        for record in self:
            if record.employee_id and record.date:
                # Prefer showing combined attendance status when applicable
                combined = None
                if record.attendance_id and record.attendance_id.attendance_status in ('late_missing_out', 'early_missing_in'):
                    if record.attendance_id.attendance_status == 'late_missing_out':
                        combined = _('Late Check-In + Missing Check-Out')
                    else:
                        combined = _('Early Check-Out + Missing Check-In')
                type_label = dict(record._fields['deduction_type'].selection).get(record.deduction_type, '')
                display_label = combined or type_label
                record.display_name = _('%s - %s (%s)') % (
                    record.employee_id.name,
                    record.date.strftime('%Y-%m-%d'),
                    display_label
                )
            else:
                record.display_name = _('New Leave Deduction')

    @api.depends('late_minutes', 'early_minutes')
    def _compute_total_minutes(self):
        for record in self:
            record.total_minutes = record.late_minutes + record.early_minutes

    @api.depends('total_minutes')
    def _compute_deduction_days(self):
        for record in self:
            if record.total_minutes > 0:
                # Convert minutes to days (8 hours = 480 minutes = 1 day)
                record.deduction_days = record.total_minutes / 480.0
            else:
                record.deduction_days = 0.0

    @api.model
    def process_daily_deductions(self, date=None):
        """Process leave deductions for all employees for a specific date"""
        if not date:
            date = fields.Date.today() - timedelta(days=1)  # Yesterday
        
        _logger.info('Processing leave deductions for date: %s', date)
        
        # Get all attendances for the date that have late/early/missing issues
        # Include records where either check_in or check_out lies within the day
        attendances = self.env['hr.attendance'].search([
            '|',
            '&', ('check_in', '>=', date), ('check_in', '<', date + timedelta(days=1)),
            '&', ('check_out', '>=', date), ('check_out', '<', date + timedelta(days=1)),
            ('attendance_status', 'in', ['late_in', 'early_out', 'missing_in', 'missing_out', 'late_missing_out', 'early_missing_in'])
        ])
        
        for attendance in attendances:
            try:
                self._process_attendance_deduction(attendance)
            except Exception as e:
                _logger.error('Error processing deduction for attendance %s: %s', 
                            attendance.id, str(e))

    def _process_attendance_deduction(self, attendance):
        """Process leave deduction for a specific attendance"""
        # Check if deduction already exists
        existing = self.search([
            ('attendance_id', '=', attendance.id)
        ])
        
        if existing:
            return existing
        
        # Get configuration
        config = self.env['attendance.enhanced.config'].get_config()
        grace_period = config.get('grace_period_minutes', 15.0)
        
        # Skip completely if missing check-in/out has been approved
        if (getattr(attendance, 'missing_check_in', False) or not attendance.check_out) \
            and getattr(attendance, 'missing_request_state', 'none') == 'approved':
            return None

        # Handle combined statuses explicitly
        if attendance.attendance_status == 'late_missing_out':
            # Deduct late minutes (after grace); mark as late_in
            late_minutes = max(0, attendance.late_minutes - grace_period)
            if late_minutes > 0:
                deduction_vals = {
                    'employee_id': attendance.employee_id.id,
                    'date': (attendance.check_in or attendance.check_out).date(),
                    'attendance_id': attendance.id,
                    'deduction_type': 'late_in',
                    'late_minutes': late_minutes,
                    'early_minutes': 0.0,
                    'grace_period_minutes': grace_period,
                    'state': 'draft',
                    'notes': _('Missing Check-Out present')
                }
            else:
                # Pure missing_out (no late beyond grace): dashboard-only
                deduction_vals = {
                    'employee_id': attendance.employee_id.id,
                    'date': (attendance.check_in or attendance.check_out).date(),
                    'attendance_id': attendance.id,
                    'deduction_type': 'missing_out',
                    'late_minutes': 0.0,
                    'early_minutes': 0.0,
                    'grace_period_minutes': grace_period,
                    'state': 'draft'
                }
            deduction = self.create(deduction_vals)
            return deduction

        if attendance.attendance_status == 'early_missing_in':
            # Deduct early minutes (no grace); mark as early_out
            early_minutes = max(0, attendance.early_minutes)
            if early_minutes > 0:
                deduction_vals = {
                    'employee_id': attendance.employee_id.id,
                    'date': (attendance.check_in or attendance.check_out).date(),
                    'attendance_id': attendance.id,
                    'deduction_type': 'early_out',
                    'late_minutes': 0.0,
                    'early_minutes': early_minutes,
                    'grace_period_minutes': grace_period,
                    'state': 'draft',
                    'notes': _('Missing Check-In present')
                }
            else:
                # Pure missing_in (no early): dashboard-only
                deduction_vals = {
                    'employee_id': attendance.employee_id.id,
                    'date': (attendance.check_in or attendance.check_out).date(),
                    'attendance_id': attendance.id,
                    'deduction_type': 'missing_in',
                    'late_minutes': 0.0,
                    'early_minutes': 0.0,
                    'grace_period_minutes': grace_period,
                    'state': 'draft'
                }
            deduction = self.create(deduction_vals)
            return deduction

        # Handle pure missing statuses: create dashboard-only records
        if attendance.attendance_status in ('missing_in', 'missing_out'):
            deduction_type = 'missing_in' if attendance.attendance_status == 'missing_in' else 'missing_out'
            deduction_vals = {
                'employee_id': attendance.employee_id.id,
                'date': (attendance.check_in or attendance.check_out).date(),
                'attendance_id': attendance.id,
                'deduction_type': deduction_type,
                'late_minutes': 0.0,
                'early_minutes': 0.0,
                'grace_period_minutes': grace_period,
                'state': 'draft'
            }
            deduction = self.create(deduction_vals)
            return deduction

        # Default handling for standard late/early
        late_minutes = max(0, attendance.late_minutes - grace_period)
        early_minutes = max(0, attendance.early_minutes)
        # Only create deduction if there are actual minutes to deduct
        if late_minutes <= 0 and early_minutes <= 0:
            return None
        # Determine deduction type
        if late_minutes > 0 and early_minutes > 0:
            deduction_type = 'both'
        elif late_minutes > 0:
            deduction_type = 'late_in'
        else:
            deduction_type = 'early_out'
        deduction_vals = {
            'employee_id': attendance.employee_id.id,
            'date': attendance.check_in.date(),
            'attendance_id': attendance.id,
            'deduction_type': deduction_type,
            'late_minutes': late_minutes,
            'early_minutes': early_minutes,
            'grace_period_minutes': grace_period,
            'state': 'draft'
        }
        deduction = self.create(deduction_vals)
        
        # Auto-confirm if configured
        if config.get('auto_confirm_deductions', False):
            deduction.action_confirm()
        
        _logger.info('Created leave deduction for %s: %.3f days', 
                    attendance.employee_id.name, deduction.deduction_days)
        
        return deduction

    def action_confirm(self):
        """Confirm the deduction"""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft deductions can be confirmed'))
            # Set to confirmed
            record.state = 'confirmed'
            # Automatically deduct only for late/early types
            if record.deduction_type in ('late_in', 'early_out', 'both'):
                # Perform deduction immediately; will raise if allocation not found or insufficient
                record.action_deduct()

    def action_deduct(self):
        """Actually deduct the leave days from employee's allocation"""
        for record in self:
            if record.state != 'confirmed':
                raise UserError(_('Only confirmed deductions can be processed'))
            
            if record.deduction_days <= 0:
                raise UserError(_('No days to deduct'))
            
            # Find the appropriate leave allocation
            allocation = record._find_leave_allocation()
            
            if not allocation:
                raise UserError(_('No suitable leave allocation found for %s') % 
                              record.employee_id.name)
            
            # Check if there are enough days
            if allocation.number_of_days < record.deduction_days:
                raise UserError(_('Insufficient leave balance. Available: %.3f days, Required: %.3f days') % 
                              (allocation.number_of_days, record.deduction_days))
            
            # Deduct the days
            allocation.number_of_days -= record.deduction_days
            
            # Update record
            record.write({
                'state': 'deducted',
                'leave_allocation_id': allocation.id
            })
            
            # Log the deduction
            allocation.message_post(
                body=_('Deducted %.3f days for late/early attendance on %s (Deduction ID: %s)') % 
                     (record.deduction_days, record.date, record.id)
            )

    def action_cancel(self):
        """Cancel the deduction"""
        for record in self:
            if record.state == 'deducted':
                # Restore the deducted days
                if record.leave_allocation_id:
                    record.leave_allocation_id.number_of_days += record.deduction_days
                    record.leave_allocation_id.message_post(
                        body=_('Restored %.3f days - cancelled deduction for %s (Deduction ID: %s)') % 
                             (record.deduction_days, record.date, record.id)
                    )
            
            record.state = 'cancelled'

    def action_reset_to_draft(self):
        """Reset cancelled deduction back to draft"""
        for record in self:
            if record.state != 'cancelled':
                raise UserError(_('Only cancelled deductions can be reset to draft'))
            record.state = 'draft'

    def _find_leave_allocation(self):
        """Find the appropriate leave allocation for deduction"""
        # Look for annual leave allocation
        allocation = self.env['hr.leave.allocation'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'validate'),
            ('holiday_status_id.allocation_type', '=', 'fixed'),
            ('date_from', '<=', self.date),
            ('date_to', '>=', self.date),
            ('number_of_days', '>', 0)
        ], order='date_from desc', limit=1)
        
        if not allocation:
            # Look for any valid allocation
            allocation = self.env['hr.leave.allocation'].search([
                ('employee_id', '=', self.employee_id.id),
                ('state', '=', 'validate'),
                ('number_of_days', '>', 0)
            ], order='date_from desc', limit=1)
        
        return allocation

    @api.model
    def cron_process_deductions(self):
        """Cron job to process leave deductions daily"""
        yesterday = fields.Date.today() - timedelta(days=1)
        self.process_daily_deductions(yesterday)

    @api.constrains('date', 'employee_id', 'attendance_id')
    def _check_unique_attendance(self):
        for record in self:
            existing = self.search([
                ('attendance_id', '=', record.attendance_id.id),
                ('id', '!=', record.id)
            ])
            if existing:
                raise ValidationError(
                    _('Deduction already exists for this attendance record')
                )


class LeaveSummary(models.Model):
    _name = 'leave.summary'
    _description = 'Employee Leave Summary'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        index=True
    )
    leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Leave Type',
        required=True
    )
    year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: fields.Date.today().year
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        readonly=True
    )
    
    # Leave balances
    allocated_days = fields.Float(
        string='Allocated Days',
        compute='_compute_leave_balances',
        store=True,
        digits=(16, 3)
    )
    used_days = fields.Float(
        string='Used Days',
        compute='_compute_leave_balances',
        store=True,
        digits=(16, 3)
    )
    deducted_days = fields.Float(
        string='Deducted Days',
        compute='_compute_leave_balances',
        store=True,
        digits=(16, 3),
        help='Days deducted for late/early attendance'
    )
    remaining_days = fields.Float(
        string='Remaining Days',
        compute='_compute_leave_balances',
        store=True,
        digits=(16, 3)
    )
    
    # Deduction statistics
    total_deductions = fields.Integer(
        string='Total Deductions',
        compute='_compute_deduction_stats',
        store=True
    )
    late_deductions = fields.Integer(
        string='Late Check-in Deductions',
        compute='_compute_deduction_stats',
        store=True
    )
    early_deductions = fields.Integer(
        string='Early Check-out Deductions',
        compute='_compute_deduction_stats',
        store=True
    )
    
    # Additional fields for views
    deduction_count = fields.Integer(
        string='Deduction Count',
        compute='_compute_deduction_stats',
        store=True
    )
    last_updated = fields.Datetime(
        string='Last Updated',
        default=fields.Datetime.now,
        readonly=True
    )
    deduction_ids = fields.One2many(
        'leave.deduction',
        'employee_id',
        string='Related Deductions',
        domain="[('date', '>=', datetime.datetime(year, 1, 1).date()), ('date', '<=', datetime.datetime(year, 12, 31).date())]"
    )

    @api.depends('employee_id', 'leave_type_id', 'year')
    def _compute_leave_balances(self):
        for record in self:
            if not record.employee_id or not record.leave_type_id:
                record.allocated_days = 0.0
                record.used_days = 0.0
                record.deducted_days = 0.0
                record.remaining_days = 0.0
                continue
            
            year_start = datetime(record.year, 1, 1).date()
            year_end = datetime(record.year, 12, 31).date()
            
            # Get allocated days
            allocations = self.env['hr.leave.allocation'].search([
                ('employee_id', '=', record.employee_id.id),
                ('holiday_status_id', '=', record.leave_type_id.id),
                ('state', '=', 'validate'),
                ('date_from', '<=', year_end),
                ('date_to', '>=', year_start)
            ])
            record.allocated_days = sum(allocations.mapped('number_of_days'))
            
            # Get used days
            leaves = self.env['hr.leave'].search([
                ('employee_id', '=', record.employee_id.id),
                ('holiday_status_id', '=', record.leave_type_id.id),
                ('state', '=', 'validate'),
                ('date_from', '>=', year_start),
                ('date_to', '<=', year_end)
            ])
            record.used_days = sum(leaves.mapped('number_of_days'))
            
            # Get deducted days
            deductions = self.env['leave.deduction'].search([
                ('employee_id', '=', record.employee_id.id),
                ('state', '=', 'deducted'),
                ('date', '>=', year_start),
                ('date', '<=', year_end)
            ])
            record.deducted_days = sum(deductions.mapped('deduction_days'))
            
            # Calculate remaining
            record.remaining_days = record.allocated_days - record.used_days - record.deducted_days

    @api.depends('employee_id', 'year')
    def _compute_deduction_stats(self):
        for record in self:
            if not record.employee_id:
                record.total_deductions = 0
                record.late_deductions = 0
                record.early_deductions = 0
                record.deduction_count = 0
                continue
            
            year_start = datetime(record.year, 1, 1).date()
            year_end = datetime(record.year, 12, 31).date()
            
            deductions = self.env['leave.deduction'].search([
                ('employee_id', '=', record.employee_id.id),
                ('state', '=', 'deducted'),
                ('date', '>=', year_start),
                ('date', '<=', year_end)
            ])
            
            record.total_deductions = len(deductions)
            record.deduction_count = len(deductions)
            record.late_deductions = len(deductions.filtered(
                lambda d: d.deduction_type in ['late_in', 'both']
            ))
            record.early_deductions = len(deductions.filtered(
                lambda d: d.deduction_type in ['early_out', 'both']
            ))

    @api.model
    def update_all_summaries(self, year=None):
        """Update leave summaries for all employees"""
        if not year:
            year = fields.Date.today().year
        
        employees = self.env['hr.employee'].search([('active', '=', True)])
        leave_types = self.env['hr.leave.type'].search([('allocation_type', '=', 'fixed')])
        
        for employee in employees:
            for leave_type in leave_types:
                # Check if summary exists
                summary = self.search([
                    ('employee_id', '=', employee.id),
                    ('leave_type_id', '=', leave_type.id),
                    ('year', '=', year)
                ])
                
                if not summary:
                    # Create new summary
                    self.create({
                        'employee_id': employee.id,
                        'leave_type_id': leave_type.id,
                        'year': year
                    })

    def write(self, vals):
        """Update last_updated field when record is modified"""
        vals['last_updated'] = fields.Datetime.now()
        return super().write(vals)


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    deducted_days = fields.Float(
        string='Deducted Days',
        compute='_compute_deducted_days',
        store=True,
        digits=(16, 3),
        help='Total days deducted for late/early attendance'
    )
    
    deduction_ids = fields.One2many(
        'leave.deduction',
        'leave_allocation_id',
        string='Related Deductions'
    )

    @api.depends('deduction_ids', 'deduction_ids.deduction_days', 'deduction_ids.state')
    def _compute_deducted_days(self):
        for record in self:
            deductions = record.deduction_ids.filtered(lambda d: d.state == 'deducted')
            record.deducted_days = sum(deductions.mapped('deduction_days'))


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    rfid = fields.Char(
        string='RFID',
        help='RFID card number for attendance machine'
    )
    employee_number = fields.Char(
        string='Employee Number',
        help='Employee number for attendance machine'
    )
    
    # Leave deduction statistics
    total_deductions_ytd = fields.Float(
        string='Total Deductions YTD',
        compute='_compute_deduction_stats',
        digits=(16, 3),
        help='Total leave days deducted this year'
    )
    late_incidents_ytd = fields.Integer(
        string='Late Incidents YTD',
        compute='_compute_deduction_stats',
        help='Number of late check-in incidents this year'
    )
    early_incidents_ytd = fields.Integer(
        string='Early Incidents YTD',
        compute='_compute_deduction_stats',
        help='Number of early check-out incidents this year'
    )

    @api.depends('name')  # Dummy dependency to trigger computation
    def _compute_deduction_stats(self):
        current_year = fields.Date.today().year
        year_start = datetime(current_year, 1, 1).date()
        year_end = datetime(current_year, 12, 31).date()
        
        for employee in self:
            deductions = self.env['leave.deduction'].search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'deducted'),
                ('date', '>=', year_start),
                ('date', '<=', year_end)
            ])
            
            employee.total_deductions_ytd = sum(deductions.mapped('deduction_days'))
            employee.late_incidents_ytd = len(deductions.filtered(
                lambda d: d.deduction_type in ['late_in', 'both']
            ))
            employee.early_incidents_ytd = len(deductions.filtered(
                lambda d: d.deduction_type in ['early_out', 'both']
            ))