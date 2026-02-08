"""
HR Cost Model - Firestore Version
Daily cost calculation records stored as a subcollection under each workspace.
Path: workspaces/{workspace_id}/hr_cost/{date}

Stores per-worker cost breakdown with dynamic hierarchy_values snapshot,
configurable salary component breakdown, and attendance info.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

from app.database.firestore_client import db


class HRCostRepository:
    """Repository for HR Cost records - uses workspace subcollection"""

    def _collection(self, workspace_id: str):
        """Get the hr_cost subcollection for a workspace"""
        return db.collection('workspaces').document(workspace_id).collection('hr_cost')

    def get_by_date(self, workspace_id: str, date: str) -> Optional[Dict[str, Any]]:
        """Get cost record for a workspace on a specific date (doc ID = date)"""
        doc_ref = self._collection(workspace_id).document(date)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            data['id'] = doc.id
            return data
        return None

    def get_by_range(self, workspace_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get cost records for a date range"""
        query = self._collection(workspace_id) \
            .where('date', '>=', start_date) \
            .where('date', '<=', end_date)

        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)
        return results

    def save(self, workspace_id: str, date: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or overwrite cost record for a date (upsert)"""
        data['updated_at'] = datetime.utcnow()
        if 'created_at' not in data:
            data['created_at'] = datetime.utcnow()

        doc_ref = self._collection(workspace_id).document(date)
        doc_ref.set(data)

        result = data.copy()
        result['id'] = date
        return result

    def delete(self, workspace_id: str, date: str) -> bool:
        """Delete cost record for a date"""
        doc_ref = self._collection(workspace_id).document(date)
        doc_ref.delete()
        return True


class HRCost:
    """
    HR Cost model - daily cost calculation record.
    Stored at: workspaces/{workspace_id}/hr_cost/{date}

    Data structure:
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
            absent_workers: int,
            calculated_at: str,
            cost_base_hours_per_day: float,
            cost_base_days_per_month: int,
        },
        workers: [
            {
                employee_code: str,
                worker_id: str,
                worker_name: str,
                hierarchy_values: {"designation": "...", "department": "...", ...},
                salary_info: {
                    components: {"component_1": 15000, ...},
                    total_salary: float,
                    hourly_rate: float,
                },
                attendance_info: {
                    status: str,
                    hours_worked: float,
                    shifts_worked: int,
                },
                todays_cost: float,
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

    @classmethod
    def save_daily_cost(cls, workspace_id: str, date: str,
                        data: Dict[str, Any]) -> 'HRCost':
        """Save (upsert) a daily cost record"""
        data['workspace_id'] = workspace_id
        data['date'] = date
        saved = cls.repository.save(workspace_id, date, data)
        return cls(saved)

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
