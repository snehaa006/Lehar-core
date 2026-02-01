"""
Organization Model - Firestore Version
Represents a company/business entity
Users belong to one organization, workspaces exist within organizations
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid
import enum

from app.database.base_repository import BaseRepository


class PlanType(enum.Enum):
    """Subscription plan types"""
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class OrgRole(enum.Enum):
    """Organization-level roles"""
    ORG_OWNER = "org_owner"      # Full control: billing, workspaces, domains
    ORG_ADMIN = "org_admin"      # Manage users, workspaces (no billing)
    MEMBER = "member"            # Regular org member


class OrganizationRepository(BaseRepository):
    """Repository for Organization operations"""

    def __init__(self):
        super().__init__('organizations')

    def find_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Find organization by slug"""
        return self.find_one('slug', slug)

    def find_by_domain(self, domain: str) -> Optional[Dict[str, Any]]:
        """Find organization by primary domain"""
        return self.find_one('primary_domain', domain)

    def find_by_domains(self, domain: str) -> List[Dict[str, Any]]:
        """Find all organizations that have this domain (primary or secondary)"""
        from google.cloud.firestore_v1 import FieldFilter

        # First check primary domain
        results = []
        primary = self.find_one('primary_domain', domain)
        if primary:
            results.append(primary)

        # Check secondary domains (stored as array)
        query = self.collection.where(
            filter=FieldFilter("secondary_domains", "array_contains", domain)
        )
        docs = query.stream()
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            if data['id'] not in [r['id'] for r in results]:
                results.append(data)

        return results


class Organization:
    """Organization model - Firestore document wrapper"""

    repository = OrganizationRepository()

    def __init__(self, data: Dict[str, Any]):
        """Initialize organization from Firestore document data"""
        self.id = data.get('id')
        self.name = data.get('name')
        self.slug = data.get('slug')
        self.primary_domain = data.get('primary_domain')
        self.secondary_domains = data.get('secondary_domains', [])
        self.website = data.get('website')
        self.industry_type = data.get('industry_type')
        self.company_size = data.get('company_size')
        self.country = data.get('country')
        self.plan_type = PlanType(data.get('plan_type', 'free'))
        self.max_users = data.get('max_users', 5)
        self.max_workspaces = data.get('max_workspaces', 3)
        self.is_verified = data.get('is_verified', False)
        self.is_domain_verified = data.get('is_domain_verified', False)
        self.is_active = data.get('is_active', True)
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')

    @classmethod
    def create(cls, name: str, slug: str, **kwargs) -> 'Organization':
        """Create a new organization"""
        org_id = str(uuid.uuid4())

        data = {
            'name': name,
            'slug': slug,
            'primary_domain': kwargs.get('primary_domain'),
            'secondary_domains': kwargs.get('secondary_domains', []),
            'website': kwargs.get('website'),
            'industry_type': kwargs.get('industry_type'),
            'company_size': kwargs.get('company_size'),
            'country': kwargs.get('country'),
            'plan_type': kwargs.get('plan_type', 'free'),
            'max_users': kwargs.get('max_users', 5),
            'max_workspaces': kwargs.get('max_workspaces', 3),
            'is_verified': kwargs.get('is_verified', False),
            'is_domain_verified': kwargs.get('is_domain_verified', False),
            'is_active': kwargs.get('is_active', True)
        }

        created_data = cls.repository.create(org_id, data)
        return cls(created_data)

    @classmethod
    def get_by_id(cls, org_id: str) -> Optional['Organization']:
        """Get organization by ID"""
        data = cls.repository.get(org_id)
        return cls(data) if data else None

    @classmethod
    def get_by_slug(cls, slug: str) -> Optional['Organization']:
        """Get organization by slug"""
        data = cls.repository.find_by_slug(slug)
        return cls(data) if data else None

    @classmethod
    def get_by_domain(cls, domain: str) -> Optional['Organization']:
        """Get organization by primary domain"""
        data = cls.repository.find_by_domain(domain)
        return cls(data) if data else None

    @classmethod
    def get_all_by_domain(cls, domain: str) -> List['Organization']:
        """Get all organizations with this domain (for workspace listing)"""
        data_list = cls.repository.find_by_domains(domain)
        return [cls(data) for data in data_list]

    def save(self) -> bool:
        """Save organization changes to Firestore"""
        data = {
            'name': self.name,
            'slug': self.slug,
            'primary_domain': self.primary_domain,
            'secondary_domains': self.secondary_domains,
            'website': self.website,
            'industry_type': self.industry_type,
            'company_size': self.company_size,
            'country': self.country,
            'plan_type': self.plan_type.value if isinstance(self.plan_type, PlanType) else self.plan_type,
            'max_users': self.max_users,
            'max_workspaces': self.max_workspaces,
            'is_verified': self.is_verified,
            'is_domain_verified': self.is_domain_verified,
            'is_active': self.is_active
        }

        return self.repository.update(self.id, data)

    def delete(self) -> bool:
        """Delete organization from Firestore"""
        return self.repository.delete(self.id)

    @property
    def workspaces(self) -> List:
        """Get all workspaces in organization"""
        from app.models.workspace import Workspace
        return Workspace.get_by_organization(self.id)

    @property
    def users(self) -> List:
        """Get all users in organization"""
        from app.models.user import User
        user_data_list = User.repository.get_organization_users(self.id)
        return [User(data) for data in user_data_list]

    def add_secondary_domain(self, domain: str) -> bool:
        """Add a secondary domain to organization"""
        if domain not in self.secondary_domains:
            self.secondary_domains.append(domain)
            return self.save()
        return True

    def can_add_workspace(self) -> bool:
        """Check if organization can add more workspaces"""
        if self.max_workspaces is None:  # Enterprise = unlimited
            return True
        current_count = len(self.workspaces)
        return current_count < self.max_workspaces

    def can_add_user(self) -> bool:
        """Check if organization can add more users"""
        if self.max_users is None:  # Enterprise = unlimited
            return True
        current_count = len(self.users)
        return current_count < self.max_users

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON responses"""
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "primary_domain": self.primary_domain,
            "plan_type": self.plan_type.value if isinstance(self.plan_type, PlanType) else self.plan_type,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at
        }

    def __repr__(self):
        return f"<Organization {self.name} ({self.plan_type.value if isinstance(self.plan_type, PlanType) else self.plan_type})>"
