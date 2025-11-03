from odoo import models
from odoo.osv import expression


class HrOvertime(models.Model):
    _inherit = 'hr.overtime'

    def search(self, domain=None, offset=0, limit=None, order=None, **kwargs):
        """Limit listing to OT >= 0.5h unless explicitly bypassed via context.

        - Accept extra kwargs (e.g., count) for compatibility but don't pass them to super.
        - Internal calls can pass context key `overtime_any=True` to search all.
        """
        # Drop unsupported parameters (e.g., 'count') to avoid TypeError on BaseModel.search
        kwargs.pop('count', None)

        if not self.env.context.get('overtime_any'):
            # Show records when:
            # - OT hours >= 0.5 (weekdays), OR
            # - Overtime type is weekend/holiday (any positive duration)
            or_domain = expression.OR([
                [('overtime_hours', '>=', 0.5)],
                [('overtime_type', 'in', ['weekend', 'holiday'])]
            ])
            domain = expression.AND([domain or [], or_domain])
        return super(HrOvertime, self).search(domain, offset=offset, limit=limit, order=order)