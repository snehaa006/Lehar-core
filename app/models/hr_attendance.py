"""
HR Attendance Model - Firestore Version
Attendance records belong to a workspace. One record per worker per date.
Document ID format: {workspace_id}_{date}_{employee_code}
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid

from app.database.base_repository import BaseRepository
from google.cloud.firestore_v1 import FieldFilter


class HRAttendanceRepository(BaseRepository):
    """Repository for HR Attendance operations"""

    def __init__(self):
        super().__init__('hr_attendance')

    def get_by_date(self, workspace_id: str, date: str) -> List[Dict[str, Any]]:
        """Get all attendance records for a workspace on a date"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        ).where(
            filter=FieldFilter("date", "==", date)
        )

        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)
        return results

    def get_worker_attendance(self, workspace_id: str, employee_code: str, date: str) -> Optional[Dict[str, Any]]:
        """Get attendance for a specific worker on a specific date"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        ).where(
            filter=FieldFilter("employee_code", "==", employee_code)
        ).where(
            filter=FieldFilter("date", "==", date)
        ).limit(1)

        docs = list(query.stream())
        if docs:
            data = docs[0].to_dict()
            data['id'] = docs[0].id
            return data
        return None

    def get_worker_range(self, workspace_id: str, employee_code: str,
                         start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get attendance records for a worker in a date range"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        ).where(
            filter=FieldFilter("employee_code", "==", employee_code)
        ).where(
            filter=FieldFilter("date", ">=", start_date)
        ).where(
            filter=FieldFilter("date", "<=", end_date)
        )

        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)
        return results


class HRAttendance:
    """HR Attendance model - Firestore document wrapper"""

    repository = HRAttendanceRepository()

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get('id')
        self.workspace_id = data.get('workspace_id')
        self.employee_code = data.get('employee_code')
        self.worker_id = data.get('worker_id')
        self.worker_name = data.get('worker_name')
        self.department = data.get('department')
        self.date = data.get('date')
        self.status = data.get('status')  # PRESENT or ABSENT
        self.shifts_worked = data.get('shifts_worked', 0)
        self.hours_worked = data.get('hours_worked', 0.0)
        self.remarks = data.get('remarks', '')
        self.auto_marked = data.get('auto_marked', False)
        self.created_by = data.get('created_by')
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')
        self.updated_by = data.get('updated_by')

    @classmethod
    def create_or_update(cls, workspace_id: str, employee_code: str, date: str,
                         worker_data: Dict[str, Any], attendance_data: Dict[str, Any],
                         user_email: str) -> tuple:
        """
        Create or update attendance for a worker on a date.
        Returns (attendance, is_update, existing_data)
        """
        existing = cls.repository.get_worker_attendance(workspace_id, employee_code, date)

        now = datetime.utcnow()

        if existing:
            # Update existing record
            update_data = {
                'status': attendance_data['status'],
                'shifts_worked': attendance_data.get('shifts_worked', 0),
                'hours_worked': attendance_data.get('hours_worked', 0.0),
                'remarks': attendance_data.get('remarks', ''),
                'updated_by': user_email,
                'auto_marked': False,
            }
            cls.repository.update(existing['id'], update_data)
            updated = cls.repository.get(existing['id'])
            return cls(updated), True, existing
        else:
            # Create new record
            record_id = str(uuid.uuid4())
            data = {
                'workspace_id': workspace_id,
                'employee_code': employee_code,
                'worker_id': worker_data.get('id', worker_data.get('unique_worker_id', '')),
                'worker_name': worker_data.get('operator_name', ''),
                'department': worker_data.get('department', ''),
                'date': date,
                'status': attendance_data['status'],
                'shifts_worked': attendance_data.get('shifts_worked', 0),
                'hours_worked': attendance_data.get('hours_worked', 0.0),
                'remarks': attendance_data.get('remarks', ''),
                'auto_marked': attendance_data.get('auto_marked', False),
                'created_by': user_email,
            }
            created_data = cls.repository.create(record_id, data)
            return cls(created_data), False, None

    @classmethod
    def get_by_date(cls, workspace_id: str, date: str) -> List['HRAttendance']:
        data_list = cls.repository.get_by_date(workspace_id, date)
        return [cls(data) for data in data_list]

    @classmethod
    def get_worker_attendance(cls, workspace_id: str, employee_code: str,
                              date: str) -> Optional['HRAttendance']:
        data = cls.repository.get_worker_attendance(workspace_id, employee_code, date)
        return cls(data) if data else None

    @classmethod
    def get_worker_range(cls, workspace_id: str, employee_code: str,
                         start_date: str, end_date: str) -> List['HRAttendance']:
        data_list = cls.repository.get_worker_range(workspace_id, employee_code, start_date, end_date)
        return [cls(data) for data in data_list]

    @classmethod
    def bulk_create_absent(cls, workspace_id: str, workers: List[Dict[str, Any]],
                           date: str, existing_codes: set) -> int:
        """
        Auto-mark workers as ABSENT for a given date (skip those already marked).
        Returns count of newly marked workers.
        """
        count = 0
        for worker in workers:
            emp_code = worker.get('employee_code', '')
            if emp_code in existing_codes:
                continue

            record_id = str(uuid.uuid4())
            data = {
                'workspace_id': workspace_id,
                'employee_code': emp_code,
                'worker_id': worker.get('id', worker.get('unique_worker_id', '')),
                'worker_name': worker.get('operator_name', ''),
                'department': worker.get('department', ''),
                'date': date,
                'status': 'ABSENT',
                'shifts_worked': 0,
                'hours_worked': 0.0,
                'remarks': 'Auto-marked absent',
                'auto_marked': True,
                'created_by': 'system',
            }
            try:
                cls.repository.create(record_id, data)
                count += 1
            except Exception:
                continue
        return count

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'workspace_id': self.workspace_id,
            'employee_code': self.employee_code,
            'worker_id': self.worker_id,
            'worker_name': self.worker_name,
            'department': self.department,
            'date': self.date,
            'status': self.status,
            'shifts_worked': self.shifts_worked,
            'hours_worked': self.hours_worked,
            'remarks': self.remarks,
            'auto_marked': self.auto_marked,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            'updated_at': self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
            'updated_by': self.updated_by,
        }

    def __repr__(self):
        return f"<HRAttendance {self.employee_code} {self.date} {self.status}>"
