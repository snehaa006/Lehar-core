"""
User Service - Firestore Version (FIXED)
Business logic for user operations with enhanced error handling
"""
from app.models import User, Organization, WorkspaceMembership, OrgRole
from app.utils import is_strong_password
import logging

logger = logging.getLogger(__name__)


class UserService:
    """Handles user-related business logic"""

    @staticmethod
    def authenticate(email: str, password: str):
        """
        Authenticate a user

        Returns:
            tuple: (user, error_message)
        """
        try:
            user = User.get_by_email(email.lower())

            if not user:
                return None, "Invalid email or password"

            if not user.check_password(password):
                return None, "Invalid email or password"

            if not user.is_active:
                return None, "Your account has been deactivated. Please contact your administrator."

            # Check email verification
            if not user.is_email_verified:
                return None, "Please verify your email address before logging in."

            # Organization check is now optional - users can exist without orgs
            if user.organization_id and user.organization:
                if not user.organization.is_active:
                    return None, "Your organization is inactive. Please contact support."

            return user, None

        except Exception as e:
            logger.error(f"Error in authenticate: {str(e)}")
            return None, "An error occurred during authentication"

    @staticmethod
    def create_user(name: str, email: str, password: str, **kwargs):
        """
        Create a new user (simplified - no organization required)

        Returns:
            tuple: (user, error_message)
        """
        try:
            # Check if user already exists
            existing_user = User.get_by_email(email.lower())
            if existing_user:
                return None, "A user with this email already exists"

            # Validate password strength
            is_strong, password_msg = is_strong_password(password)
            if not is_strong:
                return None, password_msg

            # Generate verification token
            from app.utils import generate_verification_token
            verification_token = generate_verification_token()

            # Create user without organization
            user = User.create(
                name=name,
                email=email,
                password=password,
                email_verification_token=verification_token,
                is_email_verified=False,
                **kwargs
            )

            return user, None

        except Exception as e:
            logger.error(f"Error in create_user: {str(e)}")
            return None, f"An error occurred while creating the user: {str(e)}"

    @staticmethod
    def verify_email(token: str):
        """
        Verify a user's email address

        Returns:
            tuple: (success, message)
        """
        try:
            user = User.get_by_verification_token(token)

            if not user:
                return False, "Invalid verification link"

            if user.is_email_verified:
                return True, "Email already verified. You can now login."

            user.is_email_verified = True
            user.email_verification_token = None
            user.save()

            return True, "Email verified successfully! You can now login."

        except Exception as e:
            logger.error(f"Error in verify_email: {str(e)}")
            return False, "An error occurred during email verification"

    @staticmethod
    def get_organization_users(organization_id: str):
        """
        Get all users in organization with workspace count (FIXED)

        Returns:
            list: List of users with workspace_count attribute
        """
        try:
            users = User.get_by_organization(organization_id)

            # Add workspace count for each user
            for user in users:
                try:
                    memberships = WorkspaceMembership.get_user_memberships(user.id)
                    user.workspace_count = len(memberships) if memberships else 0
                except Exception as e:
                    logger.error(f"Error getting workspace count for user {user.id}: {str(e)}")
                    user.workspace_count = 0

            return users

        except Exception as e:
            logger.error(f"Error in get_organization_users: {str(e)}")
            return []

    @staticmethod
    def update_org_role(user_id: str, new_role: str, updated_by_user):
        """
        Update a user's organization role

        Returns:
            tuple: (success, message)
        """
        try:
            # Only org_owner can change roles
            if not updated_by_user.is_org_owner():
                return False, "Only organization owner can change roles"

            user = User.get_by_id(user_id)
            if not user:
                return False, "User not found"

            # Can't change own role
            if user.id == updated_by_user.id:
                return False, "You cannot change your own role"

            # Check if in same organization
            if user.organization_id != updated_by_user.organization_id:
                return False, "User not in your organization"

            # Validate new role
            valid_roles = ['member', 'org_admin']
            if new_role not in valid_roles:
                return False, f"Invalid role. Must be one of: {', '.join(valid_roles)}"

            # Update role
            user.org_role = OrgRole[new_role.upper()]
            user.save()

            return True, f"User role updated to {new_role}"

        except Exception as e:
            logger.error(f"Error in update_org_role: {str(e)}")
            return False, "An error occurred while updating the role"

    @staticmethod
    def deactivate_user(user_id: str, deactivated_by_user):
        """
        Deactivate a user

        Returns:
            tuple: (success, message)
        """
        try:
            # Check permissions
            if not deactivated_by_user.is_org_admin():
                return False, "Only administrators can deactivate users"

            user = User.get_by_id(user_id)
            if not user:
                return False, "User not found"

            # Can't deactivate yourself
            if user.id == deactivated_by_user.id:
                return False, "You cannot deactivate yourself"

            # Check if in same organization
            if user.organization_id != deactivated_by_user.organization_id:
                return False, "User not in your organization"

            # Can't deactivate org_owner
            if user.is_org_owner():
                return False, "Cannot deactivate organization owner"

            if not user.is_active:
                return False, "User is already inactive"

            # Deactivate user
            user.is_active = False
            user.save()

            return True, f"{user.name} has been deactivated"

        except Exception as e:
            logger.error(f"Error in deactivate_user: {str(e)}")
            return False, "An error occurred while deactivating the user"

    @staticmethod
    def activate_user(user_id: str, activated_by_user):
        """
        Activate a user

        Returns:
            tuple: (success, message)
        """
        try:
            # Check permissions
            if not activated_by_user.is_org_admin():
                return False, "Only administrators can activate users"

            user = User.get_by_id(user_id)
            if not user:
                return False, "User not found"

            # Check if in same organization
            if user.organization_id != activated_by_user.organization_id:
                return False, "User not in your organization"

            if user.is_active:
                return False, "User is already active"

            # Activate user
            user.is_active = True
            user.save()

            return True, f"{user.name} has been activated"

        except Exception as e:
            logger.error(f"Error in activate_user: {str(e)}")
            return False, "An error occurred while activating the user"