"""
Join Request Model - Firestore Version
For users requesting to join workspaces
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
import uuid
import enum

from app.database.base_repository import BaseRepository
from google.cloud.firestore_v1 import FieldFilter


class JoinRequestStatus(enum.Enum):
    """Join request status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class JoinRequestRepository(BaseRepository):
    """Repository for JoinRequest operations"""

    def __init__(self):
        super().__init__('join_requests')

    def find_pending_request(self, user_id: str, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Find pending join request for user and workspace"""
        query = self.collection.where(
            filter=FieldFilter("user_id", "==", user_id)
        ).where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        ).where(
            filter=FieldFilter("status", "==", "pending")
        ).limit(1)

        docs = list(query.stream())
        if docs:
            data = docs[0].to_dict()
            data['id'] = docs[0].id
            return data
        return None

    def get_workspace_requests(self, workspace_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all join requests for a workspace"""
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

    def get_user_requests(self, user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all join requests by a user"""
        query = self.collection.where(
            filter=FieldFilter("user_id", "==", user_id)
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

    def get_recent_rejection(self, user_id: str, workspace_id: str, hours: int = 24) -> Optional[Dict[str, Any]]:
        """Check if user was rejected recently (for cooldown)"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = self.collection.where(
            filter=FieldFilter("user_id", "==", user_id)
        ).where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        ).where(
            filter=FieldFilter("status", "==", "rejected")
        )

        docs = query.stream()
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            rejected_at = data.get('rejected_at')
            if rejected_at:
                if rejected_at.tzinfo is None:
                    rejected_at = rejected_at.replace(tzinfo=timezone.utc)
                if rejected_at > cutoff_time:
                    return data
        return None


class JoinRequest:
    """Join Request model - Firestore document wrapper"""

    repository = JoinRequestRepository()
    COOLDOWN_HOURS = 24  # Hours before user can request again after rejection

    def __init__(self, data: Dict[str, Any]):
        """Initialize join request from Firestore document data"""
        self.id = data.get('id')
        self.user_id = data.get('user_id')
        self.workspace_id = data.get('workspace_id')
        self.reason = data.get('reason')
        self.status = JoinRequestStatus(data.get('status', 'pending'))
        self.reviewed_by_user_id = data.get('reviewed_by_user_id')
        self.rejection_reason = data.get('rejection_reason')
        self.created_at = data.get('created_at')
        self.reviewed_at = data.get('reviewed_at')
        self.rejected_at = data.get('rejected_at')
        self.updated_at = data.get('updated_at')

        # Cached objects
        self._user_data = data.get('_user')
        self._workspace_data = data.get('_workspace')

    @classmethod
    def create(cls, user_id: str, workspace_id: str, reason: str, **kwargs) -> 'JoinRequest':
        """Create a new join request"""
        request_id = str(uuid.uuid4())

        data = {
            'user_id': user_id,
            'workspace_id': workspace_id,
            'reason': reason,
            'status': 'pending',
            'reviewed_by_user_id': None,
            'rejection_reason': None,
            'reviewed_at': None,
            'rejected_at': None
        }

        created_data = cls.repository.create(request_id, data)
        return cls(created_data)

    @classmethod
    def get_by_id(cls, request_id: str) -> Optional['JoinRequest']:
        """Get join request by ID"""
        data = cls.repository.get(request_id)
        return cls(data) if data else None

    @classmethod
    def get_pending_request(cls, user_id: str, workspace_id: str) -> Optional['JoinRequest']:
        """Get pending request for user and workspace"""
        data = cls.repository.find_pending_request(user_id, workspace_id)
        return cls(data) if data else None

    @classmethod
    def get_workspace_requests(cls, workspace_id: str, status: Optional[str] = None) -> List['JoinRequest']:
        """Get all join requests for a workspace"""
        data_list = cls.repository.get_workspace_requests(workspace_id, status)
        return [cls(data) for data in data_list]

    @classmethod
    def get_user_requests(cls, user_id: str, status: Optional[str] = None) -> List['JoinRequest']:
        """Get all join requests by a user"""
        data_list = cls.repository.get_user_requests(user_id, status)
        return [cls(data) for data in data_list]

    @classmethod
    def can_request_again(cls, user_id: str, workspace_id: str) -> tuple:
        """Check if user can request to join again (cooldown check)"""
        # Check for pending request
        pending = cls.get_pending_request(user_id, workspace_id)
        if pending:
            return False, "You already have a pending request for this workspace"

        # Check for recent rejection
        recent_rejection = cls.repository.get_recent_rejection(user_id, workspace_id, cls.COOLDOWN_HOURS)
        if recent_rejection:
            return False, f"You were recently rejected. Please wait {cls.COOLDOWN_HOURS} hours before requesting again."

        return True, None

    def save(self) -> bool:
        """Save join request changes to Firestore"""
        data = {
            'reason': self.reason,
            'status': self.status.value if isinstance(self.status, JoinRequestStatus) else self.status,
            'reviewed_by_user_id': self.reviewed_by_user_id,
            'rejection_reason': self.rejection_reason,
            'reviewed_at': self.reviewed_at,
            'rejected_at': self.rejected_at
        }

        return self.repository.update(self.id, data)

    def delete(self) -> bool:
        """Delete join request from Firestore"""
        return self.repository.delete(self.id)

    def approve(self, reviewed_by_user_id: str) -> bool:
        """Approve join request"""
        self.status = JoinRequestStatus.APPROVED
        self.reviewed_by_user_id = reviewed_by_user_id
        self.reviewed_at = datetime.now(timezone.utc)
        return self.save()

    def reject(self, reviewed_by_user_id: str, rejection_reason: Optional[str] = None) -> bool:
        """Reject join request"""
        self.status = JoinRequestStatus.REJECTED
        self.reviewed_by_user_id = reviewed_by_user_id
        self.rejection_reason = rejection_reason
        self.reviewed_at = datetime.now(timezone.utc)
        self.rejected_at = datetime.now(timezone.utc)
        return self.save()

    def cancel(self) -> bool:
        """Cancel join request (by requester)"""
        self.status = JoinRequestStatus.CANCELLED
        return self.save()

    @property
    def user(self):
        """Get requesting user (lazy loaded)"""
        if not hasattr(self, '_user_obj'):
            from app.models.user import User
            self._user_obj = User.get_by_id(self.user_id)
        return self._user_obj

    @property
    def workspace(self):
        """Get workspace (lazy loaded)"""
        if not hasattr(self, '_workspace_obj'):
            from app.models.workspace import Workspace
            self._workspace_obj = Workspace.get_by_id(self.workspace_id)
        return self._workspace_obj

    @property
    def reviewed_by(self):
        """Get reviewer user (lazy loaded)"""
        if not hasattr(self, '_reviewed_by_obj') and self.reviewed_by_user_id:
            from app.models.user import User
            self._reviewed_by_obj = User.get_by_id(self.reviewed_by_user_id)
        return getattr(self, '_reviewed_by_obj', None)

    def to_dict(self, include_user: bool = False, include_workspace: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for JSON responses"""
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "reason": self.reason,
            "status": self.status.value if isinstance(self.status, JoinRequestStatus) else self.status,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "reviewed_at": self.reviewed_at.isoformat() if isinstance(self.reviewed_at, datetime) else self.reviewed_at
        }

        if include_user and self.user:
            data["user"] = self.user.to_dict()

        if include_workspace and self.workspace:
            data["workspace"] = self.workspace.to_dict()

        return data

    def __repr__(self):
        return f"<JoinRequest user={self.user_id} workspace={self.workspace_id} status={self.status.value if isinstance(self.status, JoinRequestStatus) else self.status}>"
