"""
HR Settings Model - Firestore Version
Each workspace has its own HR settings document.
Document ID = workspace_id (one settings doc per workspace).
"""
from datetime import datetime
from typing import Optional, Dict, Any

from app.database.base_repository import BaseRepository


# Default values
DEFAULT_SHIFT_HOURS = 10.0
DEFAULT_TOTAL_SHIFTS = 2
DEFAULT_UNFROZEN_DAYS = 5


class HRSettingsRepository(BaseRepository):
    """Repository for HR Settings operations"""

    def __init__(self):
        super().__init__('hr_settings')


class HRSettings:
    """HR Settings model - one document per workspace"""

    repository = HRSettingsRepository()

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get('id')  # same as workspace_id
        self.workspace_id = data.get('workspace_id', data.get('id'))
        self.default_shift_hours = data.get('default_shift_hours', DEFAULT_SHIFT_HOURS)
        self.total_shifts_available = data.get('total_shifts_available', DEFAULT_TOTAL_SHIFTS)
        self.unfrozen_days = data.get('unfrozen_days', DEFAULT_UNFROZEN_DAYS)
        self.updated_by = data.get('updated_by')
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')

    @classmethod
    def get_or_create(cls, workspace_id: str) -> 'HRSettings':
        """Get settings for a workspace, creating defaults if needed"""
        data = cls.repository.get(workspace_id)
        if data:
            return cls(data)

        # Create default settings
        default_data = {
            'workspace_id': workspace_id,
            'default_shift_hours': DEFAULT_SHIFT_HOURS,
            'total_shifts_available': DEFAULT_TOTAL_SHIFTS,
            'unfrozen_days': DEFAULT_UNFROZEN_DAYS,
        }
        created = cls.repository.create(workspace_id, default_data)
        return cls(created)

    def save(self) -> bool:
        data = {
            'workspace_id': self.workspace_id,
            'default_shift_hours': self.default_shift_hours,
            'total_shifts_available': self.total_shifts_available,
            'unfrozen_days': self.unfrozen_days,
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
            'updated_by': self.updated_by,
            'updated_at': self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
        }

    def __repr__(self):
        return f"<HRSettings ws={self.workspace_id} shift={self.default_shift_hours}h unfrozen={self.unfrozen_days}d>"
