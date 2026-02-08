"""
HR Worker Model - Firestore Version
Workers belong to a workspace. Supports:
- Dynamic hierarchy fields (designation, department, custom fields)
- Configurable salary components (up to 5, renameable)
- Dynamic contact info (variable key-value pairs)
- Auto-generated employee codes (EMP-001 format, workspace unique)
- Salary versioning with history
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid

from app.database.base_repository import BaseRepository
from google.cloud.firestore_v1 import FieldFilter


class HRWorkerRepository(BaseRepository):
    """Repository for HR Worker operations"""

    def __init__(self):
        super().__init__('hr_workers')

    def get_by_workspace(self, workspace_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all workers for a workspace"""
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

    def find_by_employee_code(self, workspace_id: str, employee_code: str) -> Optional[Dict[str, Any]]:
        """Find worker by employee code within a workspace"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        ).where(
            filter=FieldFilter("employee_code", "==", employee_code.upper())
        ).limit(1)

        docs = list(query.stream())
        if docs:
            data = docs[0].to_dict()
            data['id'] = docs[0].id
            return data
        return None

    def get_max_employee_code_number(self, workspace_id: str) -> int:
        """Get the highest numeric portion of EMP-XXX codes in a workspace"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        )
        docs = query.stream()
        max_num = 0
        for doc in docs:
            data = doc.to_dict()
            code = data.get('employee_code', '')
            if code.startswith('EMP-'):
                try:
                    num = int(code.split('-')[1])
                    max_num = max(max_num, num)
                except (IndexError, ValueError):
                    continue
        return max_num


class HRWorker:
    """HR Worker model - Firestore document wrapper"""

    repository = HRWorkerRepository()

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get('id')
        self.workspace_id = data.get('workspace_id')
        self.employee_code = data.get('employee_code')
        self.operator_name = data.get('operator_name')
        self.date_of_joining = data.get('date_of_joining')
        self.coverage = data.get('coverage', '')
        # Dynamic hierarchy values: {"designation": "Operator", "department": "Production", ...}
        self.hierarchy_values = data.get('hierarchy_values', {})
        # Dynamic contact info: [{"label": "Mobile", "value": "9876543210"}, ...]
        self.contact_info = data.get('contact_info', [])
        self.is_active = data.get('is_active', True)
        self.created_by = data.get('created_by')
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')
        self.updated_by = data.get('updated_by')
        # Remuneration with dynamic salary components
        self.remuneration = data.get('remuneration', {'current_version': 0, 'history': []})
        # Backward compat properties
        self.designation = self.hierarchy_values.get('designation', data.get('designation', ''))
        self.department = self.hierarchy_values.get('department', data.get('department', ''))

    @classmethod
    def generate_employee_code(cls, workspace_id: str) -> str:
        """Generate next EMP-XXX code for workspace"""
        max_num = cls.repository.get_max_employee_code_number(workspace_id)
        return f"EMP-{max_num + 1:03d}"

    @classmethod
    def create(cls, workspace_id: str, operator_name: str, created_by: str,
               employee_code: str = None, hierarchy_values: Dict[str, str] = None,
               contact_info: List[Dict[str, str]] = None,
               salary_components: Dict[str, float] = None,
               date_of_joining: str = '', coverage: str = '', **kwargs) -> 'HRWorker':
        """Create a new worker with dynamic fields"""
        worker_id = str(uuid.uuid4())

        if not employee_code:
            employee_code = cls.generate_employee_code(workspace_id)
        else:
            employee_code = employee_code.upper()

        hierarchy_values = hierarchy_values or {}
        contact_info = contact_info or []
        salary_components = salary_components or {}

        initial_salary = {
            'version': 1,
            'components': salary_components,
            'effective_date': date_of_joining or datetime.utcnow().strftime('%Y-%m-%d'),
            'created_at': datetime.utcnow().isoformat(),
            'created_by': created_by,
            'remarks': 'Initial salary',
            'is_active': True,
            'change_reason': 'Initial salary',
        }

        data = {
            'workspace_id': workspace_id,
            'employee_code': employee_code,
            'operator_name': operator_name,
            'date_of_joining': date_of_joining,
            'coverage': coverage,
            'hierarchy_values': hierarchy_values,
            'contact_info': contact_info,
            'is_active': True,
            'created_by': created_by,
            'remuneration': {
                'current_version': 1,
                'history': [initial_salary],
            },
        }

        created_data = cls.repository.create(worker_id, data)
        return cls(created_data)

    @classmethod
    def get_by_id(cls, worker_id: str) -> Optional['HRWorker']:
        data = cls.repository.get(worker_id)
        return cls(data) if data else None

    @classmethod
    def get_by_workspace(cls, workspace_id: str, active_only: bool = True) -> List['HRWorker']:
        data_list = cls.repository.get_by_workspace(workspace_id, active_only)
        return [cls(data) for data in data_list]

    @classmethod
    def find_by_employee_code(cls, workspace_id: str, employee_code: str) -> Optional['HRWorker']:
        data = cls.repository.find_by_employee_code(workspace_id, employee_code)
        return cls(data) if data else None

    def get_current_remuneration(self) -> Dict[str, Any]:
        """Get the latest remuneration record"""
        history = self.remuneration.get('history', [])
        if not history:
            return {'components': {}, 'version': 0, 'effective_date': None}
        return history[-1]

    def add_salary_record(self, record: Dict[str, Any]) -> bool:
        """Add a new salary record to remuneration history"""
        history = self.remuneration.get('history', [])
        current_version = len(history)
        record['version'] = current_version + 1
        history.append(record)
        self.remuneration = {
            'current_version': current_version + 1,
            'history': history,
        }
        return self.save()

    def save(self) -> bool:
        data = {
            'employee_code': self.employee_code,
            'operator_name': self.operator_name,
            'date_of_joining': self.date_of_joining,
            'coverage': self.coverage,
            'hierarchy_values': self.hierarchy_values,
            'contact_info': self.contact_info,
            'is_active': self.is_active,
            'remuneration': self.remuneration,
            'updated_by': self.updated_by,
        }
        return self.repository.update(self.id, data)

    def soft_delete(self, deleted_by: str) -> bool:
        self.is_active = False
        data = {
            'is_active': False,
            'deleted_at': datetime.utcnow(),
            'deleted_by': deleted_by,
        }
        return self.repository.update(self.id, data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'workspace_id': self.workspace_id,
            'unique_worker_id': self.id,
            'employee_code': self.employee_code,
            'operator_name': self.operator_name,
            'date_of_joining': self.date_of_joining,
            'coverage': self.coverage,
            'hierarchy_values': self.hierarchy_values,
            'contact_info': self.contact_info,
            # Backward compat
            'designation': self.designation,
            'department': self.department,
            'is_active': self.is_active,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            'updated_at': self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
            'remuneration': self.remuneration,
        }

    def __repr__(self):
        return f"<HRWorker {self.operator_name} ({self.employee_code}) ws={self.workspace_id}>"
