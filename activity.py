# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime
import pytz
import re
from sql import Null, Cast
from sql.aggregate import Sum

from trytond.model import (Workflow, ModelSQL, ModelView, DeactivableMixin, fields,
    sequence_ordered)
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond import backend
from trytond.i18n import gettext
from trytond.exceptions import UserError, UserWarning
from trytond.pyson import Eval
from trytond.modules.widgets import tools


# Use Tryton's default color by default
_COLOR = '#ABD6E3'
_RGB = (67, 84, 90)

def create_anchors(text):
    return re.sub(r"((http|https):\/\/\S*)", r'<a href="\1" target="_blank" rel="noopener">\1</a>', text)

class RGB:
    def __init__(self, color=(0, 0, 0)):
        if isinstance(color, str):
            color = color.lstrip('#')
            try:
                self.value = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
            except ValueError:
                self.value = _RGB
        else:
            self.value = color
        assert isinstance(self.value, tuple)
        assert len(self.value) == 3

    def hex(self):
        return '#%02x%02x%02x' % self.value

    def increase(self, inc):
        res = []
        for x in self.value:
            res.append(max(0, min(255, x + inc)))
        self.value = tuple(res)

    def increase_ratio(self, ratio):
        self.increase(int((255 - self.gray()) * ratio))

    def gray(self):
        return (self.value[0] + self.value[1] + self.value[2]) // 3

def timedelta_to_string(interval):
    seconds = interval.total_seconds()
    hours = seconds // 3600
    minutes = (seconds - (hours * 3600)) // 60
    return '%02d:%02d' % (hours, minutes)


class ActivityType(sequence_ordered(), DeactivableMixin, ModelSQL, ModelView):
    'Activity Type'
    __name__ = "activity.type"
    name = fields.Char('Name', required=True, translate=True)
    color = fields.Char('Color', help='HTML color (hexadecimal)')
    default_duration = fields.TimeDelta('Default Duration')
    default_description = fields.Text("Default Description")

    @classmethod
    def __register__(cls, module_name):
        sql_table = cls.__table__()

        super().__register__(module_name)

        # Migration for activity descriptions to EditorJS
        tools.migrate_field(sql_table, sql_table.default_description, 'text')


class ActivityReference(ModelSQL, ModelView):
    'Activity Reference'
    __name__ = "activity.reference"
    model = fields.Many2One('ir.model', 'Model', required=True)


class Activity(Workflow, ModelSQL, ModelView):
    'Activity'
    __name__ = "activity.activity"
    code = fields.Char('Code', readonly=True)
    activity_type = fields.Many2One('activity.type', 'Type', required=True)
    subject = fields.Char('Subject')
    resource = fields.Reference('Resource', selection='get_resource')
    origin = fields.Reference('Origin', selection='get_origin')
    date = fields.Date('Date', required=True)
    duration = fields.TimeDelta('Duration')
    time = fields.Time('Time')
    dtstart = fields.DateTime('Start Date')
    dtend = fields.DateTime('End Date')
    state = fields.Selection([
            ('planned', 'Planned'),
            ('done', 'Held'),
            ('cancelled', 'Not Held'),
            ], 'State', required=True)
    description = fields.Text('Description')
    employee = fields.Many2One('company.employee', 'Employee', required=True)
    location = fields.Char('Location')
    party = fields.Many2One('party.party', "Party",
        context={
            'company': Eval('company', -1),
            },
        depends=['company'])
    summary = fields.Function(fields.Char('Summary'), 'get_summary')
    html = fields.Function(fields.Binary('HTML'), 'get_html')
    calendar_color = fields.Function(fields.Char('Color'), 'get_calendar_color')
    calendar_background_color = fields.Function(fields.Char('Background Color'),
            'get_calendar_background_color')
    day_busy_hours = fields.Function(fields.TimeDelta('Day Busy Hours'),
        'get_day_busy_hours')
    company = fields.Function(fields.Many2One('company.company', "Company"),
        'on_change_with_company', searcher='search_company')

    @classmethod
    def __setup__(cls):
        super(Activity, cls).__setup__()
        cls._order = [
            ('dtstart', 'DESC'),
            ('subject', 'ASC'),
            ('id', 'DESC'),
            ]
        cls._transitions |= set((
                ('planned', 'done'),
                ('planned', 'cancelled'),
                ('done', 'planned'),
                ('done', 'cancelled'),
                ('cancelled', 'planned'),
                ('cancelled', 'done'),
                ))
        cls._buttons.update({
                'plan': {
                    'invisible': Eval('state') == 'planned',
                    'icon': 'activity',
                    'depends': ['state'],
                    },
                'cancel': {
                    'invisible': Eval('state') == 'cancelled',
                    'icon': 'tryton-cancel',
                    'depends': ['state'],
                    },
                'do': {
                    'invisible': Eval('state') == 'done',
                    'icon': 'tryton-ok',
                    'depends': ['state'],
                    },
                'activity_split': {
                    'icon': 'tryton-activity-split',
                    },
                })

    @classmethod
    def __register__(cls, module_name):
        cursor = Transaction().connection.cursor()
        sql_table = cls.__table__()
        table = cls.__table_handler__(module_name)

        date_exists = True
        if backend.TableHandler.table_exist(cls._table):
            date_exists = table.column_exist('date')

        super(Activity, cls).__register__(module_name)

        # Migration from 5.2
        if not date_exists:
            cursor.execute(*sql_table.update(
                    columns=[sql_table.date, sql_table.time],
                    values=[Cast(sql_table.dtstart, 'DATE'),
                        Cast(sql_table.dtstart, 'TIME')]))
            cursor.execute(*sql_table.update(
                    columns=[sql_table.duration],
                    values=[sql_table.dtend - sql_table.dtstart],
                    where=sql_table.dtend != Null))
        cursor.execute(*sql_table.update(
                columns=[sql_table.state],
                values=['done'],
                where=sql_table.state == 'held'))
        cursor.execute(*sql_table.update(
                columns=[sql_table.state],
                values=['canceled'],
                where=sql_table.state == 'not_held'))

        # Migration from 5.6: rename state canceled to cancelled
        cursor.execute(*sql_table.update(
                [sql_table.state], ['cancelled'],
                where=sql_table.state == 'canceled'))

        # Migration for activity descriptions to EditorJS
        tools.migrate_field(sql_table, sql_table.description, 'text')

    @classmethod
    @ModelView.button
    @Workflow.transition('planned')
    def plan(cls, activities):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def do(cls, activities):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('cancelled')
    def cancel(cls, activities):
        pass

    @classmethod
    @ModelView.button_action('activity.act_split_relate')
    def activity_split(cls, activities):
        Warning = Pool().get('res.user.warning')
        child_activities = cls.search([
                ('origin', 'in', activities)
                ])
        if not child_activities:
            for activity in activities:
                aux = [x for x in activity.description.split('\n---\n')
                    if x.strip()]
                key = 'activity_split.%d' % len(aux)
                if Warning.check(key):
                    raise SplitWarning(key,
                        gettext('activity.create_subactivities',
                            count=len(aux)))
                for description in aux:
                    cls.copy([activity], {
                        'description': description,
                        'origin': activity,
                        })

    @fields.depends('resource', '_parent_party.id', 'party')
    def on_change_with_party(self, name=None):
        if (self.resource
                and not isinstance(self.resource, str)
                and self.resource.id > 0):
            return Activity._resource_party(self.resource)
        return self.party.id if self.party else None

    def get_rec_name(self, name):
        if self.subject:
            return '[%s] %s' % (self.code, self.subject)
        return self.code

    @classmethod
    def search_rec_name(cls, name, clause):
        return ['OR',
            ('code',) + tuple(clause[1:]),
            ('subject',) + tuple(clause[1:]),
            ]

    @staticmethod
    def default_employee():
        User = Pool().get('res.user')
        user = User(Transaction().user)
        return user.employee and user.employee.id or None

    @staticmethod
    def default_state():
        return 'planned'

    @staticmethod
    def default_resource():
        return None

    @classmethod
    def default_party(cls):
        resource = cls.default_resource()
        return Activity._resource_party(resource)

    @staticmethod
    def default_activity_type():
        return Transaction().context.get('default_activity_type')

    @staticmethod
    def _resource_party(resource):
        if not resource or resource.id < 0:
            return

        model = resource and str(resource).partition(',')[0]
        Relation = Pool().get(model)
        if model == 'party.party':
            return resource.id
        if 'party' in Relation._fields.keys():
            if resource.party:
                return resource.party.id
        return None

    @fields.depends('activity_type', '_parent_activity_type.default_description',
        'duration', 'description')
    def on_change_activity_type(self):
        if not self.activity_type:
            return
        description = self.description
        if description:
            description = tools.js_to_text(self.description)
        if not description and self.activity_type.default_description:
            self.description = self.activity_type.default_description
        if not self.duration is None:
            return
        self.duration = self.activity_type.default_duration

    @classmethod
    def get_timezone(cls):
        Company = Pool().get('company.company')
        company_id = Transaction().context.get('company')
        if company_id:
            company = Company(company_id)
            if company.timezone:
                return pytz.timezone(company.timezone)

    @classmethod
    def utc_to_local(cls, value):
        timezone = cls.get_timezone()
        if not timezone:
            return value
        converted = value
        converted = timezone.localize(value)
        converted = value + converted.utcoffset()
        return converted

    @classmethod
    def local_to_utc(cls, value):
        timezone = cls.get_timezone()
        if not timezone:
            return value
        converted = timezone.localize(value)
        converted = value - converted.utcoffset()
        return converted

    @fields.depends('dtstart')
    def on_change_dtstart(self):
        if not self.dtstart:
            return
        dt = self.utc_to_local(self.dtstart)
        self.date = dt.date()
        if dt.time() == datetime.time():
            # When time is 0:00 we consider it is a full-day activity
            # as the calendar view does not provide a mechanism to distinguish
            # between an event at midnight and a full-day event.
            #
            # Given that events at midnight are very unfrequent, this is the
            # best default
            self.time = None
        else:
            self.time = dt.time()

    @classmethod
    def get_resource(cls):
        'Return list of Model names for resource Reference'
        Reference = Pool().get('activity.reference')

        res = [(None, '')]
        for _type in Reference.search([]):
            res.append((_type.model.model, _type.model.name))
        return res

    @classmethod
    def _get_origin(cls):
        return ['activity.activity']

    @classmethod
    def get_origin(cls):
        pool = Pool()
        Model = pool.get('ir.model')
        models = Model.search([('model', 'in', cls._get_origin())])
        return [(None, '')] + [(x.model, x.name) for x in models]

    @classmethod
    def create(cls, vlist):
        pool = Pool()
        Config = pool.get('activity.configuration')

        sequence = Config(1).activity_sequence
        if not sequence:
            raise UserError(gettext('activity.no_activity_sequence'))
        vlist = [x.copy() for x in vlist]
        for vals in vlist:
            vals['code'] = sequence.get()
            vals.update(cls.update_dates(vals))
        return super(Activity, cls).create(vlist)

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        args = []
        for activities, values in zip(actions, actions):
            for activity in activities:
                args.append([activity])
                args.append(cls.update_dates(values, activity))
        super().write(*args)

    def get_html(self, name):
        return tools.js_to_html(self.description)

    @classmethod
    def update_dates(cls, values, record=None):
        values = values.copy()
        if not 'date' in values:
            dtstart = None
            if 'dtstart' in values:
                dtstart = values['dtstart']
                values['date'] = dtstart.date()
                values['time'] = dtstart.time()
            elif record:
                dtstart = record.dtstart

            if 'dtend' in values:
                dtend = values['dtend']
                if dtend and dtstart:
                    values['duration'] = dtend - dtstart
                else:
                    values['duration'] = None
                return values

        if record:
            for field in ('date', 'time', 'duration'):
                if not field in values:
                    values[field] = getattr(record, field)

        date = values.get('date')
        time = values.get('time')
        if not date:
            return values
        if not time:
            time = datetime.datetime.now().time()
        duration = values.get('duration')
        dtstart = datetime.datetime.combine(date, time or datetime.time())
        dtstart = cls.local_to_utc(dtstart)
        dtend = None
        if time and duration:
            dtend = dtstart + duration
        values['dtstart'] = dtstart
        values['dtend'] = dtend
        return values

    def get_summary(self, name):
        if self.subject:
            text = self.subject
        elif self.party:
            text = self.party.rec_name
        elif self.code:
            text = self.code
        else:
            text = ''
        text += ' (%s)' % self.activity_type.rec_name
        if self.duration:
            text += '\n%s' % timedelta_to_string(self.duration)
        if self.day_busy_hours:
            if not self.duration:
                text += '\n-'
            text += ' / %s' % timedelta_to_string(self.day_busy_hours)
        text += '\n@' + self.employee.rec_name
        return text

    def get_calendar_color(self, name):
        rgb = RGB(self.calendar_background_color)
        if rgb.gray() > 128:
            return 'black'
        return 'white'

    def get_calendar_background_color(self, name):
        color = _COLOR
        context = Transaction().context
        if context.get('activity_color_type', False):
            if self.activity_type and self.activity_type.color:
                color = self.activity_type.color
        else:
            if self.employee and self.employee.color:
                color = self.employee.color

        if self.state != 'planned':
            rgb = RGB(color)
            rgb.increase_ratio(0.8)
            color = rgb.hex()
        return color

    @classmethod
    def get_day_busy_hours(cls, activities, name):
        cursor = Transaction().connection.cursor()
        table = cls.__table__()

        employees = [x.employee.id for x in activities]
        min_date = min([x.date for x in activities])
        max_date = max([x.date for x in activities])
        query = table.select(
            table.employee,
            table.date,
            Sum(table.duration),
            where=((table.employee.in_(employees))
                & (table.date >= min_date)
                & (table.date <= max_date)),
            group_by=(table.employee, table.date))
        cursor.execute(*query)
        records = cursor.fetchall()
        sums = {}
        for record in records:
            sums[(record[0], record[1])] = record[2]

        res = {}
        for activity in activities:
            res[activity.id] = sums.get((activity.employee.id, activity.date),
                datetime.timedelta())
        return res

    @fields.depends('employee')
    def on_change_with_company(self, name=None):
        return self.employee.company.id if self.employee and self.employee.company else None

    @classmethod
    def search_company(cls, name, clause):
        return [('employee.%s' % name,) + tuple(clause[1:])]


class ActivityCalendarContext(ModelView):
    'Activity Calendar Context'
    __name__ = 'activity.calendar.context'
    activity_color_type = fields.Boolean('Use Type Color', help='If checked, '
        'uses the color of the type of the activity as event background. '
        'Otherwise uses the color defined in the employee.')

class SplitWarning(UserWarning):
    pass
