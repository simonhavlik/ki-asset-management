from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, PasswordField, BooleanField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError
import re

class UserEditForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name', validators=[Optional()])
    is_admin = BooleanField('Administrator')
    is_active = BooleanField('Active')
    password = PasswordField('New Password', validators=[Optional(), Length(min=8, message='Password must be at least 8 characters')])
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