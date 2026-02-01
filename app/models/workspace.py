"""
Workspace Model - Firestore Version
Represents an operational unit within an organization (department, plant, team)
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid
import enum

from app.database.base_repository import BaseRepository
from google.cloud.firestore_v1 import FieldFilter


class WorkspaceType(enum.Enum):
    """Types of workspaces"""
    GENERAL = "general"
    HR = "hr"
    ENGINEERING = "engineering"
    MANUFACTURING = "manufacturing"
    PLANT = "plant"
    INVENTORY = "inventory"
    ADMIN = "admin"


class WorkspaceRole(enum.Enum):
    """Workspace-level roles"""
    ADMIN = "admin"        # Full control of workspace
    MANAGER = "manager"    # Operational control
    USER = "user"          # Regular access
    VIEWER = "viewer"      # Read-only access


class WorkspaceRepository(BaseRepository):
    """Repository for Workspace operations"""

    def __init__(self):
        super().__init__('workspaces')

    def find_by_slug(self, organization_id: str, slug: str) -> Optional[Dict[str, Any]]:
        """Find workspace by organization and slug"""
        query = self.collection.where(
            filter=FieldFilter("organization_id", "==", organization_id)
        ).where(
            filter=FieldFilter("slug", "==", slug)
        ).limit(1)

        docs = list(query.stream())
        if docs:
            data = docs[0].to_dict()
            data['id'] = docs[0].id
            return data
        return None

    def get_organization_workspaces(self, organization_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all workspaces in an organization"""
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

    def count_organization_workspaces(self, organization_id: str) -> int:
        """Count workspaces in an organization"""
        workspaces = self.get_organization_workspaces(organization_id, active_only=True)
        return len(workspaces)


class Workspace:
    """Workspace model - Firestore document wrapper"""

    repository = WorkspaceRepository()

    def __init__(self, data: Dict[str, Any]):
        """Initialize workspace from Firestore document data"""
        self.id = data.get('id')
        self.organization_id = data.get('organization_id')
        self.name = data.get('name')
        self.slug = data.get('slug')
        self.description = data.get('description')
        self.workspace_type = WorkspaceType(data.get('workspace_type', 'general'))
        self.is_active = data.get('is_active', True)
        self.created_by_user_id = data.get('created_by_user_id')
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')

        # Cached organization
        self._organization_data = data.get('_organization')

    @classmethod
    def create(cls, organization_id: str, name: str, slug: str, **kwargs) -> 'Workspace':
        """Create a new workspace"""
        workspace_id = str(uuid.uuid4())

        data = {
            'organization_id': organization_id,
            'name': name,
            'slug': slug,
            'description': kwargs.get('description'),
            'workspace_type': kwargs.get('workspace_type', 'general'),
            'is_active': kwargs.get('is_active', True),
            'created_by_user_id': kwargs.get('created_by_user_id')
        }

        created_data = cls.repository.create(workspace_id, data)
        return cls(created_data)

    @classmethod
    def get_by_id(cls, workspace_id: str) -> Optional['Workspace']:
        """Get workspace by ID"""
        data = cls.repository.get(workspace_id)
        return cls(data) if data else None

    @classmethod
    def get_by_slug(cls, organization_id: str, slug: str) -> Optional['Workspace']:
        """Get workspace by organization and slug"""
        data = cls.repository.find_by_slug(organization_id, slug)
        return cls(data) if data else None

    @classmethod
    def get_by_organization(cls, organization_id: str, active_only: bool = True) -> List['Workspace']:
        """Get all workspaces in an organization"""
        data_list = cls.repository.get_organization_workspaces(organization_id, active_only)
        return [cls(data) for data in data_list]

    def save(self) -> bool:
        """Save workspace changes to Firestore"""
        data = {
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'workspace_type': self.workspace_type.value if isinstance(self.workspace_type, WorkspaceType) else self.workspace_type,
            'is_active': self.is_active
        }

        return self.repository.update(self.id, data)

    def delete(self) -> bool:
        """Delete workspace from Firestore"""
        return self.repository.delete(self.id)

    @property
    def organization(self):
        """Get parent organization"""
        if not hasattr(self, '_organization_obj'):
            from app.models.organization import Organization
            self._organization_obj = Organization.get_by_id(self.organization_id)
        return self._organization_obj

    @property
    def members(self) -> List:
        """Get all members of this workspace"""
        from app.models.workspace_membership import WorkspaceMembership
        return WorkspaceMembership.get_workspace_members(self.id)

    @property
    def member_count(self) -> int:
        """Get count of workspace members"""
        from app.models.workspace_membership import WorkspaceMembership
        return WorkspaceMembership.count_workspace_members(self.id)

    def to_dict(self, include_member_count: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for JSON responses"""
        data = {
            "id": self.id,
            "organization_id": self.organization_id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "workspace_type": self.workspace_type.value if isinstance(self.workspace_type, WorkspaceType) else self.workspace_type,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at
        }

        if include_member_count:
            data["member_count"] = self.member_count

        return data

    def to_public_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for public display (during join request)"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "workspace_type": self.workspace_type.value if isinstance(self.workspace_type, WorkspaceType) else self.workspace_type,
            "member_count": self.member_count
        }

    def __repr__(self):
        return f"<Workspace {self.name} ({self.workspace_type.value if isinstance(self.workspace_type, WorkspaceType) else self.workspace_type})>"
