"""
Input Validation Utilities
"""
import re
from email_validator import validate_email, EmailNotValidError


def is_valid_email(email):
    """Validate email format"""
    try:
        validate_email(email)
        return True
    except EmailNotValidError:
        return False


def extract_domain_from_email(email):
    """Extract domain from email (e.g., user@company.com -> company.com)"""
    if not is_valid_email(email):
        return None
    
    return email.split("@")[1].lower()


def is_work_email(email):
    """
    Check if email is a work email (not Gmail, Yahoo, etc.)
    Returns True if it's a company domain
    """
    personal_domains = [
        "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
        "icloud.com", "aol.com", "protonmail.com", "mail.com"
    ]
    
    domain = extract_domain_from_email(email)
    return domain and domain not in personal_domains


def is_strong_password(password):
    """
    Validate password strength
    Requirements:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"
    
    return True, "Password is strong"


def sanitize_slug(text):
    """Convert text to URL-friendly slug"""
    # Convert to lowercase and replace spaces with hyphens
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)  # Remove special characters
    slug = re.sub(r'[-\s]+', '-', slug)   # Replace spaces with hyphens
    return slug


def validate_phone(phone):
    """Basic phone number validation"""
    # Remove spaces and common separators
    cleaned = re.sub(r'[\s\-\(\)]', '', phone)
    
    # Check if it's 10-15 digits
    if re.match(r'^\+?\d{10,15}$', cleaned):
        return True
    
    return False
