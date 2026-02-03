"""
User Service - Firestore Version
Business logic for user operations
"""
from datetime import datetime
from app.models import User, Organization, OrgRole


class UserService:
    """Handles user-related business logic"""

    @staticmethod
    def authenticate(email: str, password: str):
        """
        Authenticate user with email and password

        Returns:
            tuple: (user, error_message)
        """
        user = User.get_by_email(email.lower())

        if not user:
            return None, "Invalid email or password"

        if not user.check_password(password):
            return None, "Invalid email or password"

        if not user.is_active:
            return None, "Account is inactive. Please contact support."

        if not user.is_email_verified:
            return None, "Please verify your email before logging in"

        # Check organization status
        if not user.organization.is_active:
            return None, "Organization is inactive"

        # Update last login
        user.last_login = datetime.utcnow()
        user.save()

        return user, None

    @staticmethod
    def verify_email(token: str):
        """
        Verify user email with token

        Returns:
            tuple: (success, message)
        """
        from flask import current_app

        current_app.logger.info(f"Email verification attempt with token: {token[:10]}...")

        user = User.get_by_verification_token(token)

        if not user:
            current_app.logger.warning(f"No user found for verification token: {token[:10]}...")
            return False, "Invalid verification token"

        current_app.logger.info(f"Found user: {user.email} (verified: {user.is_email_verified})")

        if user.is_email_verified:
            current_app.logger.info(f"User {user.email} already verified")
            return False, "Email already verified"

        # Update user verification status
        user.is_email_verified = True
        user.email_verification_token = None

        # If this is the org_owner, also verify organization
        if user.org_role == OrgRole.ORG_OWNER:
            org = user.organization
            org.is_verified = True
            org.is_domain_verified = True
            org.save()
            current_app.logger.info(f"Organization {org.name} marked as verified")

        # Save user changes
        save_result = user.save()

        if save_result:
            current_app.logger.info(f"User {user.email} successfully verified and saved to database")
            return True, "Email verified successfully! You can now log in."
        else:
            current_app.logger.error(f"Failed to save verification status for user {user.email}")
            return False, "Verification failed. Please try again or contact support."

    @staticmethod
    def get_user_by_email(email: str):
        """Find user by email"""
        return User.get_by_email(email.lower())

    @staticmethod
    def update_org_role(user_id: str, new_role: str, updated_by_user):
        """
        Update user's organization role (only org_owner can do this)
        """
        if not updated_by_user.is_org_owner():
            return False, "Only organization owner can change organization roles"

        user = User.get_by_id(user_id)
        if not user:
            return False, "User not found"

        # Can't change your own role
        if user.id == updated_by_user.id:
            return False, "Cannot change your own role"

        # Can't change role if not in same organization
        if user.organization_id != updated_by_user.organization_id:
            return False, "Cannot manage users from other organizations"

        # Can't have multiple org_owners
        if new_role == 'org_owner':
            return False, "There can only be one organization owner"

        user.org_role = OrgRole[new_role.upper()]
        user.save()

        return True, "Role updated successfully"

    @staticmethod
    def deactivate_user(user_id: str, deactivated_by_user):
        """Deactivate a user"""
        if not deactivated_by_user.is_org_admin():
            return False, "Insufficient permissions"

        user = User.get_by_id(user_id)
        if not user:
            return False, "User not found"

        if user.id == deactivated_by_user.id:
            return False, "Cannot deactivate yourself"

        if user.organization_id != deactivated_by_user.organization_id:
            return False, "Cannot manage users from other organizations"

        # Can't deactivate org_owner
        if user.is_org_owner():
            return False, "Cannot deactivate organization owner"

        user._is_active = False
        user.save()

        return True, "User deactivated successfully"

    @staticmethod
    def activate_user(user_id: str, activated_by_user):
        """Activate a user"""
        if not activated_by_user.is_org_admin():
            return False, "Insufficient permissions"

        user = User.get_by_id(user_id)
        if not user:
            return False, "User not found"

        if user.organization_id != activated_by_user.organization_id:
            return False, "Cannot manage users from other organizations"

        user._is_active = True
        user.save()

        return True, "User activated successfully"

    @staticmethod
    def get_organization_users(organization_id: str):
        """Get all users in an organization"""
        user_data_list = User.repository.get_organization_users(organization_id, active_only=False)
        return [User(data) for data in user_data_list]

    @staticmethod
    def create_user_from_invitation(invitation, password: str, name: str = None):
        """
        Create a new user from an accepted invitation

        Returns:
            tuple: (user, error_message)
        """
        from app.models import WorkspaceMembership

        try:
            # Check if user already exists
            existing_user = User.get_by_email(invitation.email)
            if existing_user:
                # User exists, just add to workspace
                if existing_user.organization_id != invitation.organization_id:
                    return None, "User belongs to a different organization"

                # Add to workspace
                WorkspaceMembership.create(
                    user_id=existing_user.id,
                    workspace_id=invitation.workspace_id,
                    workspace_role=invitation.workspace_role.value if hasattr(invitation.workspace_role, 'value') else invitation.workspace_role,
                    added_by_user_id=invitation.invited_by_user_id
                )

                return existing_user, None

            # Create new user
            user = User.create(
                organization_id=invitation.organization_id,
                name=name or invitation.name or invitation.email.split('@')[0],
                email=invitation.email,
                password=password,
                org_role='member',
                is_email_verified=True,  # Auto-verify since they clicked invite link
                is_active=True
            )

            # Add to workspace
            WorkspaceMembership.create(
                user_id=user.id,
                workspace_id=invitation.workspace_id,
                workspace_role=invitation.workspace_role.value if hasattr(invitation.workspace_role, 'value') else invitation.workspace_role,
                added_by_user_id=invitation.invited_by_user_id
            )

            return user, None

        except Exception as e:
            return None, str(e)
