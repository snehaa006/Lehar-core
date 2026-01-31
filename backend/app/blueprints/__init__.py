"""
Blueprints package initialization
"""
from app.blueprints.auth import auth_bp
from app.blueprints.dashboard import dashboard_bp
from app.blueprints.invitations import invitations_bp

__all__ = [
    "auth_bp",
    "dashboard_bp",
    "invitations_bp"
]
