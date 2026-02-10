from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
import re

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name (optional)')
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=12, message='Password must be at least 12 characters long.')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match.')
    ])
    submit = SubmitField('Register')

    def validate_email(self, field):
        # Domain restriction
        allowed_domain = 'klubinvestoru.com'
        if not field.data.lower().endswith('@' + allowed_domain):
            raise ValidationError(f'Email must end with @{allowed_domain}')
        # Additional email validation (basic)
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', field.data):
            raise ValidationError('Invalid email format')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Send Reset Link')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=12, message='Password must be at least 12 characters long.')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match.')
    ])
    submit = SubmitField('Reset Password')

class TokenForm(FlaskForm):
    token = StringField('Activation Code', validators=[DataRequired()])
    submit = SubmitField('Activate')