# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # F18 Integration Fields
    rfid = fields.Char(
        string='RFID Card',
        help='RFID card number for F18 attendance machine',
        index=True
    )
    employee_number = fields.Char(
        string='Employee Number',
        help='Employee number for F18 attendance machine',
        index=True
    )
    f18_user_id = fields.Integer(
        string='F18 User ID',
        help='User ID in F18 attendance machine',
        index=True
    )
    
    # Attendance Statistics (Current Month)
    attendance_count_month = fields.Integer(
        string='Attendance Days (Month)',
        compute='_compute_attendance_stats',
        help='Number of attendance days this month'
    )
    late_count_month = fields.Integer(
        string='Late Arrivals (Month)',
        compute='_compute_attendance_stats',
        help='Number of late arrivals this month'
    )
    early_count_month = fields.Integer(
        string='Early Departures (Month)',
        compute='_compute_attendance_stats',
        help='Number of early departures this month'
    )
    overtime_hours_month = fields.Float(
        string='Overtime Hours (Month)',
        compute='_compute_attendance_stats',
        digits=(16, 2),
        help='Total overtime hours this month'
    )
    
    # Attendance Statistics (Year to Date)
    attendance_count_ytd = fields.Integer(
        string='Attendance Days (YTD)',
        compute='_compute_attendance_stats_ytd',
        help='Number of attendance days year to date'
    )
    late_count_ytd = fields.Integer(
        string='Late Arrivals (YTD)',
        compute='_compute_attendance_stats_ytd',
        help='Number of late arrivals year to date'
    )
    early_count_ytd = fields.Integer(
        string='Early Departures (YTD)',
        compute='_compute_attendance_stats_ytd',
        help='Number of early departures year to date'
    )
    overtime_hours_ytd = fields.Float(
        string='Overtime Hours (YTD)',
        compute='_compute_attendance_stats_ytd',
        digits=(16, 2),
        help='Total overtime hours year to date'
    )
    
    # Leave Deduction Statistics
    leave_deductions_month = fields.Float(
        string='Leave Deductions (Month)',
        compute='_compute_leave_deduction_stats',
        digits=(16, 3),
        help='Leave days deducted this month for late/early attendance'
    )
    leave_deductions_ytd = fields.Float(
        string='Leave Deductions (YTD)',
        compute='_compute_leave_deduction_stats',
        digits=(16, 3),
        help='Leave days deducted year to date for late/early attendance'
    )
    
    # Perfect Attendance
    perfect_attendance_month = fields.Boolean(
        string='Perfect Attendance (Month)',
        compute='_compute_perfect_attendance',
        help='No late arrivals or early departures this month'
    )
    perfect_attendance_ytd = fields.Boolean(
        string='Perfect Attendance (YTD)',
        compute='_compute_perfect_attendance',
        help='No late arrivals or early departures year to date'
    )
    
    # Average Working Hours
    avg_working_hours_month = fields.Float(
        string='Avg Working Hours (Month)',
        compute='_compute_avg_working_hours',
        digits=(16, 2),
        help='Average working hours per day this month'
    )
    
    # Last Attendance
    last_attendance_date = fields.Datetime(
        string='Last Attendance',
        compute='_compute_last_attendance',
        help='Date and time of last attendance record'
    )
    last_attendance_status = fields.Selection([
        ('normal', 'Normal'),
        ('late_in', 'Late Check-In'),
        ('early_out', 'Early Check-Out'),
        ('missing_out', 'Missing Check-Out'),
        ('missing_in', 'Missing Check-In'),
        ('overtime', 'Overtime')
    ], string='Last Attendance Status',
       compute='_compute_last_attendance',
       help='Status of last attendance record')

    @api.depends('name')  # Dummy dependency to trigger computation
    def _compute_attendance_stats(self):
        """Compute attendance statistics for current month"""
        current_date = fields.Date.today()
        month_start = current_date.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        for employee in self:
            # Get attendances for current month
            attendances = self.env['hr.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', month_start),
                ('check_in', '<=', month_end)
            ])
            
            employee.attendance_count_month = len(set(attendances.mapped(lambda a: a.check_in.date())))
            employee.late_count_month = len(attendances.filtered(
                lambda a: a.attendance_status in ['late_in']
            ))
            employee.early_count_month = len(attendances.filtered(
                lambda a: a.attendance_status in ['early_out']
            ))
            
            # Get overtime for current month
            overtimes = self.env['hr.overtime'].search([
                ('employee_id', '=', employee.id),
                ('date', '>=', month_start),
                ('date', '<=', month_end)
            ])
            employee.overtime_hours_month = sum(overtimes.mapped('overtime_hours'))

    @api.depends('name')  # Dummy dependency to trigger computation
    def _compute_attendance_stats_ytd(self):
        """Compute attendance statistics year to date"""
        current_date = fields.Date.today()
        year_start = current_date.replace(month=1, day=1)
        
        for employee in self:
            # Get attendances for year to date
            attendances = self.env['hr.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', year_start),
                ('check_in', '<=', current_date)
            ])
            
            employee.attendance_count_ytd = len(set(attendances.mapped(lambda a: a.check_in.date())))
            employee.late_count_ytd = len(attendances.filtered(
                lambda a: a.attendance_status in ['late_in']
            ))
            employee.early_count_ytd = len(attendances.filtered(
                lambda a: a.attendance_status in ['early_out']
            ))
            
            # Get overtime for year to date
            overtimes = self.env['hr.overtime'].search([
                ('employee_id', '=', employee.id),
                ('date', '>=', year_start),
                ('date', '<=', current_date)
            ])
            employee.overtime_hours_ytd = sum(overtimes.mapped('overtime_hours'))

    @api.depends('name')  # Dummy dependency to trigger computation
    def _compute_leave_deduction_stats(self):
        """Compute leave deduction statistics"""
        current_date = fields.Date.today()
        month_start = current_date.replace(day=1)
        year_start = current_date.replace(month=1, day=1)
        
        for employee in self:
            # Month deductions
            month_deductions = self.env['leave.deduction'].search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'deducted'),
                ('date', '>=', month_start),
                ('date', '<=', current_date)
            ])
            employee.leave_deductions_month = sum(month_deductions.mapped('deduction_days'))
            
            # Year to date deductions
            ytd_deductions = self.env['leave.deduction'].search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'deducted'),
                ('date', '>=', year_start),
                ('date', '<=', current_date)
            ])
            employee.leave_deductions_ytd = sum(ytd_deductions.mapped('deduction_days'))

    @api.depends('late_count_month', 'early_count_month', 'late_count_ytd', 'early_count_ytd')
    def _compute_perfect_attendance(self):
        """Compute perfect attendance status"""
        for employee in self:
            employee.perfect_attendance_month = (
                employee.late_count_month == 0 and employee.early_count_month == 0
            )
            employee.perfect_attendance_ytd = (
                employee.late_count_ytd == 0 and employee.early_count_ytd == 0
            )

    @api.depends('name')  # Dummy dependency to trigger computation
    def _compute_avg_working_hours(self):
        """Compute average working hours for current month"""
        current_date = fields.Date.today()
        month_start = current_date.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        for employee in self:
            attendances = self.env['hr.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', month_start),
                ('check_in', '<=', month_end),
                ('check_out', '!=', False)
            ])
            
            if attendances:
                total_hours = sum(attendances.mapped('worked_hours'))
                unique_days = len(set(attendances.mapped(lambda a: a.check_in.date())))
                employee.avg_working_hours_month = total_hours / unique_days if unique_days > 0 else 0.0
            else:
                employee.avg_working_hours_month = 0.0

    @api.depends('name')  # Dummy dependency to trigger computation
    def _compute_last_attendance(self):
        """Compute last attendance information"""
        for employee in self:
            last_attendance = self.env['hr.attendance'].search([
                ('employee_id', '=', employee.id)
            ], order='check_in desc', limit=1)
            
            if last_attendance:
                employee.last_attendance_date = last_attendance.check_in
                employee.last_attendance_status = last_attendance.attendance_status or 'normal'
            else:
                employee.last_attendance_date = False
                employee.last_attendance_status = False

    def action_view_attendances(self):
        """Open attendance records for this employee"""
        return {
            'name': _('Attendances - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'hr.attendance',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

    def action_view_overtimes(self):
        """Open overtime records for this employee"""
        return {
            'name': _('Overtimes - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'hr.overtime',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

    def action_view_leave_deductions(self):
        """Open leave deduction records for this employee"""
        return {
            'name': _('Leave Deductions - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'leave.deduction',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

    @api.model
    def find_employee_by_identifier(self, identifier):
        """Find employee by various identifiers (RFID, employee number, F18 user ID)"""
        if not identifier:
            return self.env['hr.employee']
        
        # Try to find by RFID first
        employee = self.search([('rfid', '=', identifier)], limit=1)
        if employee:
            return employee
        
        # Try by employee number
        employee = self.search([('employee_number', '=', identifier)], limit=1)
        if employee:
            return employee
        
        # Try by F18 user ID (if it's a number)
        try:
            f18_id = int(identifier)
            employee = self.search([('f18_user_id', '=', f18_id)], limit=1)
            if employee:
                return employee
        except ValueError:
            pass
        
        # Try by barcode (existing field)
        employee = self.search([('barcode', '=', identifier)], limit=1)
        if employee:
            return employee
        
        return self.env['hr.employee']

    @api.model
    def get_attendance_dashboard_data(self):
        """Get data for attendance dashboard"""
        current_date = fields.Date.today()
        month_start = current_date.replace(day=1)
        year_start = current_date.replace(month=1, day=1)
        
        # Get all active employees
        employees = self.search([('active', '=', True)])
        
        # Calculate statistics
        total_employees = len(employees)
        present_today = len(self.env['hr.attendance'].search([
            ('employee_id', 'in', employees.ids),
            ('check_in', '>=', current_date),
            ('check_in', '<', current_date + timedelta(days=1))
        ]).mapped('employee_id'))
        
        late_today = len(self.env['hr.attendance'].search([
            ('employee_id', 'in', employees.ids),
            ('check_in', '>=', current_date),
            ('check_in', '<', current_date + timedelta(days=1)),
            ('attendance_status', '=', 'late_in')
        ]))
        
        # Perfect attendance this month
        perfect_attendance = employees.filtered('perfect_attendance_month')
        
        # Top overtime employees this month
        top_overtime = employees.sorted('overtime_hours_month', reverse=True)[:5]
        
        return {
            'total_employees': total_employees,
            'present_today': present_today,
            'late_today': late_today,
            'perfect_attendance_count': len(perfect_attendance),
            'perfect_attendance_employees': perfect_attendance.mapped('name'),
            'top_overtime_employees': [
                {
                    'name': emp.name,
                    'overtime_hours': emp.overtime_hours_month
                } for emp in top_overtime if emp.overtime_hours_month > 0
            ]
        }