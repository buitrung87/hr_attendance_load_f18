# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta
from odoo import models, fields, api, _, tools
from odoo.tools import float_round

_logger = logging.getLogger(__name__)


class AttendanceDashboard(models.Model):
    _name = 'attendance.dashboard'
    _description = 'Attendance Dashboard'
    _auto = False
    _rec_name = 'employee_id'

    # Employee information
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    job_id = fields.Many2one('hr.job', string='Job Position', readonly=True)
    
    # Date information
    date = fields.Date(string='Date', readonly=True)
    month = fields.Char(string='Month', readonly=True)
    year = fields.Integer(string='Year', readonly=True)
    week = fields.Integer(string='Week', readonly=True)
    weekday = fields.Integer(string='Weekday', readonly=True)
    
    # Attendance data
    check_in = fields.Datetime(string='Check In', readonly=True)
    check_out = fields.Datetime(string='Check Out', readonly=True)
    worked_hours = fields.Float(string='Worked Hours', readonly=True, digits=(16, 2))
    scheduled_hours = fields.Float(string='Scheduled Hours', readonly=True, digits=(16, 2))
    
    # Status and deviations
    attendance_status = fields.Selection([
        ('normal', 'Normal'),
        ('late_in', 'Late Check-In'),
        ('early_out', 'Early Check-Out'),
        ('missing_out', 'Missing Check-Out'),
        ('missing_in', 'Missing Check-In'),
        ('overtime', 'Overtime'),
        ('both_issues', 'Late In & Early Out')
    ], string='Status', readonly=True)
    
    late_minutes = fields.Float(string='Late Minutes', readonly=True, digits=(16, 2))
    early_minutes = fields.Float(string='Early Minutes', readonly=True, digits=(16, 2))
    
    # Overtime information
    overtime_hours = fields.Float(string='Overtime Hours', readonly=True, digits=(16, 2))
    overtime_type = fields.Selection([
        ('weekday', 'Weekday'),
        ('weekend', 'Weekend'),
        ('holiday', 'Holiday')
    ], string='Overtime Type', readonly=True)
    
    # Leave deduction information
    deduction_days = fields.Float(string='Deduction Days', readonly=True, digits=(16, 3))
    deduction_type = fields.Selection([
        ('late_in', 'Late Check-In'),
        ('early_out', 'Early Check-Out'),
        ('both', 'Both Late In and Early Out')
    ], string='Deduction Type', readonly=True)
    
    # Aggregated fields for grouping
    total_worked_hours = fields.Float(string='Total Worked Hours', readonly=True, digits=(16, 2))
    total_overtime_hours = fields.Float(string='Total Overtime Hours', readonly=True, digits=(16, 2))
    total_deduction_days = fields.Float(string='Total Deduction Days', readonly=True, digits=(16, 3))
    attendance_count = fields.Integer(string='Attendance Count', readonly=True)
    late_count = fields.Integer(string='Late Count', readonly=True)
    early_count = fields.Integer(string='Early Count', readonly=True)

    def init(self):
        """Create the view"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    att.employee_id,
                    emp.department_id,
                    emp.job_id,
                    att.check_in::date AS date,
                    TO_CHAR(att.check_in, 'YYYY-MM') AS month,
                    EXTRACT(year FROM att.check_in) AS year,
                    EXTRACT(week FROM att.check_in) AS week,
                    EXTRACT(dow FROM att.check_in) AS weekday,
                    att.check_in,
                    att.check_out,
                    att.worked_hours,
                    att.scheduled_hours,
                    att.attendance_status,
                    att.late_minutes,
                    att.early_minutes,
                    ot.overtime_hours,
                    ot.overtime_type,
                    ld.deduction_days,
                    ld.deduction_type,
                    att.worked_hours AS total_worked_hours,
                    COALESCE(ot.overtime_hours, 0) AS total_overtime_hours,
                    COALESCE(ld.deduction_days, 0) AS total_deduction_days,
                    1 AS attendance_count,
                    CASE WHEN att.attendance_status IN ('late_in', 'both_issues') THEN 1 ELSE 0 END AS late_count,
                    CASE WHEN att.attendance_status IN ('early_out', 'both_issues') THEN 1 ELSE 0 END AS early_count
                FROM hr_attendance att
                LEFT JOIN hr_employee emp ON att.employee_id = emp.id
                LEFT JOIN hr_overtime ot ON att.overtime_id = ot.id
                LEFT JOIN leave_deduction ld ON att.leave_deduction_id = ld.id
                WHERE att.check_in IS NOT NULL
            )
        """ % self._table)


    def action_view_attendance(self):
        """Open hr.attendance records for the current employee and date.

        Called from the kanban button in attendance_dashboard_views.xml.
        """
        self.ensure_one()
        start_dt = datetime.combine(self.date, datetime.min.time())
        end_dt = start_dt + timedelta(days=1)

        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('check_in', '>=', fields.Datetime.to_string(start_dt)),
            ('check_in', '<', fields.Datetime.to_string(end_dt)),
        ]

        return {
            'name': _('Attendances'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.attendance',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
        }

class AttendanceSummaryReport(models.TransientModel):
    _name = 'attendance.summary.report'
    _description = 'Attendance Summary Report'

    # Filter fields
    date_from = fields.Date(
        string='Date From',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1)
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        default=fields.Date.today
    )
    employee_ids = fields.Many2many(
        'hr.employee',
        string='Employees',
        help='Leave empty to include all employees'
    )
    department_ids = fields.Many2many(
        'hr.department',
        string='Departments',
        help='Leave empty to include all departments'
    )
    
    # Report type
    report_type = fields.Selection([
        ('summary', 'Summary Report'),
        ('detailed', 'Detailed Report'),
        ('overtime', 'Overtime Report'),
        ('deductions', 'Leave Deductions Report'),
        ('perfect_attendance', 'Perfect Attendance Report')
    ], string='Report Type', default='summary', required=True)
    
    # Group by options
    group_by = fields.Selection([
        ('employee', 'Employee'),
        ('department', 'Department'),
        ('month', 'Month'),
        ('week', 'Week')
    ], string='Group By', default='employee')

    # Additional options referenced in the view
    include_weekends = fields.Boolean(string='Include Weekends', default=False)
    include_holidays = fields.Boolean(string='Include Holidays', default=False)

    def action_generate_report(self):
        """Generate the attendance report"""
        domain = self._get_domain()
        
        if self.report_type == 'summary':
            return self._generate_summary_report(domain)
        elif self.report_type == 'detailed':
            return self._generate_detailed_report(domain)
        elif self.report_type == 'overtime':
            return self._generate_overtime_report(domain)
        elif self.report_type == 'deductions':
            return self._generate_deductions_report(domain)
        elif self.report_type == 'perfect_attendance':
            return self._generate_perfect_attendance_report(domain)

    def _get_domain(self):
        """Build domain for filtering"""
        domain = [
            ('check_in', '>=', self.date_from),
            ('check_in', '<=', self.date_to)
        ]
        
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        
        if self.department_ids:
            domain.append(('employee_id.department_id', 'in', self.department_ids.ids))
        
        return domain

    def _generate_summary_report(self, domain):
        """Generate summary report"""
        attendances = self.env['hr.attendance'].search(domain)
        
        # Group data
        if self.group_by == 'employee':
            grouped_data = self._group_by_employee(attendances)
        elif self.group_by == 'department':
            grouped_data = self._group_by_department(attendances)
        elif self.group_by == 'month':
            grouped_data = self._group_by_month(attendances)
        else:  # week
            grouped_data = self._group_by_week(attendances)
        
        # Create temporary records for tree view
        summary_records = []
        for key, data in grouped_data.items():
            summary_records.append({
                'name': key,
                'total_attendances': data['count'],
                'total_worked_hours': data['worked_hours'],
                'total_overtime_hours': data['overtime_hours'],
                'total_late_count': data['late_count'],
                'total_early_count': data['early_count'],
                'total_deduction_days': data['deduction_days'],
                'perfect_attendance': (data['late_count'] == 0 and data['early_count'] == 0 and (data.get('deduction_days') or 0.0) == 0.0)
            })
        
        # Store in context for the view
        context = dict(self.env.context)
        context.update({
            'summary_data': summary_records,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'group_by': self.group_by
        })
        
        return {
            'name': _('Attendance Summary Report'),
            'type': 'ir.actions.act_window',
            'res_model': 'attendance.summary.view',
            'view_mode': 'list',
            'target': 'current',
            'context': context
        }

    def _group_by_employee(self, attendances):
        """Group attendances by employee"""
        grouped = {}
        for att in attendances:
            key = att.employee_id.name
            if key not in grouped:
                grouped[key] = {
                    'count': 0,
                    'worked_hours': 0.0,
                    'overtime_hours': 0.0,
                    'late_count': 0,
                    'early_count': 0,
                    'deduction_days': 0.0
                }
            
            grouped[key]['count'] += 1
            grouped[key]['worked_hours'] += att.worked_hours or 0.0
            grouped[key]['overtime_hours'] += att.overtime_hours or 0.0
            grouped[key]['deduction_days'] += att.deduction_days or 0.0
            
            if att.attendance_status in ['late_in', 'both_issues']:
                grouped[key]['late_count'] += 1
            if att.attendance_status in ['early_out', 'both_issues']:
                grouped[key]['early_count'] += 1
        
        return grouped

    def _group_by_department(self, attendances):
        """Group attendances by department"""
        grouped = {}
        for att in attendances:
            key = att.employee_id.department_id.name if att.employee_id.department_id else _('No Department')
            if key not in grouped:
                grouped[key] = {
                    'count': 0,
                    'worked_hours': 0.0,
                    'overtime_hours': 0.0,
                    'late_count': 0,
                    'early_count': 0,
                    'deduction_days': 0.0
                }
            
            grouped[key]['count'] += 1
            grouped[key]['worked_hours'] += att.worked_hours or 0.0
            grouped[key]['overtime_hours'] += att.overtime_hours or 0.0
            grouped[key]['deduction_days'] += att.deduction_days or 0.0
            
            if att.attendance_status in ['late_in', 'both_issues']:
                grouped[key]['late_count'] += 1
            if att.attendance_status in ['early_out', 'both_issues']:
                grouped[key]['early_count'] += 1
        
        return grouped

    def _group_by_month(self, attendances):
        """Group attendances by month"""
        grouped = {}
        for att in attendances:
            key = att.check_in.strftime('%Y-%m')
            if key not in grouped:
                grouped[key] = {
                    'count': 0,
                    'worked_hours': 0.0,
                    'overtime_hours': 0.0,
                    'late_count': 0,
                    'early_count': 0,
                    'deduction_days': 0.0
                }
            
            grouped[key]['count'] += 1
            grouped[key]['worked_hours'] += att.worked_hours or 0.0
            grouped[key]['overtime_hours'] += att.overtime_hours or 0.0
            grouped[key]['deduction_days'] += att.deduction_days or 0.0
            
            if att.attendance_status in ['late_in', 'both_issues']:
                grouped[key]['late_count'] += 1
            if att.attendance_status in ['early_out', 'both_issues']:
                grouped[key]['early_count'] += 1
        
        return grouped

    def _group_by_week(self, attendances):
        """Group attendances by week"""
        grouped = {}
        for att in attendances:
            week_start = att.check_in.date() - timedelta(days=att.check_in.weekday())
            key = f"Week {week_start.strftime('%Y-%m-%d')}"
            if key not in grouped:
                grouped[key] = {
                    'count': 0,
                    'worked_hours': 0.0,
                    'overtime_hours': 0.0,
                    'late_count': 0,
                    'early_count': 0,
                    'deduction_days': 0.0
                }
            
            grouped[key]['count'] += 1
            grouped[key]['worked_hours'] += att.worked_hours or 0.0
            grouped[key]['overtime_hours'] += att.overtime_hours or 0.0
            grouped[key]['deduction_days'] += att.deduction_days or 0.0
            
            if att.attendance_status in ['late_in', 'both_issues']:
                grouped[key]['late_count'] += 1
            if att.attendance_status in ['early_out', 'both_issues']:
                grouped[key]['early_count'] += 1
        
        return grouped

    def action_export_excel(self):
        """Export report to Excel"""
        domain = self._get_domain()
        attendances = self.env['hr.attendance'].search(domain)
        
        # Prepare data for Excel export
        data = []
        for att in attendances:
            data.append({
                'Employee': att.employee_id.name,
                'Department': att.employee_id.department_id.name if att.employee_id.department_id else '',
                'Date': att.check_in.date(),
                'Check In': att.check_in.strftime('%H:%M:%S') if att.check_in else '',
                'Check Out': att.check_out.strftime('%H:%M:%S') if att.check_out else '',
                'Worked Hours': att.worked_hours,
                'Scheduled Hours': att.scheduled_hours,
                'Status': dict(att._fields['attendance_status'].selection)[att.attendance_status] if att.attendance_status else '',
                'Late Minutes': att.late_minutes,
                'Early Minutes': att.early_minutes,
                'Overtime Hours': att.overtime_hours or 0.0,
                'Deduction Days': att.deduction_days or 0.0
            })
        
        # Create Excel file using xlsxwriter or openpyxl
        # This would require additional implementation for actual Excel generation
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Export'),
                'message': _('Excel export functionality would be implemented here'),
                'type': 'info',
                'sticky': False,
            }
        }


class AttendanceSummaryView(models.TransientModel):
    _name = 'attendance.summary.view'
    _description = 'Attendance Summary View'

    name = fields.Char(string='Name')
    total_attendances = fields.Integer(string='Total Attendances')
    total_worked_hours = fields.Float(string='Total Worked Hours', digits=(16, 2))
    total_overtime_hours = fields.Float(string='Total Overtime Hours', digits=(16, 2))
    total_late_count = fields.Integer(string='Late Arrivals')
    total_early_count = fields.Integer(string='Early Departures')
    total_deduction_days = fields.Float(string='Total Deduction Days', digits=(16, 3))
    perfect_attendance = fields.Boolean(string='Perfect Attendance')