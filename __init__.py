# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .configuration import *
from .work import *


def register():
    Pool.register(
        Configuration,
        Certification,
        CertificationLine,
        CertificationLineWorkProgressInvoicedRelation,
        Work,
        WorkInvoicedProgress,
        module='project_certification', type_='model')
