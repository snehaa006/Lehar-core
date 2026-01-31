"""
User Service - Firestore Version
Business logic for user operations
"""
from app.models import User, Organization
from datetime import datetime
# Add to imports at the top of the file
from app.models.user import UserRole

class UserService:
    """Handles user-related business logic"""
    
    @staticmethod
    def authenticate(email, password):
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
    def verify_email(token):
        """
        Verify user email with token
        
        Returns:
            tuple: (success, message)
        """
        from flask import current_app
        
        # Log verification attempt
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
        
        # If this is the first user (admin), also verify organization email
        if user.role == UserRole.SUPER_ADMIN:
            org = user.organization
            org.is_email_verified = True
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
    def get_user_by_email(email):
        """Find user by email"""
        return User.get_by_email(email.lower())
    
    @staticmethod
    def update_user_role(user_id, new_role, updated_by_user):
        """
        Update user role (only super_admin and admin can do this)
        """
        if updated_by_user.role.value not in ["super_admin", "admin"]:
            return False, "Insufficient permissions"
        
        user = User.get_by_id(user_id)
        if not user:
            return False, "User not found"
        
        # Can't change your own role
        if user.id == updated_by_user.id:
            return False, "Cannot change your own role"
        
        # Can't change role if not in same organization
        if user.organization_id != updated_by_user.organization_id:
            return False, "Cannot manage users from other organizations"
        
        from app.models import UserRole
        user.role = UserRole[new_role.upper()]
        user.save()
        
        return True, "Role updated successfully"
    
    @staticmethod
    def deactivate_user(user_id, deactivated_by_user):
        """Deactivate a user"""
        if deactivated_by_user.role.value not in ["super_admin", "admin"]:
            return False, "Insufficient permissions"
        
        user = User.get_by_id(user_id)
        if not user:
            return False, "User not found"
        
        if user.id == deactivated_by_user.id:
            return False, "Cannot deactivate yourself"
        
        if user.organization_id != deactivated_by_user.organization_id:
            return False, "Cannot manage users from other organizations"
        
        user.is_active = False
        user.save()
        
        return True, "User deactivated successfully"
    
    @staticmethod
    def get_organization_users(organization_id):
        """Get all users in an organization"""
        user_data_list = User.repository.get_organization_users(organization_id, active_only=True)
        return [User(data) for data in user_data_list]