"""
Invitation Model - Firestore Version (FIXED)
For inviting users to join specific workspaces
FIXES: Status handling to use enums consistently
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
import uuid
import enum

from app.database.base_repository import BaseRepository
from app.models.workspace import WorkspaceRole
from google.cloud.firestore_v1 import FieldFilter


class InvitationStatus(enum.Enum):
    """Invitation status"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class InvitationRepository(BaseRepository):
    """Repository for Invitation operations"""

    def __init__(self):
        super().__init__('invitations')

    def find_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Find invitation by token"""
        return self.find_one('token', token)

    def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find invitation by email"""
        return self.find_one('email', email.lower())

    def get_workspace_invitations(self, workspace_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all invitations for a workspace"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        )

        if status:
            query = query.where(filter=FieldFilter("status", "==", status))

        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)

        return results

    def get_organization_invitations(self, organization_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all invitations for an organization"""
        query = self.collection.where(
            filter=FieldFilter("organization_id", "==", organization_id)
        )

        if status:
            query = query.where(filter=FieldFilter("status", "==", status))

        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)

        return results

    def get_pending_invitation_for_email(self, workspace_id: str, email: str) -> Optional[Dict[str, Any]]:
        """Get pending invitation for an email in a workspace"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        ).where(
            filter=FieldFilter("email", "==", email.lower())
        ).where(
            filter=FieldFilter("status", "==", "pending")
        ).limit(1)

        docs = list(query.stream())
        if docs:
            data = docs[0].to_dict()
            data['id'] = docs[0].id
            return data
        return None


class Invitation:
    """Invitation model - Firestore document wrapper"""

    repository = InvitationRepository()

    def __init__(self, data: Dict[str, Any]):
        """Initialize invitation from Firestore document data"""
        self.id = data.get('id')
        self.organization_id = data.get('organization_id')
        self.workspace_id = data.get('workspace_id')
        self.email = data.get('email')
        self.name = data.get('name')
        self.workspace_role = WorkspaceRole(data.get('workspace_role', 'user'))
        self.token = data.get('token')
        
        # FIX: Convert status string to enum
        status_str = data.get('status', 'pending')
        if isinstance(status_str, str):
            self.status = InvitationStatus(status_str)
        else:
            self.status = status_str
        
        self.invited_by_user_id = data.get('invited_by_user_id')
        self.created_at = data.get('created_at')
        self.expires_at = data.get('expires_at')
        self.accepted_at = data.get('accepted_at')

        # Cache related data if included
        self._organization_data = data.get('_organization')
        self._workspace_data = data.get('_workspace')
        self._invited_by_data = data.get('_invited_by')

    @staticmethod
    def _get_utc_now():
        """Get current UTC time as timezone-aware datetime"""
        return datetime.now(timezone.utc)

    @staticmethod
    def _make_timezone_aware(dt):
        """Convert naive datetime to timezone-aware UTC datetime"""
        if dt is None:
            return None
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        return dt

    @classmethod
    def create(cls, organization_id: str, workspace_id: str, email: str,
               workspace_role: str, invited_by_user_id: Optional[str] = None,
               **kwargs) -> 'Invitation':
        """Create a new invitation"""
        invitation_id = str(uuid.uuid4())
        token = str(uuid.uuid4())

        data = {
            'organization_id': organization_id,
            'workspace_id': workspace_id,
            'email': email.lower(),
            'name': kwargs.get('name'),
            'workspace_role': workspace_role,
            'token': token,
            'status': 'pending',
            'invited_by_user_id': invited_by_user_id,
            'expires_at': datetime.now(timezone.utc) + timedelta(days=7),
            'accepted_at': None
        }

        created_data = cls.repository.create(invitation_id, data)
        return cls(created_data)

    @classmethod
    def get_by_id(cls, invitation_id: str) -> Optional['Invitation']:
        """Get invitation by ID"""
        data = cls.repository.get(invitation_id)
        return cls(data) if data else None

    @classmethod
    def get_by_token(cls, token: str) -> Optional['Invitation']:
        """Get invitation by token"""
        data = cls.repository.find_by_token(token)
        return cls(data) if data else None

    @classmethod
    def get_pending_for_email(cls, workspace_id: str, email: str) -> Optional['Invitation']:
        """Get pending invitation for an email"""
        data = cls.repository.get_pending_invitation_for_email(workspace_id, email)
        return cls(data) if data else None

    @classmethod
    def get_workspace_invitations(cls, workspace_id: str, status: Optional[str] = None) -> List['Invitation']:
        """Get all invitations for a workspace"""
        data_list = cls.repository.get_workspace_invitations(workspace_id, status)
        return [cls(data) for data in data_list]

    @classmethod
    def get_organization_invitations(cls, organization_id: str, status: Optional[str] = None) -> List['Invitation']:
        """Get all invitations for an organization"""
        data_list = cls.repository.get_organization_invitations(organization_id, status)
        return [cls(data) for data in data_list]

    def save(self) -> bool:
        """Save invitation changes to Firestore"""
        data = {
            'email': self.email,
            'name': self.name,
            'workspace_role': self.workspace_role.value if isinstance(self.workspace_role, WorkspaceRole) else self.workspace_role,
            'status': self.status.value if isinstance(self.status, InvitationStatus) else self.status,
            'expires_at': self.expires_at,
            'accepted_at': self.accepted_at
        }

        return self.repository.update(self.id, data)

    def delete(self) -> bool:
        """Delete invitation from Firestore"""
        return self.repository.delete(self.id)

    def is_valid(self) -> bool:
        """Check if invitation is still valid"""
        if self.status != InvitationStatus.PENDING:
            return False

        if self.expires_at is None:
            return True

        expires_at_aware = self._make_timezone_aware(self.expires_at)
        now_aware = self._get_utc_now()

        return expires_at_aware > now_aware

    def accept(self) -> bool:
        """Mark invitation as accepted"""
        self.status = InvitationStatus.ACCEPTED
        self.accepted_at = datetime.now(timezone.utc)
        return self.save()

    def cancel(self) -> bool:
        """Cancel invitation"""
        self.status = InvitationStatus.CANCELLED
        return self.save()

    def expire(self) -> bool:
        """Mark invitation as expired"""
        self.status = InvitationStatus.EXPIRED
        return self.save()

    @property
    def organization(self):
        """Get organization (lazy loaded)"""
        if not hasattr(self, '_organization_obj'):
            from app.models.organization import Organization
            self._organization_obj = Organization.get_by_id(self.organization_id)
        return self._organization_obj

    @property
    def workspace(self):
        """Get workspace (lazy loaded)"""
        if not hasattr(self, '_workspace_obj'):
            from app.models.workspace import Workspace
            self._workspace_obj = Workspace.get_by_id(self.workspace_id)
        return self._workspace_obj

    @property
    def invited_by(self):
        """Get user who sent invitation (lazy loaded)"""
        if not hasattr(self, '_invited_by_obj') and self.invited_by_user_id:
            from app.models.user import User
            self._invited_by_obj = User.get_by_id(self.invited_by_user_id)
        return getattr(self, '_invited_by_obj', None)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON responses"""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "workspace_role": self.workspace_role.value if isinstance(self.workspace_role, WorkspaceRole) else self.workspace_role,
            "status": self.status.value if isinstance(self.status, InvitationStatus) else self.status,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "expires_at": self.expires_at.isoformat() if isinstance(self.expires_at, datetime) else self.expires_at
        }

    def __repr__(self):
        status_str = self.status.value if isinstance(self.status, InvitationStatus) else self.status
        return f"<Invitation {self.email} to workspace={self.workspace_id} ({status_str})>"