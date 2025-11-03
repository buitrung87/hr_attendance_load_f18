# -*- coding: utf-8 -*-

import base64
import csv
import io
import logging
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ManualImportWizard(models.TransientModel):
    _name = 'manual.import.wizard'
    _description = 'Manual Attendance Import Wizard'

    name = fields.Char('Import Name', required=True, default=lambda self: _('Manual Import %s') % fields.Datetime.now().strftime('%Y-%m-%d %H:%M'))
    csv_file = fields.Binary('CSV File', required=True, help="Upload CSV file with attendance data")
    csv_filename = fields.Char('Filename')
    date_from = fields.Date('Date From', required=True, default=fields.Date.today)
    date_to = fields.Date('Date To', required=True, default=fields.Date.today)
    
    # CSV Format Options
    csv_format = fields.Selection([
        ('standard', 'Standard Format (employee_code, check_in, check_out)'),
        ('f18_export', 'F18 Export Format (user_id, checkin_time, checkout_time)'),
        ('custom', 'Custom Format')
    ], string='CSV Format', default='standard', required=True)
    
    # Custom format fields
    employee_column = fields.Integer('Employee Code Column', default=1, help="Column number for employee code (1-based)")
    checkin_column = fields.Integer('Check-in Column', default=2, help="Column number for check-in time (1-based)")
    checkout_column = fields.Integer('Check-out Column', default=3, help="Column number for check-out time (1-based)")
    has_header = fields.Boolean('Has Header Row', default=True)
    date_format = fields.Char('Date Format', default='%Y-%m-%d %H:%M:%S', help="Python date format string")
    
    # Preview and validation
    preview_data = fields.Text('Preview Data', readonly=True)
    validation_results = fields.Text('Validation Results', readonly=True)
    total_rows = fields.Integer('Total Rows', readonly=True)
    valid_rows = fields.Integer('Valid Rows', readonly=True)
    invalid_rows = fields.Integer('Invalid Rows', readonly=True)
    
    # Processing options
    skip_existing = fields.Boolean('Skip Existing Records', default=True, help="Skip records that already exist")
    auto_create_employees = fields.Boolean('Auto Create Employees', default=False, help="Automatically create missing employees")
    validate_only = fields.Boolean('Validate Only', default=False, help="Only validate data without importing")
    
    state = fields.Selection([
        ('upload', 'Upload File'),
        ('preview', 'Preview & Validate'),
        ('import', 'Import Data')
    ], default='upload', string='State')

    @api.onchange('csv_file', 'csv_format', 'employee_column', 'checkin_column', 'checkout_column', 'has_header', 'date_format')
    def _onchange_csv_file(self):
        """Preview CSV data when file or format changes"""
        if self.csv_file:
            self._preview_csv_data()

    def _preview_csv_data(self):
        """Preview and validate CSV data"""
        if not self.csv_file:
            return
            
        try:
            # Decode CSV file
            csv_data = base64.b64decode(self.csv_file)
            csv_string = csv_data.decode('utf-8')
            csv_reader = csv.reader(io.StringIO(csv_string))
            
            rows = list(csv_reader)
            if not rows:
                self.preview_data = "No data found in CSV file"
                return
                
            # Skip header if specified
            data_rows = rows[1:] if self.has_header else rows
            
            # Preview first 10 rows
            preview_lines = []
            if self.has_header and rows:
                preview_lines.append("HEADER: " + ", ".join(rows[0]))
                preview_lines.append("-" * 50)
            
            for i, row in enumerate(data_rows[:10]):
                preview_lines.append(f"Row {i+1}: {', '.join(row)}")
                
            if len(data_rows) > 10:
                preview_lines.append(f"... and {len(data_rows) - 10} more rows")
                
            self.preview_data = "\n".join(preview_lines)
            self.total_rows = len(data_rows)
            
            # Validate data
            self._validate_csv_data(data_rows)
            
        except Exception as e:
            self.preview_data = f"Error reading CSV file: {str(e)}"
            self.validation_results = str(e)

    def _validate_csv_data(self, data_rows):
        """Validate CSV data and show results"""
        validation_messages = []
        valid_count = 0
        invalid_count = 0
        
        # Get column indices based on format
        if self.csv_format == 'standard':
            emp_col, checkin_col, checkout_col = 0, 1, 2
        elif self.csv_format == 'f18_export':
            emp_col, checkin_col, checkout_col = 0, 1, 2
        else:  # custom
            emp_col = self.employee_column - 1
            checkin_col = self.checkin_column - 1
            checkout_col = self.checkout_column - 1
            
        for i, row in enumerate(data_rows[:100]):  # Validate first 100 rows
            row_errors = []
            
            # Check row length
            max_col = max(emp_col, checkin_col, checkout_col)
            if len(row) <= max_col:
                row_errors.append(f"Row {i+1}: Not enough columns (expected at least {max_col + 1})")
                invalid_count += 1
                continue
                
            # Validate employee code
            employee_code = row[emp_col].strip()
            if not employee_code:
                row_errors.append(f"Row {i+1}: Empty employee code")
            else:
                # Check if employee exists
                employee = self.env['hr.employee'].search([
                    '|', ('employee_number', '=', employee_code),
                    ('rfid_card_code', '=', employee_code)
                ], limit=1)
                if not employee and not self.auto_create_employees:
                    row_errors.append(f"Row {i+1}: Employee '{employee_code}' not found")
                    
            # Validate check-in time
            checkin_str = row[checkin_col].strip()
            if not checkin_str:
                row_errors.append(f"Row {i+1}: Empty check-in time")
            else:
                try:
                    checkin_time = datetime.strptime(checkin_str, self.date_format)
                    # Check date range
                    if not (self.date_from <= checkin_time.date() <= self.date_to):
                        row_errors.append(f"Row {i+1}: Check-in date outside range")
                except ValueError:
                    row_errors.append(f"Row {i+1}: Invalid check-in time format")
                    
            # Validate check-out time (optional)
            checkout_str = row[checkout_col].strip() if len(row) > checkout_col else ''
            if checkout_str:
                try:
                    checkout_time = datetime.strptime(checkout_str, self.date_format)
                    if checkin_str:
                        try:
                            checkin_time = datetime.strptime(checkin_str, self.date_format)
                            if checkout_time <= checkin_time:
                                row_errors.append(f"Row {i+1}: Check-out time must be after check-in")
                        except ValueError:
                            pass  # Already reported checkin error
                except ValueError:
                    row_errors.append(f"Row {i+1}: Invalid check-out time format")
                    
            if row_errors:
                validation_messages.extend(row_errors)
                invalid_count += 1
            else:
                valid_count += 1
                
        # Check for existing records if skip_existing is enabled
        if self.skip_existing:
            existing_count = 0
            for i, row in enumerate(data_rows[:50]):  # Check first 50 for performance
                if len(row) > max(emp_col, checkin_col):
                    employee_code = row[emp_col].strip()
                    checkin_str = row[checkin_col].strip()
                    try:
                        checkin_time = datetime.strptime(checkin_str, self.date_format)
                        employee = self.env['hr.employee'].search([
                            '|', ('employee_number', '=', employee_code),
                            ('rfid_card_code', '=', employee_code)
                        ], limit=1)
                        if employee:
                            existing = self.env['hr.attendance'].search([
                                ('employee_id', '=', employee.id),
                                ('check_in', '>=', checkin_time.replace(second=0, microsecond=0)),
                                ('check_in', '<=', checkin_time.replace(second=59, microsecond=999999))
                            ], limit=1)
                            if existing:
                                existing_count += 1
                    except (ValueError, IndexError):
                        pass
                        
            if existing_count > 0:
                validation_messages.append(f"\nFound {existing_count} existing records (will be skipped)")
        
        self.valid_rows = valid_count
        self.invalid_rows = invalid_count
        
        if validation_messages:
            self.validation_results = "\n".join(validation_messages[:20])  # Show first 20 errors
            if len(validation_messages) > 20:
                self.validation_results += f"\n... and {len(validation_messages) - 20} more validation errors"
        else:
            self.validation_results = "All rows are valid!"

    def action_preview(self):
        """Move to preview step"""
        if not self.csv_file:
            raise UserError(_("Please upload a CSV file first."))
            
        self._preview_csv_data()
        self.state = 'preview'
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'manual.import.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def action_import(self):
        """Import the CSV data"""
        if self.validate_only:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Validation Complete'),
                    'message': f'Validation completed. {self.valid_rows} valid rows, {self.invalid_rows} invalid rows.',
                    'type': 'success',
                }
            }
            
        if self.invalid_rows > 0 and not self.env.context.get('force_import'):
            raise UserError(_(
                "There are %d invalid rows. Please fix the errors or use 'Force Import' to skip invalid rows."
            ) % self.invalid_rows)
            
        return self._process_import()

    def action_force_import(self):
        """Force import even with invalid rows"""
        return self.with_context(force_import=True)._process_import()

    def _process_import(self):
        """Process the actual import"""
        if not self.csv_file:
            raise UserError(_("No CSV file to import."))
            
        try:
            # Create import record
            import_record = self.env['attendance.import'].create({
                'name': self.name,
                'import_type': 'csv',
                'csv_file': self.csv_file,
                'csv_filename': self.csv_filename,
                'import_date': fields.Datetime.now(),
                'auto_import': False,
            })
            
            # Decode and process CSV
            csv_data = base64.b64decode(self.csv_file)
            csv_string = csv_data.decode('utf-8')
            csv_reader = csv.reader(io.StringIO(csv_string))
            
            rows = list(csv_reader)
            data_rows = rows[1:] if self.has_header else rows
            
            # Get column indices
            if self.csv_format == 'standard':
                emp_col, checkin_col, checkout_col = 0, 1, 2
            elif self.csv_format == 'f18_export':
                emp_col, checkin_col, checkout_col = 0, 1, 2
            else:  # custom
                emp_col = self.employee_column - 1
                checkin_col = self.checkin_column - 1
                checkout_col = self.checkout_column - 1
                
            import_lines = []
            processed_count = 0
            failed_count = 0
            
            for i, row in enumerate(data_rows):
                try:
                    if len(row) <= max(emp_col, checkin_col):
                        continue
                        
                    employee_code = row[emp_col].strip()
                    checkin_str = row[checkin_col].strip()
                    checkout_str = row[checkout_col].strip() if len(row) > checkout_col else ''
                    
                    if not employee_code or not checkin_str:
                        continue
                        
                    # Parse times
                    checkin_time = datetime.strptime(checkin_str, self.date_format)
                    checkout_time = None
                    if checkout_str:
                        checkout_time = datetime.strptime(checkout_str, self.date_format)
                        
                    # Find or create employee
                    employee = self.env['hr.employee'].search([
                        '|', ('employee_number', '=', employee_code),
                        ('rfid_card_code', '=', employee_code)
                    ], limit=1)
                    
                    if not employee and self.auto_create_employees:
                        employee = self.env['hr.employee'].create({
                            'name': f'Employee {employee_code}',
                            'employee_number': employee_code,
                            'rfid_card_code': employee_code,
                        })
                        
                    # Check date range
                    if not (self.date_from <= checkin_time.date() <= self.date_to):
                        continue
                        
                    # Calculate worked hours
                    worked_hours = 0
                    if checkout_time:
                        worked_hours = (checkout_time - checkin_time).total_seconds() / 3600
                        
                    # Create import line
                    line_vals = {
                        'import_id': import_record.id,
                        'employee_code': employee_code,
                        'employee_id': employee.id if employee else False,
                        'check_in': checkin_time,
                        'check_out': checkout_time,
                        'worked_hours': worked_hours,
                        'raw_data': ','.join(row),
                        'state': 'draft',
                    }
                    
                    if not employee:
                        line_vals.update({
                            'state': 'failed',
                            'error_message': f'Employee {employee_code} not found'
                        })
                        failed_count += 1
                    else:
                        processed_count += 1
                        
                    import_lines.append((0, 0, line_vals))
                    
                except Exception as e:
                    failed_count += 1
                    import_lines.append((0, 0, {
                        'import_id': import_record.id,
                        'employee_code': employee_code if 'employee_code' in locals() else 'Unknown',
                        'raw_data': ','.join(row),
                        'state': 'failed',
                        'error_message': str(e),
                    }))
                    
            # Update import record
            import_record.write({
                'line_ids': import_lines,
                'total_records': len(data_rows),
                'processed_records': processed_count,
                'failed_records': failed_count,
                'state': 'draft',
            })
            
            # Process the import
            import_record.action_process_import()
            
            self.state = 'import'
            
            return {
                'type': 'ir.actions.act_window',
                'name': _('Import Result'),
                'res_model': 'attendance.import',
                'view_mode': 'form',
                'res_id': import_record.id,
                'target': 'current',
            }
            
        except Exception as e:
            _logger.error("Error during manual import: %s", str(e))
            raise UserError(_("Import failed: %s") % str(e))

    def action_back(self):
        """Go back to previous step"""
        if self.state == 'preview':
            self.state = 'upload'
        elif self.state == 'import':
            self.state = 'preview'
            
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'manual.import.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def action_download_template(self):
        """Download CSV template"""
        if self.csv_format == 'standard':
            headers = ['employee_code', 'check_in', 'check_out']
            sample_data = [
                ['EMP001', '2024-01-15 08:00:00', '2024-01-15 17:00:00'],
                ['EMP002', '2024-01-15 08:30:00', '2024-01-15 17:30:00'],
            ]
        elif self.csv_format == 'f18_export':
            headers = ['user_id', 'checkin_time', 'checkout_time']
            sample_data = [
                ['1', '2024-01-15 08:00:00', '2024-01-15 17:00:00'],
                ['2', '2024-01-15 08:30:00', '2024-01-15 17:30:00'],
            ]
        else:
            headers = ['column1', 'column2', 'column3']
            sample_data = [
                ['data1', 'data2', 'data3'],
                ['data4', 'data5', 'data6'],
            ]
            
        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(sample_data)
        csv_content = output.getvalue()
        
        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': f'attendance_import_template_{self.csv_format}.csv',
            'type': 'binary',
            'datas': base64.b64encode(csv_content.encode('utf-8')),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'text/csv',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }