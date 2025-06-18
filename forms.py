#importing necessary libraries
from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, PasswordField, SubmitField, FloatField, DateField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Length, ValidationError, Optional
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms.fields import MultipleFileField 


# This file is part of the Project Management System.
# LoginForm is used for user authentication on the login page
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=50)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

# This file is part of the Project Management System.
# ProjectForm is used for adding and editing project data
class ProjectForm(FlaskForm):
    # Basic project fields with corresponding validations
    serial_no = IntegerField('S. No.', validators=[DataRequired()])
    title = StringField('Nomenclature', validators=[DataRequired()])
    academia = StringField('Academia/Institute')
    pi_name = StringField('PI Name')
    coord_lab = StringField('Coordinating Lab')
    scientist = StringField('Coordinating Lab Scientist', validators=[DataRequired()])
    vertical = StringField('Research Vertical')
    cost_lakhs = FloatField('Cost (in Lakhs)')
    sanctioned_date = DateField('Sanctioned Date', validators=[DataRequired()])
    original_pdc = DateField('Original PDC')
    revised_pdc = DateField('Revised PDC')
    stakeholders = StringField('Stakeholding Labs')
    scope_objective = TextAreaField('Scope/Objective of Project')
    expected_deliverables = StringField('Expected Deliverables/ Technologies')
    Outcome_Dovetailing_with_Ongoing_Work=TextAreaField('Outcome Dovetailing with Ongoing Work')
    rab_meeting_date = DateField("RAB Meeting Date", format='%Y-%m-%d', validators=[Optional()])
    rab_meeting_held_date = DateField("RAB Meeting Held Date", format='%Y-%m-%d', validators=[Optional()])
    rab_minutes = MultipleFileField('RAB Minutes of Meeting', validators=[FileAllowed(['pdf'], 'PDF only!')])
    gc_meeting_date = DateField("GC Meeting Date", format='%Y-%m-%d', validators=[Optional()])
    gc_meeting_held_date = DateField("GC Meeting Held Date", format='%Y-%m-%d', validators=[Optional()])
    gc_minutes = MultipleFileField('GC Minutes of Meeting', validators=[FileAllowed(['pdf'], 'PDF only!')])
    technical_status = TextAreaField('Technical Status')
    administrative_status = SelectField('Administrative Status', choices=[('ongoing', 'Ongoing'), ('completed', 'Completed'), ('pending', 'Pending')], validators=[DataRequired()])
    final_closure_date = DateField('Final Closure Date', format='%Y-%m-%d', validators=[Optional()])
    final_closure_remarks = TextAreaField('Final Closure Remarks', validators=[Optional()])
    final_report = MultipleFileField('Final Report', validators=[FileAllowed(['pdf'], 'PDF only!')])
    submit = SubmitField('Submit')
    
    def validate_original_pdc(self, field):
        if self.sanctioned_date.data and field.data <= self.sanctioned_date.data:
            raise ValidationError("Original PDC cannot be before or equal to the Sanctioned Date.")
    
    def validate_revised_pdc(self, field):
        if self.original_pdc.data and field.data < self.original_pdc.data:
            raise ValidationError("Revised PDC cannot be before the Original PDC.")

class UploadForm(FlaskForm):
    form_no = StringField('Form No', validators=[DataRequired()])
    title = StringField('Title', validators=[DataRequired()])
    submission_schedule = TextAreaField('Submission Schedule (Mandatory Requirements)', validators=[DataRequired()])
    file = FileField('PDF File', validators=[FileRequired(), FileAllowed(['pdf'], 'PDFs only!')])
    submit = SubmitField('Upload')

class ModifyUserForm(FlaskForm):
    username = SelectField('Select User', validators=[DataRequired()], coerce=str)
    password = PasswordField('New Password (leave blank to keep unchanged)', validators=[Optional(), Length(min=8)])
    role = SelectField('Role', choices=[('admin', 'Admin'), ('viewer', 'Viewer'), ('manager', 'Manager')], validators=[DataRequired()])
    pi_name = StringField('PI Name (for Manager)', validators=[Optional()])
    submit = SubmitField('Update User')