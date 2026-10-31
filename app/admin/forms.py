from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, PasswordField, BooleanField, SelectField, SubmitField, TextAreaField, Form, FieldList, FormField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError
import re
from urllib.parse import urlsplit

class UserEditForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name', validators=[Optional()])
    is_admin = BooleanField('Administrator')
    is_active = BooleanField('Active')
    password = PasswordField('New Password', validators=[Optional(), Length(min=8, message='Password must be at least 8 characters')])
    send_setup_email = BooleanField('Send password setup email')
    submit = SubmitField('Save Changes')
    
    def validate_email(self, field):
        # Domain restriction
        allowed_domain = 'klubinvestoru.com'
        if not field.data.lower().endswith('@' + allowed_domain):
            raise ValidationError(f'Email must end with @{allowed_domain}')

class CreateUserForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name', validators=[Optional()])
    is_admin = BooleanField('Administrator')
    send_setup_email = BooleanField('Send password setup email', default=True)
    submit = SubmitField('Create User')
    
    def validate_email(self, field):
        allowed_domain = 'klubinvestoru.com'
        if not field.data.lower().endswith('@' + allowed_domain):
            raise ValidationError(f'Email must end with @{allowed_domain}')

class CsvUploadForm(FlaskForm):
    csv_file = FileField('CSV File', validators=[
        FileRequired(),
        FileAllowed(['csv'], 'Only CSV files allowed.')
    ])
    auto_create_accounts = BooleanField('Create missing analyst accounts', default=True)
    submit = SubmitField('Upload and Process')


class AnalystMappingForm(FlaskForm):
    analyst_name = StringField('Analyst Name', validators=[DataRequired()])
    user_id = SelectField('User', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Save Mapping')


class CompanyTickerForm(FlaskForm):
    ticker_symbol = StringField('Ticker Symbol', validators=[DataRequired()])
    submit = SubmitField('Save Ticker')


def _public_url(form, field):
    value = (field.data or '').strip()
    if not value:
        return
    if field.short_name == 'logo' and value.startswith('/static/'):
        if '..' not in value and re.fullmatch(r'/static/[A-Za-z0-9_./-]+', value):
            return
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or any(c.isspace() for c in value)):
        raise ValidationError('Use an HTTPS address (or /static/ for a logo).')


class PartnerEntryForm(Form):
    name = StringField('Partner name', validators=[Optional(), Length(max=100)])
    website = StringField('Website', validators=[Optional(), Length(max=1000), _public_url])
    logo = StringField('Logo URL', validators=[Optional(), Length(max=1000), _public_url])


class SitePartnersForm(FlaskForm):
    partners = FieldList(FormField(PartnerEntryForm), min_entries=0, max_entries=12)
    submit = SubmitField('Save partners')


class PublicPortfolioForm(FlaskForm):
    mode = SelectField('Public portfolio', choices=[
        ('approved', 'Board-approved positions'), ('purchased', 'Purchased positions')],
        validators=[DataRequired()])


from wtforms import HiddenField, IntegerField
from wtforms.validators import AnyOf, NumberRange

class MaintenanceScheduleForm(FlaskForm):
    job = HiddenField(validators=[DataRequired(), AnyOf(['notion', 'recalc'])])
    enabled = BooleanField()
    frequency = SelectField(choices=[('daily', 'Daily'), ('weekly', 'Weekly')], validators=[DataRequired()])
    day_of_week = SelectField(choices=[(day, day) for day in ('mon','tue','wed','thu','fri','sat','sun')], validators=[DataRequired()])
    hour = IntegerField(validators=[NumberRange(min=0, max=23)])
    minute = IntegerField(validators=[NumberRange(min=0, max=59)])
