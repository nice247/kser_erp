{
    'name': 'KSER ERP',
    'version': '18.0.1.0.0',
    'category': 'Humanitarian',
    'sequence': -1,
    'summary': 'Charity ERP system to support Khartoum State Emergency Rooms',
    'description': """
        KSER ERP - Emergency Rooms Management System
        =====================================
        This module provides integrated management for administrative, financial, and inventory operations
        with strict regulatory governance to prevent manipulation and duplicate disbursement.
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
        'web',
    ],
    'data': [
        'security/kser_security.xml',
        'security/ir.model.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'kser_erp/static/src/js/kser_indexeddb.js',
        ],
    },

    'installable': True,
    'application': True,
    'auto_install': False,
}
