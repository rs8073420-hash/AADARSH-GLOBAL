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

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(employee_bp, url_prefix='/api/employee')
    app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
    app.register_blueprint(attendance_bp, url_prefix='/api/attendance')
    app.register_blueprint(messages_bp, url_prefix='/api/messages')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(views_bp)

    # Register SocketIO events
    from .sockets.events import register_events
    register_events(socketio)

    return app
