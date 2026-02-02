"""
Workspaces Blueprint
Handles workspace management, members, and join requests
"""
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, session
from flask_login import login_required, current_user
from app.services import WorkspaceService, InvitationService
from app.models import Workspace, WorkspaceMembership, JoinRequest, Invitation
from app.utils import is_valid_email, send_invitation_email, sanitize_slug

workspaces_bp = Blueprint("workspaces", __name__, url_prefix="/workspaces")


@workspaces_bp.route("/selector", methods=["GET"])
@login_required
def workspace_selector():
    """
    Workspace selector page - shown after login
    Shows user's workspaces and options to create/join
    """
    user_workspaces = WorkspaceService.get_user_workspaces(current_user.id)

    return render_template(
        "workspaces/selector.html",
        workspaces=user_workspaces,
        has_workspaces=len(user_workspaces) > 0
    )


@workspaces_bp.route("/join", methods=["GET", "POST"])
@login_required
def join_workspace():
    """Join a workspace using its code"""
    if request.method == "GET":
        code = request.args.get("code", "")
        return render_template("workspaces/join.html", form_data={"code": code})

    data = request.get_json() if request.is_json else request.form.to_dict()
    join_code = data.get("code", "").strip().upper()

    if not join_code:
        if request.is_json:
            return jsonify({"error": "Workspace code is required"}), 400
        flash("Workspace code is required", "error")
        return render_template("workspaces/join.html", form_data=data)

    # Find workspace by code
    workspace = Workspace.get_by_join_code(join_code)
    if not workspace:
        if request.is_json:
            return jsonify({"error": "No workspace found with this code"}), 404
        flash("No workspace found with this code. Please check and try again.", "error")
        return render_template("workspaces/join.html", form_data=data)

    if not workspace.is_active:
        if request.is_json:
            return jsonify({"error": "This workspace is no longer active"}), 400
        flash("This workspace is no longer active", "error")
        return render_template("workspaces/join.html", form_data=data)

    # Check if already a member
    if WorkspaceMembership.user_is_workspace_member(current_user.id, workspace.id):
        if request.is_json:
            return jsonify({"error": "You are already a member of this workspace"}), 400
        flash("You are already a member of this workspace", "info")
        return redirect(url_for("workspaces.view_workspace", workspace_id=workspace.id))

    # Check for existing pending request
    existing_request = JoinRequest.get_pending_for_user(current_user.id, workspace.id)
    if existing_request:
        if request.is_json:
            return jsonify({"error": "You already have a pending join request for this workspace"}), 400
        flash("You already have a pending join request for this workspace", "info")
        return render_template("workspaces/join.html", form_data=data, workspace=workspace)

    # Show workspace preview if just searching
    if data.get("action") == "search":
        if request.is_json:
            return jsonify({"workspace": workspace.to_public_dict()}), 200
        return render_template("workspaces/join.html", form_data=data, workspace=workspace)

    # Create join request
    reason = data.get("reason", "").strip() or "I would like to join this workspace"
    join_request, error = WorkspaceService.request_to_join_workspace(
        user=current_user,
        workspace_id=workspace.id,
        reason=reason
    )

    if error:
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "error")
        return render_template("workspaces/join.html", form_data=data, workspace=workspace)

    if request.is_json:
        return jsonify({
            "message": "Join request submitted successfully! A workspace admin will review your request.",
            "request_id": join_request.id
        }), 201

    flash("Join request submitted successfully! A workspace admin will review your request.", "success")
    return redirect(url_for("workspaces.workspace_selector"))


@workspaces_bp.route("/switch/<workspace_id>", methods=["POST", "GET"])
@login_required
def switch_workspace(workspace_id):
    """Switch to a different workspace"""
    workspace = Workspace.get_by_id(workspace_id)
    if not workspace:
        if request.is_json:
            return jsonify({"error": "Workspace not found"}), 404
        flash("Workspace not found", "error")
        return redirect(url_for("workspaces.workspace_selector"))

    # Check if user is a member
    if not WorkspaceMembership.user_is_workspace_member(current_user.id, workspace_id):
        if request.is_json:
            return jsonify({"error": "You are not a member of this workspace"}), 403
        flash("You are not a member of this workspace", "error")
        return redirect(url_for("workspaces.workspace_selector"))

    # Update last workspace
    current_user.set_last_workspace(workspace_id)

    # Store in session too for quick access
    session['current_workspace_id'] = workspace_id

    if request.is_json:
        return jsonify({
            "message": f"Switched to {workspace.name}",
            "workspace": workspace.to_dict()
        }), 200

    flash(f"Switched to {workspace.name}", "success")
    return redirect(url_for("dashboard.index"))


@workspaces_bp.route("/", methods=["GET"])
@login_required
def list_workspaces():
    """List all workspaces user has access to"""
    user_workspaces = WorkspaceService.get_user_workspaces(current_user.id)

    return render_template(
        "workspaces/list.html",
        user_workspaces=user_workspaces,
        org_workspaces=[],  # No longer used, kept for template compatibility
        is_org_admin=False  # No longer relevant
    )


@workspaces_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_workspace():
    """Create a new workspace with optional organization details"""
    if request.method == "GET":
        return render_template("workspaces/create.html")

    data = request.get_json() if request.is_json else request.form.to_dict()

    name = data.get("name", "").strip()
    if not name:
        if request.is_json:
            return jsonify({"error": "Workspace name is required"}), 400
        flash("Workspace name is required", "error")
        return render_template("workspaces/create.html", form_data=data)

    # Create workspace with optional org details
    workspace, error = WorkspaceService.create_workspace(
        name=name,
        created_by_user=current_user,
        description=data.get("description"),
        workspace_type=data.get("workspace_type", "general"),
        # Organization details (optional, for display purposes)
        org_name=data.get("org_name", "").strip() or None,
        org_industry=data.get("org_industry", "").strip() or None,
        org_size=data.get("org_size", "").strip() or None,
        org_website=data.get("org_website", "").strip() or None
    )

    if error:
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "error")
        return render_template("workspaces/create.html", form_data=data)

    if request.is_json:
        return jsonify({
            "message": "Workspace created successfully",
            "workspace": workspace.to_dict(),
            "join_code": workspace.join_code
        }), 201

    flash(f"Workspace '{workspace.name}' created! Share code {workspace.join_code} to invite others.", "success")
    return redirect(url_for("workspaces.view_workspace", workspace_id=workspace.id))


@workspaces_bp.route("/<workspace_id>", methods=["GET"])
@login_required
def view_workspace(workspace_id):
    """View workspace details"""
    workspace = Workspace.get_by_id(workspace_id)
    if not workspace:
        flash("Workspace not found", "error")
        return redirect(url_for("workspaces.workspace_selector"))

    # Check access - must be a member
    is_member = WorkspaceMembership.user_is_workspace_member(current_user.id, workspace_id)
    is_admin = WorkspaceMembership.user_is_workspace_admin(current_user.id, workspace_id)

    if not is_member:
        flash("You don't have access to this workspace", "error")
        return redirect(url_for("workspaces.workspace_selector"))

    # Update last workspace
    current_user.set_last_workspace(workspace_id)

    # Get workspace members
    members = WorkspaceMembership.get_workspace_members(workspace_id)

    # Get pending invitations and join requests for admins
    pending_invitations = []
    pending_requests = []
    if is_admin:
        pending_invitations = InvitationService.get_workspace_invitations(workspace_id, status='pending')
        pending_requests = WorkspaceService.get_pending_join_requests(workspace_id)

    return render_template(
        "workspaces/view.html",
        workspace=workspace,
        members=members,
        pending_invitations=pending_invitations,
        pending_requests=pending_requests,
        is_admin=is_admin,
        is_org_admin=False  # Kept for template compatibility
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
