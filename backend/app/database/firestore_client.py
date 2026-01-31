"""
Firestore Database Client
Manages connection and provides database instance
"""
import os
from google.cloud import firestore
from google.oauth2 import service_account


class FirestoreClient:
    """Singleton Firestore client manager"""
    
    _instance = None
    _db = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirestoreClient, cls).__new__(cls)
            cls._instance._initialize_firestore()
        return cls._instance
    
    def _initialize_firestore(self):
        """Initialize Firestore connection"""
        # Get project ID from environment
        project_id = os.getenv("GCS_PROJECT_ID")
        
        # Check if running in GCP or local development
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        if credentials_path and os.path.exists(credentials_path):
            # Local development with service account
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path
            )
            self._db = firestore.Client(
                project=project_id,
                credentials=credentials
            )
        else:
            # Production: Use default credentials (Cloud Run, App Engine, etc.)
            self._db = firestore.Client(project=project_id)
    
    @property
    def db(self):
        """Get Firestore database instance"""
        return self._db
    
    def get_collection(self, collection_name):
        """Get a Firestore collection reference"""
        return self._db.collection(collection_name)
    
    def batch(self):
        """Get a new batch writer for batch operations"""
        return self._db.batch()
    
    def transaction(self):
        """Start a new transaction"""
        return self._db.transaction()


# Global Firestore client instance
db = FirestoreClient().db


def get_db():
    """Get the Firestore database instance (for compatibility)"""
    return db