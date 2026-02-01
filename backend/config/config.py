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
    GCS_PROJECT_ID = os.getenv("GCS_PROJECT_ID", "manufacture-erp-prod-70700")
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
    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")

    # Join Request Settings
    JOIN_REQUEST_COOLDOWN_HOURS = 24  # Hours before user can request again after rejection

    # Plan limits (includes workspace limits)
    PLAN_LIMITS = {
        "free": {
            "max_users": 5,
            "max_workspaces": 2,
            "modules": ["hr", "basic_dashboard"]
        },
        "starter": {
            "max_users": 15,
            "max_workspaces": 5,
            "modules": ["hr", "inventory", "basic_dashboard"]
        },
        "pro": {
            "max_users": 50,
            "max_workspaces": 15,
            "modules": ["hr", "inventory", "production_planning", "advanced_dashboard"]
        },
        "enterprise": {
            "max_users": None,  # Unlimited
            "max_workspaces": None,  # Unlimited
            "modules": ["all"]  # All modules including IIoT
        }
    }


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration for GCP Cloud Run (asia-south2)"""
    DEBUG = False
    TESTING = False

    # Override with environment variable if set
    SECRET_KEY = os.getenv("SECRET_KEY", Config.SECRET_KEY)

    # Production URLs
    BACKEND_URL = os.getenv("BACKEND_URL", "https://lehar-core-444463644765.asia-south2.run.app")
    FRONTEND_URL = os.getenv("FRONTEND_URL", "https://lehar-core-444463644765.asia-south2.run.app")

    # GCP Project
    GCS_PROJECT_ID = os.getenv("GCS_PROJECT_ID", "manufacture-erp-prod-70700")


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