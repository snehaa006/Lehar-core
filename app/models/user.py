"""
User Model - Firestore Version
Users can be members of multiple workspaces across organizations
Organization membership is optional - users can exist without belonging to any organization
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import uuid
import enum

from app.database.base_repository import BaseRepository
from google.cloud.firestore_v1 import FieldFilter


# OrgRole enum - duplicated here to avoid circular imports
# The canonical definition is in organization.py
class OrgRole(enum.Enum):
    """Organization-level roles"""
    ORG_OWNER = "org_owner"
    ORG_ADMIN = "org_admin"
    MEMBER = "member"


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
        query = self.collection.where(
            filter=FieldFilter("organization_id", "==", organization_id)
        )

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

    def get_organization_admins(self, organization_id: str) -> List[Dict[str, Any]]:
        """Get all org owners and admins"""
        query = self.collection.where(
            filter=FieldFilter("organization_id", "==", organization_id)
        ).where(
            filter=FieldFilter("is_active", "==", True)
        ).where(
            filter=FieldFilter("org_role", "in", ["org_owner", "org_admin"])
        )

        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)

        return results


class User(UserMixin):
    """User model - Firestore document wrapper"""

    repository = UserRepository()

    def __init__(self, data: Dict[str, Any]):
        """Initialize user from Firestore document data"""
        self.id = data.get('id')
        self.organization_id = data.get('organization_id')  # Now optional
        self.name = data.get('name')
        self.email = data.get('email')
        self.password_hash = data.get('password_hash')
        self.phone = data.get('phone')
        # org_role is optional - only relevant if user belongs to an organization
        org_role_value = data.get('org_role')
        if org_role_value:
            try:
                self.org_role = OrgRole(org_role_value)
            except ValueError:
                self.org_role = OrgRole.MEMBER
        else:
            self.org_role = None
        self.job_title = data.get('job_title')
        self.is_email_verified = data.get('is_email_verified', False)
        self.email_verification_token = data.get('email_verification_token')
        self._is_active = data.get('is_active', True)
        self.created_at = data.get('created_at')
        self.last_login = data.get('last_login')
        self.updated_at = data.get('updated_at')
        self.last_workspace_id = data.get('last_workspace_id')  # Track last used workspace

        # Cache organization data if included
        self._organization_data = data.get('_organization')

    @classmethod
    def create(cls, name: str, email: str, password: str,
               organization_id: str = None, org_role: str = None, **kwargs) -> 'User':
        """Create a new user - organization_id is now optional"""
        user_id = str(uuid.uuid4())

        data = {
            'organization_id': organization_id,  # Can be None
            'name': name,
            'email': email.lower(),
            'password_hash': generate_password_hash(password),
            'org_role': org_role,  # Can be None if no organization
            'phone': kwargs.get('phone'),
            'job_title': kwargs.get('job_title'),
            'is_email_verified': kwargs.get('is_email_verified', False),
            'email_verification_token': kwargs.get('email_verification_token'),
            'is_active': kwargs.get('is_active', True),
            'last_login': None,
            'last_workspace_id': kwargs.get('last_workspace_id')  # Track last used workspace
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

    @classmethod
    def get_organization_admins(cls, organization_id: str) -> List['User']:
        """Get all org owners and admins"""
        data_list = cls.repository.get_organization_admins(organization_id)
        return [cls(data) for data in data_list]

    def save(self) -> bool:
        """Save user changes to Firestore"""
        data = {
            'name': self.name,
            'email': self.email,
            'password_hash': self.password_hash,
            'phone': self.phone,
            'org_role': self.org_role.value if isinstance(self.org_role, OrgRole) else self.org_role,
            'job_title': self.job_title,
            'is_email_verified': self.is_email_verified,
            'email_verification_token': self.email_verification_token,
            'is_active': self._is_active,
            'last_login': self.last_login,
            'last_workspace_id': self.last_workspace_id,
            'organization_id': self.organization_id
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
        """Get organization (lazy loaded) - returns None if user has no organization"""
        if not self.organization_id:
            return None
        if not hasattr(self, '_organization_obj'):
            from app.models.organization import Organization
            self._organization_obj = Organization.get_by_id(self.organization_id)
        return self._organization_obj

    @property
    def last_workspace(self):
        """Get last used workspace (lazy loaded)"""
        if not self.last_workspace_id:
            return None
        if not hasattr(self, '_last_workspace_obj'):
            from app.models.workspace import Workspace
            self._last_workspace_obj = Workspace.get_by_id(self.last_workspace_id)
        return self._last_workspace_obj

    def set_last_workspace(self, workspace_id: str) -> bool:
        """Update last used workspace and save"""
        self.last_workspace_id = workspace_id
        return self.save()

    @property
    def workspace_memberships(self) -> List:
        """Get all workspace memberships for this user"""
        from app.models.workspace_membership import WorkspaceMembership
        return WorkspaceMembership.get_user_memberships(self.id)

    @property
    def workspaces(self) -> List:
        """Get all workspaces this user is a member of"""
        from app.models.workspace import Workspace
        memberships = self.workspace_memberships
        workspace_ids = [m.workspace_id for m in memberships]
        return [Workspace.get_by_id(wid) for wid in workspace_ids if Workspace.get_by_id(wid)]

    def is_org_owner(self) -> bool:
        """Check if user is organization owner"""
        if not self.org_role:
            return False
        return self.org_role == OrgRole.ORG_OWNER

    def is_org_admin(self) -> bool:
        """Check if user is organization admin or owner"""
        if not self.org_role:
            return False
        return self.org_role in [OrgRole.ORG_OWNER, OrgRole.ORG_ADMIN]

    def can_manage_workspaces(self) -> bool:
        """Check if user can create/manage workspaces - any user can create workspaces now"""
        return True  # Anyone can create workspaces

    def can_invite_users(self) -> bool:
        """Check if user can invite users to organization"""
        return self.is_org_admin()

    def is_workspace_admin(self, workspace_id: str) -> bool:
        """Check if user is admin of a specific workspace"""
        from app.models.workspace_membership import WorkspaceMembership
        return WorkspaceMembership.user_is_workspace_admin(self.id, workspace_id)

    def to_dict(self, include_org: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for JSON responses"""
        data = {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "org_role": self.org_role.value if isinstance(self.org_role, OrgRole) else self.org_role,
            "job_title": self.job_title,
            "is_active": self.is_active,
            "is_email_verified": self.is_email_verified,
            "last_workspace_id": self.last_workspace_id,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "last_login": self.last_login.isoformat() if self.last_login and isinstance(self.last_login, datetime) else self.last_login
        }

        if include_org and self.organization:
            data["organization"] = self.organization.to_dict()

        return data

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

    @property
    def is_active(self) -> bool:
        """Required by Flask-Login. Controls if account is active."""
        return self._is_active

    def __repr__(self):
        role_str = self.org_role.value if isinstance(self.org_role, OrgRole) else (self.org_role or 'no-org')
        return f"<User {self.email} ({role_str})>"
