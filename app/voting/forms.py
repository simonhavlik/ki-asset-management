from flask_wtf import FlaskForm
from wtforms import IntegerField, TextAreaField, SelectField
from wtforms.validators import InputRequired, NumberRange, Length, Optional


class RecommendationForm(FlaskForm):
    analysis_id = IntegerField(validators=[InputRequired()])
    days = IntegerField(validators=[InputRequired(), NumberRange(min=7, max=30)])
    rationale = TextAreaField(validators=[Optional(), Length(max=2000)])


class ExtendForm(FlaskForm):
    days = IntegerField(validators=[InputRequired(), NumberRange(min=7, max=30)])


class BallotForm(FlaskForm):
    vote = SelectField(choices=[('yes', 'Yes'), ('no', 'No'), ('remove', 'Remove')], validators=[InputRequired()])


class EligibilityForm(FlaskForm):
    mode = SelectField(choices=[('board', 'Board approval'), ('approved', 'Approved analyses')], validators=[InputRequired()])


class WithdrawForm(FlaskForm):
    pass
