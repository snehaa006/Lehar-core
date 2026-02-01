"""
Invitation Service - Firestore Version
Business logic for workspace-specific invitations
"""
from app.models import Invitation, User, WorkspaceMembership, Workspace, Organization
from app.utils import send_invitation_email
from datetime import datetime


class InvitationService:
    """Handles invitation-related business logic"""

    @staticmethod
    def create_invitation(workspace_id: str, email: str, workspace_role: str,
                          invited_by_user, name: str = None):
        """
        Create and send a workspace invitation

        Args:
            workspace_id: Workspace ID to invite to
            email: Invitee email
            workspace_role: Role to assign in workspace
            invited_by_user: User who is sending the invite
            name: Invitee name (optional)

        Returns:
            tuple: (invitation, error_message)
        """
        # Get workspace and organization
        workspace = Workspace.get_by_id(workspace_id)
        if not workspace:
            return None, "Workspace not found"

        organization = Organization.get_by_id(workspace.organization_id)
        if not organization:
            return None, "Organization not found"

        # Check permissions - must be workspace admin or org admin
        is_workspace_admin = WorkspaceMembership.user_is_workspace_admin(
            invited_by_user.id, workspace_id
        )
        if not is_workspace_admin and not invited_by_user.is_org_admin():
            return None, "Only workspace admins can invite users"

        # Check if user already exists
        existing_user = User.get_by_email(email.lower())
        if existing_user:
            # Check if already in workspace
            if WorkspaceMembership.user_is_workspace_member(existing_user.id, workspace_id):
                return None, "User is already a member of this workspace"

            # Check if in same organization
            if existing_user.organization_id != workspace.organization_id:
                return None, "User belongs to a different organization"

        # Check organization user limit for new users
        if not existing_user and not organization.can_add_user():
            return None, "Organization user limit reached. Please upgrade your plan."

        # Check if invitation already exists
        existing_invite = Invitation.get_pending_for_email(workspace_id, email.lower())
        if existing_invite and existing_invite.is_valid():
            return None, "A pending invitation already exists for this email"

        # Create invitation
        invitation = Invitation.create(
            organization_id=workspace.organization_id,
            workspace_id=workspace_id,
            email=email.lower(),
            workspace_role=workspace_role,
            invited_by_user_id=invited_by_user.id,
            name=name
        )

        # Send invitation email
        send_invitation_email(
            invite_email=email,
            invite_name=name,
            organization_name=organization.name,
            workspace_name=workspace.name,
            invitation_token=invitation.token,
            invited_by_name=invited_by_user.name
        )

        return invitation, None

    @staticmethod
    def accept_invitation(token: str, user_data: dict):
        """
        Accept an invitation and create user account / add to workspace

        Args:
            token: Invitation token
            user_data: Dict with user details (password, name, phone, etc.)

        Returns:
            tuple: (user, error_message)
        """
        invitation = Invitation.get_by_token(token)

        if not invitation:
            return None, "Invalid invitation token"

        if not invitation.is_valid():
            return None, "Invitation has expired or is no longer valid"

        # Check if user already exists
        existing_user = User.get_by_email(invitation.email)

        if existing_user:
            # User exists - check organization
            if existing_user.organization_id != invitation.organization_id:
                return None, "User belongs to a different organization"

            # Add to workspace if not already a member
            if not WorkspaceMembership.user_is_workspace_member(existing_user.id, invitation.workspace_id):
                WorkspaceMembership.create(
                    user_id=existing_user.id,
                    workspace_id=invitation.workspace_id,
                    workspace_role=invitation.workspace_role.value if hasattr(invitation.workspace_role, 'value') else invitation.workspace_role,
                    added_by_user_id=invitation.invited_by_user_id
                )

            # Mark invitation as accepted
            invitation.accept()

            return existing_user, None

        # Create new user
        user = User.create(
            organization_id=invitation.organization_id,
            name=user_data.get("name") or invitation.name or invitation.email.split('@')[0],
            email=invitation.email,
            password=user_data["password"],
            phone=user_data.get("phone"),
            org_role='member',
            is_email_verified=True,  # Auto-verify invited users
            is_active=True
        )

        # Add to workspace
        WorkspaceMembership.create(
            user_id=user.id,
            workspace_id=invitation.workspace_id,
            workspace_role=invitation.workspace_role.value if hasattr(invitation.workspace_role, 'value') else invitation.workspace_role,
            added_by_user_id=invitation.invited_by_user_id
        )

        # Mark invitation as accepted
        invitation.accept()

        return user, None

    @staticmethod
    def cancel_invitation(invitation_id: str, cancelled_by_user):
        """Cancel a pending invitation"""
        invitation = Invitation.get_by_id(invitation_id)

        if not invitation:
            return False, "Invitation not found"

        if invitation.organization_id != cancelled_by_user.organization_id:
            return False, "Cannot cancel invitations from other organizations"

        # Check permissions
        is_workspace_admin = WorkspaceMembership.user_is_workspace_admin(
            cancelled_by_user.id, invitation.workspace_id
        )
        if not is_workspace_admin and not cancelled_by_user.is_org_admin():
            return False, "Only workspace admins can cancel invitations"

        invitation.cancel()

        return True, "Invitation cancelled"

    @staticmethod
    def get_workspace_invitations(workspace_id: str, status: str = None):
        """Get all invitations for a workspace"""
        invitations = Invitation.get_workspace_invitations(workspace_id, status)

        # Sort by created_at (most recent first)
        invitations.sort(
            key=lambda x: x.created_at if isinstance(x.created_at, datetime) else datetime.min,
            reverse=True
        )

        return invitations

    @staticmethod
    def get_organization_invitations(organization_id: str, status: str = None):
        """Get all invitations for an organization"""
        invitations = Invitation.get_organization_invitations(organization_id, status)

        # Sort by created_at (most recent first)
        invitations.sort(
            key=lambda x: x.created_at if isinstance(x.created_at, datetime) else datetime.min,
            reverse=True
        )

        return invitations

    @staticmethod
    def get_invitation_details(token: str):
        """Get invitation details for display on accept page"""
        invitation = Invitation.get_by_token(token)
        if not invitation:
            return None

        return {
            'invitation': invitation,
            'workspace': invitation.workspace,
            'organization': invitation.organization,
            'is_valid': invitation.is_valid(),
            'existing_user': User.get_by_email(invitation.email)
        }
