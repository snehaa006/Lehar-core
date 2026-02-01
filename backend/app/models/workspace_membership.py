"""
Workspace Membership Model - Firestore Version
Links users to workspaces with specific roles
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid

from app.database.base_repository import BaseRepository
from app.models.workspace import WorkspaceRole
from google.cloud.firestore_v1 import FieldFilter


class WorkspaceMembershipRepository(BaseRepository):
    """Repository for WorkspaceMembership operations"""

    def __init__(self):
        super().__init__('workspace_memberships')

    def find_membership(self, user_id: str, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Find membership for a user in a workspace"""
        query = self.collection.where(
            filter=FieldFilter("user_id", "==", user_id)
        ).where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        ).limit(1)

        docs = list(query.stream())
        if docs:
            data = docs[0].to_dict()
            data['id'] = docs[0].id
            return data
        return None

    def get_user_memberships(self, user_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all workspace memberships for a user"""
        query = self.collection.where(
            filter=FieldFilter("user_id", "==", user_id)
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

    def get_workspace_members(self, workspace_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all members of a workspace"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
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

    def get_workspace_admins(self, workspace_id: str) -> List[Dict[str, Any]]:
        """Get all admins of a workspace"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        ).where(
            filter=FieldFilter("is_active", "==", True)
        ).where(
            filter=FieldFilter("workspace_role", "==", "admin")
        )

        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)

        return results

    def count_workspace_members(self, workspace_id: str) -> int:
        """Count members in a workspace"""
        members = self.get_workspace_members(workspace_id, active_only=True)
        return len(members)


class WorkspaceMembership:
    """Workspace Membership model - Firestore document wrapper"""

    repository = WorkspaceMembershipRepository()

    def __init__(self, data: Dict[str, Any]):
        """Initialize membership from Firestore document data"""
        self.id = data.get('id')
        self.user_id = data.get('user_id')
        self.workspace_id = data.get('workspace_id')
        self.workspace_role = WorkspaceRole(data.get('workspace_role', 'user'))
        self.is_active = data.get('is_active', True)
        self.added_by_user_id = data.get('added_by_user_id')
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')

        # Cached objects
        self._user_data = data.get('_user')
        self._workspace_data = data.get('_workspace')

    @classmethod
    def create(cls, user_id: str, workspace_id: str, workspace_role: str = 'user',
               **kwargs) -> 'WorkspaceMembership':
        """Create a new workspace membership"""
        membership_id = str(uuid.uuid4())

        data = {
            'user_id': user_id,
            'workspace_id': workspace_id,
            'workspace_role': workspace_role,
            'is_active': kwargs.get('is_active', True),
            'added_by_user_id': kwargs.get('added_by_user_id')
        }

        created_data = cls.repository.create(membership_id, data)
        return cls(created_data)

    @classmethod
    def get_by_id(cls, membership_id: str) -> Optional['WorkspaceMembership']:
        """Get membership by ID"""
        data = cls.repository.get(membership_id)
        return cls(data) if data else None

    @classmethod
    def get_membership(cls, user_id: str, workspace_id: str) -> Optional['WorkspaceMembership']:
        """Get membership for user in workspace"""
        data = cls.repository.find_membership(user_id, workspace_id)
        return cls(data) if data else None

    @classmethod
    def get_user_memberships(cls, user_id: str, active_only: bool = True) -> List['WorkspaceMembership']:
        """Get all memberships for a user"""
        data_list = cls.repository.get_user_memberships(user_id, active_only)
        return [cls(data) for data in data_list]

    @classmethod
    def get_workspace_members(cls, workspace_id: str, active_only: bool = True) -> List['WorkspaceMembership']:
        """Get all members of a workspace"""
        data_list = cls.repository.get_workspace_members(workspace_id, active_only)
        return [cls(data) for data in data_list]

    @classmethod
    def get_workspace_admins(cls, workspace_id: str) -> List['WorkspaceMembership']:
        """Get all admins of a workspace"""
        data_list = cls.repository.get_workspace_admins(workspace_id)
        return [cls(data) for data in data_list]

    @classmethod
    def count_workspace_members(cls, workspace_id: str) -> int:
        """Count members in a workspace"""
        return cls.repository.count_workspace_members(workspace_id)

    @classmethod
    def user_is_workspace_admin(cls, user_id: str, workspace_id: str) -> bool:
        """Check if user is admin of workspace"""
        membership = cls.get_membership(user_id, workspace_id)
        if not membership or not membership.is_active:
            return False
        return membership.workspace_role == WorkspaceRole.ADMIN

    @classmethod
    def user_is_workspace_member(cls, user_id: str, workspace_id: str) -> bool:
        """Check if user is a member of workspace"""
        membership = cls.get_membership(user_id, workspace_id)
        return membership is not None and membership.is_active

    def save(self) -> bool:
        """Save membership changes to Firestore"""
        data = {
            'workspace_role': self.workspace_role.value if isinstance(self.workspace_role, WorkspaceRole) else self.workspace_role,
            'is_active': self.is_active
        }

        return self.repository.update(self.id, data)

    def delete(self) -> bool:
        """Delete membership from Firestore"""
        return self.repository.delete(self.id)

    @property
    def user(self):
        """Get user (lazy loaded)"""
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

    def to_dict(self, include_user: bool = False, include_workspace: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for JSON responses"""
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "workspace_role": self.workspace_role.value if isinstance(self.workspace_role, WorkspaceRole) else self.workspace_role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at
        }

        if include_user and self.user:
            data["user"] = self.user.to_dict()

        if include_workspace and self.workspace:
            data["workspace"] = self.workspace.to_dict()

        return data

    def __repr__(self):
        return f"<WorkspaceMembership user={self.user_id} workspace={self.workspace_id} role={self.workspace_role.value if isinstance(self.workspace_role, WorkspaceRole) else self.workspace_role}>"
