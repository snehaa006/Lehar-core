"""
Invitations Blueprint
Handles workspace-specific invitations
"""
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.services import InvitationService
from app.utils import is_valid_email, is_strong_password

invitations_bp = Blueprint("invitations", __name__, url_prefix="/invitations")


@invitations_bp.route("/accept", methods=["GET", "POST"])
def accept_invitation():
    """Accept an invitation and create account / join workspace"""
    token = request.args.get("token")

    if not token:
        flash("Invalid invitation link", "error")
        return redirect(url_for("auth.login"))

    if request.method == "GET":
        # Show invitation details and password form
        details = InvitationService.get_invitation_details(token)

        if not details:
            flash("Invalid invitation link", "error")
            return redirect(url_for("auth.login"))

        if not details['is_valid']:
            flash("Invitation has expired or is no longer valid", "error")
            return redirect(url_for("auth.login"))

        return render_template(
            "auth/accept_invite.html",
            invitation=details['invitation'],
            workspace=details['workspace'],
            organization=details['organization'],
            existing_user=details['existing_user'],
            token=token
        )

    # POST - Accept invitation
    data = request.get_json() if request.is_json else request.form.to_dict()

    # Get invitation details to check if existing user
    details = InvitationService.get_invitation_details(token)
    if not details or not details['is_valid']:
        if request.is_json:
            return jsonify({"error": "Invalid or expired invitation"}), 400
        flash("Invalid or expired invitation", "error")
        return redirect(url_for("auth.login"))

    # If existing user, just add to workspace
    if details['existing_user']:
        user, error = InvitationService.accept_invitation(token, {})

        if error:
            if request.is_json:
                return jsonify({"error": error}), 400
            flash(error, "error")
            return redirect(url_for("invitations.accept_invitation", token=token))

        if request.is_json:
            return jsonify({
                "message": f"You've been added to {details['workspace'].name}!",
                "user": user.to_dict()
            }), 200

        flash(f"You've been added to {details['workspace'].name}!", "success")
        return redirect(url_for("auth.login"))

    # New user - validate password
    password = data.get("password", "")
    is_strong, password_msg = is_strong_password(password)

    if not is_strong:
        if request.is_json:
            return jsonify({"error": password_msg}), 400
        flash(password_msg, "error")
        return redirect(url_for("invitations.accept_invitation", token=token))

    user_data = {
        "password": password,
        "phone": data.get("phone"),
        "name": data.get("name")
    }

    user, error = InvitationService.accept_invitation(token, user_data)

    if error:
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "error")
        return redirect(url_for("invitations.accept_invitation", token=token))

    if request.is_json:
        return jsonify({
            "message": "Account created successfully! You can now login.",
            "user": user.to_dict()
        }), 201

    flash("Account created successfully! You can now login.", "success")
    return redirect(url_for("auth.login"))


@invitations_bp.route("/list", methods=["GET"])
@login_required
def list_invitations():
    """List all invitations for the organization"""
    if not current_user.is_org_admin():
        flash("You don't have permission to view invitations", "error")
        return redirect(url_for("dashboard.index"))

    status = request.args.get("status")

    invitations = InvitationService.get_organization_invitations(
        current_user.organization_id,
        status=status
    )

    # Get workspaces for the invite form
    from app.services import WorkspaceService
    workspaces = WorkspaceService.get_organization_workspaces(current_user.organization_id)

    if request.is_json:
        return jsonify({
            "invitations": [inv.to_dict() for inv in invitations]
        }), 200

    return render_template(
        "dashboard/invitations.html",
        invitations=invitations,
        workspaces=workspaces
    )


@invitations_bp.route("/send", methods=["POST"])
@login_required
def send_invitation():
    """Send a new invitation"""
    if not current_user.is_org_admin():
        flash("You don't have permission to send invitations", "error")
        return redirect(url_for("dashboard.index"))

    data = request.get_json() if request.is_json else request.form.to_dict()

    email = data.get("email", "").strip().lower()
    workspace_id = data.get("workspace_id")
    workspace_role = data.get("workspace_role", "user")
    name = data.get("name", "").strip()

    if not email or not is_valid_email(email):
        if request.is_json:
            return jsonify({"error": "Valid email is required"}), 400
        flash("Valid email is required", "error")
        return redirect(url_for("invitations.list_invitations"))

    if not workspace_id:
        if request.is_json:
            return jsonify({"error": "Workspace is required"}), 400
        flash("Workspace is required", "error")
        return redirect(url_for("invitations.list_invitations"))

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
        return redirect(url_for("invitations.list_invitations"))

    if request.is_json:
        return jsonify({
            "message": f"Invitation sent to {email}",
            "invitation": invitation.to_dict()
        }), 201

    flash(f"Invitation sent to {email}", "success")
    return redirect(url_for("invitations.list_invitations"))
