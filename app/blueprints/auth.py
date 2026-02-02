"""
Authentication Blueprint
Handles signup, login, email verification, and domain/workspace discovery
"""
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from app.services import OrganizationService, UserService, WorkspaceService
from app.utils import (
    is_valid_email, is_strong_password, validate_phone,
    generate_access_token, send_verification_email,
    extract_domain_from_email, is_work_email
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    """Simple user registration - just name, email, password"""
    if current_user.is_authenticated:
        return redirect(url_for("workspaces.workspace_selector"))

    if request.method == "GET":
        email = request.args.get("email", "")
        return render_template("auth/signup.html", errors={}, form_data={"email": email})

    # POST - Handle form submission
    data = request.get_json() if request.is_json else request.form.to_dict()

    # Validate inputs
    errors = {}

    # User data
    email = data.get("email", "").strip().lower()
    if not is_valid_email(email):
        errors["email"] = "Invalid email address"

    password = data.get("password", "")
    is_strong, password_msg = is_strong_password(password)
    if not is_strong:
        errors["password"] = password_msg

    name = data.get("name", "").strip()
    if not name:
        errors["name"] = "Name is required"

    if errors:
        if request.is_json:
            return jsonify({"errors": errors}), 400
        return render_template("auth/signup.html", errors=errors, form_data=data)

    # Create user (no organization required)
    user, error = UserService.create_user(
        name=name,
        email=email,
        password=password
    )

    if error:
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "error")
        return render_template("auth/signup.html", errors={}, form_data=data)

    # Send verification email
    send_verification_email(
        user_email=user.email,
        user_name=user.name,
        verification_token=user.email_verification_token
    )

    if request.is_json:
        return jsonify({
            "message": "Registration successful! Please check your email to verify your account.",
            "user_id": user.id
        }), 201

    flash("Registration successful! Please check your email to verify your account.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/discover-workspaces", methods=["GET", "POST"])
def discover_workspaces():
    """
    Discover existing workspaces for a domain
    Shows workspaces user can request to join
    """
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "GET":
        email = request.args.get("email", "")
        workspaces = []

        if email and is_valid_email(email) and is_work_email(email):
            domain = extract_domain_from_email(email)
            workspaces = OrganizationService.get_workspaces_for_domain(domain)

        return render_template(
            "auth/discover_workspaces.html",
            email=email,
            workspaces=workspaces,
            is_work_email=is_work_email(email) if email else False
        )

    # POST - Check email and return workspaces
    data = request.get_json() if request.is_json else request.form.to_dict()
    email = data.get("email", "").strip().lower()

    if not is_valid_email(email):
        if request.is_json:
            return jsonify({"error": "Invalid email address"}), 400
        flash("Invalid email address", "error")
        return redirect(url_for("auth.discover_workspaces"))

    if not is_work_email(email):
        # Personal email - redirect to signup
        if request.is_json:
            return jsonify({
                "is_personal_email": True,
                "message": "Personal email detected. You can create your own organization.",
                "redirect": url_for("auth.signup", email=email)
            })
        return redirect(url_for("auth.signup", email=email))

    domain = extract_domain_from_email(email)
    workspaces = OrganizationService.get_workspaces_for_domain(domain)

    if request.is_json:
        if not workspaces:
            return jsonify({
                "workspaces": [],
                "message": "No existing workspaces found. You can create a new organization.",
                "redirect": url_for("auth.signup", email=email)
            })
        return jsonify({
            "workspaces": workspaces,
            "domain": domain,
            "email": email
        })

    if not workspaces:
        flash("No existing workspaces found for your domain. You can create a new organization.", "info")
        return redirect(url_for("auth.signup", email=email))

    return render_template(
        "auth/discover_workspaces.html",
        email=email,
        workspaces=workspaces,
        is_work_email=True
    )


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """User login page"""
    if current_user.is_authenticated:
        # Redirect to last workspace or workspace selector
        if current_user.last_workspace_id:
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("workspaces.workspace_selector"))

    if request.method == "GET":
        return render_template("auth/login.html")

    data = request.get_json() if request.is_json else request.form.to_dict()

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    remember = data.get("remember", False)

    if not email or not password:
        error = "Email and password are required"
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "error")
        return render_template("auth/login.html")

    # Authenticate user
    user, error = UserService.authenticate(email, password)

    if error:
        if request.is_json:
            return jsonify({"error": error}), 401
        flash(error, "error")
        return render_template("auth/login.html", form_data={"email": email})

    # Log user in with Flask-Login
    login_user(user, remember=remember)

    if request.is_json:
        # For API calls, also return JWT token
        org_role_value = user.org_role.value if user.org_role else None
        plan_type_value = user.organization.plan_type.value if user.organization else 'free'
        access_token = generate_access_token(
            user_id=user.id,
            organization_id=user.organization_id,
            org_role=org_role_value,
            plan_type=plan_type_value
        )
        return jsonify({
            "access_token": access_token,
            "user": user.to_dict(include_org=True)
        }), 200

    # For web interface
    flash(f"Welcome back, {user.name}!", "success")

    # Redirect to next page if specified
    next_page = request.args.get('next')
    if next_page:
        return redirect(next_page)

    # Redirect to last workspace or workspace selector
    if user.last_workspace_id:
        return redirect(url_for("dashboard.index"))

    return redirect(url_for("workspaces.workspace_selector"))


@auth_bp.route("/verify-email", methods=["GET"])
def verify_email():
    """Email verification endpoint"""
    token = request.args.get("token")

    if not token:
        flash("Invalid verification link", "error")
        return redirect(url_for("auth.login"))

    success, message = UserService.verify_email(token)

    if success:
        flash(message, "success")
    else:
        flash(message, "error")

    return redirect(url_for("auth.login"))


@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    """Logout user"""
    logout_user()
    flash("You have been logged out successfully", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/check-domain", methods=["POST"])
def check_domain():
    """
    API endpoint to check if organization with email domain already exists
    Returns available workspaces if domain exists
    """
    data = request.get_json()
    email = data.get("email", "").strip().lower()

    if not is_valid_email(email):
        return jsonify({"error": "Invalid email"}), 400

    if not is_work_email(email):
        return jsonify({
            "domain_exists": False,
            "is_personal_email": True,
            "message": "Personal email detected. You can proceed with creating your own organization."
        }), 200

    domain = extract_domain_from_email(email)
    workspaces = OrganizationService.get_workspaces_for_domain(domain)

    if workspaces:
        return jsonify({
            "domain_exists": True,
            "workspaces": workspaces,
            "message": f"Found {len(workspaces)} workspace(s) for your domain. You can request to join or create a new workspace."
        }), 200

    return jsonify({
        "domain_exists": False,
        "message": "No existing organization found. You can create a new organization."
    }), 200
