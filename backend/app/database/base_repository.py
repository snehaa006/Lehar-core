"""
Base Repository Pattern for Firestore
Provides common CRUD operations for all models
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from google.cloud.firestore_v1 import FieldFilter
from app.database.firestore_client import db
from google.cloud.firestore_v1.aggregation import AggregationQuery

class BaseRepository:
    """Base class for Firestore repositories"""
    
    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self.collection = db.collection(collection_name)
    
    def create(self, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new document
        
        Args:
            doc_id: Document ID
            data: Document data
            
        Returns:
            Created document data with ID
        """
        # Add timestamps
        if 'created_at' not in data:
            data['created_at'] = datetime.utcnow()
        if 'updated_at' not in data:
            data['updated_at'] = datetime.utcnow()
        
        # Create document
        doc_ref = self.collection.document(doc_id)
        doc_ref.set(data)
        
        # Return data with ID
        result = data.copy()
        result['id'] = doc_id
        return result
    
    def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Get document by ID
        
        Args:
            doc_id: Document ID
            
        Returns:
            Document data or None if not found
        """
        doc_ref = self.collection.document(doc_id)
        doc = doc_ref.get()
        
        if doc.exists:
            data = doc.to_dict()
            data['id'] = doc.id
            return data
        return None
    
    def update(self, doc_id: str, data: Dict[str, Any]) -> bool:
        """
        Update document
        
        Args:
            doc_id: Document ID
            data: Fields to update
            
        Returns:
            True if successful
        """
        # Add updated timestamp
        data['updated_at'] = datetime.utcnow()
        
        doc_ref = self.collection.document(doc_id)
        doc_ref.update(data)
        return True
    
    def delete(self, doc_id: str) -> bool:
        """
        Delete document
        
        Args:
            doc_id: Document ID
            
        Returns:
            True if successful
        """
        doc_ref = self.collection.document(doc_id)
        doc_ref.delete()
        return True
    
    def get_all(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get all documents in collection
        
        Args:
            limit: Maximum number of documents to return
            
        Returns:
            List of documents
        """
        query = self.collection
        if limit:
            query = query.limit(limit)
        
        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)
        
        return results
    
    def filter_by(self, field: str, value: Any, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Filter documents by field value
        
        Args:
            field: Field name
            value: Field value
            limit: Maximum number of results
            
        Returns:
            List of matching documents
        """
        query = self.collection.where(filter=FieldFilter(field, "==", value))
        
        if limit:
            query = query.limit(limit)
        
        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)
        
        return results
    
    def find_one(self, field: str, value: Any) -> Optional[Dict[str, Any]]:
        """
        Find single document by field value
        
        Args:
            field: Field name
            value: Field value
            
        Returns:
            Document data or None
        """
        results = self.filter_by(field, value, limit=1)
        return results[0] if results else None
    
    def exists(self, doc_id: str) -> bool:
        """
        Check if document exists
        
        Args:
            doc_id: Document ID
            
        Returns:
            True if document exists
        """
        doc_ref = self.collection.document(doc_id)
        return doc_ref.get().exists
    
    def count(self, field: Optional[str] = None, value: Optional[Any] = None) -> int:
        """
        Count documents using Firestore aggregation
        """
        if field and value:
            query = self.collection.where(filter=FieldFilter(field, "==", value))
        else:
            query = self.collection
        
        # Use aggregation count (requires google-cloud-firestore >= 2.11.0)
        aggregation_query = AggregationQuery(query)
        aggregation_query.count()
        result = aggregation_query.get()
        
        return result[0][0].value
    
    def batch_create(self, documents: List[Dict[str, Any]]) -> bool:
        """
        Create multiple documents in a batch
        
        Args:
            documents: List of {id, data} dicts
            
        Returns:
            True if successful
        """
        batch = db.batch()
        
        for doc in documents:
            doc_id = doc['id']
            data = doc['data']
            
            # Add timestamps
            if 'created_at' not in data:
                data['created_at'] = datetime.utcnow()
            if 'updated_at' not in data:
                data['updated_at'] = datetime.utcnow()
            
            doc_ref = self.collection.document(doc_id)
            batch.set(doc_ref, data)
        
        batch.commit()
        return True
    
    def batch_update(self, updates: List[Dict[str, Any]]) -> bool:
        """
        Update multiple documents in a batch
        
        Args:
            updates: List of {id, data} dicts
            
        Returns:
            True if successful
        """
        batch = db.batch()
        
        for update in updates:
            doc_id = update['id']
            data = update['data']
            data['updated_at'] = datetime.utcnow()
            
            doc_ref = self.collection.document(doc_id)
            batch.update(doc_ref, data)
        
        batch.commit()
        return True
    
    def batch_delete(self, doc_ids: List[str]) -> bool:
        """
        Delete multiple documents in a batch
        
        Args:
            doc_ids: List of document IDs
            
        Returns:
            True if successful
        """
        batch = db.batch()
        
        for doc_id in doc_ids:
            doc_ref = self.collection.document(doc_id)
            batch.delete(doc_ref)
        
        batch.commit()
        return True