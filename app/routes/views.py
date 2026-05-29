from flask import Blueprint, render_template, redirect, url_for

views_bp = Blueprint('views', __name__)

@views_bp.route('/')
def index():
    return redirect(url_for('views.login_page'))

@views_bp.route('/login')
def login_page():
    return render_template('auth/login.html')

@views_bp.route('/admin/dashboard')
def admin_dashboard():
    return render_template('admin/dashboard.html')

@views_bp.route('/admin/employees')
def admin_employees():
    return render_template('admin/employees.html')

@views_bp.route('/admin/tasks')
def admin_tasks():
    return render_template('admin/tasks.html')

@views_bp.route('/admin/tasks/detail/<task_id>')
def admin_task_detail(task_id):
    return render_template('admin/task_detail.html', task_id=task_id)

@views_bp.route('/admin/tasks/kanban')
def admin_task_kanban():
    return render_template('admin/task_kanban.html')

@views_bp.route('/admin/tasks/calendar')
def admin_task_calendar():
    return render_template('admin/task_calendar.html')

@views_bp.route('/admin/attendance')
def admin_attendance():
    return render_template('admin/attendance.html')

@views_bp.route('/admin/analytics')
def admin_analytics():
    return render_template('admin/analytics.html')

@views_bp.route('/admin/messages')
def admin_messages():
    return render_template('admin/messages.html')

@views_bp.route('/employee/dashboard')
def employee_dashboard():
    return render_template('employee/dashboard.html')

@views_bp.route('/employee/tasks')
def employee_tasks():
    return render_template('employee/tasks.html')

@views_bp.route('/employee/tasks/detail/<task_id>')
def employee_task_detail(task_id):
    return render_template('employee/task_detail.html', task_id=task_id)


@views_bp.route('/employee/attendance')
def employee_attendance():
    return render_template('employee/attendance.html')

@views_bp.route('/employee/messages')
def employee_messages():
    return render_template('employee/messages.html')

# ===================================================================
# NEW CRM / FEATURE VIEW ROUTES
# ===================================================================

@views_bp.route('/admin/leads')
def admin_leads():
    return render_template('admin/leads.html')

@views_bp.route('/admin/crm-pipeline')
def admin_crm_pipeline():
    return render_template('admin/crm_pipeline.html')

@views_bp.route('/admin/activity-tracker')
def admin_activity_tracker():
    return render_template('admin/activity_tracker.html')

@views_bp.route('/admin/calendar')
def admin_calendar():
    return render_template('admin/calendar.html')

@views_bp.route('/admin/gamification')
def admin_gamification():
    return render_template('admin/gamification.html')

@views_bp.route('/admin/notifications')
def admin_notifications():
    return render_template('admin/notifications.html')

@views_bp.route('/admin/automation-logs')
def admin_automation_logs():
    return render_template('admin/automation_logs.html')

@views_bp.route('/employee/leads')
def employee_leads():
    return render_template('employee/leads.html')

@views_bp.route('/employee/calendar')
def employee_calendar():
    return render_template('employee/calendar.html')

@views_bp.route('/employee/notes')
def employee_notes():
    return render_template('employee/notes.html')

@views_bp.route('/employee/profile')
def employee_profile():
    return render_template('employee/profile.html')

@views_bp.route('/employee/notifications')
def employee_notifications():
    return render_template('employee/notifications.html')
