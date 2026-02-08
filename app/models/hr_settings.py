"""
HR Settings Model - Firestore Version
Each workspace has its own HR settings document.
Document ID = workspace_id (one settings doc per workspace).

Stores:
- Shift configuration (hours, total shifts, unfrozen days)
- Hierarchy field configuration (dynamic, renameable fields)
- Salary component configuration (up to 5, renameable)
- Employee limit for free tier
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

from app.database.base_repository import BaseRepository


# Default values
DEFAULT_SHIFT_HOURS = 10.0
DEFAULT_TOTAL_SHIFTS = 2
DEFAULT_UNFROZEN_DAYS = 5
DEFAULT_EMPLOYEE_LIMIT = 10
DEFAULT_COST_BASE_HOURS_PER_DAY = 8.0
DEFAULT_COST_BASE_DAYS_PER_MONTH = 30
MAX_HIERARCHY_FIELDS = 5
MAX_SALARY_COMPONENTS = 5

DEFAULT_HIERARCHY_FIELDS = [
    {'key': 'designation', 'label': 'Designation', 'sort_order': 0, 'is_active': True},
    {'key': 'department', 'label': 'Department', 'sort_order': 1, 'is_active': True},
    {'key': 'custom_1', 'label': 'Section', 'sort_order': 2, 'is_active': False},
]

DEFAULT_SALARY_COMPONENTS = [
    {'key': 'component_1', 'label': 'Basic', 'is_active': True},
    {'key': 'component_2', 'label': 'HRA', 'is_active': True},
    {'key': 'component_3', 'label': 'Bonus', 'is_active': False},
    {'key': 'component_4', 'label': 'Allowance', 'is_active': False},
    {'key': 'component_5', 'label': 'Other', 'is_active': False},
]


class HRSettingsRepository(BaseRepository):
    """Repository for HR Settings operations"""

    def __init__(self):
        super().__init__('hr_settings')


class HRSettings:
    """HR Settings model - one document per workspace"""

    repository = HRSettingsRepository()

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get('id')
        self.workspace_id = data.get('workspace_id', data.get('id'))
        self.default_shift_hours = data.get('default_shift_hours', DEFAULT_SHIFT_HOURS)
        self.total_shifts_available = data.get('total_shifts_available', DEFAULT_TOTAL_SHIFTS)
        self.unfrozen_days = data.get('unfrozen_days', DEFAULT_UNFROZEN_DAYS)
        self.employee_limit = data.get('employee_limit', DEFAULT_EMPLOYEE_LIMIT)
        self.hierarchy_fields = data.get('hierarchy_fields', DEFAULT_HIERARCHY_FIELDS)
        self.salary_components = data.get('salary_components', DEFAULT_SALARY_COMPONENTS)
        self.cost_base_hours_per_day = data.get('cost_base_hours_per_day', DEFAULT_COST_BASE_HOURS_PER_DAY)
        self.cost_base_days_per_month = data.get('cost_base_days_per_month', DEFAULT_COST_BASE_DAYS_PER_MONTH)
        self.updated_by = data.get('updated_by')
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')

    @classmethod
    def get_or_create(cls, workspace_id: str) -> 'HRSettings':
        """Get settings for a workspace, creating defaults if needed"""
        data = cls.repository.get(workspace_id)
        if data:
            return cls(data)

        default_data = {
            'workspace_id': workspace_id,
            'default_shift_hours': DEFAULT_SHIFT_HOURS,
            'total_shifts_available': DEFAULT_TOTAL_SHIFTS,
            'unfrozen_days': DEFAULT_UNFROZEN_DAYS,
            'employee_limit': DEFAULT_EMPLOYEE_LIMIT,
            'hierarchy_fields': DEFAULT_HIERARCHY_FIELDS,
            'salary_components': DEFAULT_SALARY_COMPONENTS,
            'cost_base_hours_per_day': DEFAULT_COST_BASE_HOURS_PER_DAY,
            'cost_base_days_per_month': DEFAULT_COST_BASE_DAYS_PER_MONTH,
        }
        created = cls.repository.create(workspace_id, default_data)
        return cls(created)

    def get_active_hierarchy_fields(self) -> List[Dict[str, Any]]:
        """Return only active hierarchy fields, sorted by sort_order"""
        active = [f for f in self.hierarchy_fields if f.get('is_active', True)]
        active.sort(key=lambda x: x.get('sort_order', 0))
        return active

    def get_active_salary_components(self) -> List[Dict[str, Any]]:
        """Return only active salary components"""
        return [c for c in self.salary_components if c.get('is_active', True)]

    def save(self) -> bool:
        data = {
            'workspace_id': self.workspace_id,
            'default_shift_hours': self.default_shift_hours,
            'total_shifts_available': self.total_shifts_available,
            'unfrozen_days': self.unfrozen_days,
            'employee_limit': self.employee_limit,
            'hierarchy_fields': self.hierarchy_fields,
            'salary_components': self.salary_components,
            'cost_base_hours_per_day': self.cost_base_hours_per_day,
            'cost_base_days_per_month': self.cost_base_days_per_month,
            'updated_by': self.updated_by,
        }
        return self.repository.update(self.id, data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'workspace_id': self.workspace_id,
            'default_shift_hours': self.default_shift_hours,
            'total_shifts_available': self.total_shifts_available,
            'unfrozen_days': self.unfrozen_days,
            'default_hours_worked': self.default_shift_hours,  # alias for v1 compat
            'employee_limit': self.employee_limit,
            'hierarchy_fields': self.hierarchy_fields,
            'salary_components': self.salary_components,
            'cost_base_hours_per_day': self.cost_base_hours_per_day,
            'cost_base_days_per_month': self.cost_base_days_per_month,
            'updated_by': self.updated_by,
            'updated_at': self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
        }

    def __repr__(self):
        return f"<HRSettings ws={self.workspace_id} shift={self.default_shift_hours}h>"
