"""
Dashboard Blueprint (FIXED)
Main dashboard after login - shows workspaces and user info
Enhanced with proper error handling and try-catch blocks
"""
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.utils import is_strong_password, validate_phone
from app.services import WorkspaceService, UserService

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.route("/", methods=["GET"])
@login_required
def index():
    """Main dashboard - shows user's workspaces"""
    try:
        # Get user's workspaces
        user_workspaces = WorkspaceService.get_user_workspaces(current_user.id)

        return render_template(
            "dashboard/index.html",
            user=current_user,
            organization=current_user.organization,
            workspaces=user_workspaces
        )
    except Exception as e:
        current_app.logger.error(f"Error in dashboard index: {str(e)}")
        flash("An error occurred while loading the dashboard", "error")
        return render_template("dashboard/index.html", user=current_user, workspaces=[])


@dashboard_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """User profile page"""
    try:
        if request.method == "POST":
            action = request.form.get("action")

            if action == "update_profile":
                # Update profile information
                name = request.form.get("name", "").strip()
                phone = request.form.get("phone", "").strip()
                job_title = request.form.get("job_title", "").strip()

                if not name:
                    flash("Name is required", "error")
                    return redirect(url_for("dashboard.profile"))

                if phone and not validate_phone(phone):
                    flash("Invalid phone number", "error")
                    return redirect(url_for("dashboard.profile"))

                # Update user
                current_user.name = name
                current_user.phone = phone if phone else None
                current_user.job_title = job_title if job_title else None
                current_user.save()

                flash("Profile updated successfully", "success")
                return redirect(url_for("dashboard.profile"))

            elif action == "change_password":
                # Change password
                current_password = request.form.get("current_password")
                new_password = request.form.get("new_password")
                confirm_password = request.form.get("confirm_password")

                # Verify current password
                if not current_user.check_password(current_password):
                    flash("Current password is incorrect", "error")
                    return redirect(url_for("dashboard.profile"))

                # Validate new password
                if new_password != confirm_password:
                    flash("New passwords do not match", "error")
                    return redirect(url_for("dashboard.profile"))

                is_strong, password_msg = is_strong_password(new_password)
                if not is_strong:
                    flash(password_msg, "error")
                    return redirect(url_for("dashboard.profile"))

                # Update password
                current_user.set_password(new_password)
                current_user.save()

                flash("Password changed successfully", "success")
                return redirect(url_for("dashboard.profile"))

        # GET request
        return render_template(
            "dashboard/profile.html",
            user=current_user,
            organization=current_user.organization
        )
    except Exception as e:
        current_app.logger.error(f"Error in profile: {str(e)}")
        flash("An error occurred while processing your request", "error")
        return redirect(url_for("dashboard.index"))


@dashboard_bp.route("/organization", methods=["GET", "POST"])
@login_required
def organization_settings():
    """Organization settings (org admin only)"""
    try:
        if not current_user.is_org_admin():
            flash("You don't have permission to access organization settings", "error")
            return redirect(url_for("dashboard.index"))

        if request.method == "POST":
            # Only org_owner can edit organization
            if not current_user.is_org_owner():
                flash("Only organization owner can edit these settings", "error")
                return redirect(url_for("dashboard.organization_settings"))

            # Update organization
            org = current_user.organization
            org.name = request.form.get("name", "").strip()
            org.website = request.form.get("website", "").strip() or None
            org.industry_type = request.form.get("industry_type", "").strip() or None
            org.company_size = request.form.get("company_size", "").strip() or None
            org.save()

            flash("Organization updated successfully", "success")
            return redirect(url_for("dashboard.organization_settings"))

        # GET request
        users = UserService.get_organization_users(current_user.organization_id)
        workspaces = WorkspaceService.get_organization_workspaces(current_user.organization_id)

        return render_template(
            "dashboard/organization.html",
            organization=current_user.organization,
            users=users,
            workspaces=workspaces,
            is_owner=current_user.is_org_owner()
        )
    except Exception as e:
        current_app.logger.error(f"Error in organization_settings: {str(e)}")
        flash("An error occurred while loading organization settings", "error")
        return redirect(url_for("dashboard.index"))


@dashboard_bp.route("/users", methods=["GET"])
@login_required
def users_list():
    """List all users in organization (org admin only) - FIXED"""
    try:
        if not current_user.is_org_admin():
            flash("You don't have permission to view users", "error")
            return redirect(url_for("dashboard.index"))

        users = UserService.get_organization_users(current_user.organization_id)

        return render_template(
            "dashboard/users.html",
            users=users,
            organization=current_user.organization
        )
    except Exception as e:
        current_app.logger.error(f"Error in users_list: {str(e)}")
        flash("An error occurred while loading users", "error")
        return redirect(url_for("dashboard.index"))


@dashboard_bp.route("/users/<user_id>/role", methods=["POST"])
@login_required
def update_user_role(user_id):
    """Update a user's organization role - FIXED"""
    try:
        if not current_user.is_org_owner():
            if request.is_json:
                return jsonify({"error": "Only organization owner can change roles"}), 403
            flash("Only organization owner can change roles", "error")
            return redirect(url_for("dashboard.users_list"))

        data = request.get_json() if request.is_json else request.form.to_dict()
        new_role = data.get("org_role")

        success, message = UserService.update_org_role(user_id, new_role, current_user)

        if request.is_json:
            if not success:
                return jsonify({"error": message}), 400
            return jsonify({"message": message}), 200

        if success:
            flash(message, "success")
        else:
            flash(message, "error")

        return redirect(url_for("dashboard.users_list"))
    except Exception as e:
        current_app.logger.error(f"Error in update_user_role: {str(e)}")
        if request.is_json:
            return jsonify({"error": "An error occurred while updating the role"}), 500
        flash("An error occurred while updating the role", "error")
        return redirect(url_for("dashboard.users_list"))


@dashboard_bp.route("/users/<user_id>/deactivate", methods=["POST"])
@login_required
def deactivate_user(user_id):
    """Deactivate a user - FIXED"""
    try:
        success, message = UserService.deactivate_user(user_id, current_user)

        if request.is_json:
            if not success:
                return jsonify({"error": message}), 400
            return jsonify({"message": message}), 200

        if success:
            flash(message, "success")
        else:
            flash(message, "error")

        return redirect(url_for("dashboard.users_list"))
    except Exception as e:
        current_app.logger.error(f"Error in deactivate_user: {str(e)}")
        if request.is_json:
            return jsonify({"error": "An error occurred while deactivating the user"}), 500
        flash("An error occurred while deactivating the user", "error")
        return redirect(url_for("dashboard.users_list"))


@dashboard_bp.route("/users/<user_id>/activate", methods=["POST"])
@login_required
def activate_user(user_id):
    """Activate a user - FIXED"""
    try:
        success, message = UserService.activate_user(user_id, current_user)

        if request.is_json:
            if not success:
                return jsonify({"error": message}), 400
            return jsonify({"message": message}), 200

        if success:
            flash(message, "success")
        else:
            flash(message, "error")

        return redirect(url_for("dashboard.users_list"))
    except Exception as e:
        current_app.logger.error(f"Error in activate_user: {str(e)}")
        if request.is_json:
            return jsonify({"error": "An error occurred while activating the user"}), 500
        flash("An error occurred while activating the user", "error")
        return redirect(url_for("dashboard.users_list"))