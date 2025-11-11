# -*- coding: utf-8 -*-
{
    'name': 'HR Attendance Load F18',
    'version': '18.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Enhanced attendance management with F18 integration, overtime calculation, and leave deduction',
    'description': """
HR Attendance Enhanced with F18 Integration
==========================================

This module extends the standard Odoo attendance functionality with:

* **F18 Machine Integration**: Automatic import from Ronald Jack F18 attendance machines
* **Enhanced Attendance Processing**: Automatic detection of late arrivals, early departures, and missing check-outs
* **Overtime Calculation**: Automatic calculation of overtime hours with different rates for weekdays, weekends, and holidays
* **Leave Deduction**: Automatic deduction of annual leave for late arrivals and early departures
* **Manual Import**: CSV import wizard for manual attendance data upload
* **Comprehensive Reporting**: Dashboard and reports for attendance analytics
* **REST API**: External integration endpoints for attendance data
* **Security**: Role-based access control with three user levels

Key Features:
* Automatic F18 machine data import via TCP/IP
* CSV import with data validation and preview
* Overtime calculation with approval workflow
* Leave balance integration and automatic deductions
* Color-coded attendance status indicators
* Comprehensive dashboard and reporting
* REST API for external system integration
* Multi-level security and access control
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'hr',
        'hr_attendance',
        'hr_holidays',
        'resource',
        'mail',
        'web',
    ],
    # External dependencies are optional - F18 integration requires pyzk, Excel export requires xlsxwriter
    # 'external_dependencies': {
    #     'python': ['pyzk', 'xlsxwriter'],
    # },
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/cron.xml',
        'data/ir_cron.xml',
        'data/hide_attendance_menu.xml',
        'data/leave_summary_cron.xml',
        
        # Views
        'views/attendance_import_views.xml',
        'views/attendance_device_views.xml',
        'views/overtime_views.xml',
        'views/leave_summary_views.xml',
        'views/hr_attendance_views.xml',
        'views/attendance_enhanced_config_views.xml',
        'views/attendance_dashboard_views.xml',
        
        # Wizards
        'wizard/manual_import_wizard_views.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'sequence': 95,
    'images': ['static/description/icon.png'],
}