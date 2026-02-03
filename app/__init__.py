"""
Flask Application Factory - Firestore Version
Creates and configures the Flask app
"""
import os
from flask import Flask, render_template
from flask_login import LoginManager

# Initialize Flask-Login
login_manager = LoginManager()


def create_app(config_name=None):
    """
    Application factory pattern
    
    Args:
        config_name: 'development', 'production', or 'testing'
    """
    app = Flask(__name__)
    
    # Load configuration
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")
    
    from config import config
    app.config.from_object(config[config_name])
    
    # Initialize Firestore connection (lazy initialization)
    with app.app_context():
        from app.database import db
        # Firestore connection is initialized on first use
    
    # Configure Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login"""
        from app.models import User
        return User.get_by_id(user_id)
    
    # Register blueprints
    from app.blueprints import auth_bp, dashboard_bp, invitations_bp, workspaces_bp, settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(invitations_bp)
    app.register_blueprint(workspaces_bp)
    app.register_blueprint(settings_bp)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Home route
    @app.route("/")
    def index():
        return render_template("index.html")
    
    # Health check for Cloud Run
    @app.route("/health")
    def health():
        return {"status": "healthy", "database": "firestore"}, 200
    
    return app


def register_error_handlers(app):
    """Register custom error handlers"""
    
    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404
    
    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html"), 403
    
    @app.errorhandler(500)
    def internal_error(error):
        # No need for session rollback with Firestore
        app.logger.error(f"Internal error: {error}")
        return render_template("errors/500.html"), 500