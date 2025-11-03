# Installation Guide - HR Attendance Load F18

## Prerequisites

### System Requirements
- Odoo 18 Community Edition
- Python 3.10 or higher
- PostgreSQL database
- Linux/Windows server environment

### Optional Python Dependencies
Optional packages that enhance functionality:
```bash
# Excel export support (optional)
pip install xlsxwriter
# ZKTeco SDK (optional if you plan to use SDK helpers)
pip install pyzk
```

## Installation Steps

### 1. Download and Place Module
1. Copy the `hr_attendance_load_f18` folder to your Odoo addons directory
2. Typical locations:
   - Linux: `/opt/odoo/addons/` or `/usr/lib/python3/dist-packages/odoo/addons/`
   - Windows: `C:\Program Files\Odoo\server\addons\`
   - Custom: Your custom addons path defined in `odoo.conf`

### 2. Update Addons Path
Ensure your `odoo.conf` file includes the addons directory:
```ini
[options]
addons_path = /opt/odoo/addons,/path/to/custom/addons
```

### 3. Restart Odoo Server
```bash
sudo systemctl restart odoo
# or
sudo service odoo restart
```

### 4. Update Apps List
1. Log in to Odoo as Administrator
2. Go to **Apps** menu
3. Click **Update Apps List**
4. Confirm the update

### 5. Install Module
1. In the Apps menu, search for "HR Attendance Load F18"
2. Click **Install** button
3. Wait for installation to complete

## Post-Installation Configuration

### 1. Configure User Access
1. Go to **Settings → Users & Companies → Users**
2. Assign appropriate groups to users:
   - **Attendance User**: Basic attendance viewing
   - **Attendance Manager**: Import and approve functions
   - **Attendance Administrator**: Full access

### 2. Configure Attendance Devices
1. Go to **Attendance Enhanced → Devices**
2. Create a device and set connection details:
   - IP Address: Device IP address
   - Port: Device communication port (e.g., 4370)
   - Device ID: Optional identifier
   - Active: Enable to include the device in operations
3. (Optional) Enable **Auto Pull** to allow scheduled imports via cron

### 3. Set Working Hours
1. Configure standard working hours (default: 8 hours)
2. Set overtime thresholds and rates
3. Configure grace periods for late/early attendance

### 4. Enable Automatic Features
1. **Auto Import**: Enable Auto Pull on devices; ensure cron jobs are active
2. **Auto Overtime**: Enable automatic overtime calculation
3. **Leave Deduction**: Enable automatic leave deductions

## Verification

### 1. Check Installation
1. Go to **Apps → Installed**
2. Verify "HR Attendance Load F18" is listed
3. Check version: 18.0.1.0.0

### 2. Test Basic Functions
1. **Menu Access**: Check "Attendance Enhanced" menu appears
2. **Import**: Test manual CSV import
3. **Views**: Verify enhanced attendance views work
4. **Reports**: Access dashboard and reports

### 3. Test Demo Data (Optional)
If demo data was installed:
1. Check demo employees exist
2. Verify sample attendance records
3. Test overtime and leave deduction records

## Troubleshooting

### Common Issues

**Module Not Appearing in Apps List:**
- Check addons path in `odoo.conf`
- Restart Odoo server
- Update apps list
- Check file permissions

**Installation Fails:**
- Check Python dependencies are installed
- Verify database permissions
- Check Odoo logs for detailed errors

**Device Connection Issues:**
- Verify network connectivity
- Check device IP and port
- Ensure device is accessible and not firewalled
- Test with telnet: `telnet <ip> <port>`

**Permission Errors:**
- Check user group assignments
- Verify security rules
- Check record access permissions

### Log Files
Check Odoo server logs for detailed error information:
- Linux: `/var/log/odoo/odoo-server.log`
- Windows: Check Odoo service logs
- Custom: Location defined in `odoo.conf`

## Uninstallation

### 1. Backup Data
Before uninstalling, backup any important data:
- Attendance records
- Overtime records
- Configuration settings

### 2. Uninstall Module
1. Go to **Apps → Installed**
2. Find "HR Attendance Load F18"
3. Click **Uninstall**
4. Confirm uninstallation

### 3. Clean Up (Optional)
- Remove module files from addons directory
- Clean up any custom configurations
- Remove Python dependencies if not needed

## Support

For technical support:
1. Check this documentation
2. Review Odoo server logs
3. Test with demo data
4. Contact your system administrator

## Version Information
- **Module Version**: 18.0.1.0.0
- **Odoo Version**: 18.0 Community
- **Last Updated**: January 2024