from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField
from wtforms.validators import DataRequired, Email, Length, Optional
from models import User  # Import after creating models

class EditUserForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(), 
        Length(min=2, max=50, message='Username must be between 2 and 50 characters')
    ])
    email = StringField('Email', validators=[
        DataRequired(), 
        Email(message='Please enter a valid email address')
    ])
    role = SelectField('Role', choices=[
        ('super_admin', 'Super Admin'), 
        ('admin', 'Admin'), 
        ('user', 'User')
    ], validators=[DataRequired()])
    parent_admin = SelectField('Parent Admin', coerce=int, validators=[Optional()])
    
    def __init__(self, *args, **kwargs):
        super(EditUserForm, self).__init__(*args, **kwargs)
        # Populate the parent_admin choices with available admins
        admins = User.query.filter(User.role.in_(['super_admin', 'admin'])).all()
        self.parent_admin.choices = [(0, 'None')] + [(admin.id, admin.username) for admin in admins]