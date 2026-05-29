from flask import Flask
from .config import config
from .extensions import jwt, socketio, cors, limiter, init_db

def create_app(config_name='development'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Init extensions
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)
    limiter.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')

    # Init DB
    init_db(app)

    # Register blueprints
    from .routes.auth import auth_bp
    from .routes.admin import admin_bp
    from .routes.employee import employee_bp
    from .routes.tasks import tasks_bp
    from .routes.attendance import attendance_bp
    from .routes.messages import messages_bp
    from .routes.analytics import analytics_bp
    from .routes.reports import reports_bp
    from .routes.views import views_bp
    # New feature blueprints
    from .routes.leads import lead_bp
    from .routes.productivity import productivity_bp
    from .routes.activity import activity_bp
    from .routes.notifications import notifications_bp
    from .routes.calendar import calendar_bp
    from .routes.notes import notes_bp
    from .routes.gamification import gamification_bp
    from .routes.ai import ai_bp
    from .routes.automation import automation_bp
    from .routes.attachments import attachments_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(employee_bp, url_prefix='/api/employee')
    app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
    app.register_blueprint(attendance_bp, url_prefix='/api/attendance')
    app.register_blueprint(messages_bp, url_prefix='/api/messages')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(views_bp)
    # Register new blueprints
    app.register_blueprint(lead_bp, url_prefix='/api/leads')
    app.register_blueprint(productivity_bp, url_prefix='/api/productivity')
    app.register_blueprint(activity_bp, url_prefix='/api/activity')
    app.register_blueprint(notifications_bp, url_prefix='/api/notifications')
    app.register_blueprint(calendar_bp, url_prefix='/api/calendar')
    app.register_blueprint(notes_bp, url_prefix='/api/notes')
    app.register_blueprint(gamification_bp, url_prefix='/api/gamification')
    app.register_blueprint(ai_bp, url_prefix='/api/ai')
    app.register_blueprint(automation_bp, url_prefix='/api/automation')
    app.register_blueprint(attachments_bp, url_prefix='/api/attachments')

    # Register SocketIO events
    from .sockets.events import register_events
    register_events(socketio)

    return app
