"""
Workspace Model - Firestore Version
Represents an operational unit (department, plant, team)
Organization is now optional - workspaces can be standalone
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid
import enum
import random
import string

from app.database.base_repository import BaseRepository
from google.cloud.firestore_v1 import FieldFilter


def generate_join_code() -> str:
    """Generate a short, readable join code like ABC-123"""
    letters = ''.join(random.choices(string.ascii_uppercase, k=3))
    numbers = ''.join(random.choices(string.digits, k=3))
    return f"{letters}-{numbers}"


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

    def find_by_join_code(self, join_code: str) -> Optional[Dict[str, Any]]:
        """Find workspace by join code"""
        return self.find_one('join_code', join_code.upper())

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

    def join_code_exists(self, join_code: str) -> bool:
        """Check if a join code already exists"""
        existing = self.find_one('join_code', join_code.upper())
        return existing is not None


class Workspace:
    """Workspace model - Firestore document wrapper"""

    repository = WorkspaceRepository()

    def __init__(self, data: Dict[str, Any]):
        """Initialize workspace from Firestore document data"""
        self.id = data.get('id')
        self.organization_id = data.get('organization_id')  # Now optional
        self.name = data.get('name')
        self.slug = data.get('slug')
        self.description = data.get('description')
        self.workspace_type = WorkspaceType(data.get('workspace_type', 'general'))
        self.is_active = data.get('is_active', True)
        self.created_by_user_id = data.get('created_by_user_id')
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')
        self.join_code = data.get('join_code')  # Short code for joining (e.g., ABC-123)

        # Organization details stored directly on workspace (for display purposes)
        self.org_name = data.get('org_name')  # Organization/company name
        self.org_industry = data.get('org_industry')  # Industry type
        self.org_size = data.get('org_size')  # Company size
        self.org_website = data.get('org_website')  # Website
        self.is_domain_verified = data.get('is_domain_verified', False)  # Optional domain verification
        self.verified_domain = data.get('verified_domain')  # The verified email domain

        # Cached organization (for backward compatibility)
        self._organization_data = data.get('_organization')

    @classmethod
    def create(cls, name: str, slug: str, organization_id: str = None, **kwargs) -> 'Workspace':
        """Create a new workspace - organization_id is now optional"""
        workspace_id = str(uuid.uuid4())

        # Generate unique join code
        join_code = generate_join_code()
        while cls.repository.join_code_exists(join_code):
            join_code = generate_join_code()

        data = {
            'organization_id': organization_id,  # Can be None
            'name': name,
            'slug': slug,
            'description': kwargs.get('description'),
            'workspace_type': kwargs.get('workspace_type', 'general'),
            'is_active': kwargs.get('is_active', True),
            'created_by_user_id': kwargs.get('created_by_user_id'),
            'join_code': join_code,
            # Organization details (for display purposes)
            'org_name': kwargs.get('org_name'),
            'org_industry': kwargs.get('org_industry'),
            'org_size': kwargs.get('org_size'),
            'org_website': kwargs.get('org_website'),
            'is_domain_verified': kwargs.get('is_domain_verified', False),
            'verified_domain': kwargs.get('verified_domain')
        }

        created_data = cls.repository.create(workspace_id, data)
        return cls(created_data)

    @classmethod
    def get_by_id(cls, workspace_id: str) -> Optional['Workspace']:
        """Get workspace by ID"""
        data = cls.repository.get(workspace_id)
        return cls(data) if data else None

    @classmethod
    def get_by_join_code(cls, join_code: str) -> Optional['Workspace']:
        """Get workspace by join code"""
        data = cls.repository.find_by_join_code(join_code)
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
            'is_active': self.is_active,
            'join_code': self.join_code,
            'org_name': self.org_name,
            'org_industry': self.org_industry,
            'org_size': self.org_size,
            'org_website': self.org_website,
            'is_domain_verified': self.is_domain_verified,
            'verified_domain': self.verified_domain
        }

        return self.repository.update(self.id, data)

    def delete(self) -> bool:
        """Delete workspace from Firestore"""
        return self.repository.delete(self.id)

    @property
    def organization(self):
        """Get parent organization - returns None if workspace has no organization"""
        if not self.organization_id:
            return None
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
            "join_code": self.join_code,
            "org_name": self.org_name,
            "org_industry": self.org_industry,
            "org_size": self.org_size,
            "org_website": self.org_website,
            "is_domain_verified": self.is_domain_verified,
            "verified_domain": self.verified_domain,
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
            "org_name": self.org_name,
            "member_count": self.member_count,
            "is_domain_verified": self.is_domain_verified
        }

    def __repr__(self):
        return f"<Workspace {self.name} ({self.workspace_type.value if isinstance(self.workspace_type, WorkspaceType) else self.workspace_type})>"
