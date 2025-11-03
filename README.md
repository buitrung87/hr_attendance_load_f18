# HR Attendance Load F18

Enhanced attendance management module for Odoo 18 Community with device-based integration (e.g., F18/ZKTeco), overtime calculation, and leave deduction functionality.

## 🚀 Features

### 📡 Device Integration (F18/ZKTeco)
- **Automatic Import**: Pull attendance from configured devices via TCP/IP
- **Device Management**: Manage devices under Attendance Enhanced → Devices
- **Employee Matching**: Automatic matching via RFID cards or employee numbers
- **Scheduled Import**: Cron-driven auto pull when enabled on devices

### 📊 Enhanced Attendance Processing
- **Status Detection**: Automatic detection of attendance anomalies
- **Color Coding**: Visual status indicators in list views
  - ✅ Normal attendance
  - ⚠️ Missing check-out
  - ⏰ Late check-in
  - ⌛ Early departure
  - 🕐 Overtime worked

### ⏱️ Overtime Calculation
- **Automatic Calculation**: Daily overtime computation for all employees
- **Multiple Rates**: Different rates for weekdays, weekends, and holidays
- **Approval Workflow**: Manager approval for overtime records
- **Payroll Integration**: Ready for payroll module integration

### 🏖️ Leave Integration
- **Automatic Deduction**: Late arrivals and early departures deduct from annual leave
- **Configurable Rules**: Customizable grace periods and deduction rates
- **Leave Balance**: Real-time leave balance tracking
- **Integration**: Seamless integration with hr_holidays module

### 📥 Manual Import
- **CSV Import**: Manual upload of attendance data
- **Data Validation**: Preview and validate before import
- **Multiple Formats**: Support for standard, F18, and custom CSV formats
- **Error Handling**: Comprehensive error reporting and logging

### 📈 Reporting & Dashboard
- **Attendance Dashboard**: Visual analytics with charts and KPIs
- **Multiple Reports**: Summary, detailed, overtime, and deduction reports
- **Export Options**: Excel and PDF export capabilities
- **Filtering**: Advanced filtering by employee, department, and date range

### 🔐 Security
- **Role-Based Access**: Three security levels
  - **Attendance User**: View own records
  - **Attendance Manager**: Import/edit, approve overtime
  - **Attendance Administrator**: Full access
- **Record Rules**: Secure data access based on user roles

### 🌐 REST API
- **External Integration**: REST endpoints for third-party systems
- **JSON Support**: Standard JSON payload format
- **Authentication**: Secure API access with user authentication

## 📋 Requirements

### Dependencies
- Odoo 18 Community Edition
- Python 3.10+
- Required Odoo modules: `hr`, `hr_attendance`, `hr_holidays`, `resource`, `mail`, `web`

### Python Libraries (optional)
- `pyzk`: Optional ZKTeco SDK helpers
- `xlsxwriter`: Optional Excel report generation

## 🛠️ Installation

1. **Download Module**: Place the module in your Odoo addons directory
2. **(Optional) Install Extra Libraries**:
   ```bash
   pip install xlsxwriter
   pip install pyzk
   ```
3. **Update Apps List**: Go to Apps → Update Apps List
4. **Install Module**: Search for "HR Attendance Load F18" and install

## ⚙️ Configuration

### 1. Basic Setup
Navigate to **Settings → Attendance Settings** to configure business rules:

- **Working Hours**: Standard working hours per day (default: 8 hours)
- **Overtime Threshold**: Hours after which overtime is calculated
- **Grace Periods**: Late arrival and early departure tolerance
- **Leave Deduction**: Enable/disable automatic leave deductions

### 2. Attendance Devices
Manage device connections:

- Go to **Attendance Enhanced → Devices**
- Create devices with IP and port
- Mark as **Active** and enable **Auto Pull** if desired

### 3. Import Settings
Configure automatic import via devices:

- **Auto Pull**: Enable on each device to schedule daily imports
- **Cron**: Ensure the attendance pull cron is active

### 4. Notification Settings
Configure notifications for:

- Import errors and warnings
- Overtime approval requests
- Leave deduction notifications

## 📖 Usage

### Manual Import
1. Go to **Attendance Enhanced → Attendance Import → Manual Import**
2. Upload CSV file with attendance data
3. Configure CSV format and column mapping
4. Preview data and validate
5. Process import

### CSV Format Examples

**Standard Format:**
```csv
Employee Code,Check In,Check Out
EMP001,2024-01-15 08:00:00,2024-01-15 17:00:00
EMP002,2024-01-15 08:30:00,2024-01-15 17:30:00
```

**F18 Format:**
```csv
User ID,DateTime,Status,Verify,WorkCode
1,2024-01-15 08:00:00,1,1,0
1,2024-01-15 17:00:00,0,1,0
```

### Overtime Management
1. **Automatic Calculation**: Overtime is calculated daily via cron job
2. **Manual Review**: Go to **Attendance Enhanced → Overtime → Overtime Records**
3. **Approval**: Managers can approve/reject overtime records
4. **Reports**: View overtime reports and analytics

### Leave Deduction
1. **Automatic Processing**: Late arrivals/early departures automatically create deductions
2. **Review**: Go to **Attendance Enhanced → Leave Integration → Leave Deductions**
3. **Confirmation**: Confirm or reject deduction records
4. **Balance Tracking**: Monitor leave balance changes

### Dashboard & Reports
1. **Dashboard**: Go to **Attendance Enhanced → Dashboard**
2. **Reports**: Access various reports under **Attendance Enhanced → Reports**
3. **Export**: Export data to Excel or PDF
4. **Analytics**: Use pivot tables and charts for analysis

## 🔧 API Usage

### Authentication
All API endpoints require user authentication via session or API key.

### Endpoints

**Import Single Attendance:**
```http
POST /hr_attendance_load_f18/api/import
Content-Type: application/json

{
    "employee_code": "EMP001",
    "check_in": "2024-01-15 08:00:00",
    "check_out": "2024-01-15 17:00:00"
}
```

**Bulk Import:**
```http
POST /hr_attendance_load_f18/api/bulk_import
Content-Type: application/json

{
    "attendances": [
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
    ]
}
```

**Get Employee Attendance:**
```http
GET /hr_attendance_load_f18/api/employee/EMP001/attendance?date_from=2024-01-01&date_to=2024-01-31
```

**API Status:**
```http
GET /hr_attendance_load_f18/api/status
```

## 🐛 Troubleshooting

### Common Issues

**Device Connection Failed:**
- Check device IP and port configuration
- Verify network connectivity
- Ensure device is powered on and accessible

**Import Errors:**
- Verify CSV format and column mapping
- Check employee codes exist in system
- Validate date format matches configuration

**Overtime Not Calculated:**
- Check cron job is running
- Verify working hours configuration
- Ensure attendance records exist

**Leave Deduction Not Working:**
- Check leave deduction is enabled
- Verify grace period settings
- Ensure employee has leave allocation

### Logs and Debugging
- Check Odoo server logs for detailed error messages
- Enable debug mode for additional information
- Review import logs in **Attendance Import → Import History**

## 🤝 Support

For support and questions:
- Check the documentation and troubleshooting section
- Review Odoo logs for error details
- Contact your system administrator

## 📄 License

This module is licensed under LGPL-3. See LICENSE file for details.

## 🔄 Changelog

### Version 18.0.1.0.0
- Initial release
- Device-based integration
- Overtime calculation
- Leave deduction functionality
- Manual import wizard
- Dashboard and reporting
- REST API endpoints
- Security and access control