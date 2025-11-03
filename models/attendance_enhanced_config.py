# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AttendanceEnhancedConfig(models.TransientModel):
    _name = 'attendance.enhanced.config'
    _description = 'Attendance Enhanced Configuration'
    _inherit = 'res.config.settings'

    # Machine connection configuration removed. Use attendance.device for device management.
    
    # Working Hours Configuration
    standard_working_hours = fields.Float(
        string='Standard Working Hours per Day',
        config_parameter='hr_attendance_load_f18.standard_working_hours',
        default=8.0,
        help='Standard working hours per day for overtime calculation'
    )
    overtime_threshold = fields.Float(
        string='Overtime Threshold (Hours)',
        config_parameter='hr_attendance_load_f18.overtime_threshold',
        default=8.0,
        help='Hours threshold before overtime calculation starts'
    )
    
    # Grace Period Configuration
    grace_period_minutes = fields.Float(
        string='Grace Period (Minutes)',
        config_parameter='hr_attendance_load_f18.grace_period_minutes',
        default=15.0,
        help='Grace period in minutes before late/early deduction starts'
    )
    
    # Overtime Rates
    weekday_overtime_rate = fields.Float(
        string='Weekday Overtime Rate',
        config_parameter='hr_attendance_load_f18.weekday_overtime_rate',
        default=1.5,
        help='Overtime rate multiplier for weekdays'
    )
    weekend_overtime_rate = fields.Float(
        string='Weekend Overtime Rate',
        config_parameter='hr_attendance_load_f18.weekend_overtime_rate',
        default=2.0,
        help='Overtime rate multiplier for weekends'
    )
    holiday_overtime_rate = fields.Float(
        string='Holiday Overtime Rate',
        config_parameter='hr_attendance_load_f18.holiday_overtime_rate',
        default=2.5,
        help='Overtime rate multiplier for holidays'
    )
    
    # Auto Import Configuration
    auto_import_enabled = fields.Boolean(
        string='Enable Auto Import',
        config_parameter='hr_attendance_load_f18.auto_import_enabled',
        default=True,
        help='Enable automatic attendance import from F18 machine'
    )
    auto_import_time = fields.Float(
        string='Auto Import Time',
        config_parameter='hr_attendance_load_f18.auto_import_time',
        default=6.0,
        help='Time of day to run auto import (24-hour format, e.g., 6.0 = 6:00 AM)'
    )
    import_days_back = fields.Integer(
        string='Import Days Back',
        config_parameter='hr_attendance_load_f18.import_days_back',
        default=7,
        help='Number of days back to import attendance data'
    )
    
    # Leave Deduction Configuration
    auto_confirm_deductions = fields.Boolean(
        string='Auto Confirm Deductions',
        config_parameter='hr_attendance_load_f18.auto_confirm_deductions',
        default=False,
        help='Automatically confirm leave deductions for late/early attendance'
    )
    auto_process_deductions = fields.Boolean(
        string='Auto Process Deductions',
        config_parameter='hr_attendance_load_f18.auto_process_deductions',
        default=False,
        help='Automatically process confirmed deductions'
    )
    
    # Notification Configuration
    notify_late_arrivals = fields.Boolean(
        string='Notify Late Arrivals',
        config_parameter='hr_attendance_load_f18.notify_late_arrivals',
        default=True,
        help='Send notifications for late arrivals'
    )
    notify_early_departures = fields.Boolean(
        string='Notify Early Departures',
        config_parameter='hr_attendance_load_f18.notify_early_departures',
        default=True,
        help='Send notifications for early departures'
    )
    notify_missing_checkout = fields.Boolean(
        string='Notify Missing Check-out',
        config_parameter='hr_attendance_load_f18.notify_missing_checkout',
        default=True,
        help='Send notifications for missing check-out'
    )
    
    # CSV Import Configuration
    csv_delimiter = fields.Selection([
        (',', 'Comma (,)'),
        (';', 'Semicolon (;)'),
        ('\t', 'Tab'),
        ('|', 'Pipe (|)')
    ], string='CSV Delimiter',
       config_parameter='hr_attendance_load_f18.csv_delimiter',
       default=',',
       help='Delimiter used in CSV files')
    
    csv_date_format = fields.Selection([
        ('%Y-%m-%d %H:%M:%S', 'YYYY-MM-DD HH:MM:SS'),
        ('%d/%m/%Y %H:%M:%S', 'DD/MM/YYYY HH:MM:SS'),
        ('%m/%d/%Y %H:%M:%S', 'MM/DD/YYYY HH:MM:SS'),
        ('%Y-%m-%d %H:%M', 'YYYY-MM-DD HH:MM'),
        ('%d/%m/%Y %H:%M', 'DD/MM/YYYY HH:MM')
    ], string='CSV Date Format',
       config_parameter='hr_attendance_load_f18.csv_date_format',
       default='%Y-%m-%d %H:%M:%S',
       help='Date format used in CSV files')

    @api.constrains('standard_working_hours', 'overtime_threshold')
    def _check_working_hours(self):
        for record in self:
            if record.standard_working_hours <= 0:
                raise ValidationError(_('Standard working hours must be greater than 0'))
            if record.overtime_threshold <= 0:
                raise ValidationError(_('Overtime threshold must be greater than 0'))

    @api.constrains('grace_period_minutes')
    def _check_grace_period(self):
        for record in self:
            if record.grace_period_minutes < 0:
                raise ValidationError(_('Grace period cannot be negative'))

    @api.constrains('weekday_overtime_rate', 'weekend_overtime_rate', 'holiday_overtime_rate')
    def _check_overtime_rates(self):
        for record in self:
            if record.weekday_overtime_rate < 1.0:
                raise ValidationError(_('Weekday overtime rate must be at least 1.0'))
            if record.weekend_overtime_rate < 1.0:
                raise ValidationError(_('Weekend overtime rate must be at least 1.0'))
            if record.holiday_overtime_rate < 1.0:
                raise ValidationError(_('Holiday overtime rate must be at least 1.0'))

    @api.constrains('auto_import_time')
    def _check_auto_import_time(self):
        for record in self:
            if not (0 <= record.auto_import_time < 24):
                raise ValidationError(_('Auto import time must be between 0 and 24'))

    @api.model
    def get_config(self):
        """Get current configuration values"""
        return {
            'standard_working_hours': float(self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.standard_working_hours', '8.0'
            )),
            'overtime_threshold': float(self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.overtime_threshold', '8.0'
            )),
            'grace_period_minutes': float(self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.grace_period_minutes', '15.0'
            )),
            'weekday_overtime_rate': float(self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.weekday_overtime_rate', '1.5'
            )),
            'weekend_overtime_rate': float(self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.weekend_overtime_rate', '2.0'
            )),
            'holiday_overtime_rate': float(self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.holiday_overtime_rate', '2.5'
            )),
            'auto_import_enabled': self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.auto_import_enabled', 'True'
            ).lower() == 'true',
            'auto_import_time': float(self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.auto_import_time', '6.0'
            )),
            'import_days_back': int(self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.import_days_back', '7'
            )),
            'auto_confirm_deductions': self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.auto_confirm_deductions', 'False'
            ).lower() == 'true',
            'auto_process_deductions': self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.auto_process_deductions', 'False'
            ).lower() == 'true',
            'notify_late_arrivals': self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.notify_late_arrivals', 'True'
            ).lower() == 'true',
            'notify_early_departures': self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.notify_early_departures', 'True'
            ).lower() == 'true',
            'notify_missing_checkout': self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.notify_missing_checkout', 'True'
            ).lower() == 'true',
            'csv_delimiter': self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.csv_delimiter', ','
            ),
            'csv_date_format': self.env['ir.config_parameter'].sudo().get_param(
                'hr_attendance_load_f18.csv_date_format', '%Y-%m-%d %H:%M:%S'
            ),
        }