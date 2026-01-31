"""
Organization Model - Firestore Version
Each organization represents a company/factory/client
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


class OrganizationRepository(BaseRepository):
    """Repository for Organization operations"""
    
    def __init__(self):
        super().__init__('organizations')
    
    def find_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Find organization by slug"""
        return self.find_one('slug', slug)
    
    def find_by_domain(self, domain: str) -> Optional[Dict[str, Any]]:
        """Find organization by domain"""
        return self.find_one('domain', domain)


class Organization:
    """Organization model - Firestore document wrapper"""
    
    # Repository instance
    repository = OrganizationRepository()
    
    def __init__(self, data: Dict[str, Any]):
        """Initialize organization from Firestore document data"""
        self.id = data.get('id')
        self.name = data.get('name')
        self.slug = data.get('slug')
        self.domain = data.get('domain')
        self.website = data.get('website')
        self.industry_type = data.get('industry_type')
        self.company_size = data.get('company_size')
        self.country = data.get('country')
        self.plan_type = PlanType(data.get('plan_type', 'free'))
        self.max_users = data.get('max_users', 3)
        self.is_email_verified = data.get('is_email_verified', False)
        self.industrial_verified = data.get('industrial_verified', False)
        self.is_active = data.get('is_active', True)
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')
    
    @classmethod
    def create(cls, name: str, slug: str, **kwargs) -> 'Organization':
        """
        Create a new organization
        
        Args:
            name: Organization name
            slug: URL-friendly identifier
            **kwargs: Additional organization fields
            
        Returns:
            Organization instance
        """
        org_id = str(uuid.uuid4())
        
        data = {
            'name': name,
            'slug': slug,
            'domain': kwargs.get('domain'),
            'website': kwargs.get('website'),
            'industry_type': kwargs.get('industry_type'),
            'company_size': kwargs.get('company_size'),
            'country': kwargs.get('country'),
            'plan_type': kwargs.get('plan_type', 'free'),
            'max_users': kwargs.get('max_users', 3),
            'is_email_verified': kwargs.get('is_email_verified', False),
            'industrial_verified': kwargs.get('industrial_verified', False),
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
        """Get organization by domain"""
        data = cls.repository.find_by_domain(domain)
        return cls(data) if data else None
    
    def save(self) -> bool:
        """Save organization changes to Firestore"""
        data = {
            'name': self.name,
            'slug': self.slug,
            'domain': self.domain,
            'website': self.website,
            'industry_type': self.industry_type,
            'company_size': self.company_size,
            'country': self.country,
            'plan_type': self.plan_type.value,
            'max_users': self.max_users,
            'is_email_verified': self.is_email_verified,
            'industrial_verified': self.industrial_verified,
            'is_active': self.is_active
        }
        
        return self.repository.update(self.id, data)
    
    def delete(self) -> bool:
        """Delete organization from Firestore"""
        return self.repository.delete(self.id)
    
    @property
    def users(self) -> List:
        """Get all users in organization (lazy loaded)"""
        from app.models.user import User
        user_data_list = User.repository.get_organization_users(self.id)
        return [User(data) for data in user_data_list]
    
    @property
    def invitations(self) -> List:
        """Get all invitations for organization (lazy loaded)"""
        from app.models.invitation import Invitation
        invitation_data_list = Invitation.repository.get_organization_invitations(self.id)
        return [Invitation(data) for data in invitation_data_list]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON responses"""
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "domain": self.domain,
            "plan_type": self.plan_type.value,
            "is_active": self.is_active,
            "industrial_verified": self.industrial_verified,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at
        }
    
    @property
    def storage_bucket_path(self) -> str:
        """Returns the GCS bucket path for this organization"""
        return f"organizations/{self.slug}/"
    
    def __repr__(self):
        return f"<Organization {self.name} ({self.plan_type.value})>"