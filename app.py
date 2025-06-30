### Project Management System - Flask Application ###


## Imports and Initialization ##

from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_from_directory, session, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Project, Log
from forms import LoginForm, ProjectForm, UploadForm, ModifyUserForm
import datetime as dt
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from pytz import timezone

from io import BytesIO
from flask import send_file
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from flask_migrate import Migrate
from collections import Counter, defaultdict
import calendar
import os

import uuid
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage

import csv
from io import StringIO

# Initialize Flask app and database
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Flask-Migrate for database migrations
migrate = Migrate(app, db)

UPLOAD_FOLDER = 'static/forms'
ALLOWED_EXTENSIONS = {'pdf','doc','docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

class NoticeForm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    form_no = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    submission_schedule = db.Column(db.Text, nullable=True)
    filename = db.Column(db.String(255), nullable=True)  
    filenames = db.Column(db.Text, nullable=True)  
    file_types = db.Column(db.Text, nullable=True)  

def save_files(files):
    saved_files = []
    for file in files:
        if file and file.filename:
            try:
                filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                file_type = file.filename.split('.')[-1].lower()
                saved_files.append((filename, file_type))  
            except Exception as e:
                print(f"Error saving file {file.filename}: {e}")
    return saved_files

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def log_action(user, action):
    tz = timezone('Asia/Kolkata')
    now = datetime.now(tz)
    log = Log(user_id=user.id, action=action, timestamp=now)
    db.session.add(log)
    db.session.commit()

# Rouute for the home page
@app.route('/home')
@login_required
def home():
    return render_template('main/home.html', user=current_user)


# Route for the login page
@app.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            log_action(user, "User logged in")
            flash(f"Welcome, {user.username}!", "success")
            return redirect(url_for('home'))
        flash('Invalid username or password', 'danger')
    return render_template('main/login.html', form=form)


# Route for the project search
@app.route('/ajax_search_projects')
@login_required
def ajax_search_projects():
    query = request.args.get('query', '').strip()
    if query:
        projects = Project.query.filter(
            (Project.serial_no.ilike(f"%{query}%")) |
            (Project.title.ilike(f"%{query}%"))
        ).all()
    else:
        projects = Project.query.all()

    return render_template('partials/project_table_body.html', projects=projects)


# Route for the dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    query = Project.query

    # Apply role-based filtering
    if current_user.role == 'manager':
        # Restrict projects to those with the manager's PI name
        query = query.filter(Project.scientist.ilike(f"%{current_user.coord_scientist}%"))
    elif current_user.role == 'viewer':
        # Restrict viewers to only active projects (optional logic)
        query = query.filter(Project.administrative_status != 'Completed')

    # Apply additional filters 
    column = request.args.get('column', '')
    value = request.args.get('value', '').strip()
    cost_min = request.args.get('cost_min', '').strip()
    cost_max = request.args.get('cost_max', '').strip()
    sanction_year_start = request.args.get('sanction_year_start', '').strip()
    sanction_year_end = request.args.get('sanction_year_end', '').strip()

    if column and (value or (column == 'cost_lakhs' and (cost_min or cost_max)) or (column == 'sanction_year' and (sanction_year_start or sanction_year_end))):
        if column == 'serial_no':
            query = query.filter(Project.serial_no.ilike(f"%{value}%"))
        elif column == 'title':
            query = query.filter(Project.title.ilike(f"%{value}%"))
        elif column == 'vertical':
            query = query.filter(Project.vertical.ilike(f"%{value}%"))
        elif column == 'academia':
            query = query.filter(Project.academia.ilike(f"%{value}%"))
        elif column == 'pi_name':
            query = query.filter(Project.pi_name.ilike(f"%{value}%"))
        elif column == 'coord_lab':
            query = query.filter(Project.coord_lab.ilike(f"%{value}%"))
        elif column == 'scientist':
            query = query.filter(Project.scientist.ilike(f"%{value}%"))
        elif column == 'cost_lakhs':
            try:
                if cost_min:
                    query = query.filter(Project.cost_lakhs >= float(cost_min))
                if cost_max:
                    query = query.filter(Project.cost_lakhs <= float(cost_max))
            except ValueError:
                pass
        elif column in ['sanctioned_date', 'original_pdc', 'revised_pdc']:
            try:
                date_value = datetime.strptime(value, "%Y-%m-%d").date()
                query = query.filter(getattr(Project, column) == date_value)
            except ValueError:
                pass
        elif column == 'administrative_status':
            query = query.filter(Project.administrative_status.ilike(f"%{value}%"))
        elif column == 'sanction_year':
            try:
                if sanction_year_start:
                    query = query.filter(db.extract('year', Project.sanctioned_date) >= int(sanction_year_start))
                if sanction_year_end:
                    query = query.filter(db.extract('year', Project.sanctioned_date) <= int(sanction_year_end))
                # fallback for single value (if only value is provided)
                if not (sanction_year_start or sanction_year_end) and value:
                    year = int(value)
                    query = query.filter(db.extract('year', Project.sanctioned_date) == year)
            except ValueError:
                pass

    projects = query.order_by(db.cast(Project.serial_no, db.Integer)).all()

    # --- Reminder Logic ---
    today = datetime.today().date()
    soon = today + timedelta(days=30)

    if current_user.role == 'manager':
        # Only show alerts for projects assigned to this manager
        manager_projects = [p for p in projects if p.scientist == current_user.coord_scientist]
        approaching_pdc = [
            p for p in manager_projects
            if p.revised_pdc and isinstance(p.revised_pdc, dt.date) and today <= p.revised_pdc <= soon
            and (not p.administrative_status or p.administrative_status.lower() != "completed")
        ]
        approaching_rab = [
            p for p in manager_projects
            if p.rab_meeting_date and isinstance(p.rab_meeting_date, dt.date) and today <= p.rab_meeting_date <= soon
        ]
        approaching_gc = [
            p for p in manager_projects
            if p.gc_meeting_date and isinstance(p.gc_meeting_date, dt.date) and today <= p.gc_meeting_date <= soon
        ]
    else:
        # Admin and viewer see all
        approaching_pdc = [
            p for p in projects
            if p.revised_pdc and isinstance(p.revised_pdc, dt.date) and today <= p.revised_pdc <= soon
            and (not p.administrative_status or p.administrative_status.lower() != "completed")
        ]
        approaching_rab = [
            p for p in projects
            if p.rab_meeting_date and isinstance(p.rab_meeting_date, dt.date) and today <= p.rab_meeting_date <= soon
        ]
        approaching_gc = [
            p for p in projects
            if p.gc_meeting_date and isinstance(p.gc_meeting_date, dt.date) and today <= p.gc_meeting_date <= soon
        ]

    return render_template(
        'main/dashboard.html',
        projects=projects,
        user=current_user,
        now=datetime.now(),
        approaching_pdc=approaching_pdc,
        approaching_rab=approaching_rab,
        approaching_gc=approaching_gc
    )


# Helper function to help both /visualization and /filtered_analytics routes 
def get_analytics_data(projects):
    from collections import Counter, defaultdict
    from datetime import datetime

    # Administrative Status Pie Chart
    admin_status_counts = Counter([p.administrative_status for p in projects if p.administrative_status])

    # Projects Sanctioned Per Year
    sanction_years = [p.sanctioned_date.year for p in projects if p.sanctioned_date]
    year_counts = Counter(sanction_years)
    sorted_years = sorted(year_counts.keys())
    year_labels = [str(y) for y in sorted_years]
    year_values = [year_counts[y] for y in sorted_years]

    # Donut Chart Data (Projects per Vertical)
    vertical_counts = Counter([p.vertical for p in projects if p.vertical])

    # Donut Chart Data (Verticals per Institute)
    institute_verticals = defaultdict(set)
    for p in projects:
        if p.academia and p.vertical:
            if ',' in p.academia:
                institute = p.academia.split(',', 1)[1].strip()
            else:
                institute = p.academia.strip()
            institute_verticals[institute].add(p.vertical)
    institute_vertical_counts = {inst: len(verts) for inst, verts in institute_verticals.items()}

    # Cost vs Institute
    cost_vs_institute = defaultdict(float)
    for p in projects:
        if p.academia and p.cost_lakhs:
            if ',' in p.academia:
                institute = p.academia.split(',', 1)[1].strip()
            else:
                institute = p.academia.strip()
            try:
                cost_vs_institute[institute] += float(p.cost_lakhs)
            except ValueError:
                continue
    cost_institute_labels = list(cost_vs_institute.keys())
    cost_institute_values = [cost_vs_institute[k] for k in cost_institute_labels]

    # Cost vs Vertical
    cost_vs_vertical = defaultdict(float)
    for p in projects:
        if p.vertical and p.cost_lakhs:
            try:
                cost_vs_vertical[p.vertical] += float(p.cost_lakhs)
            except ValueError:
                continue
    cost_vertical_labels = list(cost_vs_vertical.keys())
    cost_vertical_values = [cost_vs_vertical[k] for k in cost_vertical_labels]

    # Monthly Sanctions by Vertical (Stacked Bar)
    monthly_vertical_counts = defaultdict(lambda: defaultdict(int))
    all_verticals = set()
    for p in projects:
        if p.sanctioned_date and p.vertical:
            month = p.sanctioned_date.strftime('%Y-%m')
            monthly_vertical_counts[month][p.vertical] += 1
            all_verticals.add(p.vertical)
    stacked_labels = sorted(monthly_vertical_counts.keys())
    stacked_verticals = sorted(all_verticals)
    stacked_data = []
    for vertical in stacked_verticals:
        data = [monthly_vertical_counts[month].get(vertical, 0) for month in stacked_labels]
        stacked_data.append({'label': vertical, 'data': data})

    # Quarterly, Half-Yearly, Yearly Status Counts
    def get_financial_year(date):
        if date.month >= 4:
            return f"{date.year}-{str(date.year+1)[-2:]}"
        else:
            return f"{date.year-1}-{str(date.year)[-2:]}"
    def get_financial_quarter(date):
        fy = get_financial_year(date)
        if date.month in [4,5,6]:
            q = "Q1"
        elif date.month in [7,8,9]:
            q = "Q2"
        elif date.month in [10,11,12]:
            q = "Q3"
        else:
            q = "Q4"
        return f"{fy} {q}"
    def get_financial_half(date):
        fy = get_financial_year(date)
        if date.month >= 4 and date.month <= 9:
            h = "H1"
        else:
            h = "H2"
        return f"{fy} {h}"

    fy_set, fq_set, fh_set = set(), set(), set()
    for p in projects:
        if not p.sanctioned_date:
            continue
        fy_set.add(get_financial_year(p.sanctioned_date))
        fq_set.add(get_financial_quarter(p.sanctioned_date))
        fh_set.add(get_financial_half(p.sanctioned_date))
        closure_date = None
        if getattr(p, 'final_closure_date', None):
            closure_date = p.final_closure_date
        elif getattr(p, 'revised_pdc', None):
            closure_date = p.revised_pdc
        elif getattr(p, 'original_pdc', None):
            closure_date = p.original_pdc
        if closure_date:
            fy_set.add(get_financial_year(closure_date))
            fq_set.add(get_financial_quarter(closure_date))
            fh_set.add(get_financial_half(closure_date))

    year_labels_status = sorted(fy_set)
    quarter_labels = sorted(fq_set)
    half_labels = sorted(fh_set)

    status_period_counts = {
        'year': {fy: {'Open':0, 'Running':0, 'Closed':0} for fy in year_labels_status},
        'quarter': {fq: {'Open':0, 'Running':0, 'Closed':0} for fq in quarter_labels},
        'half': {fh: {'Open':0, 'Running':0, 'Closed':0} for fh in half_labels},
    }

    for p in projects:
        if not p.sanctioned_date:
            continue
        closure_date = None
        if getattr(p, 'final_closure_date', None):
            closure_date = p.final_closure_date
        elif getattr(p, 'revised_pdc', None):
            closure_date = p.revised_pdc
        elif getattr(p, 'original_pdc', None):
            closure_date = p.original_pdc

        for fy in year_labels_status:
            fy_start = datetime.strptime(fy.split('-')[0] + '-04-01', '%Y-%m-%d').date()
            fy_end = datetime.strptime(str(int(fy.split('-')[0])+1) + '-03-31', '%Y-%m-%d').date()
            if fy_start <= p.sanctioned_date <= fy_end:
                status_period_counts['year'][fy]['Open'] += 1
            elif closure_date and fy_start <= closure_date <= fy_end:
                status_period_counts['year'][fy]['Closed'] += 1
            elif p.sanctioned_date < fy_start and (not closure_date or closure_date > fy_end):
                status_period_counts['year'][fy]['Running'] += 1

        for fq in quarter_labels:
            y, q = fq.split()
            y_start = int(y.split('-')[0])
            if q == "Q1":
                q_start = datetime(y_start, 4, 1).date()
                q_end = datetime(y_start, 6, 30).date()
            elif q == "Q2":
                q_start = datetime(y_start, 7, 1).date()
                q_end = datetime(y_start, 9, 30).date()
            elif q == "Q3":
                q_start = datetime(y_start, 10, 1).date()
                q_end = datetime(y_start, 12, 31).date()
            else:
                q_start = datetime(y_start+1, 1, 1).date()
                q_end = datetime(y_start+1, 3, 31).date()
            if q_start <= p.sanctioned_date <= q_end:
                status_period_counts['quarter'][fq]['Open'] += 1
            elif closure_date and q_start <= closure_date <= q_end:
                status_period_counts['quarter'][fq]['Closed'] += 1
            elif p.sanctioned_date < q_start and (not closure_date or closure_date > q_end):
                status_period_counts['quarter'][fq]['Running'] += 1

        for fh in half_labels:
            y, h = fh.split()
            y_start = int(y.split('-')[0])
            if h == "H1":
                h_start = datetime(y_start, 4, 1).date()
                h_end = datetime(y_start, 9, 30).date()
            else:
                h_start = datetime(y_start, 10, 1).date()
                h_end = datetime(y_start+1, 3, 31).date()
            if h_start <= p.sanctioned_date <= h_end:
                status_period_counts['half'][fh]['Open'] += 1
            elif closure_date and h_start <= closure_date <= h_end:
                status_period_counts['half'][fh]['Closed'] += 1
            elif p.sanctioned_date < h_start and (not closure_date or closure_date > h_end):
                status_period_counts['half'][fh]['Running'] += 1

    quarter_data = {
        'Running': [status_period_counts['quarter'][q]['Running'] for q in quarter_labels],
        'Closed': [status_period_counts['quarter'][q]['Closed'] for q in quarter_labels],
        'Open': [status_period_counts['quarter'][q]['Open'] for q in quarter_labels],
    }
    half_data = {
        'Running': [status_period_counts['half'][h]['Running'] for h in half_labels],
        'Closed': [status_period_counts['half'][h]['Closed'] for h in half_labels],
        'Open': [status_period_counts['half'][h]['Open'] for h in half_labels],
    }
    year_data_status = {
        'Running': [status_period_counts['year'][y]['Running'] for y in year_labels_status],
        'Closed': [status_period_counts['year'][y]['Closed'] for y in year_labels_status],
        'Open': [status_period_counts['year'][y]['Open'] for y in year_labels_status],
    }

    # Average Project Duration by Sanction Year (in days)
    duration_by_year = {}
    for p in projects:
        if p.sanctioned_date:
            end_date = None
            if p.final_closure_date:
                end_date = p.final_closure_date
            elif p.revised_pdc:
                end_date = p.revised_pdc
            if end_date:
                year = p.sanctioned_date.year
                duration = (end_date - p.sanctioned_date).days
                duration_by_year.setdefault(year, []).append(duration)
    avg_duration_labels = sorted([str(y) for y in duration_by_year.keys()])
    avg_duration_values = [
        round(sum(duration_by_year[int(y)]) / len(duration_by_year[int(y)]), 1)
        for y in avg_duration_labels
    ]

    # Project Status Breakdown by Vertical
    vertical_status_counts = defaultdict(lambda: {'Running': 0, 'Closed': 0, 'Open': 0})
    for p in projects:
        if not p.vertical:
            continue
        closure_date = None
        if getattr(p, 'final_closure_date', None):
            closure_date = p.final_closure_date
        elif getattr(p, 'revised_pdc', None):
            closure_date = p.revised_pdc
        elif getattr(p, 'original_pdc', None):
            closure_date = p.original_pdc
        today = datetime.today().date()
        if closure_date and closure_date <= today:
            vertical_status_counts[p.vertical]['Closed'] += 1
        elif p.sanctioned_date and p.sanctioned_date.year == today.year and (not closure_date or closure_date > today):
            vertical_status_counts[p.vertical]['Open'] += 1
        else:
            vertical_status_counts[p.vertical]['Running'] += 1
    vertical_status_labels = sorted(vertical_status_counts.keys())
    vertical_status_data = {
        'Running': [vertical_status_counts[v]['Running'] for v in vertical_status_labels],
        'Closed': [vertical_status_counts[v]['Closed'] for v in vertical_status_labels],
        'Open': [vertical_status_counts[v]['Open'] for v in vertical_status_labels],
    }

    # Projects by Funding Range (Histogram)
    funding_brackets = [
        (0, 50), (50, 100), (100, 200), (200, 500), (500, 1000), (1000, 5000), (5000, 10000)
    ]
    funding_labels = [f"{low}-{high}L" for (low, high) in funding_brackets]
    funding_counts = [0 for _ in funding_brackets]
    for p in projects:
        if p.cost_lakhs is not None:
            for i, (low, high) in enumerate(funding_brackets):
                if low <= p.cost_lakhs < high:
                    funding_counts[i] += 1
                    break

    # Top Institutes by Number of Projects
    institute_counts = Counter()
    for p in projects:
        if p.academia:
            if ',' in p.academia:
                institute = p.academia.split(',', 1)[1].strip()
            else:
                institute = p.academia.strip()
            institute_counts[institute] += 1
    top_n = 10
    top_institutes = institute_counts.most_common(top_n)
    top_institute_labels = [x[0] for x in top_institutes]
    top_institute_values = [x[1] for x in top_institutes]

    pi_names = []
    for p in projects:
        if p.pi_name:
            before_comma = p.pi_name.split(',')[0]
            for name in before_comma.split('/'):
                clean_name = name.strip()
                if clean_name:
                    pi_names.append(clean_name)
    pi_counts = Counter(pi_names)
    top_pis = pi_counts.most_common(10)
    top_pis_labels = [pi[0] for pi in top_pis]
    top_pis_values = [pi[1] for pi in top_pis]

    # Administrative Status Trend (Line/Area Chart)
    status_trend = defaultdict(lambda: defaultdict(int))
    today = datetime.today().date()
    for p in projects:
        if p.sanctioned_date:
            start_year = p.sanctioned_date.year
            closure_date = None
            if getattr(p, 'final_closure_date', None):
                closure_date = p.final_closure_date
            elif getattr(p, 'revised_pdc', None):
                closure_date = p.revised_pdc
            elif getattr(p, 'original_pdc', None):
                closure_date = p.original_pdc
            end_year = closure_date.year if closure_date and closure_date <= today else today.year
            for year in range(start_year, end_year + 1):
                if year == end_year and closure_date and closure_date.year == year and closure_date <= today:
                    status_trend["Completed"][year] += 1
                else:
                    status_trend["Ongoing"][year] += 1
    all_statuses = sorted(status_trend.keys())
    all_years = sorted({year for status in status_trend.values() for year in status.keys()})
    status_trend_labels = [str(y) for y in all_years]
    status_trend_datasets = []
    for i, status in enumerate(all_statuses):
        data = [status_trend[status].get(y, 0) for y in all_years]
        status_trend_datasets.append({
            "label": status,
            "data": data,
        })

    # Sanctioned Cost Trend per Year
    cost_trend_year = {}
    for p in projects:
        if p.sanctioned_date and p.cost_lakhs is not None:
            year = p.sanctioned_date.year
            try:
                cost_trend_year[year] = cost_trend_year.get(year, 0) + float(p.cost_lakhs)
            except ValueError:
                continue
    cost_trend_year_labels = sorted(cost_trend_year.keys())
    cost_trend_year_values = [cost_trend_year[y] for y in cost_trend_year_labels]

    # Projects by Stakeholder Lab
    stakeholder_counts = Counter()
    for p in projects:
        if p.stakeholders:
            labs = [lab.strip() for lab in str(p.stakeholders).split(',') if lab.strip()]
            for lab in labs:
                stakeholder_counts[lab] += 1
    stakeholder_lab_labels = list(stakeholder_counts.keys())
    stakeholder_lab_values = [stakeholder_counts[k] for k in stakeholder_lab_labels]

    return dict(
        admin_status_counts=admin_status_counts,
        year_labels=year_labels,
        year_values=year_values,
        vertical_counts=vertical_counts,
        institute_vertical_counts=institute_vertical_counts,
        cost_institute_labels=cost_institute_labels,
        cost_institute_values=cost_institute_values,
        cost_vertical_labels=cost_vertical_labels,
        cost_vertical_values=cost_vertical_values,
        stacked_labels=stacked_labels,
        stacked_verticals=stacked_verticals,
        stacked_data=stacked_data,
        quarter_labels=quarter_labels,
        quarter_data=quarter_data,
        half_labels=half_labels,
        half_data=half_data,
        year_labels_status=year_labels_status,
        year_data_status=year_data_status,
        avg_duration_labels=avg_duration_labels,
        avg_duration_values=avg_duration_values,
        vertical_status_labels=vertical_status_labels,
        vertical_status_data=vertical_status_data,
        funding_labels=funding_labels,
        funding_counts=funding_counts,
        top_institute_labels=top_institute_labels,
        top_institute_values=top_institute_values,
        top_pis_labels=top_pis_labels,
        top_pis_values=top_pis_values,
        status_trend_labels=status_trend_labels,
        status_trend_datasets=status_trend_datasets,
        cost_trend_year_labels=cost_trend_year_labels,
        cost_trend_year_values=cost_trend_year_values,
        stakeholder_lab_labels=stakeholder_lab_labels,
        stakeholder_lab_values=stakeholder_lab_values,
    )

# Route for the Data Analytics Page
@app.route('/visualization')
@login_required
def visualization():
    if current_user.role == 'manager':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))
    projects = Project.query.all()
    analytics = get_analytics_data(projects)
    return render_template('main/visualization.html', filtered=False, **analytics)


#Route for filtered data analytics
@app.route('/filtered_analytics')
@login_required
def filtered_analytics():
    query = Project.query
    if current_user.role == 'manager':
        query = query.filter(Project.scientist.ilike(f"%{current_user.coord_scientist}%"))
    column = request.args.get('column', '')
    value = request.args.get('value', '').strip()
    cost_min = request.args.get('cost_min', '').strip()
    cost_max = request.args.get('cost_max', '').strip()
    sanction_year_start = request.args.get('sanction_year_start', '').strip()
    sanction_year_end = request.args.get('sanction_year_end', '').strip()

    if column and (value or (column == 'cost_lakhs' and (cost_min or cost_max)) or (column == 'sanction_year' and (sanction_year_start or sanction_year_end))):
        if column == 'serial_no':
            query = query.filter(Project.serial_no.ilike(f"%{value}%"))
        elif column == 'title':
            query = query.filter(Project.title.ilike(f"%{value}%"))
        elif column == 'vertical':
            query = query.filter(Project.vertical.ilike(f"%{value}%"))
        elif column == 'academia':
            query = query.filter(Project.academia.ilike(f"%{value}%"))
        elif column == 'pi_name':
            query = query.filter(Project.pi_name.ilike(f"%{value}%"))
        elif column == 'coord_lab':
            query = query.filter(Project.coord_lab.ilike(f"%{value}%"))
        elif column == 'scientist':
            query = query.filter(Project.scientist.ilike(f"%{value}%"))
        elif column == 'cost_lakhs':
            try:
                if cost_min:
                    query = query.filter(Project.cost_lakhs >= float(cost_min))
                if cost_max:
                    query = query.filter(Project.cost_lakhs <= float(cost_max))
            except ValueError:
                pass
        elif column in ['sanctioned_date', 'original_pdc', 'revised_pdc']:
            try:
                date_value = datetime.strptime(value, "%Y-%m-%d").date()
                query = query.filter(getattr(Project, column) == date_value)
            except ValueError:
                pass
        elif column == 'administrative_status':
            query = query.filter(Project.administrative_status.ilike(f"%{value}%"))
        elif column == 'sanction_year':
            try:
                if sanction_year_start:
                    query = query.filter(db.extract('year', Project.sanctioned_date) >= int(sanction_year_start))
                if sanction_year_end:
                    query = query.filter(db.extract('year', Project.sanctioned_date) <= int(sanction_year_end))
                # fallback for single value (if only value is provided)
                if not (sanction_year_start or sanction_year_end) and value:
                    year = int(value)
                    query = query.filter(db.extract('year', Project.sanctioned_date) == year)
            except ValueError:
                pass

    projects = query.order_by(db.cast(Project.serial_no, db.Integer)).all()
    analytics = get_analytics_data(projects)
    return render_template('partials/analytics_charts.html', filtered=True,**analytics)


# Route for the add project page (admin only)
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_project():
    if current_user.role != 'admin':
        flash("Unauthorized access. You do not have permission to add projects.", "danger")
        return redirect(url_for('dashboard'))

    form = ProjectForm()
    if form.validate_on_submit():
        
        if form.original_pdc.data < form.sanctioned_date.data:
            flash("Original PDC cannot be before the Sanctioned Date.", "danger")
            return render_template('projects/add_project.html', form=form)
        if form.revised_pdc.data < form.original_pdc.data:
            flash("Revised PDC cannot be before the Original PDC.","danger")
            return render_template('projects/add_project.html', form=form)
        
        existing_project = Project.query.filter_by(serial_no=form.serial_no.data).first()
        if existing_project:
            form.serial_no.errors.append("Project with this serial number already exists")
            return render_template('projects/add_project.html', form=form)
        

        signed_forms_filenames = []
        if form.duely_signed_forms.data:
            for file in form.duely_signed_forms.data:
                filename = None
                saved = save_files([file])
                if saved:
                    filename = saved[0][0]
                if filename:
                    signed_forms_filenames.append(filename)

        rab_filenames = []
        if form.rab_minutes.data:
            for file in form.rab_minutes.data:
                filename = None
                saved = save_files([file])
                if saved:
                    filename = saved[0][0]
                if filename:
                    rab_filenames.append(filename)

        gc_filenames = []
        if form.gc_minutes.data:
            for file in form.gc_minutes.data:
                filename = None
                saved = save_files([file])
                if saved:
                    filename = saved[0][0]
                if filename:
                    gc_filenames.append(filename)

        final_report_filenames = []
        if form.final_report.data:
            for file in form.final_report.data:
                filename = None
                saved = save_files([file])
                if saved:
                    filename = saved[0][0]
                if filename:
                    final_report_filenames.append(filename)

       
        project = Project(
            serial_no=form.serial_no.data,
            title=form.title.data,
            academia=form.academia.data,
            pi_name=form.pi_name.data,
            coord_lab=form.coord_lab.data,
            scientist=form.scientist.data,
            vertical=form.vertical.data,
            cost_lakhs=form.cost_lakhs.data,
            sanctioned_date=form.sanctioned_date.data, 
            original_pdc=form.original_pdc.data,
            revised_pdc=form.revised_pdc.data,
            stakeholders=form.stakeholders.data,
            scope_objective=form.scope_objective.data,
            expected_deliverables=form.expected_deliverables.data,
            Outcome_Dovetailing_with_Ongoing_Work=form.Outcome_Dovetailing_with_Ongoing_Work.data,
            duely_signed_forms=','.join(signed_forms_filenames),
            rab_meeting_date=form.rab_meeting_date.data,
            rab_meeting_held_date=form.rab_meeting_held_date.data,
            rab_minutes=','.join(rab_filenames),
            gc_meeting_date=form.gc_meeting_date.data,
            gc_meeting_held_date=form.gc_meeting_held_date.data,
            technical_status=form.technical_status.data,
            administrative_status=form.administrative_status.data,
            final_closure_date=form.final_closure_date.data,
            final_closure_remarks=form.final_closure_remarks.data,
            final_report=','.join(final_report_filenames)
        )
        db.session.add(project)
        db.session.commit()
        log_action(current_user, f"Added project '{form.title.data}'")
        flash("Project added successfully.", "success")
        return redirect(url_for('dashboard'))

    return render_template('projects/add_project.html', form=form)

# Route for the upload form page
@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    
    if ' ' in filename:
        original_name = filename.split(' ', 1)[1]
    elif filename[:36].count('-') == 4 and filename[36] == '_':
        original_name = filename[37:]
    elif '_' in filename:
        original_name = filename.split('_', 1)[1]
    else:
        original_name = filename

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True,
        download_name=original_name
    )


# Route for the upload form page
@app.route('/upload_form', methods=['GET', 'POST'])
@login_required
def upload_form():
    form = UploadForm()
    if form.validate_on_submit():
        files = form.files.data  
        if not files:
            flash("No files selected for upload.", "danger")
            return render_template('forms/upload_form.html', form=form)

        
        saved_files = save_files(files)
        if not saved_files:
            flash("Failed to save files. Please try again.", "danger")
            return render_template('forms/upload_form.html', form=form)

        
        filenames = ','.join([file[0] for file in saved_files])  
        file_types = ','.join([file[1] for file in saved_files])  

        
        filename = saved_files[0][0] if saved_files else None

        try:
            
            notice_form = NoticeForm(
                form_no=form.form_no.data,
                title=form.title.data,
                submission_schedule=form.submission_schedule.data,
                filename=filename,  
                filenames=filenames,  
                file_types=file_types  
            )
            db.session.add(notice_form)
            db.session.commit()
            log_action(current_user, f"Uploaded form '{form.form_no.data}'")
            flash('Files uploaded successfully!', 'success')
            return redirect(url_for('forms'))
        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred while saving the form: {e}", "danger")
            return render_template('forms/upload_form.html', form=form)

    return render_template('forms/upload_form.html', form=form)


# Route for listing all forms
@app.route('/manage_form_action', methods=['POST'])
@login_required
def manage_form_action():
    if current_user.role != 'admin':
        return "Unauthorized", 403
    form_id = request.form.get('form_id')
    action = request.form.get('action')
    if not form_id or not action:
        flash("Please select a form and action.", "danger")
        return redirect(url_for('forms'))
    if action == "edit":
        return redirect(url_for('edit_form', form_id=form_id))
    elif action == "delete":
        form_obj = NoticeForm.query.get_or_404(form_id)
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], form_obj.filename))
        except Exception:
            pass
        db.session.delete(form_obj)
        db.session.commit()
        log_action(current_user, f"Deleted form '{form_obj.form_no}'")
        flash('Form deleted successfully!', 'success')
        return redirect(url_for('forms'))
    else:
        flash("Invalid action.", "danger")
        return redirect(url_for('forms'))


# Route for listing all forms
@app.route('/edit_form/<int:form_id>', methods=['GET', 'POST'])
@login_required
def edit_form(form_id):
    form = NoticeForm.query.get_or_404(form_id)

    
    files = []
    if form.filenames:
        filenames = form.filenames.split(',')
        file_types = form.file_types.split(',') if form.file_types else [''] * len(filenames)
        for idx, filename in enumerate(filenames):
            files.append({
                'id': idx,  
                'filename': filename,
                'original_name': filename.split('_', 1)[-1],  
                'file_type': file_types[idx] if idx < len(file_types) else ''
            })

    if request.method == 'POST':
        form.form_no = request.form['form_no']
        form.title = request.form['title']
        form.submission_schedule = request.form['submission_schedule']

        
        delete_files = request.form.get('delete_files', '')
        delete_indices = [int(i) for i in delete_files.split(',') if i.strip().isdigit()]
        filenames = form.filenames.split(',') if form.filenames else []
        file_types = form.file_types.split(',') if form.file_types else []

        
        for idx in sorted(delete_indices, reverse=True):
            if 0 <= idx < len(filenames):
                try:
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filenames[idx]))
                except Exception:
                    pass
                del filenames[idx]
                if idx < len(file_types):
                    del file_types[idx]
        form.filenames = ','.join(filenames)
        form.file_types = ','.join(file_types)

        # Handle new file uploads
        uploaded_files = request.files.getlist('form_files')
        saved_files = save_files(uploaded_files)
        if saved_files:
            existing_filenames = form.filenames.split(',') if form.filenames else []
            existing_file_types = form.file_types.split(',') if form.file_types else []
            for fname, ftype in saved_files:
                existing_filenames.append(fname)
                existing_file_types.append(ftype)
            form.filenames = ','.join(existing_filenames)
            form.file_types = ','.join(existing_file_types)

        db.session.commit()
        log_action(current_user, f"Edited form '{form.form_no}'")
        flash('Form updated successfully!', 'success')
        return redirect(url_for('forms'))

    return render_template('forms/edit_form.html', form=form, files=files)




# Route for deleting a file from a form
@app.route('/delete_file', methods=['POST'])
@login_required
def delete_file():
    form_id = request.args.get('form_id', type=int)
    file_id = request.args.get('file_id', type=int)
    form = NoticeForm.query.get_or_404(form_id)

    filenames = form.filenames.split(',') if form.filenames else []
    file_types = form.file_types.split(',') if form.file_types else []

    if 0 <= file_id < len(filenames):
        # Remove file from disk
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filenames[file_id]))
        except Exception:
            pass
        # Remove from lists
        del filenames[file_id]
        if file_id < len(file_types):
            del file_types[file_id]
        form.filenames = ','.join(filenames)
        form.file_types = ','.join(file_types)
        db.session.commit()
        log_action(current_user, f"Deleted file from form '{form.form_no}'")
        flash('File deleted successfully!', 'success')
    else:
        flash('File not found.', 'danger')

    return redirect(url_for('edit_form', form_id=form_id))



# Route for listing all forms
@app.route('/delete_form/<int:form_id>', methods=['POST'])
@login_required
def delete_form(form_id):
    if current_user.role != 'admin':
        return "Unauthorized", 403
    form_obj = NoticeForm.query.get_or_404(form_id)
    # Optionally delete the file from disk
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], form_obj.filename))
    except Exception:
        pass
    db.session.delete(form_obj)
    db.session.commit()
    log_action(current_user, f"Deleted form '{form_obj.form_no}'")
    flash('Form deleted successfully!', 'success')
    return redirect(url_for('forms'))


# Route for listing all forms
@app.route('/forms/<filename>')
@login_required
def serve_form(filename):
    # If filename starts with a UUID (36 chars + '_'), strip it, else use as-is
    if len(filename) > 37 and filename[:36].count('-') == 4 and filename[36] == '_':
        original_name = filename[37:]
    else:
        original_name = filename

    print(f"DEBUG: filename={filename}, original_name={original_name}")

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True,
        download_name=original_name
    )



# Route to post technical status updates
@app.route('/post_technical_status/<int:project_id>', methods=['POST'])
@login_required
def post_technical_status(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update Technical Status.'}), 403
    technical_status = request.form.get('technical_status', '').strip()
    if technical_status:
        # Append technical_status with username and timestamp (optional)
        timestamp = datetime.now(timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M')
        new_technical_status = f"{current_user.username} ({timestamp}): {technical_status}"
        if project.technical_status:
            project.technical_status += "\n" + new_technical_status
        else:
            project.technical_status = new_technical_status
        db.session.commit()
        log_action(current_user, f"Updated technical status of project '{project.title}'")
        return jsonify({'success': True, 'technical_status': new_technical_status})
    return jsonify({'success': False, 'message': 'Technical Status cannot be empty.'}), 400




# Route to post administrative status updates
@app.route('/post_rab_meeting_scheduled_date/<int:project_id>', methods=['POST'])
@login_required
def post_rab_meeting_scheduled_date(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update RAB Meeting Scheduled Date.'}), 403
    rab_meeting_date = request.form.get('rab_meeting_date', '').strip()
    if rab_meeting_date:
        try:
            # Parse and store as date object
            project.rab_meeting_date = datetime.strptime(rab_meeting_date, "%Y-%m-%d")
            db.session.commit()
            log_action(current_user, f"Updated RAB Meeting Scheduled Date '{project.title}'")
            return jsonify({'success': True, 'rab_meeting_date': rab_meeting_date})
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format.'}), 400
    return jsonify({'success': False, 'message': 'RAB Meeting Scheduled Date cannot be empty.'}), 400



# Route to post RAB Meeting Held Date
@app.route('/post_rab_meeting_held_date/<int:project_id>', methods=['POST'])
@login_required
def post_rab_meeting_held_date(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update RAB Meeting Held Date.'}), 403

    rab_meeting_held_date = request.form.get('rab_meeting_held_date', '').strip()
    if rab_meeting_held_date:
        try:
            
            new_rab_meeting_held_date = datetime.strptime(rab_meeting_held_date, '%Y-%m-%d').date()
            project.rab_meeting_held_date = new_rab_meeting_held_date
            db.session.commit()
            log_action(current_user, f"Updated RAB Meeting Held Date for '{project.title}'")
            return jsonify({'success': True, 'rab_meeting_held_date': str(new_rab_meeting_held_date)})
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format. Use YYYY-MM-DD.'}), 400

    return jsonify({'success': False, 'message': 'RAB Meeting Held Date cannot be empty.'}), 400



# Route to post RAB Minutes of Meeting
@app.route('/post_rab_minutes_of_meeting/<int:project_id>', methods=['POST'])
@login_required
def post_rab_minutes_of_meeting(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update RAB Minutes of Meeting.'}), 403
    rab_minutes = request.form.get('rab_minutes', '').strip()
    if rab_minutes:
        new_rab_minutes = f"{rab_minutes}"
        if project.rab_minutes:
            project.rab_minutes += "\n" + new_rab_minutes
        else:
            project.rab_minutes = new_rab_minutes
        db.session.commit()
        log_action(current_user, f"Updated RAB Minutes of Meeting '{project.title}'")
        return jsonify({'success': True, 'rab_minutes': new_rab_minutes})
    return jsonify({'success': False, 'message': 'RAB Minutes of Meeting cannot be empty.'}), 400



# Route to post GC Meeting Scheduled Date
@app.route('/post_gc_meeting_scheduled_date/<int:project_id>', methods=['POST'])
@login_required
def post_gc_meeting_scheduled_date(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update GC Meeting Scheduled Date.'}), 403

    gc_meeting_date = request.form.get('gc_meeting_date', '').strip()
    if gc_meeting_date:
        try:
            # Convert string to Python date object
            new_gc_meeting_date = datetime.strptime(gc_meeting_date, '%Y-%m-%d').date()
            project.gc_meeting_date = new_gc_meeting_date
            db.session.commit()
            log_action(current_user, f"Updated GC Meeting Scheduled Date for '{project.title}'")
            return jsonify({'success': True, 'gc_meeting_date': str(new_gc_meeting_date)})
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format. Use YYYY-MM-DD.'}), 400

    return jsonify({'success': False, 'message': 'GC Meeting Scheduled Date cannot be empty.'}), 400




# Route to post GC Meeting Held Date
@app.route('/post_gc_meeting_held_date/<int:project_id>', methods=['POST'])
@login_required
def post_gc_meeting_held_date(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update GC Meeting Held Date.'}), 403

    gc_meeting_held_date = request.form.get('gc_meeting_held_date', '').strip()
    if gc_meeting_held_date:
        try:
            # Convert string to Python date object
            new_gc_meeting_held_date = datetime.strptime(gc_meeting_held_date, '%Y-%m-%d').date()
            project.gc_meeting_held_date = new_gc_meeting_held_date
            db.session.commit()
            log_action(current_user, f"Updated GC Meeting Held Date for '{project.title}'")
            return jsonify({'success': True, 'gc_meeting_held_date': str(new_gc_meeting_held_date)})
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format. Use YYYY-MM-DD.'}), 400

    return jsonify({'success': False, 'message': 'GC Meeting Held Date cannot be empty.'}), 400



# Route to post GC Minutes of Meeting
@app.route('/post_gc_minutes_of_meeting/<int:project_id>', methods=['POST'])
@login_required
def post_gc_minutes_of_meeting(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update GC Minutes of Meeting.'}), 403
    gc_minutes = request.form.get('gc_minutes', '').strip()
    if gc_minutes:
        new_gc_minutes = f"{gc_minutes}"
        if project.gc_minutes:
            project.gc_minutes += "\n" + new_gc_minutes
        else:
            project.gc_minutes = new_gc_minutes
        db.session.commit()
        log_action(current_user, f"Updated GC Minutes of Meeting '{project.title}'")
        return jsonify({'success': True, 'gc_minutes': new_gc_minutes})
    return jsonify({'success': False, 'message': 'GC Minutes of Meeting cannot be empty.'}), 400



# Route for the modify search page (admin only)
@app.route('/modify_search', methods=['GET'])
@login_required
def modify_search():
    if current_user.role != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))

    query = Project.query
    column = request.args.get('column', '')
    value = request.args.get('value', '').strip()

    if column and value:
        if column == 'serial_no':
            query = query.filter(Project.serial_no.ilike(f"%{value}%"))
        elif column == 'title':
            query = query.filter(Project.title.ilike(f"%{value}%"))
        elif column == 'vertical':
            query = query.filter(Project.vertical.ilike(f"%{value}%"))
        elif column == 'academia':
            query = query.filter(Project.academia.ilike(f"%{value}%"))
        elif column == 'pi_name':
            query = query.filter(Project.pi_name.ilike(f"%{value}%"))
        elif column == 'coord_lab':
            query = query.filter(Project.coord_lab.ilike(f"%{value}%"))
        elif column == 'scientist':
            query = query.filter(Project.scientist.ilike(f"%{value}%"))
        elif column == 'cost_lakhs':
            try:
                cost = float(value)
                query = query.filter(Project.cost_lakhs == cost)
            except ValueError:
                pass
        elif column == 'sanctioned_date':
            try:
                query = query.filter(Project.sanctioned_date == value)
            except ValueError:
                pass
        elif column == 'original_pdc':
            try:
                query = query.filter(Project.original_pdc == value)
            except ValueError:
                pass
        elif column == 'revised_pdc':
            try:
                query = query.filter(Project.revised_pdc == value)
            except ValueError:
                pass
        elif column == 'administrative_status':
            query = query.filter(Project.administrative_status.ilike(f"%{value}%"))

        projects = query.all()
    else:
        projects = None

    return render_template('projects/modify_search.html', projects=projects)



# Route for the edit project page (Admin only)
@app.route('/edit/<int:project_id>', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    if current_user.role != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))

    project = Project.query.get_or_404(project_id)
    form = ProjectForm(obj=project)

    if form.validate_on_submit():
        # Date validations (same as in add_project)
        if form.original_pdc.data <= form.sanctioned_date.data:
            flash("Original PDC cannot be before or equal to the Sanctioned Date.", "danger")
            return render_template('projects/edit_project.html', form=form, project=project)
        if form.revised_pdc.data < form.original_pdc.data:
            flash("Revised PDC cannot be before the Original PDC.", "danger")
            return render_template('projects/edit_project.html', form=form, project=project)

        # signed_forms
        duely_signed_forms_filenames = project.duely_signed_forms.split(',') if project.duely_signed_forms else []
        if form.duely_signed_forms.data:
            for file in form.duely_signed_forms.data:
                if hasattr(file, "filename") and file.filename:
                    saved = save_files([file])
                    if saved:
                        duely_signed_forms_filenames.append(saved[0][0])
        project.duely_signed_forms = ','.join([f for f in duely_signed_forms_filenames if f])

        # rab_minutes
        rab_filenames = project.rab_minutes.split(',') if project.rab_minutes else []
        if form.rab_minutes.data:
            for file in form.rab_minutes.data:
                if hasattr(file, "filename") and file.filename:
                    saved = save_files([file])
                    if saved:
                        rab_filenames.append(saved[0][0])
        project.rab_minutes = ','.join([f for f in rab_filenames if f])

        # gc_minutes
        gc_filenames = project.gc_minutes.split(',') if project.gc_minutes else []
        if form.gc_minutes.data:
            for file in form.gc_minutes.data:
                if hasattr(file, "filename") and file.filename:
                    saved = save_files([file])
                    if saved:
                        gc_filenames.append(saved[0][0])
        project.gc_minutes = ','.join([f for f in gc_filenames if f])

        # final_report
        final_report_filenames = project.final_report.split(',') if project.final_report else []
        if form.final_report.data:
            for file in form.final_report.data:
                if hasattr(file, "filename") and file.filename:
                    saved = save_files([file])
                    if saved:
                        final_report_filenames.append(saved[0][0])
        project.final_report = ','.join([f for f in final_report_filenames if f])

        # Update project
        exclude_fields = ['duely_signed_forms', 'rab_minutes', 'gc_minutes', 'final_report']
        for field in form:
            if field.name not in exclude_fields and hasattr(project, field.name):
                setattr(project, field.name, field.data)

        db.session.commit()
        log_action(current_user, f"Edited project '{project.title}'")
        flash('Project updated successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('projects/edit_project.html', form=form, project=project)




# Route for removing a file from a project (Admin only)
@app.route('/remove_mom_file/<int:project_id>/<mom_type>/<filename>')
@login_required
def remove_mom_file(project_id, mom_type, filename):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dashboard'))
    if mom_type == 'duely_signed_forms':
        files = project.duely_signed_forms.split(',') if project.duely_signed_forms else []
        files = [f for f in files if f != filename]
        project.duely_signed_forms = ','.join(files)
    elif mom_type == 'rab':
        files = project.rab_minutes.split(',') if project.rab_minutes else []
        files = [f for f in files if f != filename]
        project.rab_minutes = ','.join(files)
    elif mom_type == 'gc':
        files = project.gc_minutes.split(',') if project.gc_minutes else []
        files = [f for f in files if f != filename]
        project.gc_minutes = ','.join(files)
    elif mom_type == 'final_report':  
        files = project.final_report.split(',') if project.final_report else []
        files = [f for f in files if f != filename]
        project.final_report = ','.join(files)
    # Optionally delete file from disk
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    except Exception:
        pass
    db.session.commit()
    log_action(current_user, f"Removed {mom_type} file '{filename}' from project '{project.title}'")
    flash("File removed.", "success")
    return redirect(request.referrer or url_for('dashboard'))




# Route for the delete project page (Admin only)
@app.route('/delete', methods=['GET', 'POST'])
@login_required
def delete_project():
    if current_user.role != 'admin':
        flash("Unauthorized access. You do not have permission to delete projects", "danger")
        return redirect(url_for('dashboard'))

    query = Project.query   

    # Dropdown filter logic
    column = request.args.get('column', '')
    value = request.args.get('value', '').strip()
    if column and value:
        if column == 'serial_no':
            query = query.filter(Project.serial_no.ilike(f"%{value}%"))
        elif column == 'title':
            query = query.filter(Project.title.ilike(f"%{value}%"))

    projects = query.order_by(Project.serial_no).all()

    if request.method == 'POST':
        project_id = request.form.get('project_id')
        project = Project.query.get(project_id)
        if project:
            db.session.delete(project)
            db.session.commit()
            log_action(current_user, f"Deleted project '{project.title}'")
            flash("Project deleted successfully.", "success")
            return redirect(url_for('delete_project'))
        else:
            flash("Project not found.", "danger")

    return render_template('projects/delete_proj.html', projects=projects, now=datetime.now())



# Route for uploading minutes of meeting (Admin only)
@app.route('/upload_mom/<int:project_id>/<mom_type>', methods=['POST'])
@login_required
def upload_mom(project_id, mom_type):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dashboard'))
    file = request.files.get('mom_file')
    if file and file.filename.endswith('.pdf'):
        saved = save_files([file])
        if saved:
            filename = saved[0][0]
        if mom_type == 'duely_signed_forms':
            files = project.duely_signed_forms.split(',') if project.duely_signed_forms else []
            files.append(filename)
            project.duely_signed_forms = ','.join(files)
        elif mom_type == 'rab':
            files = project.rab_minutes.split(',') if project.rab_minutes else []
            files.append(filename)
            project.rab_minutes = ','.join(files)
        elif mom_type == 'gc':
            files = project.gc_minutes.split(',') if project.gc_minutes else []
            files.append(filename)
            project.gc_minutes = ','.join(files)
        db.session.commit()
        log_action(current_user, f"Uploaded {mom_type} file '{filename}' to project '{project.title}'")
        flash("PDF attached successfully.", "success")
    else:
        flash("Please upload a valid PDF file.", "danger")
    return redirect(request.referrer or url_for('dashboard'))



# Route for the download CSV
@app.route('/download_csv', methods=['GET'])
@login_required
def download_csv():
    projects = Project.query.order_by(db.cast(Project.serial_no, db.Integer)).all()
    output = StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Header row (same as filtered, no minutes columns)
    writer.writerow([
        "S. No", "Nomenclature", "Academia/Institute", "PI Name", "Coordinating Lab",
        "Coordinating Lab Scientist", "Research Vertical", "Sanctioned Cost (in Lakhs)",
        "Sanctioned Date", "Original PDC", "Revised PDC", "Stake Holding Labs",
        "Scope/Objective of the Project", "Expected Deliverables/Technology",
        "Outcome Dovetailing with Ongoing Work", "RAB Meeting Scheduled Date",
        "RAB Meeting Held Date", "GC Meeting Scheduled Date",
        "GC Meeting Held Date", "Technical Status",
        "Administrative Status", "Final Closure Status"
    ])

    for project in projects:
        writer.writerow([
            project.serial_no,
            project.title or '',
            project.academia or '',
            project.pi_name or '',
            project.coord_lab or '',
            project.scientist or '',
            project.vertical or '',
            project.cost_lakhs or '',
            project.sanctioned_date or '',
            project.original_pdc or '',
            project.revised_pdc or '',
            project.stakeholders or '',
            project.scope_objective or '',
            project.expected_deliverables or '',
            project.Outcome_Dovetailing_with_Ongoing_Work or '',
            project.rab_meeting_date or '',
            project.rab_meeting_held_date or '',
            project.gc_meeting_date or '',
            project.gc_meeting_held_date or '',
            (project.technical_status or '').replace('\n', ' | '),
            project.administrative_status or '',
            (str(project.final_closure_date) if project.final_closure_date else '') +
            (" | " + project.final_closure_remarks if project.final_closure_remarks else "")
        ])

    output.seek(0)
    current_date = datetime.now().strftime("%Y-%m-%d")
    filename = f"DIA_CoE_{current_date}.csv"
    response = app.response_class(
        response=output.getvalue(),
        status=200,
        mimetype='text/csv'
    )
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response


# Route for the download filtered CSV
@app.route('/download_filtered_csv', methods=['GET'])
@login_required
def download_filtered_csv():
    query = Project.query
    if current_user.role == 'manager':
        query = query.filter(Project.scientist.ilike(f"%{current_user.coord_scientist}%"))
    column = request.args.get('column', '')
    value = request.args.get('value', '').strip()
    cost_min = request.args.get('cost_min', '').strip()
    cost_max = request.args.get('cost_max', '').strip()
    sanction_year_start = request.args.get('sanction_year_start', '').strip()
    sanction_year_end = request.args.get('sanction_year_end', '').strip()

    if column and (
        value or 
        (column == 'cost_lakhs' and (cost_min or cost_max)) or
        (column == 'sanction_year' and (sanction_year_start or sanction_year_end))
    ):
        if column == 'serial_no':
            query = query.filter(Project.serial_no.ilike(f"%{value}%"))
        elif column == 'title':
            query = query.filter(Project.title.ilike(f"%{value}%"))
        elif column == 'vertical':
            query = query.filter(Project.vertical.ilike(f"%{value}%"))
        elif column == 'academia':
            query = query.filter(Project.academia.ilike(f"%{value}%"))
        elif column == 'pi_name':
            query = query.filter(Project.pi_name.ilike(f"%{value}%"))
        elif column == 'coord_lab':
            query = query.filter(Project.coord_lab.ilike(f"%{value}%"))
        elif column == 'scientist':
            query = query.filter(Project.scientist.ilike(f"%{value}%"))
        elif column == 'cost_lakhs':
            try:
                if cost_min:
                    query = query.filter(Project.cost_lakhs >= float(cost_min))
                if cost_max:
                    query = query.filter(Project.cost_lakhs <= float(cost_max))
            except ValueError:
                pass
        elif column in ['sanctioned_date', 'original_pdc', 'revised_pdc']:
            try:
                date_value = datetime.strptime(value, "%Y-%m-%d").date()
                query = query.filter(getattr(Project, column) == date_value)
            except ValueError:
                pass
        elif column == 'administrative_status':
            query = query.filter(Project.administrative_status.ilike(f"%{value}%"))
        elif column == 'sanction_year':
            try:
                if sanction_year_start:
                    query = query.filter(db.extract('year', Project.sanctioned_date) >= int(sanction_year_start))
                if sanction_year_end:
                    query = query.filter(db.extract('year', Project.sanctioned_date) <= int(sanction_year_end))
                if not (sanction_year_start or sanction_year_end) and value:
                    year = int(value)
                    query = query.filter(db.extract('year', Project.sanctioned_date) == year)
            except ValueError:
                pass

    projects = query.order_by(db.cast(Project.serial_no, db.Integer)).all()
    output = StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Header row (same as original, no minutes columns)
    writer.writerow([
        "S. No", "Nomenclature", "Academia/Institute", "PI Name", "Coordinating Lab",
        "Coordinating Lab Scientist", "Research Vertical", "Sanctioned Cost (in Lakhs)",
        "Sanctioned Date", "Original PDC", "Revised PDC", "Stake Holding Labs",
        "Scope/Objective of the Project", "Expected Deliverables/Technology",
        "Outcome Dovetailing with Ongoing Work", "RAB Meeting Scheduled Date",
        "RAB Meeting Held Date", "GC Meeting Scheduled Date",
        "GC Meeting Held Date", "Technical Status",
        "Administrative Status", "Final Closure Status"
    ])

    for project in projects:
        writer.writerow([
            project.serial_no,
            project.title or '',
            project.academia or '',
            project.pi_name or '',
            project.coord_lab or '',
            project.scientist or '',
            project.vertical or '',
            project.cost_lakhs or '',
            project.sanctioned_date or '',
            project.original_pdc or '',
            project.revised_pdc or '',
            project.stakeholders or '',
            project.scope_objective or '',
            project.expected_deliverables or '',
            project.Outcome_Dovetailing_with_Ongoing_Work or '',
            project.rab_meeting_date or '',
            project.rab_meeting_held_date or '',
            project.gc_meeting_date or '',
            project.gc_meeting_held_date or '',
            (project.technical_status or '').replace('\n', ' | '),
            project.administrative_status or '',
            (str(project.final_closure_date) if project.final_closure_date else '') +
            (" | " + project.final_closure_remarks if project.final_closure_remarks else "")
        ])

    output.seek(0)
    current_date = datetime.now().strftime("%Y-%m-%d")
    filename = f"DIA_CoE_filtered_{current_date}.csv"
    response = app.response_class(
        response=output.getvalue(),
        status=200,
        mimetype='text/csv'
    )
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response



# Route for the download PDF
@app.route('/download_pdf', methods=['GET'])
@login_required
def download_pdf():
    projects = Project.query.order_by(db.cast(Project.serial_no, db.Integer)).all()

    buffer = BytesIO()
    page_width, page_height = landscape(A4)
    margin = 30
    available_width = page_width - 2 * margin

    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=margin, rightMargin=margin)
    elements = []

    styles = getSampleStyleSheet()
    wrap_style = styles['Normal']
    wrap_style.fontSize = 7
    wrap_style.leading = 9

    # Header row using Paragraph for wrapped text
    header_row = [
        Paragraph("S. No.", wrap_style),
        Paragraph("Nomenclature", wrap_style),
        Paragraph("Academia / Institute", wrap_style),
        Paragraph("PI Name", wrap_style),
        Paragraph("Coordinating Lab", wrap_style),
        Paragraph("Coordinating Lab Scientist", wrap_style),
        Paragraph("Research Vertical", wrap_style),
        Paragraph("Cost (Lakhs)", wrap_style),
        Paragraph("Sanctioned Date", wrap_style),
        Paragraph("Original PDC", wrap_style),
        Paragraph("Revised PDC", wrap_style),
        Paragraph("Stake Holding Labs", wrap_style),
        Paragraph("Scope / Objective of the Project", wrap_style),
        Paragraph("Expected Deliverables / Technology", wrap_style),
        Paragraph("Outcome Dovetailing with Ongoing Work", wrap_style),
        Paragraph("RAB Meeting Scheduled Date", wrap_style),
        Paragraph("RAB Meeting Held Date", wrap_style),
        Paragraph("GC Meeting Scheduled Date", wrap_style),
        Paragraph("GC Meeting Held Date", wrap_style),
        Paragraph("Technical Status", wrap_style),
        Paragraph("Administrative Status", wrap_style),
        Paragraph("Final Closure Status", wrap_style)
    ]

    data = [header_row]

    for project in projects:
        data.append([
            str(project.serial_no),
            Paragraph(project.title or '', wrap_style),
            Paragraph(project.academia or '', wrap_style),
            Paragraph(project.pi_name or '', wrap_style),
            Paragraph(project.coord_lab or '', wrap_style),
            Paragraph(project.scientist or '', wrap_style),
            Paragraph(project.vertical or '', wrap_style),
            str(project.cost_lakhs or ''),
            str(project.sanctioned_date or ''),
            str(project.original_pdc or ''),
            str(project.revised_pdc or ''),
            Paragraph(project.stakeholders or '', wrap_style),
            Paragraph(project.scope_objective or '', wrap_style),
            Paragraph(project.expected_deliverables or '', wrap_style),
            Paragraph(project.Outcome_Dovetailing_with_Ongoing_Work or '', wrap_style),
            str(project.rab_meeting_date or ''),
            str(project.rab_meeting_held_date or ''),
            str(project.gc_meeting_date or ''),
            str(project.gc_meeting_held_date or ''),
            Paragraph((project.technical_status or '').replace('\n', '<br/>'), wrap_style),
            Paragraph(project.administrative_status or '', wrap_style),
            Paragraph(
                (project.final_closure_date.strftime('%Y-%m-%d') if project.final_closure_date else '') +
                ('<br/><b>Remarks:</b> ' + project.final_closure_remarks if project.final_closure_remarks else ''),
                wrap_style
            )
        ])

    # Define proportional column widths
    col_widths = [
        20,   # S. No.
        100,  # Nomenclature
        65,   # Academia / Institute
        65,   # PI Name
        60,   # Coordinating Lab
        70,   # Coordinating Lab Scientist
        60,   # Research Vertical
        50,   # Cost (Lakhs)
        75,   # Sanctioned Date
        75,   # Original PDC
        75,   # Revised PDC
        70,   # Stake Holding Labs
        75,   # Scope / Objective of the Project
        75,   # Expected Deliverables / Technology
        75,   # Outcome Dovetailing with Ongoing Work
        75,   # RAB Meeting Scheduled Date
        75,   # RAB Meeting Held Date
        75,   # GC Meeting Scheduled Date
        75,   # GC Meeting Held Date
        70,   # Technical Status
        65,   # Administrative Status
        70,   # Final Closure Status
    ]
    scale_factor = available_width / sum(col_widths)
    col_widths = [w * scale_factor for w in col_widths]

    table = Table(data, colWidths=col_widths, repeatRows=1)

    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    filename = f"DIA_CoE_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')


# Route for the download filtered PDF
@app.route('/download_filtered_pdf', methods=['GET'])
@login_required
def download_filtered_pdf():
    query = Project.query
    if current_user.role == 'manager':
        query = query.filter(Project.scientist.ilike(f"%{current_user.coord_scientist}%"))
    column = request.args.get('column', '')
    value = request.args.get('value', '').strip()
    cost_min = request.args.get('cost_min', '').strip()
    cost_max = request.args.get('cost_max', '').strip()
    sanction_year_start = request.args.get('sanction_year_start', '').strip()
    sanction_year_end = request.args.get('sanction_year_end', '').strip()

    if column and (
        value or 
        (column == 'cost_lakhs' and (cost_min or cost_max)) or
        (column == 'sanction_year' and (sanction_year_start or sanction_year_end))
    ):
        if column == 'serial_no':
            query = query.filter(Project.serial_no.ilike(f"%{value}%"))
        elif column == 'title':
            query = query.filter(Project.title.ilike(f"%{value}%"))
        elif column == 'vertical':
            query = query.filter(Project.vertical.ilike(f"%{value}%"))
        elif column == 'academia':
            query = query.filter(Project.academia.ilike(f"%{value}%"))
        elif column == 'pi_name':
            query = query.filter(Project.pi_name.ilike(f"%{value}%"))
        elif column == 'coord_lab':
            query = query.filter(Project.coord_lab.ilike(f"%{value}%"))
        elif column == 'scientist':
            query = query.filter(Project.scientist.ilike(f"%{value}%"))
        elif column == 'cost_lakhs':
            try:
                if cost_min:
                    query = query.filter(Project.cost_lakhs >= float(cost_min))
                if cost_max:
                    query = query.filter(Project.cost_lakhs <= float(cost_max))
            except ValueError:
                pass
        elif column in ['sanctioned_date', 'original_pdc', 'revised_pdc']:
            try:
                date_value = datetime.strptime(value, "%Y-%m-%d").date()
                query = query.filter(getattr(Project, column) == date_value)
            except ValueError:
                pass
        elif column == 'administrative_status':
            query = query.filter(Project.administrative_status.ilike(f"%{value}%"))
        elif column == 'sanction_year':
            try:
                if sanction_year_start:
                    query = query.filter(db.extract('year', Project.sanctioned_date) >= int(sanction_year_start))
                if sanction_year_end:
                    query = query.filter(db.extract('year', Project.sanctioned_date) <= int(sanction_year_end))
                # fallback for single value (if only value is provided)
                if not (sanction_year_start or sanction_year_end) and value:
                    year = int(value)
                    query = query.filter(db.extract('year', Project.sanctioned_date) == year)
            except ValueError:
                pass

    projects = query.order_by(db.cast(Project.serial_no, db.Integer)).all()

    # --- PDF generation logic (same as download_pdf) ---
    buffer = BytesIO()
    page_width, page_height = landscape(A4)
    margin = 30
    available_width = page_width - 2 * margin

    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=margin, rightMargin=margin)
    elements = []

    styles = getSampleStyleSheet()
    wrap_style = styles['Normal']
    wrap_style.fontSize = 7
    wrap_style.leading = 9

    header_row = [
        Paragraph("S. No.", wrap_style),
        Paragraph("Nomenclature", wrap_style),
        Paragraph("Academia / Institute", wrap_style),
        Paragraph("PI Name", wrap_style),
        Paragraph("Coordinating Lab", wrap_style),
        Paragraph("Coordinating Lab Scientist", wrap_style),
        Paragraph("Research Vertical", wrap_style),
        Paragraph("Cost (Lakhs)", wrap_style),
        Paragraph("Sanctioned Date", wrap_style),
        Paragraph("Original PDC", wrap_style),
        Paragraph("Revised PDC", wrap_style),
        Paragraph("Stake Holding Labs", wrap_style),
        Paragraph("Scope / Objective of the Project", wrap_style),
        Paragraph("Expected Deliverables / Technology", wrap_style),
        Paragraph("Outcome Dovetailing with Ongoing Work", wrap_style),
        Paragraph("RAB Meeting Scheduled Date", wrap_style),
        Paragraph("RAB Meeting Held Date", wrap_style),
        Paragraph("GC Meeting Scheduled Date", wrap_style),
        Paragraph("GC Meeting Held Date", wrap_style),
        Paragraph("Technical Status", wrap_style),
        Paragraph("Administrative Status", wrap_style),
        Paragraph("Final Closure Status", wrap_style)
    ]

    data = [header_row]

    for project in projects:
        data.append([
            str(project.serial_no),
            Paragraph(project.title or '', wrap_style),
            Paragraph(project.academia or '', wrap_style),
            Paragraph(project.pi_name or '', wrap_style),
            Paragraph(project.coord_lab or '', wrap_style),
            Paragraph(project.scientist or '', wrap_style),
            Paragraph(project.vertical or '', wrap_style),
            str(project.cost_lakhs or ''),
            str(project.sanctioned_date or ''),
            str(project.original_pdc or ''),
            str(project.revised_pdc or ''),
            Paragraph(project.stakeholders or '', wrap_style),
            Paragraph(project.scope_objective or '', wrap_style),
            Paragraph(project.expected_deliverables or '', wrap_style),
            Paragraph(project.Outcome_Dovetailing_with_Ongoing_Work or '', wrap_style),
            str(project.rab_meeting_date or ''),
            str(project.rab_meeting_held_date or ''),
            str(project.gc_meeting_date or ''),
            str(project.gc_meeting_held_date or ''),
            Paragraph((project.technical_status or '').replace('\n', '<br/>'), wrap_style),
            Paragraph(project.administrative_status or '', wrap_style),
            Paragraph(
                (project.final_closure_date.strftime('%Y-%m-%d') if project.final_closure_date else '') +
                ('<br/><b>Remarks:</b> ' + project.final_closure_remarks if project.final_closure_remarks else ''),
                wrap_style
            )
        ])

    col_widths = [
        20, 100, 65, 65, 60, 70, 60, 50, 75, 75, 75, 70, 75, 75, 75, 75, 75, 75, 75, 70, 65, 70,
    ]
    scale_factor = available_width / sum(col_widths)
    col_widths = [w * scale_factor for w in col_widths]

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    filename = f"DIA_CoE_filtered_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')


#Route for forms
@app.route('/forms')
@login_required
def forms():
    forms = NoticeForm.query.order_by(NoticeForm.form_no).all()
    return render_template('forms/forms.html', forms=forms)

# Route for the view logs page (Admin only)
@app.route('/logs')
@login_required 
def view_logs():
    if current_user.role != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))
    logs = Log.query.order_by(Log.timestamp.desc()).all()
    return render_template('main/logs.html', logs=logs, now=datetime.now())

@app.route('/contact_support')
@login_required
def contact_support():
    return render_template('main/contact_support.html')

# Route for the view profile page
@app.route('/logout')
@login_required
def logout():
    log_action(current_user, "User logged out")
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin_user = User(username='admin', password=generate_password_hash('Admin123$'), role='admin')
        viewer_user = User(username='viewer', password=generate_password_hash('Viewer123$'), role='viewer')
        db.session.add_all([admin_user, viewer_user])
        db.session.commit()


# Route for managing users (Admin only)
@app.route('/manage_users')
@login_required
def manage_users():
    if current_user.role != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))
    users = User.query.all()
    return render_template('users/manage_users.html', users=users)


# Route for creating a new user (Admin only)
@app.route('/create_user', methods=['GET', 'POST'])
@login_required
def create_user():
    if current_user.role != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))
    coordinating_scientists = sorted({p.scientist for p in Project.query.all() if p.scientist})
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        coord_scientist = request.form.get('coord_scientist') if role == 'manager' else None

        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "danger")
            return redirect(url_for('create_user'))

        # Server-side password validation
        if len(password) < 8 or not any(char.isdigit() for char in password) or not any(char.isupper() for char in password) or not any(char.islower() for char in password) or not any(char in "@$!%*?&" for char in password):
            flash("Password must be at least 8 characters long and include at least one number, one uppercase letter, one lowercase letter, and one special character (@, $, !, %, *, ?, &).", "danger")
            return redirect(url_for('create_user'))

        # Hash the password and create the user
        hashed_password = generate_password_hash(password)
        user = User(username=username, password=hashed_password, role=role, coord_scientist=coord_scientist)
        db.session.add(user)
        db.session.commit()
        log_action(current_user, f"Created user '{username}'")
        flash("User created successfully.", "success")
        return redirect(url_for('manage_users'))
    return render_template('users/create_user.html' , coordinating_scientists=coordinating_scientists)



# Route for modifying an existing user (Admin only)
@app.route('/modify_user', methods=['GET', 'POST'])
@login_required
def modify_user():
    if current_user.role != 'admin':  # Restrict access to admins
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))

    users = User.query.all()  

    if request.method == 'POST':
        username = request.form.get('username')
        new_password = request.form.get('password')
        new_role = request.form.get('role')
        coord_scientist = request.form.get('coord_scientist', '')

        # Fetch the user from the database
        user = User.query.filter_by(username=username).first()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for('modify_user'))

        # Validate the new password if provided
        if new_password:
            if len(new_password) < 8 or not any(char.isdigit() for char in new_password) or not any(char.isupper() for char in new_password) or not any(char.islower() for char in new_password) or not any(char in "@$!%*?&" for char in new_password):
                flash("Password must be at least 8 characters long and include at least one number, one uppercase letter, one lowercase letter, and one special character (@, $, !, %, *, ?, &).", "danger")
                return redirect(url_for('modify_user'))

            user.password = generate_password_hash(new_password)

        # Update the role and PI name
        user.role = new_role
        if new_role == 'manager':
            user.coord_scientist = coord_scientist
        else:
            user.coord_scientist = None

        # Commit the changes to the database
        db.session.commit()
        log_action(current_user, f"Modified user '{username}'")
        flash(f"User '{username}' has been updated successfully.", "success")
        return redirect(url_for('manage_users'))

    # Render the modify_user.html page on GET
    return render_template('users/modify_user.html', users=users)


# Route for deleting a user (Admin only)
@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':  # Restrict access to admins
        flash("Unauthorized access.", "danger")
        return redirect(url_for('manage_users'))

    user = User.query.get_or_404(user_id)

    # Prevent deletion of the currently logged-in admin
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for('manage_users'))

    db.session.delete(user)
    db.session.commit()
    log_action(current_user, f"Deleted user '{user.username}'")

    flash(f"User '{user.username}' has been deleted successfully.", "success")
    return redirect(url_for('manage_users'))



# Route for changing a user's role (Admin only)
@app.route('/change_role/<int:user_id>', methods=['POST'])
@login_required
def change_role(user_id):
    if current_user.role != 'admin':  # Restrict access to admins
        flash("Unauthorized access.", "danger")
        return redirect(url_for('manage_users'))

    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')

    if new_role not in ['admin', 'viewer']:
        flash("Invalid role selected.", "danger")
        return redirect(url_for('manage_users'))

    user.role = new_role
    db.session.commit()
    log_action(current_user, f"Changed role for user '{user.username}' to '{new_role}'")
    flash(f"Role for user '{user.username}' updated to '{new_role}'.", "success")
    return redirect(url_for('manage_users'))



# Route for changing a user's password (Admin only)
@app.route('/change_password/<int:user_id>', methods=['POST'])
@login_required
def change_password(user_id):
    if current_user.role != 'admin':  # Restrict access to admins
        flash("Unauthorized access.", "danger")
        return redirect(url_for('manage_users'))

    user = User.query.get_or_404(user_id)
    new_password = request.form.get('password')

    # Validate password
    if len(new_password) < 8 or not any(char.isdigit() for char in new_password) or not any(char.isupper() for char in new_password) or not any(char.islower() for char in new_password):
        flash("Password must be at least 8 characters long and include at least one number, one uppercase letter, and one lowercase letter.", "danger")
        return redirect(url_for('manage_users'))

    user.password = generate_password_hash(new_password)
    db.session.commit()
    log_action(current_user, f"Changed password for user '{user.username}'")
    flash(f"Password for user '{user.username}' updated successfully.", "success")
    return redirect(url_for('manage_users'))



# Route for viewing all users (Admin only)
@app.route('/view_all_users', methods=['GET'])
@login_required
def view_all_users():
    if current_user.role != 'admin':  # Restrict access to admins
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))

    users = User.query.all()
    return render_template('users/view_all_users.html', users=users)



# Route for viewing projects (restricted based on user role)
@app.route('/projects', methods=['GET'])
@login_required
def view_projects():
    if current_user.role == 'manager':
        # Restrict projects to those with the manager's PI name
        projects = Project.query.filter(Project.scientist.ilike(f"%{current_user.coord_scientist}%")).all()
    else:
        # Admins and viewers can see all projects
        projects = Project.query.all()

    return render_template('projects/projects.html', projects=projects)




# Route for changing own password
@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_own_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Validate current password
        if not check_password_hash(current_user.password, current_password):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for('change_own_password'))

        # Validate new password
        if new_password != confirm_password:
            flash("New password and confirmation do not match.", "danger")
            return redirect(url_for('change_own_password'))

        if len(new_password) < 8 or not any(char.isdigit() for char in new_password) or not any(char.isupper() for char in new_password) or not any(char.islower() for char in new_password):
            flash("Password must be at least 8 characters long and include at least one number, one uppercase letter, and one lowercase letter.", "danger")
            return redirect(url_for('change_own_password'))

        # Update password
        current_user.password = generate_password_hash(new_password)
        db.session.commit()
        log_action(current_user, f"{current_user.username} changed password for {current_user.username} user")
        flash("Password updated successfully.", "success")
        return redirect(url_for('dashboard'))

    return render_template('users/change_password.html')


# Run the Flask application
if __name__ == '__main__':
    app.run(debug=True)
