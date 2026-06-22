{
    'name': 'KSER ERP',
    'version': '18.0.1.0.0',
    'category': 'Humanitarian',
    'sequence': -1,
    'summary': 'نظام تخطيط موارد خيري لدعم غرف طوارئ ولاية الخرطوم',
    'description': """
        KSER ERP - نظام إدارة غرف الطوارئ
        =====================================
        يوفر هذا الموديول إدارة متكاملة للعمليات الإدارية والمالية والمخزونية
        مع حوكمة رقابية صارمة تمنع التلاعب وازدواجية الصرف.
    """,
    'author': 'KSER Team',
    'website': 'https://github.com/nice247/kser_erp',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'project',
        'stock',
        'account',
    ],
    'data': [
        'security/kser_security.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
