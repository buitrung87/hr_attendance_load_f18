# -*- coding: utf-8 -*-

from odoo import models, api
from odoo.osv.expression import AND as domain_and


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    @api.model
    def search(self, domain=None, offset=0, limit=None, order=None, count=False):
        """
        Restrict attendance visibility: only show own records for regular users.
        Exceptions: Attendance Manager and HR Manager retain full visibility.
        """
        user = self.env.user

        # Skip restriction when explicitly importing attendances
        if self.env.context.get('attendance_importing'):
            return super(HrAttendance, self).search(
                domain or [], offset=offset, limit=limit, order=order, count=count
            )

        # Allow managers to see all attendances
        is_manager = (
            user.has_group('hr_attendance.group_attendance_manager')
            or user.has_group('hr.group_hr_manager')
        )

        effective_domain = domain or []
        if not is_manager:
            # Limit to records of the current user only
            only_self = [('employee_id.user_id', '=', user.id)]
            effective_domain = domain_and([effective_domain, only_self])

        return super(HrAttendance, self).search(
            effective_domain, offset=offset, limit=limit, order=order, count=count
        )