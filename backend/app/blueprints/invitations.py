"""
Invitations Blueprint
Handles user invitations to organizations
"""
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.services import InvitationService
from app.utils import is_valid_email, is_strong_password

invitations_bp = Blueprint("invitations", __name__, url_prefix="/invitations")


@invitations_bp.route("/send", methods=["POST"])
@login_required
def send_invitation():
    """Send invitation to a new user"""
    # Check permissions
    if current_user.role.value not in ["super_admin", "admin"]:
        if request.is_json:
            return jsonify({"error": "Insufficient permissions"}), 403
        flash("You don't have permission to invite users", "error")
        return redirect(url_for("dashboard.organization_settings"))
    
    data = request.get_json() if request.is_json else request.form.to_dict()
    
    email = data.get("email", "").strip().lower()
    name = data.get("name", "").strip()
    role = data.get("role", "viewer").lower()
    
    # Validate
    if not is_valid_email(email):
        if request.is_json:
            return jsonify({"error": "Invalid email address"}), 400
        flash("Invalid email address", "error")
        return redirect(url_for("dashboard.organization_settings"))
    
    # Create invitation
    invitation, error = InvitationService.create_invitation(
        email=email,
        name=name,
        role=role,
        organization_id=current_user.organization_id,
        invited_by_user=current_user
    )
    
    if error:
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "error")
        return redirect(url_for("dashboard.organization_settings"))
    
    if request.is_json:
        return jsonify({
            "message": "Invitation sent successfully",
            "invitation": invitation.to_dict()
        }), 201
    
    flash(f"Invitation sent to {email}", "success")
    return redirect(url_for("dashboard.organization_settings"))


@invitations_bp.route("/accept", methods=["GET", "POST"])
def accept_invitation():
    """Accept an invitation and create account"""
    token = request.args.get("token")
    
    if not token:
        flash("Invalid invitation link", "error")
        return redirect(url_for("auth.login"))
    
    if request.method == "GET":
        # Show invitation details and password form
        from app.models import Invitation
        invitation = Invitation.get_by_token(token)
        
        if not invitation or not invitation.is_valid():
            flash("Invitation is invalid or has expired", "error")
            return redirect(url_for("auth.login"))
        
        return render_template(
            "auth/accept_invite.html",
            invitation=invitation,
            token=token
        )
    
    # POST - Accept invitation
    data = request.get_json() if request.is_json else request.form.to_dict()
    
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
        return redirect(url_for("auth.login"))
    
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
    # Check permissions
    if current_user.role.value not in ["super_admin", "admin"]:
        flash("You don't have permission to view invitations", "error")
        return redirect(url_for("dashboard.index"))
    
    status = request.args.get("status")  # pending, accepted, expired
    
    invitations = InvitationService.get_organization_invitations(
        current_user.organization_id,
        status=status
    )
    
    if request.is_json:
        return jsonify({
            "invitations": [inv.to_dict() for inv in invitations]
        }), 200
    
    return render_template(
        "dashboard/invitations.html",
        invitations=invitations
    )


@invitations_bp.route("/<invitation_id>/cancel", methods=["POST"])
@login_required
def cancel_invitation(invitation_id):
    """Cancel a pending invitation"""
    # Check permissions
    if current_user.role.value not in ["super_admin", "admin"]:
        if request.is_json:
            return jsonify({"error": "Insufficient permissions"}), 403
        flash("You don't have permission to cancel invitations", "error")
        return redirect(url_for("dashboard.organization_settings"))
    
    success, message = InvitationService.cancel_invitation(
        invitation_id,
        current_user
    )
    
    if not success:
        if request.is_json:
            return jsonify({"error": message}), 400
        flash(message, "error")
    else:
        if request.is_json:
            return jsonify({"message": message}), 200
        flash(message, "success")
    
    return redirect(url_for("invitations.list_invitations"))