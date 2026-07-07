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
        'product',
        'account',
        'web',
        'board',
        'contacts',
        'spreadsheet_dashboard',
        'web_pwa_customize',
    ],
    'data': [
        'security/kser_security.xml',
        'security/ir.model.access.csv',
        'data/kser_chronic_condition_data.xml',
        'data/kser_data.xml',
        'report/kser_report_templates.xml',
        'wizard/kser_wizards_views.xml',
        'views/kser_beneficiary_views.xml',
        'views/kser_cash_donation_views.xml',
        'views/kser_audit_log_views.xml',
        'views/inherited_views.xml',
        'views/res_config_settings_views.xml',
        'views/kser_clinic_visit_views.xml',
        'views/kser_dashboard_views.xml',
        'views/kser_prescription_views.xml',
        'views/kser_child_followup_views.xml',
        'views/kser_cash_expense_views.xml',
        'views/kser_menus.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            ('before', 'web/static/src/scss/primary_variables.scss', 'kser_erp/static/src/scss/kser_variables.scss'),
        ],
        'web.assets_backend': [
            'kser_erp/static/src/scss/kser_theme.scss',
            'kser_erp/static/src/js/kser_indexeddb.js',
            'kser_erp/static/src/js/pull_to_refresh.js',
            'kser_erp/static/src/js/ocr_list_button.js',
            'kser_erp/static/src/xml/ocr_list_button.xml',
        ],
    },

    'installable': True,
    'application': True,
    'auto_install': False,
}
