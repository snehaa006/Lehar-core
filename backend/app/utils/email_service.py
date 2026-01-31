"""
Email Service - SMTP Integration
Handles all email sending operations
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, render_template
import secrets


def generate_verification_token():
    """Generate a secure random token for email verification"""
    return secrets.token_urlsafe(32)


def send_email(to_email, subject, html_body, text_body=None):
    """
    Send email via SMTP
    
    Args:
        to_email: Recipient email
        subject: Email subject
        html_body: HTML content
        text_body: Plain text content (optional)
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = current_app.config["MAIL_DEFAULT_SENDER"]
        msg["To"] = to_email
        msg["Subject"] = subject
        
        # Attach text and HTML parts
        if text_body:
            part1 = MIMEText(text_body, "plain")
            msg.attach(part1)
        
        part2 = MIMEText(html_body, "html")
        msg.attach(part2)
        
        # Connect to SMTP server
        with smtplib.SMTP(current_app.config["MAIL_SERVER"], current_app.config["MAIL_PORT"]) as server:
            if current_app.config["MAIL_USE_TLS"]:
                server.starttls()
            
            server.login(
                current_app.config["MAIL_USERNAME"],
                current_app.config["MAIL_PASSWORD"]
            )
            
            server.send_message(msg)
        
        return True
    
    except Exception as e:
        current_app.logger.error(f"Email sending failed: {str(e)}")
        return False


def send_verification_email(user_email, user_name, verification_token):
    """
    Send email verification link to new user
    """
    # FIX: Use BACKEND_URL instead of FRONTEND_URL and include the full path with /auth prefix
    verification_url = f"{current_app.config['BACKEND_URL']}/auth/verify-email?token={verification_token}"
    
    subject = "Verify Your Email - Lehar Core Platform"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .button {{ 
                display: inline-block; 
                padding: 12px 24px; 
                background-color: #007bff; 
                color: white; 
                text-decoration: none; 
                border-radius: 5px; 
                margin: 20px 0;
            }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Welcome to Lehar Core Platform!</h2>
            <p>Hi {user_name},</p>
            <p>Thank you for registering with Lehar Core Platform. Please verify your email address to activate your account.</p>
            
            <a href="{verification_url}" class="button">Verify Email Address</a>
            
            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #007bff;">{verification_url}</p>
            
            <p>This link will expire in 24 hours.</p>
            
            <div class="footer">
                <p>If you didn't create this account, please ignore this email.</p>
                <p>© 2026 Lehar Core Platform. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_body = f"""
    Welcome to Lehar Core Platform!
    
    Hi {user_name},
    
    Thank you for registering. Please verify your email address by clicking the link below:
    
    {verification_url}
    
    This link will expire in 24 hours.
    
    If you didn't create this account, please ignore this email.
    """
    
    return send_email(user_email, subject, html_body, text_body)


def send_invitation_email(invite_email, invite_name, organization_name, invitation_token, invited_by_name):
    """
    Send invitation email to join an organization
    """
    # FIX: Use BACKEND_URL for invitations too
    invitation_url = f"{current_app.config['BACKEND_URL']}/invitations/accept?token={invitation_token}"
    
    subject = f"You've been invited to join {organization_name} on Lehar Core"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .button {{ 
                display: inline-block; 
                padding: 12px 24px; 
                background-color: #28a745; 
                color: white; 
                text-decoration: none; 
                border-radius: 5px; 
                margin: 20px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>You've Been Invited!</h2>
            <p>Hi {invite_name or 'there'},</p>
            <p><strong>{invited_by_name}</strong> has invited you to join <strong>{organization_name}</strong> on Lehar Core Platform.</p>
            
            <a href="{invitation_url}" class="button">Accept Invitation</a>
            
            <p>Or copy this link: {invitation_url}</p>
            
            <p>This invitation expires in 7 days.</p>
        </div>
    </body>
    </html>
    """
    
    return send_email(invite_email, subject, html_body)


def send_password_reset_email(user_email, user_name, reset_token):
    """
    Send password reset link
    """
    # FIX: Use BACKEND_URL for password reset too
    reset_url = f"{current_app.config['BACKEND_URL']}/auth/reset-password?token={reset_token}"
    
    subject = "Reset Your Password - Lehar Core Platform"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body>
        <div class="container">
            <h2>Password Reset Request</h2>
            <p>Hi {user_name},</p>
            <p>We received a request to reset your password. Click the button below to create a new password:</p>
            
            <a href="{reset_url}" class="button">Reset Password</a>
            
            <p>This link expires in 1 hour.</p>
            <p>If you didn't request this, please ignore this email.</p>
        </div>
    </body>
    </html>
    """
    
    return send_email(user_email, subject, html_body)