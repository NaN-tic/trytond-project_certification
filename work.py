# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime
from trytond.model import ModelSQL, ModelView, Workflow, fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Bool, Eval, If
from trytond.transaction import Transaction

__all__ = ['Certification', 'CertificationLine', 'Work',
    'WorkInvoicedProgress', 'CertificationLineWorkProgressInvoicedRelation']

_STATES = {
    'readonly': Eval('state') != 'draft',
}
_DEPENDS = ['state']


class Certification(Workflow, ModelSQL, ModelView):
    'Certification'
    __name__ = 'project.certification'
    _rec_name = 'number'
    company = fields.Many2One('company.company', 'Company', required=True,
        states=_STATES, select=True, domain=[
            ('id', If(Eval('context', {}).contains('company'), '=', '!='),
                Eval('context', {}).get('company', -1)),
            ],
        depends=_DEPENDS)
    number = fields.Char('Number', states=_STATES, depends=_DEPENDS)
    date = fields.Date('Date', required=True, states=_STATES,
        depends=_DEPENDS)
    work = fields.Many2One('project.work', 'Work',
        domain=[
            ('type', '=', 'project'),
            ],
        states=_STATES, depends=_DEPENDS)

    lines = fields.One2Many('project.certification.line', 'certification',
        'Lines', states={
            'readonly': Eval('state') == 'confirmed',
        })

    invoiced = fields.Function(fields.Boolean('Invoiced'), 'is_invoiced')
    state = fields.Selection([
            ('draft', 'Draft'),
            ('proposal', 'Proposal'),
            ('confirmed', 'Confirmed'),
            ('cancel', 'Cancel')
            ], 'State', readonly=True, select=True)

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
                    'confirmed because has not any quantity.',
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
        pool = Pool()
        Work = pool.get('project.work')
        Line = pool.get('project.certification.line')
        if not self.work:
            self.lines = []
        else:
            for work in Work.search([('parent', 'child_of', [self.work.id]),
                    ('id', '!=', self.work.id)]):
                line = Line()
                line.work = work
                line.uom = work.uom
                self.lines += (line,)

    def is_invoiced(self, name=None):
        for line in self.lines:
            if line.invoiced_progress:
                return True
        return False

    @classmethod
    def check_invoiced(cls, certifications):
        for certification in certifications:
            if certification.invoiced:
                cls.raise_user_error('certification_invoiced_error', {
                        'certification': certification.rec_name,
                        })

    @classmethod
    def check_certifications(cls, certifications):
        for certification in certifications:
            for line in certification.lines:
                if not line.quantity:
                    cls.raise_user_error('line_quantity_error', {
                            'line': line.rec_name,
                            })

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
    @Workflow.transition('confirmed')
    def confirm(cls, certifications):
        cls.check_certifications(certifications)

    @classmethod
    @ModelView.button
    @Workflow.transition('cancel')
    def cancel(cls, certifications):
        cls.check_invoiced(certifications)

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
    'Certification - Work'
    __name__ = 'project.certification.line'

    certification = fields.Many2One('project.certification', 'Certification')
    work = fields.Many2One('project.work', 'Work')

    total_quantity = fields.Function(fields.Float('Total Quantity',
            digits=(16, Eval('uom_digits', 2)), depends=['uom_digits']),
        'certified_quantities')
    pending_quantity = fields.Function(fields.Float('Pending Quantity',
            digits=(16, Eval('uom_digits', 2)), depends=['uom_digits']),
        'certified_quantities')
    certified_quantity = fields.Function(fields.Float('Certified Quantity',
            digits=(16, Eval('uom_digits', 2)), depends=['uom_digits']),
        'certified_quantities')

    quantity = fields.Float('Quantity', digits=(16, Eval('uom_digits', 2)),
        depends=['uom_digits'])

    uom_digits = fields.Function(fields.Integer('UoM Digits'),
        'on_change_with_uom_digits')

    uom = fields.Many2One('product.uom', 'UoM', domain=[
            If(Bool(Eval('work_uom_category')),
                ('category', '=', Eval('work_uom_category')),
                ('category', '!=', -1)),
            ], depends=['work_uom_category'])

    work_uom_category = fields.Function(
        fields.Many2One('product.uom.category', 'Uom Category'),
        'on_change_with_work_uom_category')

    invoiced_progress = fields.One2One(
        'certification_line-invoiced_progress',
        'certification_line', 'invoiced_progress',
        'Work Invoice Progress')

    @staticmethod
    def default_uom_digits():
        return 2

    @classmethod
    def certified_quantities(cls, lines, names):
        result = {n: {} for n in
                ('certified_quantity', 'total_quantity', 'pending_quantity')}

        for line in lines:
            work = line.work
            result['total_quantity'][line.id] = getattr(work, 'quantity', 0.0)
            result['pending_quantity'][line.id] = getattr(work,
                'certified_pending_quantity', 0.0)
            result['certified_quantity'][line.id] = getattr(work,
                'certified_quantity', 0.0)
        return result

    @fields.depends('uom')
    def on_change_with_uom_digits(self, name=None):
        if self.uom:
            return self.uom.digits
        return 2

    @fields.depends('work')
    def on_change_with_work_uom_category(self, name=None):
        if self.work:
            return self.work.uom.category.id


class Work:
    __name__ = 'project.work'
    __metaclass__ = PoolMeta

    certifications = fields.One2Many('project.certification.line', 'work',
        'Certifications')
    certified_pending_quantity = fields.Function(
        fields.Float('Pending Quantity', digits=(16, Eval('uom_digits', 2)),
            depends=['uom_digits']),
        'certified_quantities')
    certified_quantity = fields.Function(fields.Float('Pending Quantity',
            digits=(16, Eval('uom_digits', 2)), depends=['uom_digits']),
        'certified_quantities')

    @classmethod
    def __setup__(cls):
        super(Work, cls).__setup__()
        cls.progress_quantity.states['invisible'] = True

    @classmethod
    def certified_quantities(cls, works, names):
        pool = Pool()
        Uom = pool.get('product.uom')
        result = {}

        result['certified_quantity'] = {}
        result['certified_pending_quantity'] = {}

        for work in works:
            result['certified_quantity'][work.id] = 0.0
            result['certified_pending_quantity'][work.id] = work.quantity

            for cert in work.certifications:
                if cert.certification.state != 'confirmed':
                    continue
                qty = Uom.compute_qty(cert.uom, cert.quantity, work.uom)
                result['certified_quantity'][work.id] += qty
                result['certified_pending_quantity'][work.id] -= qty

        return result

    @classmethod
    def _get_total_progress_quantity(cls, works, name):
        pool = Pool()
        Uom = pool.get('product.uom')
        result = {w.id: 0 for w in works}
        result.update({w.id: Uom.compute_qty(
                    w.uom, w.certified_quantity or 0,
                    w.product_goods.default_uom)
                for w in works if w.product_goods and w.uom})
        return result

    def _get_lines_to_invoice_progress(self):
        pool = Pool()
        InvoicedProgress = pool.get('project.work.invoiced_progress')

        if not self.product_goods:
            return super(Work, self)._get_lines_to_invoice_progress()

        res = []
        if self.progress is None:
            return res

        for cert in self.certifications:
            if cert.certification.state != 'confirmed':
                continue

            if cert.invoiced_progress:
                continue

            quantity = cert.quantity
            invoiced_progress = InvoicedProgress(work=self,
                quantity=quantity, certification_line=cert)

            res.append({
                'product': self.product_goods,
                'quantity': quantity,
                'unit': self.product_goods.default_uom,
                'unit_price': self.unit_price,
                'origin': invoiced_progress,
                'description': self.name,
            })

        return res


class WorkInvoicedProgress:
    __name__ = 'project.work.invoiced_progress'
    __metaclass__ = PoolMeta

    certification_line = fields.One2One(
        'certification_line-invoiced_progress',
        'invoiced_progress', 'certification_line', 'Certification Line')


class CertificationLineWorkProgressInvoicedRelation(ModelSQL):
    'Invoice - Milestone'
    __name__ = 'certification_line-invoiced_progress'
    invoiced_progress = fields.Many2One('project.work.invoiced_progress',
        'Work Invoiced Progress', ondelete='CASCADE',
        required=True, select=True)
    certification_line = fields.Many2One('project.certification.line',
        'Certification Line',
        ondelete='CASCADE', required=True, select=True)

    # @classmethod
    # def __setup__(cls):
    #     super(CertificationLineWorkProgressInvoicedRelation, cls).__setup__()
    #     t = cls.__table__()
    #     cls._sql_constraints += [
    #         ('invoiced_progress_unique', Unique(t,
    #             t.invoiced_progress), 'The Invoice must be unique.'),
    #         ('certification_line_unique', Unique(t, t.certification_line),
    #             'The Certification Line must be unique.'),
    #         ]
