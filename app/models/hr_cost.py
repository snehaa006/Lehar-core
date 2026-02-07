"""
HR Cost Model - Firestore Version
Daily cost calculation records per workspace.
Data structure placeholder - actual cost calculation service will be added later.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

from app.database.base_repository import BaseRepository
from google.cloud.firestore_v1 import FieldFilter


class HRCostRepository(BaseRepository):
    """Repository for HR Cost records"""

    def __init__(self):
        super().__init__('hr_cost')

    def get_by_date(self, workspace_id: str, date: str) -> Optional[Dict[str, Any]]:
        """Get cost record for a workspace on a specific date"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
        ).where(
            filter=FieldFilter("date", "==", date)
        ).limit(1)

        docs = list(query.stream())
        if docs:
            data = docs[0].to_dict()
            data['id'] = docs[0].id
            return data
        return None

    def get_by_range(self, workspace_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get cost records for a date range"""
        query = self.collection.where(
            filter=FieldFilter("workspace_id", "==", workspace_id)
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


class HRCost:
    """
    HR Cost model - daily cost calculation record.

    Expected data structure (populated by external cost service):
    {
        workspace_id: str,
        date: "YYYY-MM-DD",
        summary: {
            total_company_cost: float,
            total_attendance_hours: float,
        },
        calculation_metadata: {
            total_workers: int,
            present_workers: int,
            calculated_at: str,
        },
        workers: [
            {
                employee_code: str,
                worker_id: str,
                worker_name: str,
                department: str,
                designation: str,
                salary_info: { hourly_rate: float, ... },
                attendance_info: { status: str, hours_worked: float, shifts_worked: int },
                todays_salary: float,
            }
        ]
    }
    """

    repository = HRCostRepository()

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get('id')
        self.workspace_id = data.get('workspace_id')
        self.date = data.get('date')
        self.summary = data.get('summary', {})
        self.calculation_metadata = data.get('calculation_metadata', {})
        self.workers = data.get('workers', [])
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')

    @classmethod
    def get_by_date(cls, workspace_id: str, date: str) -> Optional['HRCost']:
        data = cls.repository.get_by_date(workspace_id, date)
        return cls(data) if data else None

    @classmethod
    def get_by_range(cls, workspace_id: str, start_date: str, end_date: str) -> List['HRCost']:
        data_list = cls.repository.get_by_range(workspace_id, start_date, end_date)
        return [cls(data) for data in data_list]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'workspace_id': self.workspace_id,
            'date': self.date,
            'summary': self.summary,
            'calculation_metadata': self.calculation_metadata,
            'workers': self.workers,
        }

    def __repr__(self):
        return f"<HRCost ws={self.workspace_id} date={self.date}>"
