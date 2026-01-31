"""
User Model - Firestore Version
Users belong to organizations and have specific roles
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import uuid
import enum

from app.database.base_repository import BaseRepository
from google.cloud.firestore_v1 import FieldFilter


class UserRole(enum.Enum):
    """User roles within an organization"""
    SUPER_ADMIN = "super_admin"  # Billing, add/remove users, all modules
    ADMIN = "admin"              # Manage modules, view reports
    MANAGER = "manager"          # Use operational modules
    HR_USER = "hr"               # Only HR module
    VIEWER = "viewer"            # Read-only dashboards


class UserRepository(BaseRepository):
    """Repository for User operations"""
    
    def __init__(self):
        super().__init__('users')
    
    def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find user by email"""
        return self.find_one('email', email.lower())
    
    def find_by_email_verification_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Find user by email verification token"""
        return self.find_one('email_verification_token', token)
    
    def get_organization_users(self, organization_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all users in an organization"""
        from app.database.firestore_client import db
        
        query = self.collection.where(filter=FieldFilter("organization_id", "==", organization_id))
        
        if active_only:
            query = query.where(filter=FieldFilter("is_active", "==", True))
        
        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)
        
        return results
    
    def count_organization_users(self, organization_id: str, active_only: bool = True) -> int:
        """Count users in an organization"""
        users = self.get_organization_users(organization_id, active_only)
        return len(users)


class User(UserMixin):
    """User model - Firestore document wrapper"""
    
    # Repository instance
    repository = UserRepository()
    
    def __init__(self, data: Dict[str, Any]):
        """Initialize user from Firestore document data"""
        self.id = data.get('id')
        self.organization_id = data.get('organization_id')
        self.name = data.get('name')
        self.email = data.get('email')
        self.password_hash = data.get('password_hash')
        self.phone = data.get('phone')
        self.role = UserRole(data.get('role', 'viewer'))
        self.job_title = data.get('job_title')
        self.is_email_verified = data.get('is_email_verified', False)
        self.email_verification_token = data.get('email_verification_token')
        self._is_active = data.get('is_active', True)

        self.created_at = data.get('created_at')
        self.last_login = data.get('last_login')
        self.updated_at = data.get('updated_at')
        
        # Cache organization data if included
        self._organization_data = data.get('_organization')
    
    @classmethod
    def create(cls, organization_id: str, name: str, email: str, password: str, 
               role: str = 'viewer', **kwargs) -> 'User':
        """
        Create a new user
        
        Args:
            organization_id: Organization ID
            name: User name
            email: User email
            password: Plain text password (will be hashed)
            role: User role
            **kwargs: Additional user fields
            
        Returns:
            User instance
        """
        user_id = str(uuid.uuid4())
        
        data = {
            'organization_id': organization_id,
            'name': name,
            'email': email.lower(),
            'password_hash': generate_password_hash(password),
            'role': role,
            'phone': kwargs.get('phone'),
            'job_title': kwargs.get('job_title'),
            'is_email_verified': kwargs.get('is_email_verified', False),
            'email_verification_token': kwargs.get('email_verification_token'),
            'is_active': kwargs.get('is_active', True),
            'last_login': None
        }
        
        created_data = cls.repository.create(user_id, data)
        return cls(created_data)
    
    @classmethod
    def get_by_id(cls, user_id: str) -> Optional['User']:
        """Get user by ID"""
        data = cls.repository.get(user_id)
        return cls(data) if data else None
    
    @classmethod
    def get_by_email(cls, email: str) -> Optional['User']:
        """Get user by email"""
        data = cls.repository.find_by_email(email)
        return cls(data) if data else None
    
    @classmethod
    def get_by_verification_token(cls, token: str) -> Optional['User']:
        """Get user by email verification token"""
        data = cls.repository.find_by_email_verification_token(token)
        return cls(data) if data else None
    
    def save(self) -> bool:
        """Save user changes to Firestore"""
        data = {
            'name': self.name,
            'email': self.email,
            'password_hash': self.password_hash,
            'phone': self.phone,
            'role': self.role.value,
            'job_title': self.job_title,
            'is_email_verified': self.is_email_verified,
            'email_verification_token': self.email_verification_token,
            'is_active': self._is_active,

            'last_login': self.last_login
        }
        
        return self.repository.update(self.id, data)
    
    def delete(self) -> bool:
        """Delete user from Firestore"""
        return self.repository.delete(self.id)
    
    def set_password(self, password: str):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password: str) -> bool:
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    @property
    def organization(self):
        """Get organization (lazy loaded)"""
        if not hasattr(self, '_organization_obj'):
            from app.models.organization import Organization
            self._organization_obj = Organization.get_by_id(self.organization_id)
        return self._organization_obj
    
    def to_dict(self, include_org: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for JSON responses"""
        data = {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role.value,
            "job_title": self.job_title,
            "is_active": self.is_active,
            "is_email_verified": self.is_email_verified,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "last_login": self.last_login.isoformat() if self.last_login and isinstance(self.last_login, datetime) else self.last_login
        }
        
        if include_org and self.organization:
            data["organization"] = self.organization.to_dict()
        
        return data
    
    def can_access_module(self, module_name: str) -> bool:
        """Check if user can access a specific module based on role and org plan"""
        # Module access logic - to be implemented based on plan limits
        from config.config import Config
        
        if not self.organization:
            return False
        
        plan_limits = Config.PLAN_LIMITS.get(self.organization.plan_type.value, {})
        allowed_modules = plan_limits.get('modules', [])
        
        if 'all' in allowed_modules:
            return True
        
        return module_name in allowed_modules
    
    # Flask-Login required methods
    def get_id(self) -> str:
        """Return the user ID as a string"""
        return str(self.id)
    
    @property
    def is_authenticated(self) -> bool:
        """Return True if the user is authenticated"""
        return True
    
    @property
    def is_anonymous(self) -> bool:
        """Return False as anonymous users aren't supported"""
        return False
    
    def __repr__(self):
        return f"<User {self.email} ({self.role.value})>"
    @property
    def is_active(self) -> bool:
        """Required by Flask-Login. Controls if account is active."""
        return self._is_active
