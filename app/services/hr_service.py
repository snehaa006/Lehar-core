"""
HR Service - Business logic for the HR Portal
All operations are workspace-scoped.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from flask import current_app

from app.models.hr_department import HRDepartment
from app.models.hr_manpower_type import HRManpowerType
from app.models.hr_worker import HRWorker
from app.models.hr_attendance import HRAttendance
from app.models.hr_settings import HRSettings, DEFAULT_SHIFT_HOURS
from app.models.hr_cost import HRCost
from app.models.workspace_membership import WorkspaceMembership
from app.models.user import User


class HRService:
    """Handles all HR portal business logic, workspace-scoped"""

    # ==================== DEPARTMENT ====================

    @staticmethod
    def get_departments(workspace_id: str) -> List[Dict[str, Any]]:
        depts = HRDepartment.get_by_workspace(workspace_id)
        return [d.to_dict() for d in depts]

    @staticmethod
    def create_department(workspace_id: str, name: str, created_by: str,
                          head: str = '', description: str = '') -> Tuple[Optional[Dict], Optional[str]]:
        if not name.strip():
            return None, "Department name is required"

        existing = HRDepartment.find_by_name(workspace_id, name.strip())
        if existing:
            return None, "Department with this name already exists"

        dept = HRDepartment.create(
            workspace_id=workspace_id,
            name=name.strip(),
            created_by=created_by,
            head=head.strip(),
            description=description.strip(),
        )
        return dept.to_dict(), None

    @staticmethod
    def update_department(dept_id: str, workspace_id: str, name: str,
                          updated_by: str, head: str = '', description: str = '') -> Tuple[bool, Optional[str]]:
        dept = HRDepartment.get_by_id(dept_id)
        if not dept or dept.workspace_id != workspace_id:
            return False, "Department not found"
        if not name.strip():
            return False, "Department name is required"

        # Check duplicate (skip self)
        existing = HRDepartment.find_by_name(workspace_id, name.strip())
        if existing and existing.id != dept_id:
            return False, "Department with this name already exists"

        dept.name = name.strip()
        dept.head = head.strip()
        dept.description = description.strip()
        dept.save()
        return True, None

    @staticmethod
    def archive_department(dept_id: str, workspace_id: str, archived_by: str) -> Tuple[bool, Optional[str]]:
        dept = HRDepartment.get_by_id(dept_id)
        if not dept or dept.workspace_id != workspace_id:
            return False, "Department not found"
        dept.archive(archived_by)
        return True, None

    # ==================== MANPOWER TYPES ====================

    @staticmethod
    def get_manpower_types(workspace_id: str) -> List[Dict[str, Any]]:
        types = HRManpowerType.get_by_workspace(workspace_id)
        return [t.to_dict() for t in types]

    @staticmethod
    def create_manpower_type(workspace_id: str, name: str, created_by: str) -> Tuple[Optional[Dict], Optional[str]]:
        if not name.strip():
            return None, "Manpower type name is required"

        existing = HRManpowerType.find_by_name(workspace_id, name.strip())
        if existing:
            return None, "Manpower type with this name already exists"

        mt = HRManpowerType.create(workspace_id, name.strip(), created_by)
        return mt.to_dict(), None

    @staticmethod
    def archive_manpower_type(type_id: str, workspace_id: str, archived_by: str) -> Tuple[bool, Optional[str]]:
        mt = HRManpowerType.get_by_id(type_id)
        if not mt or mt.workspace_id != workspace_id:
            return False, "Manpower type not found"
        mt.archive(archived_by)
        return True, None

    # ==================== WORKERS ====================

    @staticmethod
    def get_workers(workspace_id: str) -> List[Dict[str, Any]]:
        workers = HRWorker.get_by_workspace(workspace_id)
        result = [w.to_dict() for w in workers]
        result.sort(key=lambda x: x.get('created_at', '') or '', reverse=True)
        return result

    @staticmethod
    def get_worker(workspace_id: str, worker_id: str) -> Optional[Dict[str, Any]]:
        worker = HRWorker.get_by_id(worker_id)
        if not worker or worker.workspace_id != workspace_id:
            # Try by employee code
            worker = HRWorker.find_by_employee_code(workspace_id, worker_id)
        if not worker:
            return None
        return worker.to_dict()

    @staticmethod
    def create_worker(workspace_id: str, data: Dict[str, Any], created_by: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Create a new worker with validation"""
        # Required fields
        operator_name = data.get('operator_name', '').strip()
        designation = data.get('designation', '').strip()
        department = data.get('department', '').strip()
        employee_code = data.get('employee_code', '').strip().upper()
        esi_number = data.get('esi_number', '').strip()
        date_of_joining = data.get('date_of_joining', '').strip()
        coverage = data.get('coverage', '').strip()
        mobile_number = data.get('mobile_number', '').strip()
        basic_salary = data.get('basic_salary', 0)
        hra = data.get('hra', 0)

        # Validate required
        for field_name, value in [('Operator name', operator_name), ('Designation', designation),
                                  ('Department', department), ('Employee code', employee_code),
                                  ('ESI number', esi_number), ('Date of joining', date_of_joining),
                                  ('Coverage', coverage)]:
            if not value:
                return None, f"{field_name} is required"

        # Validate mobile
        if mobile_number and (not mobile_number.isdigit() or len(mobile_number) != 10):
            return None, "Mobile number must be exactly 10 digits"

        # Validate ESI
        if not esi_number.isdigit():
            return None, "ESI number must be numeric"

        # Validate date
        try:
            datetime.strptime(date_of_joining, '%Y-%m-%d')
        except ValueError:
            return None, "Date of joining must be in YYYY-MM-DD format"

        # Validate salary
        try:
            basic_salary = float(basic_salary)
            hra = float(hra)
            if basic_salary < 0 or hra < 0:
                return None, "Salary values cannot be negative"
        except (ValueError, TypeError):
            return None, "Salary must be a valid number"

        # Check duplicate employee code
        existing = HRWorker.find_by_employee_code(workspace_id, employee_code)
        if existing:
            return None, f"Employee code '{employee_code}' already exists"

        worker = HRWorker.create(
            workspace_id=workspace_id,
            employee_code=employee_code,
            operator_name=operator_name,
            designation=designation,
            department=department,
            created_by=created_by,
            mobile_number=mobile_number,
            esi_number=esi_number,
            date_of_joining=date_of_joining,
            coverage=coverage,
            basic_salary=basic_salary,
            hra=hra,
        )
        return worker.to_dict(), None

    @staticmethod
    def update_worker(workspace_id: str, employee_code: str, data: Dict[str, Any],
                      updated_by: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Update worker basic info and optionally salary"""
        worker = HRWorker.find_by_employee_code(workspace_id, employee_code.upper())
        if not worker:
            return None, "Worker not found"

        # Validate required basic fields
        operator_name = data.get('operator_name', '').strip()
        designation = data.get('designation', '').strip()
        department = data.get('department', '').strip()
        mobile_number = data.get('mobile_number', '').strip()
        esi_number = data.get('esi_number', '').strip()
        date_of_joining = data.get('date_of_joining', '').strip()
        coverage = data.get('coverage', '').strip()

        for field_name, value in [('Operator name', operator_name), ('Designation', designation),
                                  ('Department', department), ('ESI number', esi_number),
                                  ('Date of joining', date_of_joining), ('Coverage', coverage)]:
            if not value:
                return None, f"{field_name} is required"

        if mobile_number and (not mobile_number.isdigit() or len(mobile_number) != 10):
            return None, "Mobile number must be exactly 10 digits"
        if not esi_number.isdigit():
            return None, "ESI number must be numeric"
        try:
            datetime.strptime(date_of_joining, '%Y-%m-%d')
        except ValueError:
            return None, "Date of joining must be in YYYY-MM-DD format"

        # Update basic info
        worker.operator_name = operator_name
        worker.designation = designation
        worker.department = department
        worker.mobile_number = mobile_number
        worker.esi_number = esi_number
        worker.date_of_joining = date_of_joining
        worker.coverage = coverage
        worker.updated_by = updated_by

        # Handle salary/bonus updates
        new_basic = data.get('basic_salary')
        new_hra = data.get('hra')
        bonus_amount = data.get('bonus')
        effective_date = data.get('effective_date', '').strip() or datetime.utcnow().strftime('%Y-%m-%d')
        change_reason = data.get('change_reason', '').strip()
        remarks = data.get('remarks', '').strip()

        salary_updated = False

        if new_basic is not None or new_hra is not None or bonus_amount is not None:
            current = worker.get_current_remuneration()
            current_basic = current.get('basic_salary', 0)
            current_hra = current.get('hra', 0)

            if effective_date:
                try:
                    datetime.strptime(effective_date, '%Y-%m-%d')
                except ValueError:
                    return None, "effective_date must be YYYY-MM-DD"

            if (new_basic is not None or new_hra is not None) and bonus_amount is not None:
                return None, "Cannot update salary and give bonus in the same transaction"

            if new_basic is not None or new_hra is not None:
                final_basic = current_basic
                final_hra = current_hra
                if new_basic is not None:
                    try:
                        final_basic = float(new_basic)
                        if final_basic < 0:
                            return None, "Basic salary cannot be negative"
                    except (ValueError, TypeError):
                        return None, "Basic salary must be a valid number"
                if new_hra is not None:
                    try:
                        final_hra = float(new_hra)
                        if final_hra < 0:
                            return None, "HRA cannot be negative"
                    except (ValueError, TypeError):
                        return None, "HRA must be a valid number"

                if final_basic == current_basic and final_hra == current_hra:
                    return None, "New salary is same as current salary. No change made."

                record = {
                    'basic_salary': final_basic,
                    'hra': final_hra,
                    'bonus': 0,
                    'effective_date': effective_date,
                    'created_at': datetime.utcnow().isoformat(),
                    'created_by': updated_by,
                    'remarks': remarks or f"Basic: {current_basic} -> {final_basic}, HRA: {current_hra} -> {final_hra}",
                    'is_active': True,
                    'change_reason': change_reason or 'Salary update',
                    'change_type': 'salary_increase',
                }
                worker.add_salary_record(record)
                salary_updated = True

            elif bonus_amount is not None:
                try:
                    bonus_amount = float(bonus_amount)
                    if bonus_amount <= 0:
                        return None, "Bonus must be greater than 0"
                except (ValueError, TypeError):
                    return None, "Bonus must be a valid number"

                record = {
                    'basic_salary': current_basic,
                    'hra': current_hra,
                    'bonus': bonus_amount,
                    'effective_date': effective_date,
                    'created_at': datetime.utcnow().isoformat(),
                    'created_by': updated_by,
                    'remarks': remarks or f"Bonus of {bonus_amount}",
                    'is_active': True,
                    'change_reason': change_reason or 'Bonus payment',
                    'change_type': 'bonus',
                }
                worker.add_salary_record(record)
                salary_updated = True

        if not salary_updated:
            worker.save()

        return worker.to_dict(), None

    @staticmethod
    def delete_worker(workspace_id: str, worker_id: str, deleted_by: str) -> Tuple[bool, Optional[str]]:
        """Soft delete a worker"""
        worker = HRWorker.get_by_id(worker_id)
        if not worker or worker.workspace_id != workspace_id:
            worker = HRWorker.find_by_employee_code(workspace_id, worker_id)
        if not worker:
            return False, "Worker not found"
        worker.soft_delete(deleted_by)
        return True, None

    @staticmethod
    def get_remuneration_history(workspace_id: str, employee_code: str) -> Optional[Dict[str, Any]]:
        worker = HRWorker.find_by_employee_code(workspace_id, employee_code.upper())
        if not worker:
            return None
        history = worker.remuneration.get('history', [])
        return {
            'employee_code': worker.employee_code,
            'operator_name': worker.operator_name,
            'total_versions': len(history),
            'history': history,
        }

    @staticmethod
    def bulk_upload_workers(workspace_id: str, workers_data: List[Dict], created_by: str) -> Dict[str, Any]:
        """Bulk upload workers with validation against workspace departments/designations"""
        results = {'success': 0, 'failed': 0, 'errors': []}

        # Load valid departments and designations
        depts = HRDepartment.get_by_workspace(workspace_id)
        valid_depts = {d.name.lower(): d.name for d in depts}

        types = HRManpowerType.get_by_workspace(workspace_id)
        valid_desig = {t.name.lower(): t.name for t in types}

        # Get existing codes
        existing_workers = HRWorker.get_by_workspace(workspace_id, active_only=False)
        existing_codes = {w.employee_code for w in existing_workers}

        for wd in workers_data:
            try:
                emp_code = wd.get('employee_code', '').strip().upper()
                operator_name = wd.get('operator_name', '').strip()
                esi_number = wd.get('esi_number', '').strip()
                doj = wd.get('date_of_joining', '').strip()
                coverage = wd.get('coverage', '').strip()
                designation_input = wd.get('designation', '').strip()
                department_input = wd.get('department', '').strip()
                mobile = wd.get('mobile_number', '').strip() if wd.get('mobile_number') else ''
                basic_salary = wd.get('basic_salary', 0)
                hra = wd.get('hra', 0)

                if not all([emp_code, operator_name, esi_number, doj, coverage, designation_input, department_input]):
                    results['failed'] += 1
                    results['errors'].append({'employee_code': emp_code or 'UNKNOWN', 'error': 'Missing required fields'})
                    continue

                if emp_code in existing_codes:
                    results['failed'] += 1
                    results['errors'].append({'employee_code': emp_code, 'error': 'Employee code already exists'})
                    continue

                if mobile and (not mobile.isdigit() or len(mobile) != 10):
                    results['failed'] += 1
                    results['errors'].append({'employee_code': emp_code, 'error': 'Invalid mobile number'})
                    continue

                if not esi_number.isdigit():
                    results['failed'] += 1
                    results['errors'].append({'employee_code': emp_code, 'error': 'Invalid ESI number'})
                    continue

                try:
                    datetime.strptime(doj, '%Y-%m-%d')
                except ValueError:
                    results['failed'] += 1
                    results['errors'].append({'employee_code': emp_code, 'error': 'Invalid date format'})
                    continue

                if designation_input.lower() not in valid_desig:
                    results['failed'] += 1
                    results['errors'].append({'employee_code': emp_code, 'error': f"Invalid designation '{designation_input}'"})
                    continue

                if department_input.lower() not in valid_depts:
                    results['failed'] += 1
                    results['errors'].append({'employee_code': emp_code, 'error': f"Invalid department '{department_input}'"})
                    continue

                try:
                    basic_salary = float(basic_salary)
                    hra = float(hra)
                    if basic_salary < 0 or hra < 0:
                        raise ValueError()
                except (ValueError, TypeError):
                    results['failed'] += 1
                    results['errors'].append({'employee_code': emp_code, 'error': 'Invalid salary values'})
                    continue

                HRWorker.create(
                    workspace_id=workspace_id,
                    employee_code=emp_code,
                    operator_name=operator_name,
                    designation=valid_desig[designation_input.lower()],
                    department=valid_depts[department_input.lower()],
                    created_by=created_by,
                    mobile_number=mobile,
                    esi_number=esi_number,
                    date_of_joining=doj,
                    coverage=coverage,
                    basic_salary=basic_salary,
                    hra=hra,
                )
                existing_codes.add(emp_code)
                results['success'] += 1

            except Exception as e:
                results['failed'] += 1
                results['errors'].append({'employee_code': wd.get('employee_code', 'UNKNOWN'), 'error': str(e)})

        return results

    # ==================== ATTENDANCE ====================

    @staticmethod
    def auto_mark_absent(workspace_id: str, date: str) -> int:
        """Auto-mark all active workers without attendance as ABSENT"""
        workers = HRWorker.get_by_workspace(workspace_id)
        existing_records = HRAttendance.get_by_date(workspace_id, date)
        existing_codes = {r.employee_code for r in existing_records}

        worker_dicts = [w.to_dict() for w in workers]
        return HRAttendance.bulk_create_absent(workspace_id, worker_dicts, date, existing_codes)

    @staticmethod
    def get_attendance_by_date(workspace_id: str, date: str) -> List[Dict[str, Any]]:
        """Get all attendance for a date, auto-marking absent first"""
        HRService.auto_mark_absent(workspace_id, date)
        records = HRAttendance.get_by_date(workspace_id, date)
        return [r.to_dict() for r in records]

    @staticmethod
    def mark_attendance(workspace_id: str, data: Dict[str, Any],
                        user_email: str) -> Tuple[Optional[Dict], Optional[str], Dict[str, Any]]:
        """
        Mark/update attendance for a worker.
        Returns (attendance_dict, error, metadata)
        metadata includes: is_update, is_frozen, should_send_email, email_reason, days_ago
        """
        employee_code = data.get('employee_code', '').strip().upper()
        date = data.get('date', '').strip()
        status = data.get('status', '').upper()
        shifts_worked = data.get('shifts_worked', 1)
        hours_worked = data.get('hours_worked', 10.0)
        remarks = data.get('remarks', '').strip()

        metadata = {'is_update': False, 'is_frozen': False, 'should_send_email': False,
                     'email_reason': '', 'days_ago': 0, 'email_sent': False}

        if not employee_code:
            return None, "employee_code is required", metadata

        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return None, "date must be in YYYY-MM-DD format", metadata

        today = datetime.utcnow().date()
        if date_obj.date() > today:
            return None, "Cannot mark attendance for future dates", metadata

        if status not in ('PRESENT', 'ABSENT'):
            return None, "status must be PRESENT or ABSENT", metadata

        # Find worker
        worker = HRWorker.find_by_employee_code(workspace_id, employee_code)
        if not worker:
            return None, f"Worker with employee code '{employee_code}' does not exist", metadata
        if not worker.is_active:
            return None, "Worker is not active", metadata

        # Get settings for unfrozen period
        settings = HRSettings.get_or_create(workspace_id)
        unfrozen_days = settings.unfrozen_days

        # Adjust status data
        if status == 'ABSENT':
            shifts_worked = 0
            hours_worked = 0.0
        else:
            if shifts_worked < 1:
                shifts_worked = 1
            if hours_worked < 1:
                return None, "Hours worked must be at least 1", metadata

        attendance_data = {
            'status': status,
            'shifts_worked': shifts_worked,
            'hours_worked': float(hours_worked),
            'remarks': remarks,
        }

        attendance, is_update, existing_data = HRAttendance.create_or_update(
            workspace_id=workspace_id,
            employee_code=employee_code,
            date=date,
            worker_data=worker.to_dict(),
            attendance_data=attendance_data,
            user_email=user_email,
        )

        # Determine frozen/unfrozen and email logic
        days_ago = (today - date_obj.date()).days
        is_today = date_obj.date() == today
        is_within_unfrozen = 0 <= days_ago < unfrozen_days
        is_frozen = not is_today and not is_within_unfrozen

        should_send_email = False
        email_reason = ""

        if is_today:
            email_reason = "Today's date - no email"
        elif is_within_unfrozen:
            email_reason = f"Within unfrozen period ({days_ago} days ago)"
        elif is_frozen:
            if not is_update:
                should_send_email = True
                email_reason = "New entry on frozen date"
            else:
                # Check if data actually changed
                if existing_data:
                    changes = []
                    if existing_data.get('status') != status:
                        changes.append(f"status: {existing_data.get('status')} -> {status}")
                    if existing_data.get('shifts_worked') != shifts_worked:
                        changes.append("shifts changed")
                    if existing_data.get('hours_worked') != hours_worked:
                        changes.append("hours changed")
                    if (existing_data.get('remarks', '') or '').strip() != remarks:
                        changes.append("remarks changed")
                    if changes:
                        should_send_email = True
                        email_reason = f"Frozen date changes: {', '.join(changes)}"
                    else:
                        email_reason = "No changes on frozen date"

        metadata.update({
            'is_update': is_update,
            'is_frozen': is_frozen,
            'should_send_email': should_send_email,
            'email_reason': email_reason,
            'days_ago': days_ago,
        })

        return attendance.to_dict(), None, metadata

    @staticmethod
    def get_daily_summary(workspace_id: str, date: str) -> Dict[str, Any]:
        """Calculate daily attendance summary by department"""
        workers = HRWorker.get_by_workspace(workspace_id)
        records = HRAttendance.get_by_date(workspace_id, date)
        attendance_map = {r.employee_code: r for r in records}

        dept_data = {}
        for worker in workers:
            dept = worker.department or 'Unknown'
            if dept not in dept_data:
                dept_data[dept] = {'total_workers': 0, 'present_count': 0,
                                   'absent_count': 0, 'total_manhours': 0.0}

            dept_data[dept]['total_workers'] += 1
            att = attendance_map.get(worker.employee_code)
            if att:
                if att.status == 'PRESENT':
                    dept_data[dept]['present_count'] += 1
                    dept_data[dept]['total_manhours'] += att.hours_worked * att.shifts_worked
                elif att.status == 'ABSENT':
                    dept_data[dept]['absent_count'] += 1

        departments = [
            {'department': dept, **data}
            for dept, data in dept_data.items()
        ]

        return {
            'date': date,
            'total_workers': len(workers),
            'total_present': sum(d['present_count'] for d in departments),
            'total_absent': sum(d['absent_count'] for d in departments),
            'total_manhours': sum(d['total_manhours'] for d in departments),
            'departments': departments,
        }

    # ==================== SETTINGS ====================

    @staticmethod
    def get_settings(workspace_id: str) -> Dict[str, Any]:
        settings = HRSettings.get_or_create(workspace_id)
        return settings.to_dict()

    @staticmethod
    def update_settings(workspace_id: str, data: Dict[str, Any],
                        updated_by: str) -> Tuple[Dict[str, Any], Optional[str]]:
        total_shifts = data.get('total_shifts_available', 2)
        default_hours = data.get('default_hours_worked', 10.0)
        unfrozen_days = data.get('unfrozen_days', 5)

        if total_shifts < 1:
            return {}, "Total shifts must be at least 1"
        if default_hours < 1 or default_hours > 12:
            return {}, "Default hours must be between 1 and 12"
        if unfrozen_days < 0 or unfrozen_days > 365:
            return {}, "Unfrozen days must be between 0 and 365"

        settings = HRSettings.get_or_create(workspace_id)
        settings.total_shifts_available = int(total_shifts)
        settings.default_shift_hours = float(default_hours)
        settings.unfrozen_days = int(unfrozen_days)
        settings.updated_by = updated_by
        settings.save()
        return settings.to_dict(), None

    # ==================== COST ANALYTICS ====================

    @staticmethod
    def get_cost_summary(workspace_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """Get company-level cost summary for a date range"""
        records = HRCost.get_by_range(workspace_id, start_date, end_date)

        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        total_days = (end - start).days + 1

        if not records:
            return {
                'start_date': start_date, 'end_date': end_date,
                'total_company_cost': 0, 'total_attendance_hours': 0,
                'average_cost_per_day': 0, 'average_hours_per_worker': 0,
                'days_processed': 0, 'days_missing': total_days, 'date_range_days': total_days,
            }

        total_cost = sum(r.summary.get('total_company_cost', 0) for r in records)
        total_hours = sum(r.summary.get('total_attendance_hours', 0) for r in records)
        days_processed = len(records)
        total_worker_days = sum(r.calculation_metadata.get('total_workers', 0) for r in records)

        return {
            'start_date': start_date, 'end_date': end_date,
            'total_company_cost': round(total_cost, 2),
            'total_attendance_hours': round(total_hours, 2),
            'average_cost_per_day': round(total_cost / days_processed, 2) if days_processed else 0,
            'average_hours_per_worker': round(total_hours / total_worker_days, 2) if total_worker_days else 0,
            'days_processed': days_processed,
            'days_missing': total_days - days_processed,
            'date_range_days': total_days,
        }

    @staticmethod
    def get_department_breakdown(workspace_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get department-wise cost breakdown for a date range"""
        records = HRCost.get_by_range(workspace_id, start_date, end_date)
        if not records:
            return []

        dept_data = {}
        total_company_cost = 0
        num_days = len(records)

        for record in records:
            total_company_cost += record.summary.get('total_company_cost', 0)
            for worker in record.workers:
                dept = worker.get('department', 'Unknown')
                if dept not in dept_data:
                    dept_data[dept] = {'total_cost': 0, 'total_hours': 0, 'unique_workers': set()}
                dept_data[dept]['total_cost'] += worker.get('todays_salary', 0)
                dept_data[dept]['total_hours'] += worker.get('attendance_info', {}).get('hours_worked', 0)
                dept_data[dept]['unique_workers'].add(worker.get('employee_code'))

        departments = []
        for dept, data in dept_data.items():
            pct = (data['total_cost'] / total_company_cost * 100) if total_company_cost else 0
            departments.append({
                'department': dept,
                'total_cost': round(data['total_cost'], 2),
                'total_hours': round(data['total_hours'], 2),
                'percentage_of_total': round(pct, 2),
                'total_workers': len(data['unique_workers']),
            })

        departments.sort(key=lambda x: x['total_cost'], reverse=True)
        return departments

    @staticmethod
    def get_daily_cost_breakdown(workspace_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get day-by-day cost breakdown"""
        records = HRCost.get_by_range(workspace_id, start_date, end_date)
        if not records:
            return []

        daily = []
        for record in records:
            workers_present = sum(
                1 for w in record.workers
                if w.get('attendance_info', {}).get('hours_worked', 0) > 0
            )
            daily.append({
                'date': record.date,
                'total_cost': round(record.summary.get('total_company_cost', 0), 2),
                'total_hours': round(record.summary.get('total_attendance_hours', 0), 2),
                'workers_present': workers_present,
                'total_workers': record.calculation_metadata.get('total_workers', 0),
            })

        daily.sort(key=lambda x: x['date'])
        return daily

    @staticmethod
    def get_worker_cost(workspace_id: str, employee_code: str,
                        start_date: str, end_date: str) -> Optional[Dict[str, Any]]:
        """Get cost details for a specific worker"""
        records = HRCost.get_by_range(workspace_id, start_date, end_date)
        if not records:
            return None

        worker_info = None
        total_cost = 0
        total_hours = 0
        days_present = 0
        days_absent = 0
        daily_breakdown = []

        for record in records:
            for worker in record.workers:
                if worker.get('employee_code') == employee_code:
                    if not worker_info:
                        worker_info = {
                            'employee_code': worker.get('employee_code'),
                            'worker_name': worker.get('worker_name'),
                            'department': worker.get('department'),
                            'designation': worker.get('designation'),
                        }
                    salary = worker.get('todays_salary', 0)
                    hours = worker.get('attendance_info', {}).get('hours_worked', 0)
                    total_cost += salary
                    total_hours += hours
                    if hours > 0:
                        days_present += 1
                    else:
                        days_absent += 1
                    daily_breakdown.append({
                        'date': record.date,
                        'status': worker.get('attendance_info', {}).get('status', 'UNKNOWN'),
                        'hours_worked': hours,
                        'todays_salary': round(salary, 2),
                    })
                    break

        if not worker_info:
            return None

        daily_breakdown.sort(key=lambda x: x['date'])
        return {
            'worker_info': worker_info,
            'start_date': start_date, 'end_date': end_date,
            'total_cost': round(total_cost, 2),
            'total_hours': round(total_hours, 2),
            'days_present': days_present, 'days_absent': days_absent,
            'daily_breakdown': daily_breakdown,
        }

    # ==================== EMAIL NOTIFICATIONS ====================

    @staticmethod
    def get_workspace_admin_emails(workspace_id: str) -> List[str]:
        """Get email addresses of all workspace admins"""
        admin_memberships = WorkspaceMembership.get_workspace_admins(workspace_id)
        emails = []
        for membership in admin_memberships:
            user = User.get_by_id(membership.user_id)
            if user and user.email:
                emails.append(user.email)
        return emails

    @staticmethod
    def send_attendance_notification(workspace_id: str, worker_name: str,
                                     employee_code: str, date: str,
                                     status: str, is_update: bool,
                                     old_data: Optional[Dict] = None,
                                     new_data: Optional[Dict] = None,
                                     user_email: str = '') -> bool:
        """Send attendance notification email to workspace admins"""
        try:
            from app.utils.email_service import send_email

            admin_emails = HRService.get_workspace_admin_emails(workspace_id)
            if not admin_emails:
                current_app.logger.warning(f"No admin emails found for workspace {workspace_id}")
                return False

            if is_update and old_data and new_data:
                subject = f"HR Portal: Attendance Updated - {worker_name} ({date})"
                changes = []
                if old_data.get('status') != new_data.get('status'):
                    changes.append(f"Status: {old_data.get('status')} -> {new_data.get('status')}")
                if old_data.get('shifts_worked') != new_data.get('shifts_worked'):
                    changes.append(f"Shifts: {old_data.get('shifts_worked')} -> {new_data.get('shifts_worked')}")
                if old_data.get('hours_worked') != new_data.get('hours_worked'):
                    changes.append(f"Hours: {old_data.get('hours_worked')} -> {new_data.get('hours_worked')}")
                changes_html = "<br>".join([f"- {c}" for c in changes]) if changes else "No field changes"
                html_body = f"""
                <h2>Attendance Update Notification</h2>
                <p>Attendance updated for <b>{worker_name}</b> ({employee_code}) on <b>{date}</b>.</p>
                <p><b>Changes:</b><br>{changes_html}</p>
                <p>Updated by: {user_email}</p>
                """
            else:
                subject = f"HR Portal: Backdated Attendance - {worker_name} ({date})"
                html_body = f"""
                <h2>Backdated Attendance Entry</h2>
                <p>A backdated attendance entry was created:</p>
                <ul>
                    <li><b>Worker:</b> {worker_name} ({employee_code})</li>
                    <li><b>Date:</b> {date}</li>
                    <li><b>Status:</b> {status}</li>
                    <li><b>Marked by:</b> {user_email}</li>
                </ul>
                """

            for email in admin_emails:
                send_email(email, subject, html_body)

            return True
        except Exception as e:
            current_app.logger.error(f"Failed to send attendance notification: {e}")
            return False

    # ==================== DASHBOARD STATS ====================

    @staticmethod
    def get_dashboard_stats(workspace_id: str) -> Dict[str, Any]:
        """Get statistics for the HR dashboard"""
        depts = HRDepartment.get_by_workspace(workspace_id)
        types = HRManpowerType.get_by_workspace(workspace_id)
        workers = HRWorker.get_by_workspace(workspace_id)
        settings = HRSettings.get_or_create(workspace_id)

        return {
            'total_departments': len(depts),
            'active_departments': len([d for d in depts if d.is_active]),
            'manpower_types': len(types),
            'total_workers': len(workers),
            'shift_hours': settings.default_shift_hours,
        }
