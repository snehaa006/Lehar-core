"""
Settings Blueprint
Consolidated settings page with profile, workspace, and domain verification
"""
import uuid
import hashlib
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.utils import is_strong_password, validate_phone
from app.services import WorkspaceService
from app.models import Workspace, WorkspaceMembership

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


def generate_dns_verification_token(workspace_id: str) -> str:
    """Generate a unique DNS verification token for a workspace"""
    raw = f"lehar-verify-{workspace_id}-{uuid.uuid4().hex[:8]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


@settings_bp.route("/", methods=["GET"])
@login_required
def index():
    """Main settings page"""
    # Get user's workspaces where they are admin
    user_workspaces = WorkspaceService.get_user_workspaces(current_user.id)
    admin_workspaces = [
        ws for ws in user_workspaces
        if ws['role'].value == 'admin'
    ]

    return render_template(
        "settings/index.html",
        user=current_user,
        admin_workspaces=admin_workspaces,
        organization=current_user.organization
    )


@settings_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Profile settings"""
    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_profile":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            job_title = request.form.get("job_title", "").strip()

            if not name:
                flash("Name is required", "error")
                return redirect(url_for("settings.profile"))

            if phone and not validate_phone(phone):
                flash("Invalid phone number", "error")
                return redirect(url_for("settings.profile"))

            current_user.name = name
            current_user.phone = phone if phone else None
            current_user.job_title = job_title if job_title else None
            current_user.save()

            flash("Profile updated successfully", "success")
            return redirect(url_for("settings.profile"))

        elif action == "change_password":
            current_password = request.form.get("current_password")
            new_password = request.form.get("new_password")
            confirm_password = request.form.get("confirm_password")

            if not current_user.check_password(current_password):
                flash("Current password is incorrect", "error")
                return redirect(url_for("settings.profile"))

            if new_password != confirm_password:
                flash("New passwords do not match", "error")
                return redirect(url_for("settings.profile"))

            is_strong, password_msg = is_strong_password(new_password)
            if not is_strong:
                flash(password_msg, "error")
                return redirect(url_for("settings.profile"))

            current_user.set_password(new_password)
            current_user.save()

            flash("Password changed successfully", "success")
            return redirect(url_for("settings.profile"))

    return render_template(
        "settings/profile.html",
        user=current_user,
        organization=current_user.organization
    )


@settings_bp.route("/workspace/<workspace_id>", methods=["GET", "POST"])
@login_required
def workspace_settings(workspace_id):
    """Workspace settings (admin only)"""
    workspace = Workspace.get_by_id(workspace_id)
    if not workspace:
        flash("Workspace not found", "error")
        return redirect(url_for("settings.index"))

    # Check if user is workspace admin
    if not WorkspaceMembership.user_is_workspace_admin(current_user.id, workspace_id):
        flash("You don't have permission to access workspace settings", "error")
        return redirect(url_for("settings.index"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_workspace":
            workspace.name = request.form.get("name", "").strip()
            workspace.description = request.form.get("description", "").strip()
            workspace.org_name = request.form.get("org_name", "").strip() or None
            workspace.org_industry = request.form.get("org_industry", "").strip() or None
            workspace.org_size = request.form.get("org_size", "").strip() or None
            workspace.org_website = request.form.get("org_website", "").strip() or None
            workspace.save()

            flash("Workspace updated successfully", "success")
            return redirect(url_for("settings.workspace_settings", workspace_id=workspace_id))

        elif action == "initiate_verification":
            # Generate verification token and domain
            domain = request.form.get("domain", "").strip().lower()
            if not domain:
                flash("Please enter a domain to verify", "error")
                return redirect(url_for("settings.workspace_settings", workspace_id=workspace_id))

            # Generate DNS token
            token = generate_dns_verification_token(workspace_id)

            # Store pending verification data
            workspace.verified_domain = domain
            workspace.is_domain_verified = False
            # Store token in a custom field (we'll check this during verification)
            workspace._verification_token = token
            workspace.save()

            flash(f"DNS verification initiated. Add a TXT record to {domain}", "success")
            return redirect(url_for("settings.workspace_settings", workspace_id=workspace_id))

        elif action == "verify_domain":
            # Check DNS for verification token
            domain = workspace.verified_domain
            if not domain:
                flash("No domain configured for verification", "error")
                return redirect(url_for("settings.workspace_settings", workspace_id=workspace_id))

            # In production, you would check DNS TXT records here
            # For now, we'll simulate verification
            try:
                import dns.resolver
                answers = dns.resolver.resolve(domain, 'TXT')
                expected_token = f"lehar-verify={workspace.id[:16]}"

                verified = False
                for rdata in answers:
                    txt_value = str(rdata).strip('"')
                    if expected_token in txt_value:
                        verified = True
                        break

                if verified:
                    workspace.is_domain_verified = True
                    workspace.save()
                    flash(f"Domain {domain} verified successfully!", "success")
                else:
                    flash("Verification failed. TXT record not found.", "error")
            except Exception as e:
                # If DNS library not available, allow manual verification for now
                current_app.logger.warning(f"DNS verification error: {e}")
                flash("DNS verification requires the dnspython library. Please verify manually or install the library.", "error")

            return redirect(url_for("settings.workspace_settings", workspace_id=workspace_id))

    # Generate expected TXT record value
    expected_txt = f"lehar-verify={workspace.id[:16]}"

    return render_template(
        "settings/workspace.html",
        workspace=workspace,
        expected_txt=expected_txt,
        user=current_user
    )


@settings_bp.route("/workspace/<workspace_id>/regenerate-code", methods=["POST"])
@login_required
def regenerate_join_code(workspace_id):
    """Regenerate workspace join code"""
    workspace = Workspace.get_by_id(workspace_id)
    if not workspace:
        flash("Workspace not found", "error")
        return redirect(url_for("settings.index"))

    if not WorkspaceMembership.user_is_workspace_admin(current_user.id, workspace_id):
        flash("You don't have permission to regenerate join code", "error")
        return redirect(url_for("settings.index"))

    from app.models.workspace import generate_join_code

    new_code = generate_join_code()
    while Workspace.repository.join_code_exists(new_code):
        new_code = generate_join_code()

    workspace.join_code = new_code
    workspace.save()

    flash(f"Join code regenerated: {new_code}", "success")
    return redirect(url_for("settings.workspace_settings", workspace_id=workspace_id))
