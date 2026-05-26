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
