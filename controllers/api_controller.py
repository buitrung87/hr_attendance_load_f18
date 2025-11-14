# -*- coding: utf-8 -*-

import json
import logging
from datetime import datetime

from odoo import http, fields, _
from odoo.http import request
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class AttendanceEnhancedAPI(http.Controller):
    """REST API Controller for Attendance Enhanced Module"""

    def _authenticate_api_request(self, api_key=None):
        """Authenticate API request using API key or session"""
        if api_key:
            # Check if API key is valid (you can implement your own logic)
            config = request.env['attendance.enhanced.config'].sudo().search([
                ('api_key', '=', api_key),
                ('active', '=', True)
            ], limit=1)
            if not config:
                return False, {'error': 'Invalid API key', 'code': 401}
        elif not request.session.uid:
            return False, {'error': 'Authentication required', 'code': 401}
        
        return True, {}

    def _validate_employee_code(self, employee_code):
        """Validate and find employee by code"""
        if not employee_code:
            return None, {'error': 'Employee code is required', 'code': 400}
            
        allowed_company_ids = request.env.context.get('allowed_company_ids') or request.env.companies.ids
        employee = request.env['hr.employee'].search([
            '|', ('employee_number', '=', employee_code),
            ('rfid_card_code', '=', employee_code),
            ('company_id', 'in', allowed_company_ids)
        ], limit=1)
        
        if not employee:
            return None, {'error': f'Employee {employee_code} not found', 'code': 404}
            
        return employee, {}

    def _parse_datetime(self, datetime_str, field_name):
        """Parse datetime string with multiple format support"""
        if not datetime_str:
            return None, {'error': f'{field_name} is required', 'code': 400}
            
        # Try multiple datetime formats
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%d/%m/%Y %H:%M:%S',
            '%d/%m/%Y %H:%M',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(datetime_str, fmt), {}
            except ValueError:
                continue
                
        return None, {'error': f'Invalid {field_name} format. Use YYYY-MM-DD HH:MM:SS', 'code': 400}

    @http.route('/hr_attendance_load_f18/api/import', type='json', auth='none', methods=['POST'], csrf=False)
    def api_import_attendance(self, **kwargs):
        """
        Import single attendance record via API
        
        Expected JSON payload:
        {
            "employee_code": "EMP001",
            "check_in": "2024-01-15 08:00:00",
            "check_out": "2024-01-15 17:00:00",  # Optional
            "api_key": "your_api_key"  # Optional if using session auth
        }
        """
        try:
            # Get request data
            data = request.jsonrequest or {}
            api_key = data.get('api_key')
            
            # Authenticate request
            auth_success, auth_error = self._authenticate_api_request(api_key)
            if not auth_success:
                return auth_error
                
            # Validate required fields
            employee_code = data.get('employee_code')
            check_in_str = data.get('check_in')
            check_out_str = data.get('check_out')
            
            # Validate employee
            employee, employee_error = self._validate_employee_code(employee_code)
            if not employee:
                return employee_error
                
            # Parse check-in time
            check_in, checkin_error = self._parse_datetime(check_in_str, 'check_in')
            if not check_in:
                return checkin_error
                
            # Parse check-out time (optional)
            check_out = None
            if check_out_str:
                check_out, checkout_error = self._parse_datetime(check_out_str, 'check_out')
                if not check_out:
                    return checkout_error
                    
                # Validate check-out is after check-in
                if check_out <= check_in:
                    return {'error': 'Check-out time must be after check-in time', 'code': 400}
            
            # Check for existing attendance record
            existing = request.env['hr.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', check_in.replace(second=0, microsecond=0)),
                ('check_in', '<=', check_in.replace(second=59, microsecond=999999))
            ], limit=1)
            
            if existing:
                return {
                    'error': f'Attendance record already exists for {employee_code} at {check_in_str}',
                    'code': 409,
                    'existing_id': existing.id
                }
            
            # Create attendance record
            attendance_vals = {
                'employee_id': employee.id,
                'check_in': check_in,
                'check_out': check_out,
                'import_source': 'api',
                'notes': f'Imported via API at {fields.Datetime.now()}'
            }
            
            AttendanceModel = request.env['hr.attendance']
            if 'company_id' in AttendanceModel._fields:
                attendance_vals['company_id'] = employee.company_id.id
            attendance = AttendanceModel.create(attendance_vals)
            
            # Calculate worked hours if check_out is provided
            worked_hours = 0
            if check_out:
                worked_hours = (check_out - check_in).total_seconds() / 3600
            
            _logger.info("Attendance imported via API: Employee %s, Check-in %s", employee_code, check_in_str)
            
            return {
                'success': True,
                'message': 'Attendance record created successfully',
                'data': {
                    'id': attendance.id,
                    'employee_code': employee_code,
                    'employee_name': employee.name,
                    'check_in': check_in.strftime('%Y-%m-%d %H:%M:%S'),
                    'check_out': check_out.strftime('%Y-%m-%d %H:%M:%S') if check_out else None,
                    'worked_hours': round(worked_hours, 2),
                    'status': attendance.attendance_status
                }
            }
            
        except Exception as e:
            _logger.error("API import error: %s", str(e))
            return {'error': f'Internal server error: {str(e)}', 'code': 500}

    @http.route('/hr_attendance_load_f18/api/bulk_import', type='json', auth='none', methods=['POST'], csrf=False)
    def api_bulk_import_attendance(self, **kwargs):
        """
        Import multiple attendance records via API
        
        Expected JSON payload:
        {
            "records": [
                {
                    "employee_code": "EMP001",
                    "check_in": "2024-01-15 08:00:00",
                    "check_out": "2024-01-15 17:00:00"
                },
                {
                    "employee_code": "EMP002",
                    "check_in": "2024-01-15 08:30:00",
                    "check_out": "2024-01-15 17:30:00"
                }
            ],
            "api_key": "your_api_key"
        }
        """
        try:
            # Get request data
            data = request.jsonrequest or {}
            api_key = data.get('api_key')
            records = data.get('records', [])
            
            # Authenticate request
            auth_success, auth_error = self._authenticate_api_request(api_key)
            if not auth_success:
                return auth_error
                
            if not records:
                return {'error': 'No records provided', 'code': 400}
                
            if len(records) > 1000:
                return {'error': 'Maximum 1000 records allowed per request', 'code': 400}
            
            # Process records
            results = {
                'success': [],
                'errors': [],
                'total': len(records),
                'processed': 0,
                'failed': 0
            }
            
            for i, record in enumerate(records):
                try:
                    employee_code = record.get('employee_code')
                    check_in_str = record.get('check_in')
                    check_out_str = record.get('check_out')
                    
                    # Validate employee
                    employee, employee_error = self._validate_employee_code(employee_code)
                    if not employee:
                        results['errors'].append({
                            'index': i,
                            'employee_code': employee_code,
                            'error': employee_error['error']
                        })
                        results['failed'] += 1
                        continue
                        
                    # Parse times
                    check_in, checkin_error = self._parse_datetime(check_in_str, 'check_in')
                    if not check_in:
                        results['errors'].append({
                            'index': i,
                            'employee_code': employee_code,
                            'error': checkin_error['error']
                        })
                        results['failed'] += 1
                        continue
                        
                    check_out = None
                    if check_out_str:
                        check_out, checkout_error = self._parse_datetime(check_out_str, 'check_out')
                        if not check_out:
                            results['errors'].append({
                                'index': i,
                                'employee_code': employee_code,
                                'error': checkout_error['error']
                            })
                            results['failed'] += 1
                            continue
                            
                        if check_out <= check_in:
                            results['errors'].append({
                                'index': i,
                                'employee_code': employee_code,
                                'error': 'Check-out time must be after check-in time'
                            })
                            results['failed'] += 1
                            continue
                    
                    # Check for existing record
                    existing = request.env['hr.attendance'].search([
                        ('employee_id', '=', employee.id),
                        ('check_in', '>=', check_in.replace(second=0, microsecond=0)),
                        ('check_in', '<=', check_in.replace(second=59, microsecond=999999))
                    ], limit=1)
                    
                    if existing:
                        results['errors'].append({
                            'index': i,
                            'employee_code': employee_code,
                            'error': f'Attendance record already exists at {check_in_str}'
                        })
                        results['failed'] += 1
                        continue
                    
                    # Create attendance record
                    attendance_vals = {
                        'employee_id': employee.id,
                        'check_in': check_in,
                        'check_out': check_out,
                        'import_source': 'api_bulk',
                        'notes': f'Bulk imported via API at {fields.Datetime.now()}'
                    }
                    
                    AttendanceModel = request.env['hr.attendance']
                    if 'company_id' in AttendanceModel._fields:
                        attendance_vals['company_id'] = employee.company_id.id
                    attendance = AttendanceModel.create(attendance_vals)
                    
                    worked_hours = 0
                    if check_out:
                        worked_hours = (check_out - check_in).total_seconds() / 3600
                    
                    results['success'].append({
                        'index': i,
                        'id': attendance.id,
                        'employee_code': employee_code,
                        'employee_name': employee.name,
                        'check_in': check_in.strftime('%Y-%m-%d %H:%M:%S'),
                        'check_out': check_out.strftime('%Y-%m-%d %H:%M:%S') if check_out else None,
                        'worked_hours': round(worked_hours, 2)
                    })
                    results['processed'] += 1
                    
                except Exception as e:
                    results['errors'].append({
                        'index': i,
                        'employee_code': record.get('employee_code', 'Unknown'),
                        'error': str(e)
                    })
                    results['failed'] += 1
            
            _logger.info("Bulk attendance import via API: %d processed, %d failed", 
                        results['processed'], results['failed'])
            
            return {
                'success': True,
                'message': f'Bulk import completed: {results["processed"]} processed, {results["failed"]} failed',
                'results': results
            }
            
        except Exception as e:
            _logger.error("API bulk import error: %s", str(e))
            return {'error': f'Internal server error: {str(e)}', 'code': 500}

    @http.route('/hr_attendance_load_f18/api/employee/<string:employee_code>/attendance', 
                type='json', auth='none', methods=['GET'], csrf=False)
    def api_get_employee_attendance(self, employee_code, **kwargs):
        """
        Get attendance records for specific employee
        
        Query parameters:
        - date_from: Start date (YYYY-MM-DD)
        - date_to: End date (YYYY-MM-DD)
        - limit: Maximum records to return (default: 100)
        """
        try:
            # Get request data
            data = request.jsonrequest or {}
            api_key = data.get('api_key')
            
            # Authenticate request
            auth_success, auth_error = self._authenticate_api_request(api_key)
            if not auth_success:
                return auth_error
                
            # Validate employee
            employee, employee_error = self._validate_employee_code(employee_code)
            if not employee:
                return employee_error
            
            # Parse query parameters
            date_from_str = data.get('date_from')
            date_to_str = data.get('date_to')
            limit = min(int(data.get('limit', 100)), 1000)  # Max 1000 records
            
            # Build domain
            domain = [('employee_id', '=', employee.id)]
            
            if date_from_str:
                try:
                    date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
                    domain.append(('check_in', '>=', fields.Datetime.to_string(date_from)))
                except ValueError:
                    return {'error': 'Invalid date_from format. Use YYYY-MM-DD', 'code': 400}
                    
            if date_to_str:
                try:
                    date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
                    domain.append(('check_in', '<=', fields.Datetime.to_string(date_to.replace(hour=23, minute=59, second=59))))
                except ValueError:
                    return {'error': 'Invalid date_to format. Use YYYY-MM-DD', 'code': 400}
            
            # Get attendance records
            allowed_company_ids = request.env.context.get('allowed_company_ids') or request.env.companies.ids
            domain = domain + [('employee_id.company_id', 'in', allowed_company_ids)]
            attendances = request.env['hr.attendance'].search(
                domain, order='check_in desc', limit=limit
            )
            
            # Format response
            records = []
            for attendance in attendances:
                worked_hours = 0
                if attendance.check_out:
                    worked_hours = (attendance.check_out - attendance.check_in).total_seconds() / 3600
                    
                records.append({
                    'id': attendance.id,
                    'check_in': attendance.check_in.strftime('%Y-%m-%d %H:%M:%S'),
                    'check_out': attendance.check_out.strftime('%Y-%m-%d %H:%M:%S') if attendance.check_out else None,
                    'worked_hours': round(worked_hours, 2),
                    'status': attendance.attendance_status,
                    'late_minutes': attendance.late_minutes,
                    'early_minutes': attendance.early_minutes,
                    'import_source': attendance.import_source,
                    'notes': attendance.notes
                })
            
            return {
                'success': True,
                'employee': {
                    'code': employee_code,
                    'name': employee.name,
                    'department': employee.department_id.name if employee.department_id else None
                },
                'records': records,
                'total': len(records)
            }
            
        except Exception as e:
            _logger.error("API get attendance error: %s", str(e))
            return {'error': f'Internal server error: {str(e)}', 'code': 500}

    @http.route('/hr_attendance_load_f18/api/status', type='json', auth='none', methods=['GET'], csrf=False)
    def api_get_status(self, **kwargs):
        """Get API status and configuration info"""
        try:
            data = request.jsonrequest or {}
            api_key = data.get('api_key')
            
            # Authenticate request
            auth_success, auth_error = self._authenticate_api_request(api_key)
            if not auth_success:
                return auth_error
            
            # Get configuration (business parameters only)
            config_dict = request.env['attendance.enhanced.config'].sudo().get_config()
            # Device status: count active auto-pull devices
            devices = request.env['attendance.device'].sudo().search([('active', '=', True)])
            auto_pull_devices = devices.filtered(lambda d: d.auto_pull)

            return {
                'success': True,
                'status': 'active',
                'version': '1.0',
                'module': 'hr_attendance_load_f18',
                'configuration': {
                    'auto_import_enabled': bool(config_dict.get('auto_import_enabled', False)),
                    'devices_active': len(devices),
                    'devices_auto_pull': len(auto_pull_devices),
                    'standard_working_hours': float(config_dict.get('standard_working_hours', 8.0)),
                    'overtime_threshold': float(config_dict.get('overtime_threshold', 8.0))
                },
                'endpoints': [
                    '/hr_attendance_load_f18/api/import',
                    '/hr_attendance_load_f18/api/bulk_import',
                    '/hr_attendance_load_f18/api/employee/<code>/attendance',
                    '/hr_attendance_load_f18/api/status'
                ]
            }
            
        except Exception as e:
            _logger.error("API status error: %s", str(e))
            return {'error': f'Internal server error: {str(e)}', 'code': 500}