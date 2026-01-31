"""
Application Configuration - Firestore Version
Handles environment-based settings for development and production
"""
import os
from datetime import timedelta


class Config:
    """Base configuration"""
    
    # Application
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    APP_NAME = "Lehar Core Platform"
    
    # Firestore Configuration
    GCS_PROJECT_ID = os.getenv("GCS_PROJECT_ID", "")
    GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    
    # JWT Configuration
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    
    # Google Cloud Storage
    GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "lehar-core-prod")
    
    # Email Configuration (SMTP)
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True") == "True"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "noreply@leharcore.com")
    
    # Application URLs
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5000")
    # FIX: Added BACKEND_URL for email verification links
    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")

    
    # Plan limits
    PLAN_LIMITS = {
        "free": {
            "max_users": 3,
            "modules": ["hr", "basic_dashboard"]
        },
        "starter": {
            "max_users": 10,
            "modules": ["hr", "inventory", "basic_dashboard"]
        },
        "pro": {
            "max_users": 25,
            "modules": ["hr", "inventory", "production_planning", "advanced_dashboard"]
        },
        "enterprise": {
            "max_users": None,  # Unlimited
            "modules": ["all"]  # All modules including IIoT
        }
    }


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    
    # Override with environment variable if set
    SECRET_KEY = os.getenv("SECRET_KEY", Config.SECRET_KEY)


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    # Use emulator for testing
    FIRESTORE_EMULATOR_HOST = os.getenv("FIRESTORE_EMULATOR_HOST", "localhost:8080")


# Configuration dictionary
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig
}