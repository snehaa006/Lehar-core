"""
Workspaces Blueprint
Handles workspace management, members, and join requests
"""
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.services import WorkspaceService, InvitationService
from app.models import Workspace, WorkspaceMembership, JoinRequest, Invitation
from app.utils import is_valid_email, send_invitation_email

workspaces_bp = Blueprint("workspaces", __name__, url_prefix="/workspaces")


@workspaces_bp.route("/", methods=["GET"])
@login_required
def list_workspaces():
    """List all workspaces user has access to"""
    user_workspaces = WorkspaceService.get_user_workspaces(current_user.id)

    # Get all organization workspaces for org admins
    org_workspaces = []
    if current_user.is_org_admin():
        org_workspaces = WorkspaceService.get_organization_workspaces(current_user.organization_id)

    return render_template(
        "workspaces/list.html",
        user_workspaces=user_workspaces,
        org_workspaces=org_workspaces,
        is_org_admin=current_user.is_org_admin()
    )


@workspaces_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_workspace():
    """Create a new workspace"""
    if not current_user.can_manage_workspaces():
        flash("You don't have permission to create workspaces", "error")
        return redirect(url_for("workspaces.list_workspaces"))

    if request.method == "GET":
        return render_template("workspaces/create.html")

    data = request.get_json() if request.is_json else request.form.to_dict()

    name = data.get("name", "").strip()
    if not name:
        if request.is_json:
            return jsonify({"error": "Workspace name is required"}), 400
        flash("Workspace name is required", "error")
        return render_template("workspaces/create.html", form_data=data)

    workspace, error = WorkspaceService.create_workspace(
        organization_id=current_user.organization_id,
        name=name,
        created_by_user=current_user,
        description=data.get("description"),
        workspace_type=data.get("workspace_type", "general")
    )

    if error:
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "error")
        return render_template("workspaces/create.html", form_data=data)

    if request.is_json:
        return jsonify({
            "message": "Workspace created successfully",
            "workspace": workspace.to_dict()
        }), 201

    flash(f"Workspace '{workspace.name}' created successfully!", "success")
    return redirect(url_for("workspaces.view_workspace", workspace_id=workspace.id))


@workspaces_bp.route("/<workspace_id>", methods=["GET"])
@login_required
def view_workspace(workspace_id):
    """View workspace details"""
    workspace = Workspace.get_by_id(workspace_id)
    if not workspace:
        flash("Workspace not found", "error")
        return redirect(url_for("workspaces.list_workspaces"))

    # Check access
    is_member = WorkspaceMembership.user_is_workspace_member(current_user.id, workspace_id)
    is_admin = WorkspaceMembership.user_is_workspace_admin(current_user.id, workspace_id)
    is_org_admin = current_user.is_org_admin()

    if not is_member and not is_org_admin:
        flash("You don't have access to this workspace", "error")
        return redirect(url_for("workspaces.list_workspaces"))

    # Get workspace members
    members = WorkspaceMembership.get_workspace_members(workspace_id)

    # Get pending invitations and join requests for admins
    pending_invitations = []
    pending_requests = []
    if is_admin or is_org_admin:
        pending_invitations = InvitationService.get_workspace_invitations(workspace_id, status='pending')
        pending_requests = WorkspaceService.get_pending_join_requests(workspace_id)

    return render_template(
        "workspaces/view.html",
        workspace=workspace,
        members=members,
        pending_invitations=pending_invitations,
        pending_requests=pending_requests,
        is_admin=is_admin,
        is_org_admin=is_org_admin
    )


@workspaces_bp.route("/<workspace_id>/invite", methods=["POST"])
@login_required
def invite_to_workspace(workspace_id):
    """Invite a user to join workspace"""
    data = request.get_json() if request.is_json else request.form.to_dict()

    email = data.get("email", "").strip().lower()
    workspace_role = data.get("workspace_role", "user")
    name = data.get("name", "").strip()

    if not is_valid_email(email):
        if request.is_json:
            return jsonify({"error": "Invalid email address"}), 400
        flash("Invalid email address", "error")
        return redirect(url_for("workspaces.view_workspace", workspace_id=workspace_id))

    invitation, error = InvitationService.create_invitation(
        workspace_id=workspace_id,
        email=email,
        workspace_role=workspace_role,
        invited_by_user=current_user,
        name=name
    )

    if error:
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "error")
        return redirect(url_for("workspaces.view_workspace", workspace_id=workspace_id))

    if request.is_json:
        return jsonify({
            "message": f"Invitation sent to {email}",
            "invitation": invitation.to_dict()
        }), 201

    flash(f"Invitation sent to {email}", "success")
    return redirect(url_for("workspaces.view_workspace", workspace_id=workspace_id))


@workspaces_bp.route("/<workspace_id>/members/<user_id>/remove", methods=["POST"])
@login_required
def remove_member(workspace_id, user_id):
    """Remove a member from workspace"""
    success, error = WorkspaceService.remove_user_from_workspace(
        user_id=user_id,
        workspace_id=workspace_id,
        removed_by_user=current_user
    )

    if request.is_json:
        if not success:
            return jsonify({"error": error}), 400
        return jsonify({"message": "Member removed successfully"}), 200

    if not success:
        flash(error, "error")
    else:
        flash("Member removed successfully", "success")

    return redirect(url_for("workspaces.view_workspace", workspace_id=workspace_id))


@workspaces_bp.route("/<workspace_id>/members/<user_id>/role", methods=["POST"])
@login_required
def update_member_role(workspace_id, user_id):
    """Update a member's role in workspace"""
    data = request.get_json() if request.is_json else request.form.to_dict()
    new_role = data.get("workspace_role")

    if not new_role:
        if request.is_json:
            return jsonify({"error": "Role is required"}), 400
        flash("Role is required", "error")
        return redirect(url_for("workspaces.view_workspace", workspace_id=workspace_id))

    success, error = WorkspaceService.update_workspace_role(
        user_id=user_id,
        workspace_id=workspace_id,
        new_role=new_role,
        updated_by_user=current_user
    )

    if request.is_json:
        if not success:
            return jsonify({"error": error}), 400
        return jsonify({"message": "Role updated successfully"}), 200

    if not success:
        flash(error, "error")
    else:
        flash("Role updated successfully", "success")

    return redirect(url_for("workspaces.view_workspace", workspace_id=workspace_id))


@workspaces_bp.route("/<workspace_id>/join-requests/<request_id>/approve", methods=["POST"])
@login_required
def approve_join_request(workspace_id, request_id):
    """Approve a join request"""
    data = request.get_json() if request.is_json else request.form.to_dict()
    workspace_role = data.get("workspace_role", "user")

    success, error = WorkspaceService.approve_join_request(
        request_id=request_id,
        approved_by_user=current_user,
        workspace_role=workspace_role
    )

    if request.is_json:
        if not success:
            return jsonify({"error": error}), 400
        return jsonify({"message": "Join request approved"}), 200

    if not success:
        flash(error, "error")
    else:
        flash("Join request approved", "success")

    return redirect(url_for("workspaces.view_workspace", workspace_id=workspace_id))


@workspaces_bp.route("/<workspace_id>/join-requests/<request_id>/reject", methods=["POST"])
@login_required
def reject_join_request(workspace_id, request_id):
    """Reject a join request"""
    data = request.get_json() if request.is_json else request.form.to_dict()
    rejection_reason = data.get("rejection_reason")

    success, error = WorkspaceService.reject_join_request(
        request_id=request_id,
        rejected_by_user=current_user,
        rejection_reason=rejection_reason
    )

    if request.is_json:
        if not success:
            return jsonify({"error": error}), 400
        return jsonify({"message": "Join request rejected"}), 200

    if not success:
        flash(error, "error")
    else:
        flash("Join request rejected", "success")

    return redirect(url_for("workspaces.view_workspace", workspace_id=workspace_id))


@workspaces_bp.route("/invitations/<invitation_id>/cancel", methods=["POST"])
@login_required
def cancel_invitation(invitation_id):
    """Cancel a pending invitation"""
    invitation = Invitation.get_by_id(invitation_id)
    if not invitation:
        if request.is_json:
            return jsonify({"error": "Invitation not found"}), 404
        flash("Invitation not found", "error")
        return redirect(url_for("workspaces.list_workspaces"))

    workspace_id = invitation.workspace_id

    success, error = InvitationService.cancel_invitation(
        invitation_id=invitation_id,
        cancelled_by_user=current_user
    )

    if request.is_json:
        if not success:
            return jsonify({"error": error}), 400
        return jsonify({"message": "Invitation cancelled"}), 200

    if not success:
        flash(error, "error")
    else:
        flash("Invitation cancelled", "success")

    return redirect(url_for("workspaces.view_workspace", workspace_id=workspace_id))
