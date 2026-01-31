"""
Dashboard Blueprint
Main dashboard after login - role-based landing page
"""
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.utils import is_strong_password, validate_phone

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.route("/", methods=["GET"])
@login_required
def index():
    """
    Main dashboard - role-based view
    Different dashboards for different roles
    """
    role = current_user.role.value
    plan = current_user.organization.plan_type.value
    
    # Render different templates based on role
    if role == "super_admin":
        return render_template(
            "dashboard/super_admin_dashboard.html",
            user=current_user,
            organization=current_user.organization
        )
    
    elif role == "admin":
        return render_template(
            "dashboard/admin_dashboard.html",
            user=current_user,
            organization=current_user.organization
        )
    
    elif role == "manager":
        return render_template(
            "dashboard/manager_dashboard.html",
            user=current_user,
            organization=current_user.organization  # FIXED: Added organization
        )
    
    elif role == "hr":
        return render_template(
            "dashboard/hr_dashboard.html",
            user=current_user,
            organization=current_user.organization  # FIXED: Added organization
        )
    
    else:  # viewer
        return render_template(
            "dashboard/viewer_dashboard.html",
            user=current_user,
            organization=current_user.organization  # FIXED: Added organization
        )


@dashboard_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """User profile page"""
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


@dashboard_bp.route("/organization", methods=["GET", "POST"])
@login_required
def organization_settings():
    """Organization settings (admin only)"""
    if current_user.role.value not in ["super_admin", "admin"]:
        return jsonify({"error": "Insufficient permissions"}), 403
    
    if request.method == "POST":
        # Only super_admin can edit organization
        if current_user.role.value != "super_admin":
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
    from app.services import UserService
    users = UserService.get_organization_users(current_user.organization_id)
    
    return render_template(
        "dashboard/organization.html",
        organization=current_user.organization,
        users=users
    )