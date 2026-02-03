"""
Main Application Entry Point - Firestore Version
Run this file to start the Flask server
"""
import os
from app import create_app
from app.models import Organization, User, Invitation
from app.database import db

# Create Flask app
app = create_app()

# Shell context for Flask CLI
@app.shell_context_processor
def make_shell_context():
    """Make database and models available in Flask shell"""
    return {
        "db": db,
        "Organization": Organization,
        "User": User,
        "Invitation": Invitation
    }


if __name__ == "__main__":
    # Get port from environment (Cloud Run sets PORT)
    port = int(os.getenv("PORT", 8080))
    
    # Run the application
    app.run(
        host="0.0.0.0",
        port=port,
        debug=app.config["DEBUG"]
    )