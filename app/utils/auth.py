"""
JWT Authentication Utilities
Handles token generation and validation
"""
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app
from app.models import User


def generate_access_token(user_id, organization_id, role, plan_type):
    """
    Generate JWT access token
    
    Payload includes:
    - user_id
    - organization_id
    - role
    - plan_type (for feature gating)
    """
    payload = {
        "user_id": user_id,
        "organization_id": organization_id,
        "role": role,
        "plan_type": plan_type,
        "exp": datetime.utcnow() + current_app.config["JWT_ACCESS_TOKEN_EXPIRES"],
        "iat": datetime.utcnow()
    }
    
    token = jwt.encode(
        payload,
        current_app.config["JWT_SECRET_KEY"],
        algorithm="HS256"
    )
    
    return token


def generate_refresh_token(user_id):
    """Generate JWT refresh token"""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + current_app.config["JWT_REFRESH_TOKEN_EXPIRES"],
        "iat": datetime.utcnow()
    }
    
    token = jwt.encode(
        payload,
        current_app.config["JWT_SECRET_KEY"],
        algorithm="HS256"
    )
    
    return token


def decode_token(token):
    """
    Decode and validate JWT token
    Returns payload if valid, None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            current_app.config["JWT_SECRET_KEY"],
            algorithms=["HS256"]
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def token_required(f):
    """
    Decorator to protect routes with JWT authentication
    
    Usage:
        @app.route('/dashboard')
        @token_required
        def dashboard(current_user):
            return f"Hello {current_user.name}"
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check for token in headers
        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            try:
                token = auth_header.split(" ")[1]  # "Bearer <token>"
            except IndexError:
                return jsonify({"error": "Invalid token format"}), 401
        
        if not token:
            return jsonify({"error": "Authentication token is missing"}), 401
        
        # Decode token
        payload = decode_token(token)
        
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401
        
        # Get user from database
        from app import db
        current_user = db.session.query(User).filter_by(id=payload["user_id"]).first()
        
        if not current_user or not current_user.is_active:
            return jsonify({"error": "User not found or inactive"}), 401
        
        # Pass current_user to the route
        return f(current_user=current_user, *args, **kwargs)
    
    return decorated


def role_required(allowed_roles):
    """
    Decorator to check if user has required role
    
    Usage:
        @app.route('/admin')
        @token_required
        @role_required(['super_admin', 'admin'])
        def admin_panel(current_user):
            return "Admin area"
    """
    def decorator(f):
        @wraps(f)
        def decorated(current_user, *args, **kwargs):
            if current_user.role.value not in allowed_roles:
                return jsonify({"error": "Insufficient permissions"}), 403
            
            return f(current_user=current_user, *args, **kwargs)
        
        return decorated
    return decorator
