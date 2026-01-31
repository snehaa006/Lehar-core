"""
Invitation Service - Firestore Version
Business logic for user invitations
"""
from app.models import Invitation, User, UserRole
from app.utils import generate_verification_token, send_invitation_email
from app.services.organization_service import OrganizationService
from datetime import datetime


class InvitationService:
    """Handles invitation-related business logic"""
    
    @staticmethod
    def create_invitation(email, name, role, organization_id, invited_by_user):
        """
        Create and send an invitation
        
        Args:
            email: Invitee email
            name: Invitee name (optional)
            role: Role to assign
            organization_id: Organization ID
            invited_by_user: User who is sending the invite
        
        Returns:
            tuple: (invitation, error_message)
        """
        # Check permissions
        if invited_by_user.role.value not in ["super_admin", "admin"]:
            return None, "Only admins can invite users"
        
        # Check if organization can add more users
        if not OrganizationService.can_add_user(invited_by_user.organization):
            return None, "User limit reached. Please upgrade your plan."
        
        # Check if user already exists
        existing_user = User.get_by_email(email.lower())
        if existing_user:
            if existing_user.organization_id == organization_id:
                return None, "User is already part of this organization"
            else:
                return None, "User already has an account with another organization"
        
        # Check if invitation already exists
        existing_invite = Invitation.get_pending_for_email(organization_id, email.lower())
        
        # FIX: existing_invite is already an Invitation object, don't wrap it again
        if existing_invite and existing_invite.is_valid():
            return None, "Invitation already sent to this email"
        
        # Create invitation
        invitation = Invitation.create(
            email=email.lower(),
            name=name,
            role=role,
            organization_id=organization_id,
            invited_by_user_id=invited_by_user.id
        )
        
        # Send invitation email
        send_invitation_email(
            invite_email=email,
            invite_name=name,
            organization_name=invited_by_user.organization.name,
            invitation_token=invitation.token,
            invited_by_name=invited_by_user.name
        )
        
        return invitation, None
    
    @staticmethod
    def accept_invitation(token, user_data):
        """
        Accept an invitation and create user account
        
        Args:
            token: Invitation token
            user_data: Dict with user details (password, phone, etc.)
        
        Returns:
            tuple: (user, error_message)
        """
        invitation = Invitation.get_by_token(token)
        
        if not invitation:
            return None, "Invalid invitation token"
        
        if not invitation.is_valid():
            return None, "Invitation has expired or is no longer valid"
        
        # Create user
        user = User.create(
            organization_id=invitation.organization_id,
            name=invitation.name or user_data.get("name"),
            email=invitation.email,
            password=user_data["password"],
            phone=user_data.get("phone"),
            role=invitation.role,
            is_email_verified=True,  # Auto-verify invited users
            is_active=True
        )
        
        # Update invitation status
        invitation.accept()
        
        return user, None
    
    @staticmethod
    def cancel_invitation(invitation_id, cancelled_by_user):
        """Cancel a pending invitation"""
        invitation = Invitation.get_by_id(invitation_id)
        
        if not invitation:
            return False, "Invitation not found"
        
        if invitation.organization_id != cancelled_by_user.organization_id:
            return False, "Cannot cancel invitations from other organizations"
        
        if cancelled_by_user.role.value not in ["super_admin", "admin"]:
            return False, "Only admins can cancel invitations"
        
        invitation.cancel()
        
        return True, "Invitation cancelled"
    
    @staticmethod
    def get_organization_invitations(organization_id, status=None):
        """Get all invitations for an organization"""
        invitation_data_list = Invitation.repository.get_organization_invitations(
            organization_id,
            status=status
        )
        
        # Convert to Invitation objects
        invitations = [Invitation(data) for data in invitation_data_list]
        
        # Sort by created_at (most recent first)
        invitations.sort(
            key=lambda x: x.created_at if isinstance(x.created_at, datetime) else datetime.min,
            reverse=True
        )
        
        return invitations