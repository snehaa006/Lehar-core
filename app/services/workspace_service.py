"""
Workspace Service - Firestore Version
Business logic for workspace operations
"""
from app.models import (
    Workspace, WorkspaceMembership, JoinRequest, Invitation,
    User, Organization, WorkspaceRole
)
from app.utils import sanitize_slug


class WorkspaceService:
    """Handles workspace-related business logic"""

    @staticmethod
    def create_workspace(name: str, created_by_user, organization_id: str = None, **kwargs):
        """
        Create a new workspace - organization is now optional

        Args:
            name: Workspace name
            created_by_user: User creating the workspace
            organization_id: Optional organization ID (for backward compatibility)
            **kwargs: Additional workspace fields including org details

        Returns:
            tuple: (workspace, error_message)
        """
        try:
            # Any user can create workspaces now
            if not created_by_user.can_manage_workspaces():
                return None, "You don't have permission to create workspaces"

            # If organization_id provided, check limits (backward compatibility)
            if organization_id:
                organization = Organization.get_by_id(organization_id)
                if organization and not organization.can_add_workspace():
                    return None, f"Organization has reached maximum number of workspaces ({organization.max_workspaces})"

            # Create unique slug
            slug = sanitize_slug(name)
            base_slug = slug
            counter = 1
            # For slug uniqueness, we check globally now since org is optional
            existing = Workspace.get_by_id(slug)  # Simple check
            while existing:
                slug = f"{base_slug}-{counter}"
                counter += 1
                existing = Workspace.get_by_id(slug)

            # Create workspace with optional org details
            workspace = Workspace.create(
                name=name,
                slug=slug,
                organization_id=organization_id,
                description=kwargs.get('description'),
                workspace_type=kwargs.get('workspace_type', 'general'),
                created_by_user_id=created_by_user.id,
                # Organization details stored on workspace
                org_name=kwargs.get('org_name'),
                org_industry=kwargs.get('org_industry'),
                org_size=kwargs.get('org_size'),
                org_website=kwargs.get('org_website'),
                is_domain_verified=kwargs.get('is_domain_verified', False),
                verified_domain=kwargs.get('verified_domain')
            )

            # Add creator as workspace admin
            WorkspaceMembership.create(
                user_id=created_by_user.id,
                workspace_id=workspace.id,
                workspace_role='admin',
                added_by_user_id=created_by_user.id
            )

            # Set this as user's last workspace
            created_by_user.set_last_workspace(workspace.id)

            return workspace, None

        except Exception as e:
            return None, str(e)

    @staticmethod
    def get_workspace_by_id(workspace_id: str):
        """Get workspace by ID"""
        return Workspace.get_by_id(workspace_id)

    @staticmethod
    def get_organization_workspaces(organization_id: str):
        """Get all workspaces in an organization"""
        return Workspace.get_by_organization(organization_id)

    @staticmethod
    def get_user_workspaces(user_id: str):
        """Get all workspaces a user is a member of"""
        memberships = WorkspaceMembership.get_user_memberships(user_id)
        workspaces = []
        for membership in memberships:
            workspace = Workspace.get_by_id(membership.workspace_id)
            if workspace:
                workspaces.append({
                    'workspace': workspace,
                    'role': membership.workspace_role
                })
        return workspaces

    @staticmethod
    def add_user_to_workspace(user_id: str, workspace_id: str, workspace_role: str,
                               added_by_user):
        """
        Add a user to a workspace

        Returns:
            tuple: (membership, error_message)
        """
        try:
            # Check if adding user has permission
            is_workspace_admin = WorkspaceMembership.user_is_workspace_admin(
                added_by_user.id, workspace_id
            )
            if not is_workspace_admin and not added_by_user.is_org_admin():
                return None, "You don't have permission to add users to this workspace"

            # Check if user is already a member
            existing = WorkspaceMembership.get_membership(user_id, workspace_id)
            if existing and existing.is_active:
                return None, "User is already a member of this workspace"

            # Check if users are in same organization
            user = User.get_by_id(user_id)
            workspace = Workspace.get_by_id(workspace_id)

            if not user or not workspace:
                return None, "User or workspace not found"

            if user.organization_id != workspace.organization_id:
                return None, "User must be in the same organization"

            # Create membership
            membership = WorkspaceMembership.create(
                user_id=user_id,
                workspace_id=workspace_id,
                workspace_role=workspace_role,
                added_by_user_id=added_by_user.id
            )

            return membership, None

        except Exception as e:
            return None, str(e)

    @staticmethod
    def remove_user_from_workspace(user_id: str, workspace_id: str, removed_by_user):
        """
        Remove a user from a workspace

        Returns:
            tuple: (success, error_message)
        """
        try:
            # Check if removing user has permission
            is_workspace_admin = WorkspaceMembership.user_is_workspace_admin(
                removed_by_user.id, workspace_id
            )
            if not is_workspace_admin and not removed_by_user.is_org_admin():
                return False, "You don't have permission to remove users from this workspace"

            # Can't remove yourself if you're the only admin
            if user_id == removed_by_user.id:
                admins = WorkspaceMembership.get_workspace_admins(workspace_id)
                if len(admins) == 1:
                    return False, "Cannot remove yourself as the only admin. Promote another admin first."

            membership = WorkspaceMembership.get_membership(user_id, workspace_id)
            if not membership:
                return False, "User is not a member of this workspace"

            membership.delete()
            return True, "User removed from workspace"

        except Exception as e:
            return False, str(e)

    @staticmethod
    def update_workspace_role(user_id: str, workspace_id: str, new_role: str,
                               updated_by_user):
        """
        Update a user's role in a workspace

        Returns:
            tuple: (success, error_message)
        """
        try:
            # Check if updating user has permission
            is_workspace_admin = WorkspaceMembership.user_is_workspace_admin(
                updated_by_user.id, workspace_id
            )
            if not is_workspace_admin and not updated_by_user.is_org_admin():
                return False, "You don't have permission to change roles in this workspace"

            membership = WorkspaceMembership.get_membership(user_id, workspace_id)
            if not membership:
                return False, "User is not a member of this workspace"

            # Can't demote yourself if you're the only admin
            if user_id == updated_by_user.id and new_role != 'admin':
                admins = WorkspaceMembership.get_workspace_admins(workspace_id)
                if len(admins) == 1:
                    return False, "Cannot demote yourself as the only admin"

            membership.workspace_role = WorkspaceRole[new_role.upper()]
            membership.save()

            return True, "Role updated successfully"

        except Exception as e:
            return False, str(e)

    @staticmethod
    def request_to_join(user_id: str, workspace_id: str, reason: str):
        """
        Create a join request for a workspace

        Returns:
            tuple: (join_request, error_message)
        """
        try:
            # Check if user can request again (cooldown)
            can_request, error = JoinRequest.can_request_again(user_id, workspace_id)
            if not can_request:
                return None, error

            # Check if user is already a member
            if WorkspaceMembership.user_is_workspace_member(user_id, workspace_id):
                return None, "You are already a member of this workspace"

            # Check if workspace exists
            workspace = Workspace.get_by_id(workspace_id)
            if not workspace:
                return None, "Workspace not found"

            # Create join request
            join_request = JoinRequest.create(
                user_id=user_id,
                workspace_id=workspace_id,
                reason=reason
            )

            return join_request, None

        except Exception as e:
            return None, str(e)

    @staticmethod
    def request_to_join_workspace(user, workspace_id: str, reason: str):
        """
        Wrapper method for join request using user object

        Returns:
            tuple: (join_request, error_message)
        """
        return WorkspaceService.request_to_join(user.id, workspace_id, reason)

    @staticmethod
    def approve_join_request(request_id: str, approved_by_user, workspace_role: str = 'user'):
        """
        Approve a join request

        Returns:
            tuple: (success, error_message)
        """
        try:
            join_request = JoinRequest.get_by_id(request_id)
            if not join_request:
                return False, "Join request not found"

            if join_request.status.value != 'pending':
                return False, "This request has already been processed"

            # Check if approving user has permission (workspace admin)
            is_workspace_admin = WorkspaceMembership.user_is_workspace_admin(
                approved_by_user.id, join_request.workspace_id
            )
            if not is_workspace_admin:
                return False, "You don't have permission to approve join requests"

            # No longer checking organization - users can join workspaces across organizations

            # Approve request
            join_request.approve(approved_by_user.id)

            # Add user to workspace
            WorkspaceMembership.create(
                user_id=join_request.user_id,
                workspace_id=join_request.workspace_id,
                workspace_role=workspace_role,
                added_by_user_id=approved_by_user.id
            )

            return True, "Join request approved"

        except Exception as e:
            return False, str(e)

    @staticmethod
    def reject_join_request(request_id: str, rejected_by_user, rejection_reason: str = None):
        """
        Reject a join request

        Returns:
            tuple: (success, error_message)
        """
        try:
            join_request = JoinRequest.get_by_id(request_id)
            if not join_request:
                return False, "Join request not found"

            if join_request.status.value != 'pending':
                return False, "This request has already been processed"

            # Check if rejecting user has permission
            is_workspace_admin = WorkspaceMembership.user_is_workspace_admin(
                rejected_by_user.id, join_request.workspace_id
            )
            if not is_workspace_admin and not rejected_by_user.is_org_admin():
                return False, "You don't have permission to reject join requests"

            # Reject request
            join_request.reject(rejected_by_user.id, rejection_reason)

            return True, "Join request rejected"

        except Exception as e:
            return False, str(e)

    @staticmethod
    def get_pending_join_requests(workspace_id: str):
        """Get all pending join requests for a workspace"""
        return JoinRequest.get_workspace_requests(workspace_id, status='pending')

    @staticmethod
    def send_workspace_invitation(workspace_id: str, email: str, workspace_role: str,
                                   invited_by_user, name: str = None):
        """
        Send an invitation to join a workspace

        Returns:
            tuple: (invitation, error_message)
        """
        try:
            workspace = Workspace.get_by_id(workspace_id)
            if not workspace:
                return None, "Workspace not found"

            # Check if inviting user has permission
            is_workspace_admin = WorkspaceMembership.user_is_workspace_admin(
                invited_by_user.id, workspace_id
            )
            if not is_workspace_admin and not invited_by_user.is_org_admin():
                return None, "You don't have permission to invite users"

            # Check if user is already a member
            existing_user = User.get_by_email(email)
            if existing_user:
                if WorkspaceMembership.user_is_workspace_member(existing_user.id, workspace_id):
                    return None, "User is already a member of this workspace"

            # Check for pending invitation
            pending = Invitation.get_pending_for_email(workspace_id, email)
            if pending:
                return None, "A pending invitation already exists for this email"

            # Check organization user limit
            organization = Organization.get_by_id(workspace.organization_id)
            if not existing_user and not organization.can_add_user():
                return None, f"Organization has reached maximum number of users ({organization.max_users})"

            # Create invitation
            invitation = Invitation.create(
                organization_id=workspace.organization_id,
                workspace_id=workspace_id,
                email=email,
                workspace_role=workspace_role,
                invited_by_user_id=invited_by_user.id,
                name=name
            )

            return invitation, None

        except Exception as e:
            return None, str(e)
