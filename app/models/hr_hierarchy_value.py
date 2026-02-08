"""
HR Hierarchy Value Model - Firestore Version
Generic model replacing HRDepartment and HRManpowerType.
Supports dynamic hierarchy fields (department, designation, custom fields).
Each value belongs to a workspace and a specific field_key.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid

from app.database.base_repository import BaseRepository
from google.cloud.firestore_v1 import FieldFilter


class HRHierarchyValueRepository(BaseRepository):
    """Repository for HR Hierarchy Value operations"""

    def __init__(self):
        super().__init__('hr_hierarchy_values')

    def get_by_workspace_and_field(self, workspace_id: str, field_key: str,
                                   active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all values for a specific hierarchy field in a workspace"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        ).where(
            filter=FieldFilter("field_key", "==", field_key)
        )
        if active_only:
            query = query.where(filter=FieldFilter("is_active", "==", True))

        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)
        return results

    def get_by_workspace(self, workspace_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all hierarchy values for a workspace"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        )
        if active_only:
            query = query.where(filter=FieldFilter("is_active", "==", True))

        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)
        return results

    def find_by_name(self, workspace_id: str, field_key: str, name: str) -> Optional[Dict[str, Any]]:
        """Find value by name within a workspace and field (case-insensitive)"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        ).where(
            filter=FieldFilter("field_key", "==", field_key)
        ).where(
            filter=FieldFilter("name_lower", "==", name.lower())
        ).where(
            filter=FieldFilter("is_active", "==", True)
        ).limit(1)

        docs = list(query.stream())
        if docs:
            data = docs[0].to_dict()
            data['id'] = docs[0].id
            return data
        return None


class HRHierarchyValue:
    """HR Hierarchy Value model - Firestore document wrapper"""

    repository = HRHierarchyValueRepository()

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get('id')
        self.workspace_id = data.get('workspace_id')
        self.field_key = data.get('field_key')
        self.name = data.get('name')
        self.name_lower = data.get('name_lower', '')
        self.description = data.get('description', '')
        self.is_active = data.get('is_active', True)
        self.created_by = data.get('created_by')
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')
        self.archived_at = data.get('archived_at')
        self.archived_by = data.get('archived_by')

    @classmethod
    def create(cls, workspace_id: str, field_key: str, name: str, created_by: str,
               description: str = '') -> 'HRHierarchyValue':
        value_id = str(uuid.uuid4())
        data = {
            'workspace_id': workspace_id,
            'field_key': field_key,
            'name': name,
            'name_lower': name.lower(),
            'description': description,
            'is_active': True,
            'created_by': created_by,
        }
        created_data = cls.repository.create(value_id, data)
        return cls(created_data)

    @classmethod
    def get_by_id(cls, value_id: str) -> Optional['HRHierarchyValue']:
        data = cls.repository.get(value_id)
        return cls(data) if data else None

    @classmethod
    def get_by_workspace_and_field(cls, workspace_id: str, field_key: str,
                                   active_only: bool = True) -> List['HRHierarchyValue']:
        data_list = cls.repository.get_by_workspace_and_field(workspace_id, field_key, active_only)
        return [cls(data) for data in data_list]

    @classmethod
    def get_by_workspace(cls, workspace_id: str, active_only: bool = True) -> List['HRHierarchyValue']:
        data_list = cls.repository.get_by_workspace(workspace_id, active_only)
        return [cls(data) for data in data_list]

    @classmethod
    def find_by_name(cls, workspace_id: str, field_key: str, name: str) -> Optional['HRHierarchyValue']:
        data = cls.repository.find_by_name(workspace_id, field_key, name)
        return cls(data) if data else None

    def save(self) -> bool:
        data = {
            'name': self.name,
            'name_lower': self.name.lower(),
            'description': self.description,
            'is_active': self.is_active,
        }
        return self.repository.update(self.id, data)

    def archive(self, archived_by: str) -> bool:
        self.is_active = False
        self.archived_by = archived_by
        self.archived_at = datetime.utcnow()
        data = {
            'is_active': False,
            'archived_by': archived_by,
            'archived_at': self.archived_at,
        }
        return self.repository.update(self.id, data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'workspace_id': self.workspace_id,
            'field_key': self.field_key,
            'name': self.name,
            'description': self.description,
            'is_active': self.is_active,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            'updated_at': self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
        }

    def __repr__(self):
        return f"<HRHierarchyValue {self.field_key}={self.name} (ws={self.workspace_id})>"
