"""
Organization Service - Firestore Version
Business logic for organization operations
"""
from app.models import Organization, User, Workspace, WorkspaceMembership, OrgRole, PlanType
from app.utils import sanitize_slug, extract_domain_from_email, is_work_email


class OrganizationService:
    """Handles organization-related business logic"""

    @staticmethod
    def create_organization_with_workspace(org_data: dict, admin_data: dict, workspace_data: dict):
        """
        Create a new organization with its first admin user and first workspace

        Args:
            org_data: dict with organization details
            admin_data: dict with admin user details
            workspace_data: dict with first workspace details

        Returns:
            tuple: (organization, admin_user, workspace, error_message)
        """
        try:
            # Extract domain from admin email
            domain = extract_domain_from_email(admin_data["email"])
            is_work = is_work_email(admin_data["email"])

            # For work emails, check if organization with this domain already exists
            if is_work:
                existing_org = Organization.get_by_domain(domain)
                if existing_org:
                    return None, None, None, f"Organization with domain {domain} already exists. Please request to join an existing workspace."

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
                primary_domain=domain if is_work else None,
                website=org_data.get("website"),
                industry_type=org_data.get("industry_type"),
                company_size=org_data.get("company_size"),
                country=org_data.get("country"),
                plan_type='free',
                max_users=5,
                max_workspaces=3
            )

            # Create admin user (org_owner)
            from app.utils import generate_verification_token

            admin_user = User.create(
                organization_id=organization.id,
                name=admin_data["name"],
                email=admin_data["email"],
                password=admin_data["password"],
                phone=admin_data.get("phone"),
                org_role='org_owner',
                job_title=admin_data.get("job_title"),
                email_verification_token=generate_verification_token()
            )

            # Create first workspace
            workspace_slug = sanitize_slug(workspace_data["name"])
            workspace = Workspace.create(
                organization_id=organization.id,
                name=workspace_data["name"],
                slug=workspace_slug,
                description=workspace_data.get("description"),
                workspace_type=workspace_data.get("workspace_type", "general"),
                created_by_user_id=admin_user.id
            )

            # Add admin user as workspace admin
            WorkspaceMembership.create(
                user_id=admin_user.id,
                workspace_id=workspace.id,
                workspace_role='admin',
                added_by_user_id=admin_user.id
            )

            return organization, admin_user, workspace, None

        except Exception as e:
            return None, None, None, str(e)

    @staticmethod
    def get_organization_by_domain(domain: str):
        """Find organization by email domain"""
        return Organization.get_by_domain(domain)

    @staticmethod
    def get_organization_by_slug(slug: str):
        """Find organization by slug"""
        return Organization.get_by_slug(slug)

    @staticmethod
    def get_workspaces_for_domain(domain: str):
        """
        Get all workspaces for organizations with this domain
        Used during registration to show available workspaces

        Returns list of dict with workspace info for display
        """
        organizations = Organization.get_all_by_domain(domain)
        workspaces_info = []

        for org in organizations:
            workspaces = Workspace.get_by_organization(org.id, active_only=True)
            for workspace in workspaces:
                workspaces_info.append({
                    'workspace_id': workspace.id,
                    'workspace_name': workspace.name,
                    'workspace_description': workspace.description,
                    'workspace_type': workspace.workspace_type.value if hasattr(workspace.workspace_type, 'value') else workspace.workspace_type,
                    'member_count': workspace.member_count,
                    'organization_id': org.id,
                    'organization_name': org.name
                })

        return workspaces_info

    @staticmethod
    def can_add_user(organization):
        """Check if organization can add more users based on plan"""
        return organization.can_add_user()

    @staticmethod
    def can_add_workspace(organization):
        """Check if organization can add more workspaces based on plan"""
        return organization.can_add_workspace()

    @staticmethod
    def upgrade_plan(organization, new_plan_type: str):
        """Upgrade organization plan"""
        from config.config import Config

        plan_config = Config.PLAN_LIMITS.get(new_plan_type)
        if not plan_config:
            return False, "Invalid plan type"

        organization.plan_type = PlanType[new_plan_type.upper()]
        organization.max_users = plan_config["max_users"]
        organization.max_workspaces = plan_config.get("max_workspaces", 10)

        organization.save()
        return True, "Plan upgraded successfully"

    @staticmethod
    def verify_organization(organization_id: str):
        """Mark organization as verified"""
        organization = Organization.get_by_id(organization_id)
        if organization:
            organization.is_verified = True
            organization.save()
            return True
        return False
