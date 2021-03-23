# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond import backend
from trytond.model import ModelSingleton, ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.pyson import Eval
from trytond.modules.company.model import (
    CompanyMultiValueMixin, CompanyValueMixin)

__all__ = ['Configuration', 'ConfigurationSequence']


class Configuration(
        ModelSingleton, ModelSQL, ModelView, CompanyMultiValueMixin):
    'Activity Configuration'
    __name__ = 'activity.configuration'
    activity_sequence = fields.MultiValue(fields.Many2One('ir.sequence',
            'Activity Sequence', required=True,
            domain=[
                ('company', 'in',
                    [Eval('context', {}).get('company', -1), None]),
                ('code', '=', 'activity.activity'),
                ]))

    @classmethod
    def multivalue_model(cls, field):
        pool = Pool()
        if field == 'activity_sequence':
            return pool.get('activity.configuration.sequence')
        return super(Configuration, cls).multivalue_model(field)

    @classmethod
    def default_activity_sequence(cls, **pattern):
        field_name = 'activity_sequence'
        return getattr(
            cls.multivalue_model(field_name),
            'default_%s' % field_name, lambda: None)()


class ConfigurationSequence(ModelSQL, CompanyValueMixin):
    'Activity Sequence Configuration'
    __name__ = 'activity.configuration.sequence'

    activity_sequence = fields.Many2One('ir.sequence',
        'Activity Sequence', required=True,
        domain=[
            ('company', 'in', [Eval('company', -1), None]),
            ('code', '=', 'activity.activity'),
            ],
        depends=['company'])

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        old_table = 'activity_configuration_company'
        if (not TableHandler.table_exist(cls._table)
                and TableHandler.table_exist(old_table)):
            TableHandler.table_rename(old_table, cls._table)

        super(ConfigurationSequence, cls).__register__(module_name)

    @classmethod
    def default_activity_sequence(cls):
        pool = Pool()
        ModelData = pool.get('ir.model.data')
        try:
            return ModelData.get_id('activity', 'sequence_activity')
        except KeyError:
            return None
