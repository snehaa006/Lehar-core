"""
Database Package
Contains Firestore client and base repository
"""
from app.database.firestore_client import db, get_db, FirestoreClient
from app.database.base_repository import BaseRepository

__all__ = [
    'db',
    'get_db',
    'FirestoreClient',
    'BaseRepository'
]