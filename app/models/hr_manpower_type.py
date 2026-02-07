"""
HR Manpower Type Model - Firestore Version
Manpower types (designations) belong to a workspace.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid

from app.database.base_repository import BaseRepository
from google.cloud.firestore_v1 import FieldFilter


class HRManpowerTypeRepository(BaseRepository):
    """Repository for HR Manpower Type operations"""

    def __init__(self):
        super().__init__('hr_manpower_types')

    def get_by_workspace(self, workspace_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all manpower types for a workspace"""
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

    def find_by_name(self, workspace_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Find manpower type by name within a workspace"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
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


class HRManpowerType:
    """HR Manpower Type model - Firestore document wrapper"""

    repository = HRManpowerTypeRepository()

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get('id')
        self.workspace_id = data.get('workspace_id')
        self.name = data.get('name')
        self.name_lower = data.get('name_lower', '')
        self.is_active = data.get('is_active', True)
        self.created_by = data.get('created_by')
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')
        self.archived_at = data.get('archived_at')
        self.archived_by = data.get('archived_by')

    @classmethod
    def create(cls, workspace_id: str, name: str, created_by: str) -> 'HRManpowerType':
        """Create a new manpower type"""
        type_id = str(uuid.uuid4())
        data = {
            'workspace_id': workspace_id,
            'name': name,
            'name_lower': name.lower(),
            'is_active': True,
            'created_by': created_by,
        }
        created_data = cls.repository.create(type_id, data)
        return cls(created_data)

    @classmethod
    def get_by_id(cls, type_id: str) -> Optional['HRManpowerType']:
        data = cls.repository.get(type_id)
        return cls(data) if data else None

    @classmethod
    def get_by_workspace(cls, workspace_id: str, active_only: bool = True) -> List['HRManpowerType']:
        data_list = cls.repository.get_by_workspace(workspace_id, active_only)
        return [cls(data) for data in data_list]

    @classmethod
    def find_by_name(cls, workspace_id: str, name: str) -> Optional['HRManpowerType']:
        data = cls.repository.find_by_name(workspace_id, name)
        return cls(data) if data else None

    def archive(self, archived_by: str) -> bool:
        self.is_active = False
        data = {
            'is_active': False,
            'archived_by': archived_by,
            'archived_at': datetime.utcnow(),
        }
        return self.repository.update(self.id, data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'workspace_id': self.workspace_id,
            'name': self.name,
            'is_active': self.is_active,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
        }

    def __repr__(self):
        return f"<HRManpowerType {self.name} (ws={self.workspace_id})>"
