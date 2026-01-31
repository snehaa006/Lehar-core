"""
Organization Service - Firestore Version
Business logic for organization operations
"""
from app.models import Organization, User, UserRole, PlanType
from app.utils import sanitize_slug, extract_domain_from_email, is_work_email


class OrganizationService:
    """Handles organization-related business logic"""
    
    @staticmethod
    def create_organization(org_data, admin_data):
        """
        Create a new organization with its first admin user
        
        Args:
            org_data: dict with organization details
            admin_data: dict with admin user details
        
        Returns:
            tuple: (organization, admin_user, error_message)
        """
        try:
            # Extract domain from admin email
            domain = extract_domain_from_email(admin_data["email"])
            
            # Check if organization with this domain already exists
            existing_org = Organization.get_by_domain(domain)
            if existing_org and is_work_email(admin_data["email"]):
                return None, None, f"Organization with domain {domain} already exists. Please contact your admin."
            
            # Create organization slug
            org_slug = sanitize_slug(org_data["name"])
            
            # Ensure slug is unique
            base_slug = org_slug
            counter = 1
            while Organization.get_by_slug(org_slug):
                org_slug = f"{base_slug}-{counter}"
                counter += 1
            
            # Create organization
            organization = Organization.create(
                name=org_data["name"],
                slug=org_slug,
                domain=domain if is_work_email(admin_data["email"]) else None,
                website=org_data.get("website"),
                industry_type=org_data.get("industry_type"),
                company_size=org_data.get("company_size"),
                country=org_data.get("country"),
                plan_type='free',
                max_users=3  # Free plan default
            )
            
            # Create admin user
            from app.utils import generate_verification_token
            
            admin_user = User.create(
                organization_id=organization.id,
                name=admin_data["name"],
                email=admin_data["email"],
                password=admin_data["password"],  # Will be hashed by User.create
                phone=admin_data.get("phone"),
                role='super_admin',
                job_title=admin_data.get("job_title"),
                email_verification_token=generate_verification_token()
            )
            
            return organization, admin_user, None
        
        except Exception as e:
            return None, None, str(e)
    
    @staticmethod
    def get_organization_by_domain(domain):
        """Find organization by email domain"""
        return Organization.get_by_domain(domain)
    
    @staticmethod
    def get_organization_by_slug(slug):
        """Find organization by slug"""
        return Organization.get_by_slug(slug)
    
    @staticmethod
    def can_add_user(organization):
        """Check if organization can add more users based on plan"""
        if organization.max_users is None:  # Enterprise = unlimited
            return True
        
        current_user_count = User.repository.count_organization_users(
            organization.id,
            active_only=True
        )
        
        return current_user_count < organization.max_users
    
    @staticmethod
    def upgrade_plan(organization, new_plan_type):
        """Upgrade organization plan"""
        from config.config import Config
        
        plan_config = Config.PLAN_LIMITS.get(new_plan_type)
        if not plan_config:
            return False, "Invalid plan type"
        
        organization.plan_type = PlanType[new_plan_type.upper()]
        organization.max_users = plan_config["max_users"]
        
        organization.save()
        return True, "Plan upgraded successfully"
    
    @staticmethod
    def verify_organization(organization_id):
        """Mark organization as industrially verified"""
        organization = Organization.get_by_id(organization_id)
        if organization:
            organization.industrial_verified = True
            organization.save()
            return True
        return False