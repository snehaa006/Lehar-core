"""
HR Department Model - Firestore Version
Departments belong to a workspace. Each workspace manages its own departments.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid

from app.database.base_repository import BaseRepository
from google.cloud.firestore_v1 import FieldFilter


class HRDepartmentRepository(BaseRepository):
    """Repository for HR Department operations"""

    def __init__(self):
        super().__init__('hr_departments')

    def get_by_workspace(self, workspace_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all departments for a workspace"""
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
        """Find department by name within a workspace (case-sensitive)"""
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


class HRDepartment:
    """HR Department model - Firestore document wrapper"""

    repository = HRDepartmentRepository()

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get('id')
        self.workspace_id = data.get('workspace_id')
        self.name = data.get('name')
        self.name_lower = data.get('name_lower', '')
        self.head = data.get('head')
        self.description = data.get('description')
        self.is_active = data.get('is_active', True)
        self.created_by = data.get('created_by')
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')
        self.archived_at = data.get('archived_at')
        self.archived_by = data.get('archived_by')

    @classmethod
    def create(cls, workspace_id: str, name: str, created_by: str, **kwargs) -> 'HRDepartment':
        """Create a new department"""
        dept_id = str(uuid.uuid4())
        data = {
            'workspace_id': workspace_id,
            'name': name,
            'name_lower': name.lower(),
            'head': kwargs.get('head', ''),
            'description': kwargs.get('description', ''),
            'is_active': True,
            'created_by': created_by,
        }
        created_data = cls.repository.create(dept_id, data)
        return cls(created_data)

    @classmethod
    def get_by_id(cls, dept_id: str) -> Optional['HRDepartment']:
        data = cls.repository.get(dept_id)
        return cls(data) if data else None

    @classmethod
    def get_by_workspace(cls, workspace_id: str, active_only: bool = True) -> List['HRDepartment']:
        data_list = cls.repository.get_by_workspace(workspace_id, active_only)
        return [cls(data) for data in data_list]

    @classmethod
    def find_by_name(cls, workspace_id: str, name: str) -> Optional['HRDepartment']:
        data = cls.repository.find_by_name(workspace_id, name)
        return cls(data) if data else None

    def save(self) -> bool:
        data = {
            'name': self.name,
            'name_lower': self.name.lower(),
            'head': self.head,
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
            'name': self.name,
            'head': self.head,
            'description': self.description,
            'is_active': self.is_active,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            'updated_at': self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
        }

    def __repr__(self):
        return f"<HRDepartment {self.name} (ws={self.workspace_id})>"
