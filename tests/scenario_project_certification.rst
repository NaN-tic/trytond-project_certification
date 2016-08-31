=========================================
Project Product Progress Service Scenario
=========================================

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from proteus import config, Model, Wizard
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.account.tests.tools import create_chart, \
    ...     get_accounts
    >>> from trytond.modules.account_invoice.tests.tools import \
    ...     create_payment_term
    >>> today = datetime.datetime.today()
    >>> yestarday = datetime.datetime.today() - relativedelta(days=1)
    >>> two_days_ago = datetime.datetime.today() - relativedelta(days=2)

Create database::

    >>> config = config.set_trytond()
    >>> config.pool.test = True

Install project_certification::

    >>> Module = Model.get('ir.module')
    >>> module, = Module.find([
    ...         ('name', '=', 'project_certification'),
    ...     ])
    >>> module.click('install')
    >>> Wizard('ir.module.install_upgrade').execute('upgrade')

Create company::

    >>> _ = create_company()
    >>> company = get_company()

Create chart of accounts::

    >>> _ = create_chart(company)
    >>> accounts = get_accounts(company)
    >>> revenue = accounts['revenue']

Reload the context::

    >>> User = Model.get('res.user')
    >>> Group = Model.get('res.group')
    >>> config._context = User.get_preferences(True, config.context)

Create project user::

    >>> project_user = User()
    >>> project_user.name = 'Project'
    >>> project_user.login = 'project'
    >>> project_user.main_company = company
    >>> project_group, = Group.find([('name', '=', 'Project Administration')])
    >>> timesheet_group, = Group.find([('name', '=', 'Timesheet Administration')])
    >>> project_user.groups.extend([project_group, timesheet_group])
    >>> project_user.save()

Create project invoice user::

    >>> project_invoice_user = User()
    >>> project_invoice_user.name = 'Project Invoice'
    >>> project_invoice_user.login = 'project_invoice'
    >>> project_invoice_user.main_company = company
    >>> project_invoice_group, = Group.find([('name', '=', 'Project Invoice')])
    >>> project_group, = Group.find([('name', '=', 'Project Administration')])
    >>> project_invoice_user.groups.extend(
    ...     [project_invoice_group, project_group])
    >>> project_invoice_user.save()

Create project certification user::

    >>> project_certification_user = User()
    >>> project_certification_user.name = 'Project Certification'
    >>> project_certification_user.login = 'project_certification'
    >>> project_certification_user.main_company = company
    >>> project_invoice_group, = Group.find([('name', '=', 'Project Certification')])
    >>> project_group, = Group.find([('name', '=', 'Project Administration')])
    >>> project_certification_user.groups.extend(
    ...     [project_invoice_group, project_group])
    >>> project_certification_user.save()

Create payment term::

    >>> payment_term = create_payment_term()
    >>> payment_term.save()

Create customer::

    >>> Party = Model.get('party.party')
    >>> customer = Party(name='Customer')
    >>> customer.customer_payment_term = payment_term
    >>> customer.save()

Create employee::

    >>> Employee = Model.get('company.employee')
    >>> employee = Employee()
    >>> party = Party(name='Employee')
    >>> party.save()
    >>> employee.party = party
    >>> employee.company = company
    >>> employee.save()

Create products::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> hour, = ProductUom.find([('name', '=', 'Hour')])

    >>> Product = Model.get('product.product')
    >>> ProductTemplate = Model.get('product.template')

    >>> service = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'Service'
    >>> template.default_uom = hour
    >>> template.type = 'service'
    >>> template.list_price = Decimal('20')
    >>> template.cost_price = Decimal('5')
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> service.template = template
    >>> service.save()

    >>> product = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'Good'
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.list_price = Decimal('100')
    >>> template.cost_price = Decimal('50')
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> product.template = template
    >>> product.save()

Create a Project::

    >>> config.user = project_user.id
    >>> ProjectWork = Model.get('project.work')
    >>> TimesheetWork = Model.get('timesheet.work')
    >>> TimesheetLine = Model.get('timesheet.line')

    >>> project = ProjectWork()
    >>> project.name = 'Test certification'
    >>> project.type = 'project'
    >>> project.party = customer
    >>> project.project_invoice_method = 'progress'
    >>> project.invoice_product_type = 'service'

    >>> task1 = ProjectWork()
    >>> task1.name = 'Task 1'
    >>> task1.type = 'task'
    >>> task1.invoice_product_type = 'goods'
    >>> task1.product_goods = service
    >>> task1.quantity = 100.0
    >>> task1.uom = hour
    >>> project.children.append(task1)
    >>> project.save()

    >>> task2 = ProjectWork()
    >>> task2.name = 'Task 2'
    >>> task2.type = 'task'
    >>> task2.invoice_product_type = 'goods'
    >>> task2.product_goods = product
    >>> task2.quantity = 1000.0
    >>> task2.uom = unit
    >>> project.children.append(task2)

    >>> project.save()
    >>> task1, task2 = project.children

Create First Certification::

    >>> config.user = project_certification_user.id
    >>> Certification = Model.get('project.certification')
    >>> certification = Certification()
    >>> certification.work = project
    >>> certification.date = two_days_ago
    >>> certification.company = company
    >>> line1, line2 = certification.lines
    >>> line1.quantity = 5
    >>> line2.quantity = 10
    >>> certification.save()
    >>> certification.reload()

Propose Certifications::

    >>> certification.click('proposal')

Check Certifications::

    >>> line1, line2 = certification.lines
    >>> line1.work_quantity
    100.0
    >>> line1.certified_quantity
    0.0
    >>> line1.pending_quantity
    100.0
    >>> line2.work_quantity
    1000.0
    >>> line2.certified_quantity
    0.0
    >>> line2.pending_quantity
    1000.0

Confirm Certifications::

    >>> certification.click('confirm')

Invoice project::

    >>> config.user = project_invoice_user.id
    >>> project.click('invoice')
    >>> project.invoiced_amount
    Decimal('1100.00')

Check Certifications::

    >>> line1, line2 = certification.lines
    >>> line1.work_quantity
    100.0
    >>> line1.certified_quantity
    5.0
    >>> line1.pending_quantity
    95.0
    >>> line2.work_quantity
    1000.0
    >>> line2.certified_quantity
    10.0
    >>> line2.pending_quantity
    990.0

Create Second Certification::

    >>> config.user = project_certification_user.id
    >>> certification = Certification()
    >>> certification.work = project
    >>> certification.date = two_days_ago
    >>> certification.state = 'draft'
    >>> certification.company = company
    >>> line1, line2 = certification.lines
    >>> line1.work = task1
    >>> line1.quantity = 5
    >>> line1.save()
    >>> line2.work = task2
    >>> line2.quantity = 10
    >>> line2.save()

Propose Certifications::

    >>> certification.click('proposal')

Check Certifications::

    >>> line1, line2 = certification.lines
    >>> line1.work_quantity
    100.0
    >>> line1.certified_quantity
    5.0
    >>> line1.pending_quantity
    95.0
    >>> line2.work_quantity
    1000.0
    >>> line2.certified_quantity
    10.0
    >>> line2.pending_quantity
    990.0

Confirm Certifications::

    >>> certification.click('confirm')

Check Certifications::

    >>> line1, line2 = certification.lines
    >>> line1.work_quantity
    100.0
    >>> line1.certified_quantity
    10.0
    >>> line1.pending_quantity
    90.0
    >>> line2.work_quantity
    1000.0
    >>> line2.certified_quantity
    20.0
    >>> line2.pending_quantity
    980.0

Invoice project::

    >>> config.user = project_invoice_user.id
    >>> project.click('invoice')
    >>> project.invoiced_amount
    Decimal('2200.00')

Check Certifications::

    >>> line1, line2 = certification.lines
    >>> line1.work_quantity
    100.0
    >>> line1.certified_quantity
    10.0
    >>> line1.pending_quantity
    90.0
    >>> line2.work_quantity
    1000.0
    >>> line2.certified_quantity
    20.0
    >>> line2.pending_quantity
    980.0

Create Third Certification::

    >>> config.user = project_certification_user.id
    >>> certification = Certification()
    >>> certification.work = project
    >>> certification.date = two_days_ago
    >>> certification.state = 'draft'
    >>> certification.company = company
    >>> line1, line2 = certification.lines
    >>> line1.work = task1
    >>> line1.quantity = -2
    >>> line1.save()
    >>> line2.work = task2
    >>> line2.quantity = -18
    >>> line2.save()

Propose Certifications::

    >>> certification.click('proposal')

Check Certifications::

    >>> line1, line2 = certification.lines
    >>> line1.work_quantity
    100.0
    >>> line1.certified_quantity
    10.0
    >>> line1.pending_quantity
    90.0
    >>> line2.work_quantity
    1000.0
    >>> line2.certified_quantity
    20.0
    >>> line2.pending_quantity
    980.0

Confirm Certifications::

    >>> certification.click('confirm')

Invoice project::

    >>> config.user = project_invoice_user.id
    >>> project.click('invoice')
    >>> project.invoiced_amount
    Decimal('360.00')

Check Certifications::

    >>> line1, line2 = certification.lines
    >>> line1.work_quantity
    100.0
    >>> line1.certified_quantity
    8.0
    >>> line1.pending_quantity
    92.0
    >>> line2.work_quantity
    1000.0
    >>> line2.certified_quantity
    2.0
    >>> line2.pending_quantity
    998.0
