# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime
from trytond.model import ModelSQL, ModelView, Workflow, fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Bool, Eval, If
from trytond.transaction import Transaction

__all__ = ['Certification', 'CertificationLine', 'Work']

_STATES = {
    'readonly': Eval('state') != 'draft',
}
_DEPENDS = ['state']


class Certification(Workflow, ModelSQL, ModelView):
    'Certification'
    __name__ = 'project.certification'
    _rec_name = 'number'
    company = fields.Many2One('company.company', 'Company', required=True,
        domain=[
            ('id', If(Eval('context', {}).contains('company'), '=', '!='),
                Eval('context', {}).get('company', -1)),
            ],
        states=_STATES, depends=_DEPENDS)
    number = fields.Char('Number', states=_STATES, depends=_DEPENDS)
    reference = fields.Char('Reference', states=_STATES, depends=_DEPENDS)

    date = fields.Date('Date', required=True, states=_STATES,
        depends=_DEPENDS)
    work = fields.Many2One('project.work', 'Project', required=True, domain=[
            ('type', '=', 'project'),
            ('company', '=', Eval('company', -1)),
            ],
        states={
                'readonly': (Eval('state') != 'draft') | Bool(Eval('lines')),
            }, depends=['company', 'state', 'lines'])
    lines = fields.One2Many('project.certification.line', 'certification',
        'Lines', states={
            'readonly': Eval('state').in_(['confirmed', 'cancel']),
            }, depends=['state'])
    state = fields.Selection([
            ('draft', 'Draft'),
            ('proposal', 'Proposal'),
            ('confirmed', 'Confirmed'),
            ('cancel', 'Cancel')
            ], 'State', readonly=True)

    @classmethod
    def __setup__(cls):
        super(Certification, cls).__setup__()
        cls._transitions |= set((
                ('draft', 'proposal'),
                ('proposal', 'draft'),
                ('proposal', 'confirmed'),
                ('confirmed', 'cancel'),
                ('draft', 'cancel'),
                ('cancel', 'draft'),
                ))
        cls._buttons.update({
            'confirm': {
                'invisible': (Eval('state') != 'proposal'),
                'icon': 'tryton-go-next',
                },
            'proposal': {
                'invisible': (Eval('state') != 'draft'),
                'icon': 'tryton-ok',
                },

            'draft': {
                'invisible': ~Eval('state').in_(['proposal', 'cancel']),
                'icon': 'tryton-clear',
                },
            'cancel': {
                'invisible': ~Eval('state').in_(['confirmed', 'draft']),
                'icon': 'tryton-cancel',
                },
            })
        cls._error_messages.update({
                'delete_non_draft': ('Certification "%s" must be in draft '
                    'state in order to be deleted.'),
                'line_quantity_error': 'Certification "%(line)s" can not be '
                    'confirmed because has not any quantity or exceeds.',
                'certification_invoiced_error': 'You cannot cancel '
                    'certification "%(certification)s" because it has been '
                    'invoiced.',
                })

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_date():
        return datetime.datetime.now()

    @staticmethod
    def default_state():
        return 'draft'

    @fields.depends('work', 'lines')
    def on_change_work(self):
        if not self.work:
            self.lines = []
        else:
            self._certification_lines_from_work(self.work.children)

    def _certification_lines_from_work(self, projects):
        for task in projects:
            if (task.invoice_product_type == 'goods'
                    and task.certified_pending_quantity):
                line = self._get_certification_line_work(task)
                self.lines += (line,)
            if task.children:
                self._certification_lines_from_work(task.children)

    def _get_certification_line_work(self, work):
        pool = Pool()
        Line = pool.get('project.certification.line')
        line = Line()
        line.work = work
        line.uom = work.uom
        line.work_quantity = work.quantity
        line.certified_quantity = work.certified_quantity
        line.pending_quantity = work.certified_pending_quantity
        line.quantity = 0.0
        return line

    @classmethod
    @ModelView.button
    @Workflow.transition('draft')
    def draft(cls, certifications):
        pass

    @classmethod
    @Workflow.transition('proposal')
    def proposal(cls, certifications):
        pass

    @classmethod
    @Workflow.transition('cancel')
    def cancel(cls, certifications):
        pass

    @classmethod
    @Workflow.transition('confirmed')
    def confirm(cls, certifications):
        cls.check_certifications(certifications)

    @classmethod
    def check_certifications(cls, certifications):
        for certification in certifications:
            for line in certification.lines:
                if not line.quantity or line.quantity > line.pending_quantity:
                    cls.raise_user_error('line_quantity_error', {
                            'line': line.rec_name,
                            })

    @classmethod
    def create(cls, vlist):
        pool = Pool()
        Sequence = pool.get('ir.sequence')
        Configuration = pool.get('certification.configuration')
        config = Configuration(1)
        vlist = [x.copy() for x in vlist]
        for values in vlist:
            if not values.get('number'):
                values['number'] = Sequence.get_id(
                    config.certification_sequence.id)
        return super(Certification, cls).create(vlist)

    @classmethod
    def delete(cls, certifications):
        cls.draft(certifications)
        for certification in certifications:
            if certification.state != 'draft':
                cls.raise_user_error('delete_non_draft', (
                        certification.rec_name,
                        ))
        return super(Certification, cls).delete(certifications)

    @classmethod
    def copy(cls, certifications, default=None):
        if default is None:
            default = {}
        default.setdefault('date', cls.default_date())
        default.setdefault('number')
        return super(Certification, cls).copy(certifications, default=default)


class CertificationLine(ModelSQL, ModelView):
    'Certification Line'
    __name__ = 'project.certification.line'

    certification = fields.Many2One('project.certification', 'Certification',
        required=True, readonly=True, ondelete='CASCADE')
    work = fields.Many2One('project.work', 'Project', required=True, domain=[
            ('type', '=', 'project'),
            ('invoice_product_type', '=', 'goods'),
            ('parent', 'child_of',
                Eval('_parent_certification', {}).get('work', -1)),
            ])
    work_uom_category = fields.Function(
        fields.Many2One('product.uom.category', 'Uom Category'),
        'on_change_with_work_uom_category')
    uom = fields.Many2One('product.uom', 'UoM', domain=[
            If(Bool(Eval('work_uom_category')),
                ('category', '=', Eval('work_uom_category')),
                ('category', '!=', -1)),
            ], depends=['work_uom_category'], required=True)
    uom_digits = fields.Function(fields.Integer('UoM Digits'),
        'on_change_with_uom_digits')
    work_quantity = fields.Function(fields.Float('Work Quantity',
            digits=(16, Eval('uom_digits', 2)), depends=['uom_digits']),
        'on_change_with_work_quantity')
    certified_quantity = fields.Function(fields.Float('Certified Quantity',
            digits=(16, Eval('uom_digits', 2)), depends=['uom_digits']),
        'on_change_with_certified_quantity')
    pending_quantity = fields.Function(fields.Float('Pending Quantity',
            digits=(16, Eval('uom_digits', 2)), depends=['uom_digits']),
        'on_change_with_pending_quantity')
    quantity = fields.Float('Quantity', digits=(16, Eval('uom_digits', 2)),
        domain=[
            ['OR',
                ('quantity', '=', None),
                [
                    ('quantity', '>=', 0.0),
#                    ('quantity', '<=', Eval('pending_quantity')),
                    ]]
            ],
        depends=['uom_digits', 'pending_quantity'])

    @classmethod
    def __setup__(cls):
        super(CertificationLine, cls).__setup__()
        cls._error_messages.update({
            'wrong_certified_quantity': ('You try to certify '
                '"%(quantity)s" but only "%(pending_quantity)s"'
                ' pending quanrity on line "%(line)s"')
            })

    @fields.depends('work')
    def on_change_with_work_uom_category(self, name=None):
        if self.work:
            return self.work.uom.category.id

    @fields.depends('work')
    def on_change_work(self, name=None):
        if self.work:
            self.uom = self.work.uom

    @staticmethod
    def default_uom_digits():
        return 2

    @fields.depends('uom')
    def on_change_with_uom_digits(self, name=None):
        if self.uom:
            return self.uom.digits
        return 2

    @fields.depends('work', 'uom')
    def on_change_with_work_quantity(self, name=None):
        pool = Pool()
        Uom = pool.get('product.uom')
        if self.work:
            if self.uom:
                return Uom.compute_qty(
                    self.work.uom, self.work.quantity, self.uom)
            return self.work.quantity

    @fields.depends('id', 'work', 'uom')
    def on_change_with_certified_quantity(self, name=None):
        if self.work:
            return self.work.get_certified_quantity(
                exclude_certification_line_id=self.id if self.id > 0 else None,
                to_uom=self.uom)

    @fields.depends('id', 'work', 'uom')
    def on_change_with_pending_quantity(self, name=None):
        if self.work:
            return self.work.quantity - self.work.certified_quantity

    @staticmethod
    def default_quantity():
        return 0.0


class Work:
    __name__ = 'project.work'
    __metaclass__ = PoolMeta
    certifications = fields.One2Many('project.certification', 'work',
        'Certifications', readonly=True, states={
            'invisible': Eval('type') != 'project',
            }, depends=['type'])
    certification_lines = fields.One2Many('project.certification.line', 'work',
        'Certifications', readonly=True, states={
            'invisible': ((Eval('type') != 'task')
                | (Eval('invoice_product_type') != 'goods')),
            }, depends=['type', 'invoice_product_type'])
    certified_quantity = fields.Function(fields.Float('Certified Quantity',
            digits=(16, Eval('uom_digits', 2)), states={
                'invisible': ((Eval('type') != 'task')
                    | (Eval('invoice_product_type') != 'goods')),
                }, depends=['uom_digits', 'type', 'invoice_product_type']),
        'get_certified_quantity')
    certified_pending_quantity = fields.Function(
        fields.Float('Pending Quantity', digits=(16, Eval('uom_digits', 2)),
            states={
                'invisible': ((Eval('type') != 'task')
                    | (Eval('invoice_product_type') != 'goods')),
                }, depends=['uom_digits', 'type', 'invoice_product_type']),
        'get_certified_pending_quantity')

    @classmethod
    def __setup__(cls):
        super(Work, cls).__setup__()
        cls.progress_quantity.states['required'] = False
        cls.progress_quantity_func.readonly = True

    def get_certified_quantity(self, name=None,
            exclude_certification_line_id=None, to_uom=None):
        pool = Pool()
        Uom = pool.get('product.uom')
        if to_uom == None:
            to_uom = self.uom
        return sum((
                Uom.compute_qty(cl.uom, cl.quantity, to_uom)
                for cl in self.certification_lines
                if (cl.certification.state == 'confirmed'
                    and cl.id != exclude_certification_line_id)),
            0.0)

    def get_certified_pending_quantity(self, name):
        if self.quantity and self.certified_quantity:
            return self.quantity - self.certified_quantity
        elif self.quantity:
            return self.quantity
        return 0

    def total_progress_quantity(self, name=None):
        pool = Pool()
        Uom = pool.get('product.uom')
        if self.invoice_product_type != 'goods':
            return 0.0
        return Uom.compute_qty(self.uom, self.certified_quantity or 0,
            self.product_goods.default_uom)

    def _get_lines_to_invoice_progress(self):
        pool = Pool()
        InvoicedProgress = pool.get('project.work.invoiced_progress')

        if not self.product_goods:
            return super(Work, self)._get_lines_to_invoice_progress()

        res = []
        if self.total_progress_quantity() <= self.invoiced_quantity:
            return res

        quantity = self.total_progress_quantity() - self.invoiced_quantity
        res.append({
                'product': self.product_goods,
                'quantity': quantity,
                'unit': self.product_goods.default_uom,
                'unit_price': self.list_price,
                'origin': InvoicedProgress(
                    work=self,
                    quantity=quantity),
                'description': self.name,
                })

        return res

    @classmethod
    def copy(cls, works, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default['certifications'] = None
        default['certification_lines'] = None
        return super(Work, cls).copy(works, default=default)
