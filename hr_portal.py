"""
HR Portal Blueprint - hr_portal.py (FINAL VERSION - MAIN BUCKET ONLY)

Manages workforce allocation, department management, attendance tracking, and worker management.
Accessible to HR admin and admins.
ALL DATA STORED IN MAIN BUCKET.

UPDATES:
1. No emails sent for current day attendance edits
2. Emails sent for ANY backdated entry (past dates)
3. Auto-mark workers as ABSENT for past dates when page loads
4. Cannot edit future dates
5. Single bucket architecture - all data in main bucket
"""
import os
import requests
import json
from datetime import datetime, timedelta
from uuid import uuid4, UUID
# Change this at the top of hr_portal.py
from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for, current_app
from functools import wraps

from utils import get_gcs_bucket, read_from_gcs, write_to_gcs
from config import ( # Make sure HR_WORKERS_FILE_NAME is imported
    DEPARTMENTS_FILE, MANPOWER_TYPES_FILE, HR_SETTINGS_FILE,
    HR_ATTENDANCE_FOLDER, DEFAULT_MANPOWER_TYPES, DEFAULT_SHIFT_HOURS,
    IST, EMAIL_APPROVERS, USERS_FILE
)
from decorators import service_access_required

hr_portal_bp = Blueprint('hr_portal', __name__,
                         template_folder='templates/hr_portal',
                         url_prefix='/hr')


# Worker management configuration - NOW IN MAIN BUCKET
from config import HR_WORKERS_FILE_NAME
WORKERS_FOLDER = "hr_workers/"
ATTENDANCE_FOLDER = "hr_attendance_v1/"  # New attendance system
ATTENDANCE_SUMMARIES_FOLDER = "hr_attendance_summaries/"


def _get_all_active_workers(bucket):
    """Helper function to get all active workers from the single source file."""
    try:
        workers_data = read_from_gcs(bucket, HR_WORKERS_FILE_NAME)
        if not workers_data or not isinstance(workers_data, list):
            current_app.logger.warning("hr_workers.json is not a valid list or is empty.")
            return []
        
        # The file is a direct list of workers
        active_workers = [w for w in workers_data if w.get('is_active', True)]
        return active_workers
    except Exception as e:
        current_app.logger.error(f"Failed to get all active workers: {e}")
        return []

# Add this configuration at the top of hr_portal.py (after other constants)
HR_COST_FOLDER = "hr_cost/"  # Frozen daily cost calculations
HR_COST_SERVICE_URL = os.getenv('HR_COST_SERVICE_URL', 'https://hr-cost-calculator-943483190840.asia-south1.run.app')
# ==================== AUTO-ABSENT HELPER ====================

def auto_mark_absent_for_date(date_str):
    """
    Automatically mark all workers without attendance as ABSENT for a given date.
    This ensures that every worker has an attendance record in the database.
    Only runs for past dates (not today or future).
    """
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        today = datetime.now(IST).date()
        
        # Only auto-mark for past dates
        if date_obj.date() >= today:
            print(f"[AUTO-ABSENT] Skipping {date_str} - not a past date")
            return 0
        
        bucket = get_gcs_bucket()
        if not bucket:
            print(f"[AUTO-ABSENT] Could not connect to storage")
            return 0
        
        # Get all active workers
        all_workers = _get_all_active_workers(bucket)
        
        # Check which workers already have attendance
        marked_worker_ids = set()
        prefix = f"{ATTENDANCE_FOLDER}{date_str}/"
        try:
            blobs = bucket.list_blobs(prefix=prefix)
            for blob in blobs:
                if blob.name == prefix or not blob.name.endswith('.json'):
                    continue
                # Extract worker_id from filename
                worker_id = blob.name.split('/')[-1].replace('.json', '')
                marked_worker_ids.add(worker_id)
        except Exception as e:
            print(f"[AUTO-ABSENT] Error listing attendance: {e}")
        
        # Auto-mark unmarked workers as ABSENT
        auto_marked_count = 0
        for worker in all_workers: # This now uses the corrected list
            worker_id = worker['unique_worker_id']
            if worker_id not in marked_worker_ids:
                absent_record = {
                    'worker_id': worker_id,
                    'date': date_str,
                    'status': 'ABSENT',
                    'shifts_worked': 0,
                    'hours_worked': 0.0,
                    'remarks': 'Auto-marked absent for past date',
                    'created_at': datetime.now(IST).isoformat(),
                    'updated_at': datetime.now(IST).isoformat(),
                    'auto_marked': True  # FLAG: This is auto-marked
                }
                
                attendance_path = f"{ATTENDANCE_FOLDER}{date_str}/{worker_id}.json"
                try:
                    if write_to_gcs(bucket, attendance_path, absent_record):
                        auto_marked_count += 1
                        print(f"[AUTO-ABSENT] Marked {worker['operator_name']} as ABSENT for {date_str}")
                except Exception as e:
                    print(f"[AUTO-ABSENT] Failed to mark worker {worker_id}: {e}")
        
        if auto_marked_count > 0:
            print(f"[AUTO-ABSENT] Successfully auto-marked {auto_marked_count} workers as ABSENT for {date_str}")
        
        return auto_marked_count
        
    except Exception as e:
        print(f"[AUTO-ABSENT] Error in auto_mark_absent_for_date: {e}")
        return 0



# ==================== INITIALIZATION ====================

def initialize_hr_data():
    """Initialize HR Portal data files if they don't exist"""
    bucket = get_gcs_bucket()
    if not bucket:
        return False

    # Initialize manpower types
    manpower_types = read_from_gcs(bucket, MANPOWER_TYPES_FILE)
    if not manpower_types:
        manpower_types = {
            'types': [
                {
                    'id': f'type_{i}',
                    'name': name,
                    'created_at': datetime.now(IST).isoformat(),
                    'is_active': True
                }
                for i, name in enumerate(DEFAULT_MANPOWER_TYPES, 1)
            ]
        }
        write_to_gcs(bucket, MANPOWER_TYPES_FILE, manpower_types)

    # Initialize departments
    departments = read_from_gcs(bucket, DEPARTMENTS_FILE)
    if not departments:
        departments = {'departments': []}
        write_to_gcs(bucket, DEPARTMENTS_FILE, departments)

    # Initialize settings - UPDATED WITH UNFROZEN_DAYS
    settings = read_from_gcs(bucket, HR_SETTINGS_FILE)
    if not settings:
        settings = {
            'default_shift_hours': DEFAULT_SHIFT_HOURS,
            'total_shifts_available': 2,
            'unfrozen_days': 5,  # ✅ NEW: Default to 5 days unfrozen
            'last_updated': datetime.now(IST).isoformat()
        }
        write_to_gcs(bucket, HR_SETTINGS_FILE, settings)

    return True



# ==================== MAIN PAGES ====================

@hr_portal_bp.route('/')
@service_access_required('hr_portal')
def hr_home():
    """HR Portal dashboard"""
    initialize_hr_data()

    bucket = get_gcs_bucket()
    if not bucket:
        flash('Could not connect to storage.', 'error')
        return render_template('hr_dashboard.html', stats={})

    # Get statistics
    departments_data = read_from_gcs(bucket, DEPARTMENTS_FILE)
    manpower_data = read_from_gcs(bucket, MANPOWER_TYPES_FILE)
    settings_data = read_from_gcs(bucket, HR_SETTINGS_FILE)

    total_depts = len(departments_data.get('departments', [])) if departments_data else 0
    active_depts = len([d for d in departments_data.get('departments', []) if d.get('is_active', True)]) if departments_data else 0
    total_types = len(manpower_data.get('types', [])) if manpower_data else 0
    shift_hours = settings_data.get('default_shift_hours', DEFAULT_SHIFT_HOURS) if settings_data else DEFAULT_SHIFT_HOURS

    stats = {
        'total_departments': total_depts,
        'active_departments': active_depts,
        'manpower_types': total_types,
        'shift_hours': shift_hours
    }

    return render_template('hr_dashboard.html', stats=stats)


@hr_portal_bp.route('/departments')
@service_access_required('hr_portal')
def manage_departments():
    """Department management page"""
    return render_template('departments.html')


@hr_portal_bp.route('/manpower-types')
@service_access_required('hr_portal')
def manage_manpower_types():
    """Manpower type management page"""
    return render_template('manpower_types.html')


@hr_portal_bp.route('/attendance')
@service_access_required('hr_portal')
def daily_attendance():
    """Daily attendance and allocation page (Original system)"""
    today = datetime.now(IST).strftime('%Y-%m-%d')
    return render_template('attendance.html', selected_date=today)


@hr_portal_bp.route('/attendance-v1')
@service_access_required('hr_portal')
def daily_attendance_v1():
    """Daily attendance and allocation page (V1 API - Worker-based system)"""
    today = datetime.now(IST).strftime('%Y-%m-%d')
    return render_template('hr_attendance.html', selected_date=today)


@hr_portal_bp.route('/settings')
@service_access_required('hr_portal')
def hr_settings():
    """HR Portal settings page"""
    return render_template('hr_settings.html')


@hr_portal_bp.route('/reports')
@service_access_required('hr_portal')
def hr_reports():
    """HR Portal reports page"""
    return render_template('hr_reports.html')


@hr_portal_bp.route('/workers')
@service_access_required('hr_portal')
def manage_workers():
    """Worker management page"""
    return render_template('hr_addworker.html')


@hr_portal_bp.route('/cost-analytics')
@service_access_required('hr_portal')
def cost_analytics():
    """HR Cost Analytics page"""
    return render_template('hr_cost_analytics.html')


# ==================== DEPARTMENT API ====================

@hr_portal_bp.route('/api/departments', methods=['GET'])
@service_access_required('hr_portal')
def get_departments():
    """Get all departments"""
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        departments_data = read_from_gcs(bucket, DEPARTMENTS_FILE)
        if not departments_data:
            departments_data = {'departments': []}

        return jsonify(departments_data.get('departments', [])), 200

    except Exception as e:
        return jsonify({"error": f"Failed to load departments: {str(e)}"}), 500


@hr_portal_bp.route('/api/departments', methods=['POST'])
@service_access_required('hr_portal')
def create_department():
    """Create a new department"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        head = data.get('head', '').strip()
        description = data.get('description', '').strip()

        if not name:
            return jsonify({"error": "Department name is required"}), 400

        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        departments_data = read_from_gcs(bucket, DEPARTMENTS_FILE)
        if not departments_data:
            departments_data = {'departments': []}

        # Check for duplicate name
        if any(d['name'].lower() == name.lower() and d.get('is_active', True)
               for d in departments_data.get('departments', [])):
            return jsonify({"error": "Department with this name already exists"}), 400

        # Create new department
        dept_id = f"dept_{datetime.now(IST).strftime('%Y%m%d%H%M%S')}"
        new_dept = {
            'id': dept_id,
            'name': name,
            'head': head,
            'description': description,
            'created_at': datetime.now(IST).isoformat(),
            'created_by': session.get('user_email'),
            'is_active': True
        }

        departments_data['departments'].append(new_dept)

        if write_to_gcs(bucket, DEPARTMENTS_FILE, departments_data):
            return jsonify({"message": "Department created successfully", "department": new_dept}), 201
        else:
            return jsonify({"error": "Failed to save department"}), 500

    except Exception as e:
        return jsonify({"error": f"Failed to create department: {str(e)}"}), 500


@hr_portal_bp.route('/api/departments/<dept_id>', methods=['PUT'])
@service_access_required('hr_portal')
def update_department(dept_id):
    """Update a department"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        head = data.get('head', '').strip()
        description = data.get('description', '').strip()

        if not name:
            return jsonify({"error": "Department name is required"}), 400

        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        departments_data = read_from_gcs(bucket, DEPARTMENTS_FILE)
        if not departments_data:
            return jsonify({"error": "No departments found"}), 404

        # Find and update department
        dept_found = False
        for dept in departments_data['departments']:
            if dept['id'] == dept_id:
                dept['name'] = name
                dept['head'] = head
                dept['description'] = description
                dept['updated_at'] = datetime.now(IST).isoformat()
                dept['updated_by'] = session.get('user_email')
                dept_found = True
                break

        if not dept_found:
            return jsonify({"error": "Department not found"}), 404

        if write_to_gcs(bucket, DEPARTMENTS_FILE, departments_data):
            return jsonify({"message": "Department updated successfully"}), 200
        else:
            return jsonify({"error": "Failed to save changes"}), 500

    except Exception as e:
        return jsonify({"error": f"Failed to update department: {str(e)}"}), 500


@hr_portal_bp.route('/api/departments/<dept_id>', methods=['DELETE'])
@service_access_required('hr_portal')
def delete_department(dept_id):
    """Archive a department (soft delete)"""
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        departments_data = read_from_gcs(bucket, DEPARTMENTS_FILE)
        if not departments_data:
            return jsonify({"error": "No departments found"}), 404

        # Mark department as inactive (soft delete - keeps historical records)
        dept_found = False
        for dept in departments_data['departments']:
            if dept['id'] == dept_id:
                dept['is_active'] = False
                dept['archived_at'] = datetime.now(IST).isoformat()
                dept['archived_by'] = session.get('user_email')
                dept_found = True
                break

        if not dept_found:
            return jsonify({"error": "Department not found"}), 404

        if write_to_gcs(bucket, DEPARTMENTS_FILE, departments_data):
            return jsonify({"message": "Department archived successfully"}), 200
        else:
            return jsonify({"error": "Failed to save changes"}), 500

    except Exception as e:
        return jsonify({"error": f"Failed to delete department: {str(e)}"}), 500


# ==================== MANPOWER TYPES API ====================

@hr_portal_bp.route('/api/manpower-types', methods=['GET'])
@service_access_required('hr_portal')
def get_manpower_types():
    """Get all manpower types"""
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        manpower_data = read_from_gcs(bucket, MANPOWER_TYPES_FILE)
        if not manpower_data:
            initialize_hr_data()
            manpower_data = read_from_gcs(bucket, MANPOWER_TYPES_FILE)

        return jsonify(manpower_data.get('types', [])), 200

    except Exception as e:
        return jsonify({"error": f"Failed to load manpower types: {str(e)}"}), 500


@hr_portal_bp.route('/api/manpower-types', methods=['POST'])
@service_access_required('hr_portal')
def create_manpower_type():
    """Create a new manpower type"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()

        if not name:
            return jsonify({"error": "Manpower type name is required"}), 400

        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        manpower_data = read_from_gcs(bucket, MANPOWER_TYPES_FILE)
        if not manpower_data:
            manpower_data = {'types': []}

        # Check for duplicate
        if any(t['name'].lower() == name.lower() and t.get('is_active', True)
               for t in manpower_data.get('types', [])):
            return jsonify({"error": "Manpower type with this name already exists"}), 400

        # Create new type
        type_id = f"type_{datetime.now(IST).strftime('%Y%m%d%H%M%S')}"
        new_type = {
            'id': type_id,
            'name': name,
            'created_at': datetime.now(IST).isoformat(),
            'created_by': session.get('user_email'),
            'is_active': True
        }

        manpower_data['types'].append(new_type)

        if write_to_gcs(bucket, MANPOWER_TYPES_FILE, manpower_data):
            return jsonify({"message": "Manpower type created successfully", "type": new_type}), 201
        else:
            return jsonify({"error": "Failed to save manpower type"}), 500

    except Exception as e:
        return jsonify({"error": f"Failed to create manpower type: {str(e)}"}), 500


@hr_portal_bp.route('/api/manpower-types/<type_id>', methods=['DELETE'])
@service_access_required('hr_portal')
def delete_manpower_type(type_id):
    """Archive a manpower type (soft delete)"""
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        manpower_data = read_from_gcs(bucket, MANPOWER_TYPES_FILE)
        if not manpower_data:
            return jsonify({"error": "No manpower types found"}), 404

        # Mark type as inactive
        type_found = False
        for mtype in manpower_data['types']:
            if mtype['id'] == type_id:
                mtype['is_active'] = False
                mtype['archived_at'] = datetime.now(IST).isoformat()
                mtype['archived_by'] = session.get('user_email')
                type_found = True
                break

        if not type_found:
            return jsonify({"error": "Manpower type not found"}), 404

        if write_to_gcs(bucket, MANPOWER_TYPES_FILE, manpower_data):
            return jsonify({"message": "Manpower type archived successfully"}), 200
        else:
            return jsonify({"error": "Failed to save changes"}), 500

    except Exception as e:
        return jsonify({"error": f"Failed to delete manpower type: {str(e)}"}), 500


# ==================== WORKER MANAGEMENT API (NOW USING MAIN BUCKET) ====================

@hr_portal_bp.route('/api/workers', methods=['GET'])
@service_access_required('hr_portal')
def get_workers():
    """Get all workers from main bucket"""
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        # Read all workers from the single JSON file
        all_workers = read_from_gcs(bucket, HR_WORKERS_FILE_NAME)
        if not all_workers or not isinstance(all_workers, list):
            return jsonify([]), 200

        # The file is a list, so filter it directly
        active_workers = [w for w in all_workers if w.get('is_active', True)]

        # Sort by created_at descending
        active_workers.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return jsonify(active_workers), 200

    except Exception as e:
        return jsonify({"error": f"Failed to load workers: {str(e)}"}), 500


# ==================== UPDATED WORKER MANAGEMENT API ====================

@hr_portal_bp.route('/api/workers', methods=['POST'])
@service_access_required('hr_portal')
def add_worker():
    """Add a new worker with complete information including mobile, ESI, DOJ, coverage, basic salary and HRA"""
    try:
        data = request.get_json()
        
        # Validate required fields
        operator_name = data.get('operator_name', '').strip()
        designation = data.get('designation', '').strip()
        department = data.get('department', '').strip()
        employee_code = data.get('employee_code', '').strip().upper()
        mobile_number = data.get('mobile_number', '').strip()
        esi_number = data.get('esi_number', '').strip()
        date_of_joining = data.get('date_of_joining', '').strip()
        coverage = data.get('coverage', '').strip()
        basic_salary = data.get('basic_salary', 0)
        hra = data.get('hra', 0)
        
        # Validate all required fields
        if not operator_name:
            return jsonify({"error": "Operator name is required"}), 400
        if not designation:
            return jsonify({"error": "Designation is required"}), 400
        if not department:
            return jsonify({"error": "Department is required"}), 400
        if not employee_code:
            return jsonify({"error": "Employee code is required"}), 400
        if not mobile_number:
            return jsonify({"error": "Mobile number is required"}), 400
        if not esi_number:
            return jsonify({"error": "ESI number is required"}), 400
        if not date_of_joining:
            return jsonify({"error": "Date of joining is required"}), 400
        if not coverage:
            return jsonify({"error": "Coverage is required"}), 400
        
        # Validate mobile number (10 digits)
        if not mobile_number.isdigit() or len(mobile_number) != 10:
            return jsonify({"error": "Mobile number must be exactly 10 digits"}), 400
        
        # Validate ESI number (numeric)
        if not esi_number.isdigit():
            return jsonify({"error": "ESI number must be numeric"}), 400
        
        # Validate date of joining
        try:
            datetime.strptime(date_of_joining, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Date of joining must be in YYYY-MM-DD format"}), 400
        
        # Coverage can be any string value
        
        # Validate salaries
        try:
            basic_salary = float(basic_salary)
            if basic_salary < 0:
                return jsonify({"error": "Basic salary cannot be negative"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Basic salary must be a valid number"}), 400
        
        try:
            hra = float(hra)
            if hra < 0:
                return jsonify({"error": "HRA cannot be negative"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "HRA must be a valid number"}), 400

        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        # Read existing workers file
        all_workers = read_from_gcs(bucket, HR_WORKERS_FILE_NAME) or []

        # Check if employee code already exists
        if any(w['employee_code'] == employee_code for w in all_workers):
            return jsonify({"error": f"Employee code '{employee_code}' already exists"}), 400


        # Generate unique worker ID for internal reference
        unique_worker_id = str(uuid4())
        
        # Create INITIAL salary record - with basic and HRA, effective from date of joining
        initial_salary = {
            'version': 1,
            'basic_salary': basic_salary,
            'hra': hra,
            'effective_date': date_of_joining,  # Use date of joining, not today
            'created_at': datetime.now(IST).isoformat(),
            'created_by': session.get('user_email'),
            'remarks': 'Initial salary',
            'is_active': True,
            'change_reason': 'Initial salary'
        }

        # Build complete worker data
        worker_data = {
            "unique_worker_id": unique_worker_id,
            "employee_code": employee_code,
            "operator_name": operator_name,
            "mobile_number": mobile_number,
            "esi_number": esi_number,
            "date_of_joining": date_of_joining,
            "coverage": coverage,
            "designation": designation,
            "department": department,
            "is_active": True,
            "created_at": datetime.now(IST).isoformat(),
            "created_by": session.get('user_email'),
            "remuneration": {
                'current_version': 1,
                'history': [initial_salary]
            }
        }

        # Add new worker to the list and write back the entire file
        all_workers.append(worker_data)

        if write_to_gcs(bucket, HR_WORKERS_FILE_NAME, all_workers):
            return jsonify({
                "message": "Worker added successfully",
                "worker": worker_data
            }), 201
        else:
            return jsonify({"error": "Failed to save worker"}), 500

    except Exception as e:
        return jsonify({"error": f"Failed to add worker: {str(e)}"}), 500




@hr_portal_bp.route('/api/workers/<worker_id>', methods=['GET'])
@service_access_required('hr_portal')
def get_worker(worker_id):
    """Get a specific worker by ID from main bucket"""
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        all_workers = read_from_gcs(bucket, HR_WORKERS_FILE_NAME)
        if not all_workers or not isinstance(all_workers, list):
            return jsonify({"error": "Worker not found"}), 404

        # Find the worker by unique_worker_id or employee_code
        worker_data = next((w for w in all_workers if w.get('unique_worker_id') == worker_id or w.get('employee_code') == worker_id), None)
        if not worker_data:
            return jsonify({"error": "Worker not found"}), 404

        return jsonify(worker_data), 200

    except Exception as e:
        return jsonify({"error": f"Failed to load worker: {str(e)}"}), 500

def get_current_remuneration(worker_data):
    """Extract current remuneration from worker data - handles basic + HRA"""
    try:
        remuneration = worker_data.get('remuneration', {})
        history = remuneration.get('history', [])
        
        if not history:
            return {'basic_salary': 0, 'hra': 0, 'version': 0, 'effective_date': None}
        
        return history[-1]  # Latest record
    except Exception as e:
        print(f"Error getting current remuneration: {e}")
        return {'basic_salary': 0, 'hra': 0, 'version': 0, 'effective_date': None}

@hr_portal_bp.route('/api/workers/<employee_code>', methods=['PUT'])
@service_access_required('hr_portal')
def update_worker(employee_code):
    """
    Update a worker - can update basic info AND/OR salary components
    
    Basic info: name, designation, department, mobile, ESI, DOJ, coverage
    Salary changes:
    - basic_salary: Update basic salary component
    - hra: Update HRA component
    - Can update either one or both
    - bonus: One-time bonus (creates version, keeps current basic and HRA)
    """
    try:
        data = request.get_json()
        
        # Basic info fields
        operator_name = data.get('operator_name', '').strip()
        designation = data.get('designation', '').strip()
        department = data.get('department', '').strip()
        mobile_number = data.get('mobile_number', '').strip()  # Can be empty
        esi_number = data.get('esi_number', '').strip()
        date_of_joining = data.get('date_of_joining', '').strip()
        coverage = data.get('coverage', '').strip()
        
        # Salary fields (optional)
        new_basic_salary = data.get('basic_salary')
        new_hra = data.get('hra')
        bonus_amount = data.get('bonus')
        effective_date = data.get('effective_date', '').strip()
        change_reason = data.get('change_reason', '').strip()
        remarks = data.get('remarks', '').strip()

        # Validate required basic fields
        if not operator_name:
            return jsonify({"error": "Operator name is required"}), 400
        if not designation:
            return jsonify({"error": "Designation is required"}), 400
        if not department:
            return jsonify({"error": "Department is required"}), 400
        # mobile_number is now OPTIONAL - no validation required
        if not esi_number:
            return jsonify({"error": "ESI number is required"}), 400
        if not date_of_joining:
            return jsonify({"error": "Date of joining is required"}), 400
        if not coverage:
            return jsonify({"error": "Coverage is required"}), 400
        
        # Validate mobile number ONLY if provided
        if mobile_number:  # Only validate if not empty
            if not mobile_number.isdigit() or len(mobile_number) != 10:
                return jsonify({"error": "Mobile number must be exactly 10 digits"}), 400
        
        # Validate ESI number
        if not esi_number.isdigit():
            return jsonify({"error": "ESI number must be numeric"}), 400
        
        # Validate date of joining
        try:
            datetime.strptime(date_of_joining, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Date of joining must be in YYYY-MM-DD format"}), 400

        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        # Load all workers
        all_workers = read_from_gcs(bucket, HR_WORKERS_FILE_NAME)
        if not all_workers or not isinstance(all_workers, list):
            return jsonify({"error": "Worker not found"}), 404

        worker_index = -1
        for i, w in enumerate(all_workers):
            if w.get('employee_code') == employee_code.upper():
                worker_data = w # get a reference to the worker
                worker_index = i
                break
        if worker_index == -1:
            return jsonify({"error": "Worker not found"}), 404

        # Update basic info
        worker_data['operator_name'] = operator_name
        worker_data['designation'] = designation
        worker_data['department'] = department
        worker_data['mobile_number'] = mobile_number  # Can be empty string
        worker_data['esi_number'] = esi_number
        worker_data['date_of_joining'] = date_of_joining
        worker_data['coverage'] = coverage
        worker_data['updated_at'] = datetime.now(IST).isoformat()
        worker_data['updated_by'] = session.get('user_email')

        # Check if salary/bonus update is needed
        salary_updated = False
        
        if new_basic_salary is not None or new_hra is not None or bonus_amount is not None:
            # Get current salary info
            current_remuneration = get_current_remuneration(worker_data)
            current_basic = current_remuneration.get('basic_salary', 0)
            current_hra = current_remuneration.get('hra', 0)
            
            # Validate effective_date
            if effective_date:
                try:
                    datetime.strptime(effective_date, '%Y-%m-%d')
                except ValueError:
                    return jsonify({"error": "effective_date must be YYYY-MM-DD"}), 400
            else:
                effective_date = datetime.now(IST).strftime('%Y-%m-%d')

            # Get history
            history = worker_data['remuneration'].get('history', [])
            current_version = len(history)
            
            # Determine the type of change
            if (new_basic_salary is not None or new_hra is not None) and bonus_amount is not None:
                return jsonify({"error": "Cannot update salary and give bonus in the same transaction"}), 400
            
            if new_basic_salary is not None or new_hra is not None:
                # SALARY UPDATE - update basic and/or HRA
                final_basic = current_basic
                final_hra = current_hra
                
                if new_basic_salary is not None:
                    try:
                        new_basic_salary = float(new_basic_salary)
                        if new_basic_salary < 0:
                            return jsonify({"error": "Basic salary cannot be negative"}), 400
                        final_basic = new_basic_salary
                    except (ValueError, TypeError):
                        return jsonify({"error": "Basic salary must be a valid number"}), 400
                
                if new_hra is not None:
                    try:
                        new_hra = float(new_hra)
                        if new_hra < 0:
                            return jsonify({"error": "HRA cannot be negative"}), 400
                        final_hra = new_hra
                    except (ValueError, TypeError):
                        return jsonify({"error": "HRA must be a valid number"}), 400
                
                # Only create version if something actually changed
                if final_basic != current_basic or final_hra != current_hra:
                    change_description = []
                    if final_basic != current_basic:
                        change_description.append(f"Basic: ₹{current_basic} → ₹{final_basic}")
                    if final_hra != current_hra:
                        change_description.append(f"HRA: ₹{current_hra} → ₹{final_hra}")
                    
                    new_record = {
                        'version': current_version + 1,
                        'basic_salary': final_basic,
                        'hra': final_hra,
                        'bonus': 0,
                        'effective_date': effective_date,
                        'created_at': datetime.now(IST).isoformat(),
                        'created_by': session.get('user_email'),
                        'remarks': remarks if remarks else '; '.join(change_description),
                        'is_active': True,
                        'change_reason': change_reason if change_reason else 'Salary update',
                        'change_type': 'salary_increase'
                    }
                    history.append(new_record)
                    salary_updated = True
                else:
                    return jsonify({"error": "New salary is same as current salary. No change made."}), 400
                    
            elif bonus_amount is not None:
                # ONE-TIME BONUS - keep current basic and HRA, add bonus
                try:
                    bonus_amount = float(bonus_amount)
                    if bonus_amount <= 0:
                        return jsonify({"error": "Bonus must be greater than 0"}), 400
                except (ValueError, TypeError):
                    return jsonify({"error": "Bonus must be a valid number"}), 400
                
                new_record = {
                    'version': current_version + 1,
                    'basic_salary': current_basic,
                    'hra': current_hra,
                    'bonus': bonus_amount,
                    'effective_date': effective_date,
                    'created_at': datetime.now(IST).isoformat(),
                    'created_by': session.get('user_email'),
                    'remarks': remarks if remarks else f'Bonus of ₹{bonus_amount}',
                    'is_active': True,
                    'change_reason': change_reason if change_reason else 'Bonus payment',
                    'change_type': 'bonus'
                }
                history.append(new_record)
                salary_updated = True

            if salary_updated:
                worker_data['remuneration'] = {
                    'current_version': current_version + 1,
                    'history': history
                }

        # Update the worker in the list
        all_workers[worker_index] = worker_data

        # Save the entire workers file back
        if write_to_gcs(bucket, HR_WORKERS_FILE_NAME, all_workers):
            message = "Worker updated successfully"
            if salary_updated:
                message += " with new salary record"
            return jsonify({
                "message": message,
                "worker": all_workers[worker_index]
            }), 200
        else:
            return jsonify({"error": "Failed to update worker"}), 500

    except Exception as e:
        return jsonify({"error": f"Failed to update worker: {str(e)}"}), 500

@hr_portal_bp.route('/api/workers/<employee_code>/remuneration/history', methods=['GET'])
@service_access_required('hr_portal')
def get_remuneration_history(employee_code):
    """Get complete remuneration history for a worker"""
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        all_workers = read_from_gcs(bucket, HR_WORKERS_FILE_NAME)
        if not all_workers or not isinstance(all_workers, list):
            return jsonify({"error": "Worker not found"}), 404

        # Find the worker
        worker_data = next((w for w in all_workers if w.get('employee_code') == employee_code.upper()), None)
        if not worker_data:
            return jsonify({"error": "Worker not found"}), 404

        remuneration = worker_data.get('remuneration', {'history': []})
        history = remuneration.get('history', [])

        return jsonify({
            "employee_code": employee_code,
            "operator_name": worker_data.get('operator_name'),
            "total_versions": len(history),
            "history": history
        }), 200

    except Exception as e:
        return jsonify({"error": f"Failed to retrieve history: {str(e)}"}), 500

@hr_portal_bp.route('/api/workers/<worker_id>', methods=['DELETE'])
@service_access_required('hr_portal')
def delete_worker(worker_id):
    """Delete a worker in main bucket (soft delete)"""
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        # Load all workers
        all_workers = read_from_gcs(bucket, HR_WORKERS_FILE_NAME)
        if not all_workers or not isinstance(all_workers, list):
            return jsonify({"error": "Worker not found"}), 404

        worker_index = -1
        for i, w in enumerate(all_workers):
            if w.get('employee_code') == worker_id or w.get('unique_worker_id') == worker_id:
                worker_index = i
                break
        if worker_index == -1:
            return jsonify({"error": "Worker not found"}), 404

        # Mark as inactive (soft delete)
        all_workers[worker_index]['is_active'] = False
        all_workers[worker_index]['deleted_at'] = datetime.now(IST).isoformat()
        all_workers[worker_index]['deleted_by'] = session.get('user_email')

        # Save back to main bucket
        if write_to_gcs(bucket, HR_WORKERS_FILE_NAME, all_workers):
            return jsonify({"message": "Worker deleted successfully"}), 200
        else:
            return jsonify({"error": "Failed to delete worker"}), 500

    except Exception as e:
        return jsonify({"error": f"Failed to delete worker: {str(e)}"}), 500
# ==================== BULK WORKER UPLOAD API (UPDATED) ====================
@hr_portal_bp.route('/api/workers/bulk', methods=['POST'])
@service_access_required('hr_portal')
def bulk_upload_workers():
    """
    Bulk upload workers from validated CSV data
    Expected payload: { "workers": [list of worker objects] }
    Returns: { "success": count, "failed": count, "errors": [list] }
    
    UPDATED: Validates departments and designations against existing GCS data
    UPDATED: Mobile number is now OPTIONAL
    """
    try:
        data = request.get_json()
        workers_data = data.get('workers', [])
        
        if not workers_data or not isinstance(workers_data, list):
            return jsonify({"error": "workers array is required"}), 400
        
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500
        
        # Load valid departments and designations from GCS
        departments_data = read_from_gcs(bucket, DEPARTMENTS_FILE)
        manpower_data = read_from_gcs(bucket, MANPOWER_TYPES_FILE)
        
        if not departments_data or not manpower_data:
            return jsonify({"error": "Failed to load departments or designations"}), 500
        
        # Build valid sets (case-insensitive) and exact name maps
        valid_departments_lower = {}
        for dept in departments_data.get('departments', []):
            if dept.get('is_active', True):
                dept_name = dept['name'].strip()
                valid_departments_lower[dept_name.lower()] = dept_name
        
        valid_designations_lower = {}
        for desig in manpower_data.get('types', []):
            if desig.get('is_active', True):
                desig_name = desig['name'].strip()
                valid_designations_lower[desig_name.lower()] = desig_name
        
        # Get existing worker codes for duplicate checking
        all_workers = read_from_gcs(bucket, HR_WORKERS_FILE_NAME) or []
        existing_codes = {w['employee_code'].strip().upper() for w in all_workers}

        
        results = {
            'success': 0,
            'failed': 0,
            'errors': []
        }
        
        new_workers_to_add = []
        for worker_data in workers_data:
            try:
                # Validate required fields - STRIP ALL WHITESPACE
                employee_code = worker_data.get('employee_code', '').strip().upper()
                operator_name = worker_data.get('operator_name', '').strip()
                mobile_number = worker_data.get('mobile_number', '').strip() if worker_data.get('mobile_number') else ''
                esi_number = worker_data.get('esi_number', '').strip()
                date_of_joining = worker_data.get('date_of_joining', '').strip()
                coverage = worker_data.get('coverage', '').strip()
                designation_input = worker_data.get('designation', '').strip()
                department_input = worker_data.get('department', '').strip()
                basic_salary = worker_data.get('basic_salary')
                hra = worker_data.get('hra')
                
                # Basic validation - MOBILE NUMBER IS NOW OPTIONAL
                if not all([employee_code, operator_name, esi_number, 
                           date_of_joining, coverage, designation_input, department_input]):
                    results['failed'] += 1
                    results['errors'].append({
                        'employee_code': employee_code or 'UNKNOWN',
                        'error': 'Missing required fields'
                    })
                    continue
                
                if employee_code in existing_codes:
                    results['failed'] += 1
                    results['errors'].append({
                        'employee_code': employee_code,
                        'error': 'Employee code already exists'
                    })
                    continue
                
                # Validate mobile (OPTIONAL - only validate if provided)
                if mobile_number:  # Only validate if mobile number is provided
                    if not mobile_number.isdigit() or len(mobile_number) != 10:
                        results['failed'] += 1
                        results['errors'].append({
                            'employee_code': employee_code,
                            'error': 'Invalid mobile number (must be 10 digits)'
                        })
                        continue
                
                # Validate ESI
                if not esi_number.isdigit():
                    results['failed'] += 1
                    results['errors'].append({
                        'employee_code': employee_code,
                        'error': 'Invalid ESI number (must be numeric)'
                    })
                    continue
                
                # Validate date
                try:
                    datetime.strptime(date_of_joining, '%Y-%m-%d')
                except ValueError:
                    results['failed'] += 1
                    results['errors'].append({
                        'employee_code': employee_code,
                        'error': 'Invalid date format (must be YYYY-MM-DD)'
                    })
                    continue
                
                # Validate designation against GCS data (case-insensitive)
                designation_lower = designation_input.lower()
                if designation_lower not in valid_designations_lower:
                    results['failed'] += 1
                    results['errors'].append({
                        'employee_code': employee_code,
                        'error': f"Invalid designation '{designation_input}' (not in system)"
                    })
                    continue
                
                # Validate department against GCS data (case-insensitive)
                department_lower = department_input.lower()
                if department_lower not in valid_departments_lower:
                    results['failed'] += 1
                    results['errors'].append({
                        'employee_code': employee_code,
                        'error': f"Invalid department '{department_input}' (not in system)"
                    })
                    continue
                
                # Use exact case from system
                designation = valid_designations_lower[designation_lower]
                department = valid_departments_lower[department_lower]
                
                # Validate salary
                try:
                    basic_salary = float(basic_salary)
                    hra = float(hra)
                    if basic_salary < 0 or hra < 0:
                        raise ValueError("Negative salary")
                except (ValueError, TypeError):
                    results['failed'] += 1
                    results['errors'].append({
                        'employee_code': employee_code,
                        'error': 'Invalid salary values (must be positive numbers)'
                    })
                    continue
                
                # Generate unique worker ID
                unique_worker_id = str(uuid4())
                
                # Create initial salary record
                initial_salary = {
                    'version': 1,
                    'basic_salary': basic_salary,
                    'hra': hra,
                    'effective_date': date_of_joining,
                    'created_at': datetime.now(IST).isoformat(),
                    'created_by': session.get('user_email'),
                    'remarks': 'Initial salary (bulk upload)',
                    'is_active': True,
                    'change_reason': 'Initial salary'
                }
                
                # Build worker data - mobile_number can be empty string
                worker = {
                    "unique_worker_id": unique_worker_id,
                    "employee_code": employee_code,
                    "operator_name": operator_name,
                    "mobile_number": mobile_number,  # Can be empty string
                    "esi_number": esi_number,
                    "date_of_joining": date_of_joining,
                    "coverage": coverage,
                    "designation": designation,  # Exact case from system
                    "department": department,    # Exact case from system
                    "is_active": True,
                    "created_at": datetime.now(IST).isoformat(),
                    "created_by": session.get('user_email'),
                    "remuneration": {
                        'current_version': 1,
                        'history': [initial_salary]
                    }
                }
                
                new_workers_to_add.append(worker)
                existing_codes.add(employee_code) # Prevent duplicates within the same upload
                    
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'employee_code': worker_data.get('employee_code', 'UNKNOWN'),
                    'error': str(e)
                })

        # If there are new workers to add, append them and write the file once
        if new_workers_to_add:
            all_workers.extend(new_workers_to_add)
            if write_to_gcs(bucket, HR_WORKERS_FILE_NAME, all_workers):
                results['success'] = len(new_workers_to_add)
            else:
                results['failed'] += len(new_workers_to_add)
                results['errors'].append({
                    'employee_code': 'N/A',
                    'error': 'Failed to save the updated worker file to storage.'
                })
        
        return jsonify(results), 200
        
    except Exception as e:
        return jsonify({"error": f"Bulk upload failed: {str(e)}"}), 500
# ==================== ORIGINAL ATTENDANCE API ====================

@hr_portal_bp.route('/api/attendance/<date>', methods=['GET'])
@service_access_required('hr_portal')
def get_attendance(date):
    """Get attendance for a specific date (Original system - uses main bucket)"""
    try:
        # Validate date format
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        attendance_file = f"{HR_ATTENDANCE_FOLDER}attendance_{date.replace('-', '')}.json"
        attendance_data = read_from_gcs(bucket, attendance_file)

        if not attendance_data:
            # Return empty structure
            settings = read_from_gcs(bucket, HR_SETTINGS_FILE)
            shift_hours = settings.get('default_shift_hours', DEFAULT_SHIFT_HOURS) if settings else DEFAULT_SHIFT_HOURS

            attendance_data = {
                'date': date,
                'shift_hours': shift_hours,
                'allocations': [],
                'created_at': None,
                'updated_at': None
            }

        return jsonify(attendance_data), 200

    except Exception as e:
        return jsonify({"error": f"Failed to load attendance: {str(e)}"}), 500


@hr_portal_bp.route('/api/attendance/<date>', methods=['POST'])
@service_access_required('hr_portal')
def save_attendance(date):
    """Save attendance for a specific date (Original system - uses main bucket)"""
    try:
        # Validate date format
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

        data = request.get_json()
        allocations = data.get('allocations', [])
        shift_hours = data.get('shift_hours', DEFAULT_SHIFT_HOURS)

        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        attendance_file = f"{HR_ATTENDANCE_FOLDER}attendance_{date.replace('-', '')}.json"

        # Check if backdated entry
        today = datetime.now(IST).date()
        is_backdated = date_obj.date() < today

        # Get existing data to check if updating
        existing_data = read_from_gcs(bucket, attendance_file)
        is_update = existing_data is not None

        attendance_data = {
            'date': date,
            'shift_hours': shift_hours,
            'allocations': allocations,
            'created_at': existing_data['created_at'] if existing_data else datetime.now(IST).isoformat(),
            'created_by': existing_data.get('created_by', session.get('user_email')) if existing_data else session.get('user_email'),
            'updated_at': datetime.now(IST).isoformat(),
            'updated_by': session.get('user_email')
        }

        if write_to_gcs(bucket, attendance_file, attendance_data):
            # Send notification if backdated or updating existing entry
            if is_backdated or (is_update and date_obj.date() != today):
                send_backdated_attendance_email(date, session.get('user_email'), is_update)

            return jsonify({"message": "Attendance saved successfully"}), 200
        else:
            return jsonify({"error": "Failed to save attendance"}), 500

    except Exception as e:
        return jsonify({"error": f"Failed to save attendance: {str(e)}"}), 500

# ==================== V1 ATTENDANCE API (FIXED EMAIL + AUTO-ABSENT) ====================

# UPDATED EMAIL LOGIC FOR hr_portal.py
# Replace the create_attendance_v1() function starting around line 920

# FIXED VERSION - Replace the create_attendance_v1() function in hr_portal.py
# Starting around line 920

@hr_portal_bp.route('/api/v1/attendance', methods=['POST'])
@service_access_required('hr_portal')
def create_attendance_v1():
    """
    Create/update attendance for a specific worker
    
    EMAIL RULES (FIXED):
    - NO EMAIL: When marking/updating attendance for TODAY
    - NO EMAIL: When marking/updating attendance within UNFROZEN PERIOD
    - SEND EMAIL: For dates beyond the unfrozen period (FROZEN dates)
    """
    print("\n" + "="*80)
    print("[ATTENDANCE API] create_attendance_v1() called")
    print("="*80)
    
    try:
        data = request.get_json()
        print(f"[ATTENDANCE API] Request data: {data}")
        
        # Validate required fields
        employee_code = data.get('employee_code', '').strip().upper()
        date = data.get('date', '').strip()
        status = data.get('status', '').upper()
        shifts_worked = data.get('shifts_worked', 1)
        hours_worked = data.get('hours_worked', 10.0)
        remarks = data.get('remarks', '').strip()

        if not employee_code:
            return jsonify({"error": "employee_code is required"}), 400

        # Validate date format
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400

        # Prevent editing future dates
        today = datetime.now(IST).date()
        print(f"[ATTENDANCE API] Today: {today}, Requested date: {date_obj.date()}")
        
        if date_obj.date() > today:
            return jsonify({"error": "Cannot mark attendance for future dates"}), 400

        # Validate status
        valid_statuses = ['PRESENT', 'ABSENT']
        if status not in valid_statuses:
            return jsonify({"error": f"status must be one of: {', '.join(valid_statuses)}"}), 400

        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        # Check if worker exists
        all_workers = read_from_gcs(bucket, HR_WORKERS_FILE_NAME)
        if not all_workers or not isinstance(all_workers, list):
            return jsonify({"error": f"Worker with employee code '{employee_code}' does not exist"}), 404
        
        worker_data = next((w for w in all_workers if w.get('employee_code') == employee_code), None)
        if not worker_data:
            return jsonify({"error": f"Worker with employee code '{employee_code}' does not exist"}), 404

        
        if not worker_data.get('is_active', True):
            return jsonify({"error": "Worker is not active"}), 400

        print(f"[ATTENDANCE API] Worker found: {worker_data.get('operator_name')}")

        # Get settings for unfrozen period
        settings_data = read_from_gcs(bucket, HR_SETTINGS_FILE)
        unfrozen_days = 5  # Default
        if settings_data:
            unfrozen_days = settings_data.get('unfrozen_days', 5)
        
        print(f"[ATTENDANCE API] Unfrozen days setting: {unfrozen_days}")

        # Validate attendance data based on status
        if status == 'ABSENT':
            shifts_worked = 0
            hours_worked = 0.0
        else:
            if shifts_worked < 1:
                shifts_worked = 1
            if hours_worked < 1:
                return jsonify({"error": "Hours worked must be at least 1"}), 400

        # Check if attendance already exists
        attendance_path = f"{ATTENDANCE_FOLDER}{date}/{employee_code}.json"
        existing_data = read_from_gcs(bucket, attendance_path)
        
        print(f"[ATTENDANCE API] Existing data found: {existing_data is not None}")
        if existing_data:
            print(f"[ATTENDANCE API] Old status: {existing_data.get('status')}")
            print(f"[ATTENDANCE API] Old shifts: {existing_data.get('shifts_worked')}")
            print(f"[ATTENDANCE API] Old hours: {existing_data.get('hours_worked')}")
        
        now = datetime.now(IST).isoformat()
        is_update = existing_data is not None

        # Prepare attendance record
        if existing_data:
            attendance_record = {
                'employee_code': employee_code,
                'worker_id': worker_data['unique_worker_id'],
                'worker_name': worker_data['operator_name'],
                'department': worker_data['department'],
                'date': date,
                'status': status,
                'shifts_worked': shifts_worked,
                'hours_worked': hours_worked,
                'remarks': remarks,
                'created_at': existing_data.get('created_at', now),
                'updated_at': now,
                'updated_by': session.get('user_email'),
                'auto_marked': False
            }
        else:
            attendance_record = {
                'employee_code': employee_code,
                'worker_id': worker_data['unique_worker_id'],
                'worker_name': worker_data['operator_name'],
                'department': worker_data['department'],
                'date': date,
                'status': status,
                'shifts_worked': shifts_worked,
                'hours_worked': hours_worked,
                'remarks': remarks,
                'created_at': now,
                'updated_at': now,
                'created_by': session.get('user_email'),
                'auto_marked': False
            }

        print(f"[ATTENDANCE API] New status: {status}")
        print(f"[ATTENDANCE API] New shifts: {shifts_worked}")
        print(f"[ATTENDANCE API] New hours: {hours_worked}")

        # Save attendance record
        if not write_to_gcs(bucket, attendance_path, attendance_record):
            return jsonify({"error": "Failed to save attendance"}), 500

        print(f"[ATTENDANCE API] ✅ Attendance saved to GCS")

        # ========================================
        # EMAIL LOGIC - DETERMINE IF EMAIL NEEDED
        # ========================================
        is_today = date_obj.date() == today
        days_difference = (today - date_obj.date()).days
        is_within_unfrozen = days_difference >= 0 and days_difference < unfrozen_days
        is_frozen = not is_today and not is_within_unfrozen
        
        print(f"\n[EMAIL LOGIC] Date analysis:")
        print(f"  - Is today: {is_today}")
        print(f"  - Days ago: {days_difference}")
        print(f"  - Within unfrozen ({unfrozen_days} days): {is_within_unfrozen}")
        print(f"  - Is frozen: {is_frozen}")
        
        should_send_email = False
        email_reason = None
        
        if is_today:
            should_send_email = False
            email_reason = "Today's date - no email"
            print(f"[EMAIL LOGIC] ❌ No email - today's date")
        
        elif is_within_unfrozen:
            should_send_email = False
            email_reason = f"Within unfrozen period ({days_difference} days ago) - no email"
            print(f"[EMAIL LOGIC] ❌ No email - within unfrozen period")
        
        elif is_frozen:
            print(f"[EMAIL LOGIC] Date is FROZEN - checking for changes...")
            
            if not is_update:
                # Brand new entry for frozen date
                should_send_email = True
                email_reason = "New entry on frozen date"
                print(f"[EMAIL LOGIC] ✅ Will send email - new entry on frozen date")
            
            else:
                # Existing record is being updated on frozen date
                old_status = existing_data.get('status', '')
                new_status = status
                
                print(f"[EMAIL LOGIC] Comparing old vs new:")
                print(f"  - Old status: '{old_status}'")
                print(f"  - New status: '{new_status}'")
                
                # Check if status changed
                if old_status != new_status:
                    should_send_email = True
                    email_reason = f"Status changed on frozen date: {old_status} → {new_status}"
                    print(f"[EMAIL LOGIC] ✅ STATUS CHANGED: {old_status} → {new_status}")
                
                else:
                    # Status is same - check if other data changed
                    print(f"[EMAIL LOGIC] Status unchanged, checking other fields...")
                    
                    changes_detected = []
                    
                    if existing_data.get('shifts_worked') != shifts_worked:
                        changes_detected.append(f"shifts: {existing_data.get('shifts_worked')} → {shifts_worked}")
                    
                    if existing_data.get('hours_worked') != hours_worked:
                        changes_detected.append(f"hours: {existing_data.get('hours_worked')} → {hours_worked}")
                    
                    old_remarks = (existing_data.get('remarks') or '').strip()
                    new_remarks = (remarks or '').strip()
                    if old_remarks != new_remarks:
                        changes_detected.append(f"remarks: '{old_remarks}' → '{new_remarks}'")
                    
                    if changes_detected:
                        should_send_email = True
                        email_reason = f"Frozen date details changed: {', '.join(changes_detected)}"
                        print(f"[EMAIL LOGIC] ✅ Changes detected: {changes_detected}")
                    else:
                        should_send_email = False
                        email_reason = "No changes detected"
                        print(f"[EMAIL LOGIC] ❌ No changes detected")
        
        print(f"\n[EMAIL DECISION] Should send email: {should_send_email}")
        print(f"[EMAIL DECISION] Reason: {email_reason}")
        
        # Send email if needed
        email_sent = False
        if should_send_email:
            worker_name = worker_data.get('operator_name', 'Unknown')
            user_email = session.get('user_email', 'Unknown')
            
            print(f"\n{'='*80}")
            print(f"[EMAIL] ATTEMPTING TO SEND EMAIL")
            print(f"{'='*80}")
            print(f"[EMAIL] Worker: {worker_name} ({employee_code})")
            print(f"[EMAIL] Date: {date}")
            print(f"[EMAIL] Status: {status}")
            print(f"[EMAIL] Is Update: {is_update}")
            print(f"[EMAIL] Reason: {email_reason}")
            
            try:
                if is_update:
                    print(f"[EMAIL] Sending UPDATE email...")
                    email_sent = send_attendance_update_email(
                        worker_name=worker_name,
                        employee_code=employee_code,
                        date=date,
                        old_data=existing_data,
                        new_data=attendance_record,
                        timestamp=now
                    )
                else:
                    print(f"[EMAIL] Sending NEW ENTRY email...")
                    email_sent = send_backdated_new_entry_email(
                        worker_name=worker_name,
                        employee_code=employee_code,
                        date=date,
                        status=status,
                        user_email=user_email
                    )
                
                if email_sent:
                    print(f"[EMAIL] ✅✅✅ EMAIL SENT SUCCESSFULLY ✅✅✅")
                else:
                    print(f"[EMAIL] ❌❌❌ EMAIL FAILED ❌❌❌")
                    
            except Exception as e:
                print(f"[EMAIL] ❌❌❌ EMAIL EXCEPTION: {e} ❌❌❌")
                import traceback
                traceback.print_exc()
                email_sent = False
        
        # Build response message
        if is_frozen and should_send_email:
            if email_sent:
                message = f"Frozen date attendance updated - notification sent to admins ({email_reason})"
            else:
                message = f"Frozen date attendance updated - notification failed to send ({email_reason})"
        elif is_frozen:
            message = f"Frozen date attendance updated - no changes detected"
        elif is_within_unfrozen:
            message = f"Attendance marked successfully (within {unfrozen_days}-day editable period)"
        else:
            message = "Attendance marked successfully"

        print(f"\n[ATTENDANCE API] Response message: {message}")
        print(f"[ATTENDANCE API] Email sent: {email_sent}")
        print("="*80 + "\n")

        return jsonify({
            "message": message,
            "attendance": attendance_record,
            "email_sent": email_sent,
            "is_frozen": is_frozen,
            "days_ago": days_difference,
            "should_send_email": should_send_email,
            "email_reason": email_reason
        }), 201 if not is_update else 200

    except Exception as e:
        print(f"[ATTENDANCE API] ❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to create attendance: {str(e)}"}), 500
    
@hr_portal_bp.route('/test-email-direct')
@service_access_required('hr_portal')
def test_email_direct():
    """Test email functionality with admin detection"""
    try:
        result = send_backdated_new_entry_email(
            worker_name="Test Worker",
            employee_code="TEST001",
            date="2026-01-15",
            status="PRESENT",
            user_email=session.get('user_email')
        )
        
        if result:
            return jsonify({
                "success": True,
                "message": "✅ Email sent successfully! Check admin inboxes."
            })
        else:
            return jsonify({
                "success": False,
                "message": "❌ Email failed. Check server logs for details."
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"❌ Error: {str(e)}"
        }), 500 
@hr_portal_bp.route('/api/v1/attendance/<employee_code>/<date>', methods=['GET'])
@service_access_required('hr_portal')
def get_attendance_v1(employee_code, date):
    """Get attendance for a specific worker on a specific date"""
    try:
        employee_code = employee_code.strip().upper()

        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400

        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        attendance_path = f"{ATTENDANCE_FOLDER}{date}/{employee_code}.json"
        attendance_data = read_from_gcs(bucket, attendance_path)

        if not attendance_data:
            return jsonify({"error": f"Attendance not found for worker {employee_code} on {date}"}), 404

        return jsonify(attendance_data), 200

    except Exception as e:
        return jsonify({"error": f"Failed to retrieve attendance: {str(e)}"}), 500


@hr_portal_bp.route('/api/v1/attendance/date/<date>', methods=['GET'])
@service_access_required('hr_portal')
def get_attendance_by_date_v1(date):
    """
    Get all attendance records for a specific date
    
    CRITICAL FEATURE: AUTO-MARKS ALL EMPLOYEES AS ABSENT FOR ANY DATE
    - This ensures every employee has an attendance record
    - Makes it easy to detect when someone changes ABSENT → PRESENT
    - Works for TODAY, past dates, and handles empty databases
    """
    try:
        # Validate date format
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400

        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        # CRITICAL: Auto-mark ABSENT for ALL dates (including today)
        # This ensures every employee always has a record
        print(f"[ATTENDANCE] Auto-marking all unmarked workers as ABSENT for {date}")
        auto_mark_absent_for_date(date)

        # Get all attendance records (now including auto-marked ones)
        records = []
        prefix = f"{ATTENDANCE_FOLDER}{date}/"
        
        try:
            blobs = bucket.list_blobs(prefix=prefix)
            
            for blob in blobs:
                if blob.name == prefix or not blob.name.endswith('.json'):
                    continue
                    
                try:
                    content = blob.download_as_text()
                    record_data = json.loads(content)
                    records.append(record_data)
                except Exception as e:
                    print(f"[ATTENDANCE] Error loading {blob.name}: {e}")
                    continue
        except Exception as e:
            print(f"[ATTENDANCE] Error listing attendance: {e}")

        return jsonify(records), 200

    except Exception as e:
        print(f"[ATTENDANCE] Error: {e}")
        return jsonify([]), 200


@hr_portal_bp.route('/api/v1/summary/<date>', methods=['GET'])
@service_access_required('hr_portal')
def get_daily_summary_v1(date):
    """Get or calculate daily attendance summary"""
    try:
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400

        summary = calculate_daily_summary_v1(date)
        return jsonify(summary), 200

    except Exception as e:
        print(f"[SUMMARY] Error: {e}")
        return jsonify({"error": f"Failed to retrieve summary: {str(e)}"}), 500


@hr_portal_bp.route('/api/v1/summary/<date>/finalize', methods=['POST'])
@service_access_required('hr_portal')
def finalize_daily_summary_v1(date):
    """Explicitly finalize and save daily summary"""
    try:
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400

        summary = calculate_daily_summary_v1(date)

        return jsonify({
            "message": "Daily summary finalized successfully",
            "summary": summary
        }), 200

    except Exception as e:
        return jsonify({"error": f"Failed to finalize summary: {str(e)}"}), 500


@hr_portal_bp.route('/api/v1/settings', methods=['GET'])
@service_access_required('hr_portal')
def get_attendance_settings_v1():
    """Get attendance settings - auto-creates if not exists"""
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        settings_data = read_from_gcs(bucket, HR_SETTINGS_FILE)
        
        if settings_data:
            v1_settings = {
                'total_shifts_available': settings_data.get('total_shifts_available', 2),
                'default_hours_worked': settings_data.get('default_shift_hours', 10.0),
                'unfrozen_days': settings_data.get('unfrozen_days', 5),  # ✅ NEW
                'updated_at': settings_data.get('last_updated')
            }
            return jsonify(v1_settings), 200
        
        # Auto-create default settings
        print("[SETTINGS] No settings found, creating defaults...")
        default_settings = {
            'total_shifts_available': 2,
            'default_shift_hours': 10.0,
            'unfrozen_days': 5,  # ✅ NEW
            'last_updated': datetime.now(IST).isoformat()
        }
        
        try:
            write_to_gcs(bucket, HR_SETTINGS_FILE, default_settings)
            print("[SETTINGS] Default settings created successfully")
        except Exception as e:
            print(f"[SETTINGS] Warning: Failed to save default settings: {e}")
        
        v1_settings = {
            'total_shifts_available': 2,
            'default_hours_worked': 10.0,
            'unfrozen_days': 5,  # ✅ NEW
            'updated_at': default_settings['last_updated']
        }
        return jsonify(v1_settings), 200
        
    except Exception as e:
        print(f"[SETTINGS] Error: {e}")
        return jsonify({
            'total_shifts_available': 2,
            'default_hours_worked': 10.0,
            'unfrozen_days': 5,  # ✅ NEW
            'updated_at': datetime.now(IST).isoformat()
        }), 200

@hr_portal_bp.route('/api/v1/settings', methods=['POST'])
@service_access_required('hr_portal')
def update_attendance_settings_v1():
    """Update attendance settings"""
    try:
        data = request.get_json()
        
        total_shifts = data.get('total_shifts_available', 2)
        default_hours = data.get('default_hours_worked', 10.0)
        unfrozen_days = data.get('unfrozen_days', 5)  # ✅ NEW

        if total_shifts < 1:
            return jsonify({"error": "Total shifts must be at least 1"}), 400
        if default_hours < 1 or default_hours > 12:
            return jsonify({"error": "Default hours must be between 1 and 12"}), 400
        if unfrozen_days < 0 or unfrozen_days > 365:  # ✅ NEW VALIDATION
            return jsonify({"error": "Unfrozen days must be between 0 and 365"}), 400

        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        settings = {
            'total_shifts_available': total_shifts,
            'default_shift_hours': default_hours,
            'unfrozen_days': unfrozen_days,  # ✅ NEW
            'last_updated': datetime.now(IST).isoformat(),
            'updated_by': session.get('user_email')
        }

        if write_to_gcs(bucket, HR_SETTINGS_FILE, settings):
            v1_settings = {
                'total_shifts_available': total_shifts,
                'default_hours_worked': default_hours,
                'unfrozen_days': unfrozen_days,  # ✅ NEW
                'updated_at': settings['last_updated']
            }
            return jsonify(v1_settings), 200
        else:
            return jsonify({"error": "Failed to save settings"}), 500

    except Exception as e:
        return jsonify({"error": f"Failed to update settings: {str(e)}"}), 500



# ==================== HELPER FUNCTIONS (FIXED) ====================

def auto_mark_absent_for_date(date_str):
    """
    CRITICAL FUNCTION: Automatically mark all workers without attendance as ABSENT
    
    UPDATED BEHAVIOR:
    - Runs for ALL dates (including today)
    - Ensures every employee always has an attendance record
    - This is the foundation for detecting backdated changes
    """
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        
        bucket = get_gcs_bucket()
        if not bucket:
            print(f"[AUTO-ABSENT] Could not connect to storage")
            return 0
        
        # Get all active workers
        all_workers = _get_all_active_workers(bucket)
        
        if not all_workers:
            print(f"[AUTO-ABSENT] No active workers found")
            return 0
        
        # Check which workers already have attendance
        marked_employee_codes = set()
        prefix = f"{ATTENDANCE_FOLDER}{date_str}/"
        
        try:
            blobs = bucket.list_blobs(prefix=prefix)
            for blob in blobs:
                if blob.name == prefix or not blob.name.endswith('.json'):
                    continue
                employee_code = blob.name.split('/')[-1].replace('.json', '')
                marked_employee_codes.add(employee_code)
        except Exception as e:
            print(f"[AUTO-ABSENT] Error listing attendance: {e}")
        
        # Auto-mark unmarked workers as ABSENT
        auto_marked_count = 0
        for worker in all_workers:
            employee_code = worker['employee_code']
            if employee_code not in marked_employee_codes:
                absent_record = {
                    'employee_code': employee_code,
                    'worker_id': worker['unique_worker_id'],
                    'worker_name': worker['operator_name'],
                    'department': worker['department'],
                    'date': date_str,
                    'status': 'ABSENT',
                    'shifts_worked': 0,
                    'hours_worked': 0.0,
                    'remarks': 'Auto-marked absent',
                    'created_at': datetime.now(IST).isoformat(),
                    'updated_at': datetime.now(IST).isoformat(),
                    'auto_marked': True  # FLAG: This was auto-marked
                }
                
                attendance_path = f"{ATTENDANCE_FOLDER}{date_str}/{employee_code}.json"
                try:
                    if write_to_gcs(bucket, attendance_path, absent_record):
                        auto_marked_count += 1
                        print(f"[AUTO-ABSENT] ✓ {worker['operator_name']} ({employee_code}) → ABSENT for {date_str}")
                except Exception as e:
                    print(f"[AUTO-ABSENT] ✗ Failed to mark {employee_code}: {e}")
        
        if auto_marked_count > 0:
            print(f"[AUTO-ABSENT] ✅ Auto-marked {auto_marked_count} workers as ABSENT for {date_str}")
        else:
            print(f"[AUTO-ABSENT] All workers already have attendance for {date_str}")
        
        return auto_marked_count
        
    except Exception as e:
        print(f"[AUTO-ABSENT] Error: {e}")
        import traceback
        traceback.print_exc()
        return 0


def calculate_daily_summary_v1(date_str):
    """Calculate daily attendance summary by department"""
    bucket = get_gcs_bucket()
    if not bucket:
        print(f"Error: Could not connect to storage")
        return {
            'date': date_str,
            'total_workers': 0,
            'total_present': 0,
            'total_absent': 0,
            'total_manhours': 0.0,
            'departments': [],
            'saved_at': datetime.now(IST).isoformat()
        }
    
    # Get all active workers from the single file
    workers = _get_all_active_workers(bucket)

    # Get all attendance records
    attendance_records = []
    prefix = f"{ATTENDANCE_FOLDER}{date_str}/"
    
    try:
        blobs = bucket.list_blobs(prefix=prefix)
        for blob in blobs:
            if blob.name == prefix or not blob.name.endswith('.json'):
                continue
            try:
                content = blob.download_as_text()
                record_data = json.loads(content)
                attendance_records.append(record_data)
            except Exception as e:
                print(f"Error loading attendance from {blob.name}: {e}")
    except Exception as e:
        print(f"Error listing attendance for {date_str}: {e}")

    # Create attendance map using employee_code
    attendance_map = {r['employee_code']: r for r in attendance_records}
    
    # Calculate department summaries
    dept_data = {}
    
    for worker in workers:
        dept = worker.get('department', 'Unknown')
        if dept not in dept_data:
            dept_data[dept] = {
                'total_workers': 0,
                'present_count': 0,
                'absent_count': 0,
                'total_manhours': 0.0
            }
        
        dept_data[dept]['total_workers'] += 1
        
        # Look up attendance by employee_code
        attendance = attendance_map.get(worker['employee_code'])
        if attendance:
            if attendance['status'] == 'PRESENT':
                dept_data[dept]['present_count'] += 1
                dept_data[dept]['total_manhours'] += attendance['hours_worked'] * attendance['shifts_worked']
            elif attendance['status'] == 'ABSENT':
                dept_data[dept]['absent_count'] += 1

    # Build department summaries
    departments = [
        {
            'department': dept,
            'total_workers': data['total_workers'],
            'present_count': data['present_count'],
            'absent_count': data['absent_count'],
            'total_manhours': data['total_manhours']
        }
        for dept, data in dept_data.items()
    ]
    
    # Calculate totals
    total_workers = len(workers)
    total_present = sum(d['present_count'] for d in departments)
    total_absent = sum(d['absent_count'] for d in departments)
    total_manhours = sum(d['total_manhours'] for d in departments)
    
    summary = {
        'date': date_str,
        'total_workers': total_workers,
        'total_present': total_present,
        'total_absent': total_absent,
        'total_manhours': total_manhours,
        'departments': departments,
        'saved_at': datetime.now(IST).isoformat()
    }
    
    # Save summary
    try:
        summary_path = f"{ATTENDANCE_SUMMARIES_FOLDER}{date_str}.json"
        write_to_gcs(bucket, summary_path, summary)
    except Exception as e:
        print(f"Warning: Failed to save summary to GCS: {e}")
    
    return summary


def has_attendance_changed(old_data, new_data):
    """Check if attendance data has meaningfully changed"""
    if not old_data:
        return True

    fields_to_check = ['status', 'shifts_worked', 'hours_worked', 'remarks']

    for field in fields_to_check:
        old_val = old_data.get(field)
        new_val = new_data.get(field)

        # Normalize strings
        if isinstance(old_val, str):
            old_val = old_val.strip()
        if isinstance(new_val, str):
            new_val = new_val.strip()

        if old_val != new_val:
            print(f"[CHANGE DETECTION] Field '{field}' changed: '{old_val}' → '{new_val}'")
            return True

    return False


# FIXED EMAIL FUNCTIONS - Replace in hr_portal.py
# These should replace the existing email functions

def send_backdated_new_entry_email(worker_name, employee_code, date, status, user_email):
    """
    Send notification email for backdated new attendance entries
    Fetches admin emails from users.json in GCS
    
    FIXED:
    - Added more detailed error handling
    - Added validation for empty recipient list
    - Improved logging for debugging
    """
    print(f"\n{'='*80}")
    print(f"[EMAIL] send_backdated_new_entry_email() called")
    print(f"{'='*80}")
    print(f"[EMAIL] Worker: {worker_name} ({employee_code})")
    print(f"[EMAIL] Date: {date}")
    print(f"[EMAIL] Status: {status}")
    print(f"[EMAIL] User: {user_email}")
    
    try:
        # Step 1: Get admin emails from users.json
        print(f"\n[EMAIL STEP 1] Fetching admin emails from users.json...")
        bucket = get_gcs_bucket()
        
        if not bucket:
            print(f"[EMAIL] ❌ ERROR: Could not get GCS bucket!")
            return False
        
        print(f"[EMAIL] ✅ GCS bucket connected")
        print(f"[EMAIL] Loading users from: {USERS_FILE}")
        
        users_data = read_from_gcs(bucket, USERS_FILE)
        admin_emails = []
        
        if not users_data:
            print(f"[EMAIL] ❌ ERROR: Could not load users.json from GCS")
            print(f"[EMAIL] Falling back to EMAIL_APPROVERS: {EMAIL_APPROVERS}")
            admin_emails = EMAIL_APPROVERS
        else:
            print(f"[EMAIL] ✅ users.json loaded successfully")
            print(f"[EMAIL] Total users in file: {len(users_data)}")
            
            # Debug: Print all users
            for user in users_data:
                print(f"[EMAIL]   - User: {user.get('email')} | Role: {user.get('role')}")
            
            # Filter users with role='admin'
            admin_emails = [
                user['email'].strip()  # FIXED: Strip whitespace
                for user in users_data 
                if user.get('role') == 'admin' and user.get('email')  # FIXED: Check email exists
            ]
            
            print(f"[EMAIL] Found {len(admin_emails)} admin(s)")
            for email in admin_emails:
                print(f"[EMAIL]   - Admin email: {email}")
        
        # Fallback to EMAIL_APPROVERS if no admins found
        if not admin_emails:
            print(f"[EMAIL] ⚠️  No admins found in users.json")
            print(f"[EMAIL] Using EMAIL_APPROVERS fallback: {EMAIL_APPROVERS}")
            admin_emails = EMAIL_APPROVERS
        
        # FIXED: Validate email list is not empty
        if not admin_emails or not isinstance(admin_emails, list):
            print(f"[EMAIL] ❌ FATAL: No valid recipients found!")
            return False
        
        # FIXED: Remove any None or empty string emails
        admin_emails = [email for email in admin_emails if email and email.strip()]
        
        if not admin_emails:
            print(f"[EMAIL] ❌ FATAL: All emails were invalid!")
            return False
        
        print(f"[EMAIL] ✅ Final recipient list: {admin_emails}")
        
        # Step 2: Get Flask-Mail instance
        print(f"\n[EMAIL STEP 2] Getting Flask-Mail instance...")
        from flask_mail import Message
        mail_instance = current_app.extensions.get('mail')
        
        if not mail_instance:
            print(f"[EMAIL] ❌ ERROR: Flask-Mail not initialized!")
            print(f"[EMAIL] Available extensions: {list(current_app.extensions.keys())}")
            return False
        
        print(f"[EMAIL] ✅ Flask-Mail instance found")
        
        # Step 3: Get sender from config
        print(f"\n[EMAIL STEP 3] Getting sender configuration...")
        sender = current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('MAIL_USERNAME')
        
        # FIXED: Validate sender
        if not sender:
            print(f"[EMAIL] ❌ ERROR: No sender configured!")
            return False
        
        print(f"[EMAIL] MAIL_DEFAULT_SENDER: {current_app.config.get('MAIL_DEFAULT_SENDER')}")
        print(f"[EMAIL] MAIL_USERNAME: {current_app.config.get('MAIL_USERNAME')}")
        print(f"[EMAIL] Using sender: {sender}")
        
        # Step 4: Build email
        print(f"\n[EMAIL STEP 4] Building email...")
        subject = f"HR Portal: Backdated Attendance Entry - {worker_name} ({date})"
        print(f"[EMAIL] Subject: {subject}")
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2c3e50;">⚠️ Backdated Attendance Entry</h2>
            <p>Hello,</p>
            <p>A backdated attendance entry has been created in the HR Portal.</p>
            
            <div style="background: #f8f9fa; padding: 16px; border-radius: 8px; margin: 16px 0;">
                <h3 style="margin-top: 0;">Attendance Details:</h3>
                <ul style="list-style: none; padding: 0;">
                    <li><strong>Worker:</strong> {worker_name}</li>
                    <li><strong>Employee Code:</strong> {employee_code}</li>
                    <li><strong>Date:</strong> {date}</li>
                    <li><strong>Status:</strong> <span style="color: {'#10b981' if status == 'PRESENT' else '#ef4444'}; font-weight: bold;">{status}</span></li>
                    <li><strong>Marked by:</strong> {user_email}</li>
                    <li><strong>Timestamp:</strong> {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}</li>
                </ul>
            </div>
            
            <p style="color: #ef4444; font-weight: bold;">⚠️ This is a backdated entry for a past date.</p>
            
            <br>
            <p>Best regards,<br><strong>KBI ERP - HR Portal</strong></p>
        </body>
        </html>
        """
        
        # FIXED: Create message with proper error handling
        try:
            msg = Message(
                subject=subject,
                sender=sender,
                recipients=admin_emails,
                html=html_body
            )
            print(f"[EMAIL] ✅ Message object created")
        except Exception as msg_error:
            print(f"[EMAIL] ❌ Failed to create message: {msg_error}")
            return False
        
        # Step 5: Send email
        print(f"\n[EMAIL STEP 5] Sending email...")
        print(f"[EMAIL]   From: {sender}")
        print(f"[EMAIL]   To: {admin_emails}")
        print(f"[EMAIL]   Subject: {subject}")
        
        try:
            with current_app.app_context():
                mail_instance.send(msg)
            print(f"[EMAIL] ✅✅✅ EMAIL SENT SUCCESSFULLY ✅✅✅")
            print(f"{'='*80}\n")
            return True
        except Exception as send_error:
            print(f"[EMAIL] ❌ Send failed: {send_error}")
            import traceback
            traceback.print_exc()
            return False
        
    except Exception as e:
        print(f"[EMAIL] ❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*80}\n")
        return False



def send_attendance_update_email(worker_name, employee_code, date, old_data, new_data, timestamp):
    """
    Send email notification for attendance updates
    Fetches admin emails from users.json in GCS
    
    FIXED:
    - Removed duplicate function definition
    - Added validation for changes
    - Improved error handling
    """
    print(f"\n{'='*80}")
    print(f"[EMAIL] send_attendance_update_email() called")
    print(f"{'='*80}")
    print(f"[EMAIL] Worker: {worker_name} ({employee_code})")
    print(f"[EMAIL] Date: {date}")
    
    try:
        # Step 1: Get admin emails
        print(f"\n[EMAIL STEP 1] Fetching admin emails...")
        bucket = get_gcs_bucket()
        
        if not bucket:
            print(f"[EMAIL] ❌ ERROR: Could not get GCS bucket!")
            return False
        
        print(f"[EMAIL] ✅ GCS bucket connected")
        users_data = read_from_gcs(bucket, USERS_FILE)
        admin_emails = []
        
        if not users_data:
            print(f"[EMAIL] ⚠️  Could not load users.json, using EMAIL_APPROVERS")
            admin_emails = EMAIL_APPROVERS
        else:
            print(f"[EMAIL] ✅ users.json loaded, total users: {len(users_data)}")
            admin_emails = [
                user['email'].strip()  # FIXED: Strip whitespace
                for user in users_data 
                if user.get('role') == 'admin' and user.get('email')  # FIXED: Check email exists
            ]
            print(f"[EMAIL] Found {len(admin_emails)} admin(s): {admin_emails}")
        
        if not admin_emails:
            print(f"[EMAIL] Using EMAIL_APPROVERS fallback: {EMAIL_APPROVERS}")
            admin_emails = EMAIL_APPROVERS
        
        # FIXED: Validate emails
        admin_emails = [email for email in admin_emails if email and email.strip()]
        
        if not admin_emails:
            print(f"[EMAIL] ❌ FATAL: No valid recipients!")
            return False
        
        # Step 2: Get Flask-Mail
        print(f"\n[EMAIL STEP 2] Getting Flask-Mail...")
        from flask_mail import Message
        mail_instance = current_app.extensions.get('mail')
        
        if not mail_instance:
            print(f"[EMAIL] ❌ ERROR: Flask-Mail not initialized!")
            return False
        
        print(f"[EMAIL] ✅ Flask-Mail found")
        
        # Step 3: Get sender
        print(f"\n[EMAIL STEP 3] Getting sender...")
        sender = current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('MAIL_USERNAME')
        
        if not sender:
            print(f"[EMAIL] ❌ ERROR: No sender configured!")
            return False
        
        print(f"[EMAIL] Sender: {sender}")
        
        # Step 4: Build changes comparison
        print(f"\n[EMAIL STEP 4] Building change comparison...")
        changes = []
        
        old_status = old_data.get('status', '')
        new_status = new_data.get('status', '')
        print(f"[EMAIL]   Status: '{old_status}' → '{new_status}'")
        if old_status != new_status:
            changes.append(f"<strong>Status:</strong> {old_status} → {new_status}")
        
        old_shifts = old_data.get('shifts_worked', 0)
        new_shifts = new_data.get('shifts_worked', 0)
        print(f"[EMAIL]   Shifts: {old_shifts} → {new_shifts}")
        if old_shifts != new_shifts:
            changes.append(f"<strong>Shifts:</strong> {old_shifts} → {new_shifts}")
        
        old_hours = old_data.get('hours_worked', 0)
        new_hours = new_data.get('hours_worked', 0)
        print(f"[EMAIL]   Hours: {old_hours} → {new_hours}")
        if old_hours != new_hours:
            changes.append(f"<strong>Hours:</strong> {old_hours} → {new_hours}")
        
        old_remarks = (old_data.get('remarks') or '').strip()
        new_remarks = (new_data.get('remarks') or '').strip()
        print(f"[EMAIL]   Remarks: '{old_remarks}' → '{new_remarks}'")
        if old_remarks != new_remarks:
            old_remarks_display = old_remarks if old_remarks else '(empty)'
            new_remarks_display = new_remarks if new_remarks else '(empty)'
            changes.append(f"<strong>Remarks:</strong> {old_remarks_display} → {new_remarks_display}")

        print(f"[EMAIL] Total changes detected: {len(changes)}")
        
        # FIXED: Don't send email if no changes
        if not changes:
            print(f"[EMAIL] ⚠️  No changes detected - skipping email")
            return True  # Return True because this is expected behavior
        
        changes_html = "<br>".join([f"• {change}" for change in changes])
        
        # Step 5: Build email
        print(f"\n[EMAIL STEP 5] Building email message...")
        subject = f"HR Portal: Attendance Updated - {worker_name} ({date})"

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2c3e50;">🔄 Attendance Update Notification</h2>
            <p>Hello,</p>
            <p>Attendance has been updated for the following worker:</p>
            
            <div style="background: #f8f9fa; padding: 16px; border-radius: 8px; margin: 16px 0;">
                <h3 style="margin-top: 0;">Worker Information:</h3>
                <ul style="list-style: none; padding: 0;">
                    <li><strong>Worker:</strong> {worker_name}</li>
                    <li><strong>Employee Code:</strong> {employee_code}</li>
                    <li><strong>Date:</strong> {date}</li>
                    <li><strong>Updated:</strong> {timestamp}</li>
                </ul>
            </div>
            
            <div style="background: #fff3cd; padding: 16px; border-radius: 8px; margin: 16px 0;">
                <h3 style="margin-top: 0; color: #856404;">📝 Changes Made:</h3>
                <div style="padding-left: 16px;">
                    {changes_html}
                </div>
            </div>
            
            <br>
            <p>Best regards,<br><strong>KBI ERP - HR Portal</strong></p>
        </body>
        </html>
        """

        # FIXED: Create message with error handling
        try:
            msg = Message(
                subject=subject,
                sender=sender,
                recipients=admin_emails,
                html=html_body
            )
            print(f"[EMAIL] ✅ Message object created")
        except Exception as msg_error:
            print(f"[EMAIL] ❌ Failed to create message: {msg_error}")
            return False
        
        # Step 6: Send
        print(f"\n[EMAIL STEP 6] Sending email...")
        print(f"[EMAIL]   From: {sender}")
        print(f"[EMAIL]   To: {admin_emails}")
        print(f"[EMAIL]   Subject: {subject}")
        
        try:
            with current_app.app_context():
                mail_instance.send(msg)
            print(f"[EMAIL] ✅✅✅ EMAIL SENT SUCCESSFULLY ✅✅✅")
            print(f"{'='*80}\n")
            return True
        except Exception as send_error:
            print(f"[EMAIL] ❌ Send failed: {send_error}")
            import traceback
            traceback.print_exc()
            return False
        
    except Exception as e:
        print(f"[EMAIL] ❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*80}\n")
        return False


# ==========


# ==================== SETTINGS API ====================

@hr_portal_bp.route('/api/settings', methods=['GET'])
@service_access_required('hr_portal')
def get_settings():
    """Get HR Portal settings"""
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        settings = read_from_gcs(bucket, HR_SETTINGS_FILE)
        if not settings:
            settings = {
                'default_shift_hours': DEFAULT_SHIFT_HOURS,
                'total_shifts_available': 2,
                'unfrozen_days': 5,  # ✅ NEW
                'last_updated': datetime.now(IST).isoformat()
            }

        return jsonify(settings), 200

    except Exception as e:
        return jsonify({"error": f"Failed to load settings: {str(e)}"}), 500

@hr_portal_bp.route('/api/settings', methods=['POST'])
@service_access_required('hr_portal')
def update_settings():
    """Update HR Portal settings"""
    try:
        data = request.get_json()
        shift_hours = data.get('default_shift_hours', DEFAULT_SHIFT_HOURS)

        # Validate shift hours
        try:
            shift_hours = float(shift_hours)
            if shift_hours <= 0 or shift_hours > 24:
                return jsonify({"error": "Shift hours must be between 0 and 24"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid shift hours value"}), 400

        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        settings = {
            'default_shift_hours': shift_hours,
            'total_shifts_available': data.get('total_shifts_available', 2),
            'last_updated': datetime.now(IST).isoformat(),
            'updated_by': session.get('user_email')
        }

        if write_to_gcs(bucket, HR_SETTINGS_FILE, settings):
            return jsonify({"message": "Settings updated successfully"}), 200
        else:
            return jsonify({"error": "Failed to save settings"}), 500

    except Exception as e:
        return jsonify({"error": f"Failed to update settings: {str(e)}"}), 500


# ==================== REPORTS API ====================

@hr_portal_bp.route('/api/reports/summary', methods=['GET'])
@service_access_required('hr_portal')
def get_summary_report():
    """Get summary report for a date range"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not start_date or not end_date:
            return jsonify({"error": "start_date and end_date are required"}), 400

        # Validate dates
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

        if start > end:
            return jsonify({"error": "start_date must be before end_date"}), 400

        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500

        # Collect attendance data for date range
        report_data = []
        current_date = start

        while current_date <= end:
            date_str = current_date.strftime('%Y-%m-%d')
            attendance_file = f"{HR_ATTENDANCE_FOLDER}attendance_{date_str.replace('-', '')}.json"
            attendance_data = read_from_gcs(bucket, attendance_file)

            if attendance_data and attendance_data.get('allocations'):
                # Calculate totals for this day
                total_manpower = sum(alloc.get('count', 0) for alloc in attendance_data['allocations'])
                total_manhours = sum(alloc.get('count', 0) * alloc.get('hours', attendance_data.get('shift_hours', DEFAULT_SHIFT_HOURS))
                                   for alloc in attendance_data['allocations'])

                report_data.append({
                    'date': date_str,
                    'total_manpower': total_manpower,
                    'total_manhours': total_manhours,
                    'allocations': attendance_data['allocations']
                })

            current_date += timedelta(days=1)

        return jsonify({
            'start_date': start_date,
            'end_date': end_date,
            'data': report_data
        }), 200

    except Exception as e:
        return jsonify({"error": f"Failed to generate report: {str(e)}"}), 500





def validate_email_list(emails):
    """
    Validate and clean a list of email addresses
    Returns list of valid emails or empty list
    """
    if not emails:
        return []
    
    if not isinstance(emails, list):
        emails = [emails]
    
    # Remove None, empty strings, and strip whitespace
    valid_emails = []
    for email in emails:
        if email and isinstance(email, str):
            email = email.strip()
            if email and '@' in email:  # Basic email validation
                valid_emails.append(email)
    
    return valid_emails




# ==================== HR COST ANALYTICS HELPER FUNCTIONS ====================

def fetch_daily_cost_record(bucket, date_str):
    """
    Fetch a single daily cost record from GCS
    Returns None if not found
    """
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        year = date_obj.year
        month = date_obj.month
        
        # Path: hr_cost/YYYY/MM/YYYY-MM-DD.json
        blob_path = f"{HR_COST_FOLDER}{year}/{month:02d}/{date_str}.json"
        
        data = read_from_gcs(bucket, blob_path)
        return data
        
    except Exception as e:
        print(f"[COST ANALYTICS] Error fetching {date_str}: {e}")
        return None


def fetch_cost_records_range(bucket, start_date, end_date):
    """
    Fetch all daily cost records between start_date and end_date (inclusive)
    Returns list of records with date included
    """
    records = []
    
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        current = start
        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            record = fetch_daily_cost_record(bucket, date_str)
            
            if record:
                records.append(record)
            
            current += timedelta(days=1)
        
        print(f"[COST ANALYTICS] Fetched {len(records)} records from {start_date} to {end_date}")
        return records
        
    except Exception as e:
        print(f"[COST ANALYTICS] Error fetching range: {e}")
        return []


# ==================== HR COST ANALYTICS API ROUTES ====================

@hr_portal_bp.route('/cost-analytics')
@service_access_required('hr_portal')
def cost_analytics_dashboard():
    """HR Cost Analytics Dashboard page"""
    return render_template('hr_cost_analytics.html')


@hr_portal_bp.route('/api/cost-analytics/summary', methods=['GET'])
@service_access_required('hr_portal')
def get_cost_summary():
    """
    Get company-level cost summary for a date range
    
    Query params:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    
    Returns:
    - total_company_cost: Total cost across all days
    - total_attendance_hours: Total hours worked
    - average_cost_per_day: Average daily cost
    - average_hours_per_worker: Average hours per worker per day
    - days_processed: Number of days with data
    - days_missing: Number of days without data
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({"error": "start_date and end_date are required"}), 400
        
        # Validate dates
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        if start > end:
            return jsonify({"error": "start_date must be before end_date"}), 400
        
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500
        
        # Fetch all records in range
        records = fetch_cost_records_range(bucket, start_date, end_date)
        
        if not records:
            return jsonify({
                "start_date": start_date,
                "end_date": end_date,
                "total_company_cost": 0,
                "total_attendance_hours": 0,
                "average_cost_per_day": 0,
                "average_hours_per_worker": 0,
                "days_processed": 0,
                "days_missing": (end - start).days + 1
            }), 200
        
        # Aggregate data
        total_cost = sum(r['summary']['total_company_cost'] for r in records)
        total_hours = sum(r['summary']['total_attendance_hours'] for r in records)
        days_processed = len(records)
        total_days = (end - start).days + 1
        days_missing = total_days - days_processed
        
        # Calculate averages
        avg_cost_per_day = total_cost / days_processed if days_processed > 0 else 0
        
        # Average hours per worker (across all days)
        total_worker_days = sum(r['calculation_metadata']['total_workers'] for r in records)
        avg_hours_per_worker = total_hours / total_worker_days if total_worker_days > 0 else 0
        
        return jsonify({
            "start_date": start_date,
            "end_date": end_date,
            "total_company_cost": round(total_cost, 2),
            "total_attendance_hours": round(total_hours, 2),
            "average_cost_per_day": round(avg_cost_per_day, 2),
            "average_hours_per_worker": round(avg_hours_per_worker, 2),
            "days_processed": days_processed,
            "days_missing": days_missing,
            "date_range_days": total_days
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to get summary: {str(e)}"}), 500


@hr_portal_bp.route('/api/cost-analytics/department-breakdown', methods=['GET'])
@service_access_required('hr_portal')
def get_department_breakdown():
    """
    Get department-wise cost breakdown for a date range
    
    Query params:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    
    Returns list of departments with:
    - department: Department name
    - total_cost: Total cost for this department
    - total_hours: Total attendance hours
    - percentage_of_total: % contribution to company cost
    - worker_count: Average workers per day (sum of daily counts / num days)
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({"error": "start_date and end_date are required"}), 400
        
        # Validate dates
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500
        
        # Fetch all records
        records = fetch_cost_records_range(bucket, start_date, end_date)
        
        if not records:
            return jsonify([]), 200
        
        # Aggregate by department
        dept_data = {}
        total_company_cost = 0
        num_days = len(records)  # Number of days in the period
        
        for record in records:
            total_company_cost += record['summary']['total_company_cost']
            
            # Track daily worker counts per department
            daily_dept_workers = {}
            
            for worker in record.get('workers', []):
                dept = worker.get('department', 'Unknown')
                
                if dept not in dept_data:
                    dept_data[dept] = {
                        'total_cost': 0,
                        'total_hours': 0,
                        'daily_worker_counts': [],  # List of worker counts per day
                        'unique_workers': set()  # Track unique workers
                    }
                
                dept_data[dept]['total_cost'] += worker.get('todays_salary', 0)
                dept_data[dept]['total_hours'] += worker.get('attendance_info', {}).get('hours_worked', 0)
                dept_data[dept]['unique_workers'].add(worker.get('employee_code'))
                
                # Count workers present in this day for this department
                if worker.get('attendance_info', {}).get('hours_worked', 0) > 0:
                    daily_dept_workers[dept] = daily_dept_workers.get(dept, 0) + 1
            
            # Store daily counts for each department
            for dept in dept_data.keys():
                dept_data[dept]['daily_worker_counts'].append(daily_dept_workers.get(dept, 0))
        
        # Build response
        departments = []
        for dept, data in dept_data.items():
            percentage = (data['total_cost'] / total_company_cost * 100) if total_company_cost > 0 else 0
            
            # Calculate average workers per day
            total_worker_days = sum(data['daily_worker_counts'])
            avg_workers_per_day = total_worker_days / num_days if num_days > 0 else 0
            total_unique_workers = len(data['unique_workers'])
            
            departments.append({
                'department': dept,
                'total_cost': round(data['total_cost'], 2),
                'total_hours': round(data['total_hours'], 2),
                'percentage_of_total': round(percentage, 2),
                'worker_count': round(avg_workers_per_day, 1),  # Average workers per day
                'total_workers': total_unique_workers  # Total unique workers in department
            })
        
        # Sort by total cost descending
        departments.sort(key=lambda x: x['total_cost'], reverse=True)
        
        return jsonify(departments), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to get department breakdown: {str(e)}"}), 500


@hr_portal_bp.route('/api/cost-analytics/worker-cost', methods=['GET'])
@service_access_required('hr_portal')
def get_worker_cost():
    """
    Get cost details for a specific worker in a date range
    
    Query params:
    - employee_code: Worker's employee code (required)
    - start_date: YYYY-MM-DD (required)
    - end_date: YYYY-MM-DD (required)
    
    Returns:
    - worker_info: Basic worker details
    - total_cost: Total cost paid to this worker
    - total_hours: Total hours worked
    - days_present: Number of days present
    - days_absent: Number of days absent
    - daily_breakdown: Day-by-day cost and hours
    """
    try:
        employee_code = request.args.get('employee_code', '').strip().upper()
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not employee_code:
            return jsonify({"error": "employee_code is required"}), 400
        
        if not start_date or not end_date:
            return jsonify({"error": "start_date and end_date are required"}), 400
        
        # Validate dates
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500
        
        # Fetch all records
        records = fetch_cost_records_range(bucket, start_date, end_date)
        
        if not records:
            return jsonify({"error": "No cost data found for this date range"}), 404
        
        # Find worker in records
        worker_info = None
        total_cost = 0
        total_hours = 0
        days_present = 0
        days_absent = 0
        daily_breakdown = []
        
        for record in records:
            date = record.get('date')
            
            for worker in record.get('workers', []):
                if worker.get('employee_code') == employee_code:
                    # Capture worker info (first occurrence)
                    if not worker_info:
                        worker_info = {
                            'employee_code': worker.get('employee_code'),
                            'worker_id': worker.get('worker_id'),
                            'worker_name': worker.get('worker_name'),
                            'department': worker.get('department'),
                            'designation': worker.get('designation')
                        }
                    
                    # Aggregate totals
                    todays_salary = worker.get('todays_salary', 0)
                    hours_worked = worker.get('attendance_info', {}).get('hours_worked', 0)
                    status = worker.get('attendance_info', {}).get('status', 'UNKNOWN')
                    
                    total_cost += todays_salary
                    total_hours += hours_worked
                    
                    if hours_worked > 0:
                        days_present += 1
                    else:
                        days_absent += 1
                    
                    # Daily breakdown
                    daily_breakdown.append({
                        'date': date,
                        'status': status,
                        'hours_worked': hours_worked,
                        'todays_salary': round(todays_salary, 2),
                        'shifts_worked': worker.get('attendance_info', {}).get('shifts_worked', 0),
                        'hourly_rate': worker.get('salary_info', {}).get('hourly_rate', 0)
                    })
                    
                    break  # Found worker for this date
        
        if not worker_info:
            return jsonify({"error": f"Worker {employee_code} not found in cost records"}), 404
        
        # Sort daily breakdown by date
        daily_breakdown.sort(key=lambda x: x['date'])
        
        return jsonify({
            "worker_info": worker_info,
            "start_date": start_date,
            "end_date": end_date,
            "total_cost": round(total_cost, 2),
            "total_hours": round(total_hours, 2),
            "days_present": days_present,
            "days_absent": days_absent,
            "daily_breakdown": daily_breakdown
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to get worker cost: {str(e)}"}), 500


@hr_portal_bp.route('/api/cost-analytics/workers-list', methods=['GET'])
@service_access_required('hr_portal')
def get_workers_list_for_analytics():
    """
    Get list of all workers for selection in analytics
    Returns simplified worker list with employee_code and name
    """
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500
        
        workers = _get_all_active_workers(bucket)
        
        # Sort by name
        workers.sort(key=lambda x: x.get('operator_name', ''))
        
        return jsonify(workers), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to get workers list: {str(e)}"}), 500


@hr_portal_bp.route('/api/cost-analytics/recalculate', methods=['POST'])
@service_access_required('hr_portal')
def trigger_cost_recalculation():
    """
    Manually trigger cost recalculation for a specific date
    
    POST body:
    - date: YYYY-MM-DD (required)
    - force: true/false (optional, default false)
    
    This calls the HR cost calculation service
    """
    try:
        data = request.get_json()
        date = data.get('date', '').strip()
        force = data.get('force', False)
        
        if not date:
            return jsonify({"error": "date is required"}), 400
        
        # Validate date
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        # Build service URL
        import requests
        
        params = {'date': date}
        if force:
            params['force'] = 'true'
        
        print(f"[COST RECALC] Calling service: {HR_COST_SERVICE_URL}")
        print(f"[COST RECALC] Params: {params}")
        
        # Call the cost calculation service
        try:
            response = requests.get(HR_COST_SERVICE_URL, params=params, timeout=300)
            
            if response.status_code == 200:
                result = response.json()
                return jsonify({
                    "success": True,
                    "message": f"Cost recalculation completed for {date}",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "success": False,
                    "message": f"Service returned error: {response.status_code}",
                    "error": response.text
                }), 500
                
        except requests.exceptions.Timeout:
            return jsonify({
                "success": False,
                "message": "Service timeout - calculation may still be in progress"
            }), 504
        except requests.exceptions.RequestException as e:
            return jsonify({
                "success": False,
                "message": f"Failed to call service: {str(e)}"
            }), 500
        
    except Exception as e:
        return jsonify({"error": f"Failed to trigger recalculation: {str(e)}"}), 500


@hr_portal_bp.route('/api/cost-analytics/date-availability', methods=['GET'])
@service_access_required('hr_portal')
def check_date_availability():
    """
    Check which dates have cost data available in a range
    
    Query params:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    
    Returns:
    - available_dates: List of dates with data
    - missing_dates: List of dates without data
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({"error": "start_date and end_date are required"}), 400
        
        # Validate dates
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500
        
        available_dates = []
        missing_dates = []
        
        current = start
        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            record = fetch_daily_cost_record(bucket, date_str)
            
            if record:
                available_dates.append(date_str)
            else:
                missing_dates.append(date_str)
            
            current += timedelta(days=1)
        
        return jsonify({
            "start_date": start_date,
            "end_date": end_date,
            "available_dates": available_dates,
            "missing_dates": missing_dates,
            "total_available": len(available_dates),
            "total_missing": len(missing_dates)
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to check availability: {str(e)}"}), 500
    
"""
Add this endpoint to hr_portal.py after the other cost analytics endpoints
(around line 2100, after get_department_breakdown)
"""

@hr_portal_bp.route('/api/cost-analytics/daily-breakdown', methods=['GET'])
@service_access_required('hr_portal')
def get_daily_breakdown():
    """
    Get day-by-day breakdown for a date range
    
    Query params:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    
    Returns list of daily summaries
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({"error": "start_date and end_date are required"}), 400
        
        # Validate dates
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        if start > end:
            return jsonify({"error": "start_date must be before end_date"}), 400
        
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500
        
        # Fetch all records in range
        records = fetch_cost_records_range(bucket, start_date, end_date)
        
        if not records:
            return jsonify([]), 200
        
        # Build daily breakdown
        daily_data = []
        
        for record in records:
            date = record.get('date')
            summary = record.get('summary', {})
            metadata = record.get('calculation_metadata', {})
            workers = record.get('workers', [])
            
            # Calculate workers_present by counting workers who actually worked
            workers_present = 0
            for worker in workers:
                attendance_info = worker.get('attendance_info', {})
                hours_worked = attendance_info.get('hours_worked', 0)
                
                # Count as present if they worked any hours
                if hours_worked > 0:
                    workers_present += 1
            
            # Get total workers from metadata
            total_workers = metadata.get('total_workers', len(workers))
            
            daily_data.append({
                'date': date,
                'total_cost': round(summary.get('total_company_cost', 0), 2),
                'total_hours': round(summary.get('total_attendance_hours', 0), 2),
                'workers_present': workers_present,
                'total_workers': total_workers
            })
        
        # Sort by date
        daily_data.sort(key=lambda x: x['date'])
        
        return jsonify(daily_data), 200
        
    except Exception as e:
        print(f"[DAILY BREAKDOWN] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to get daily breakdown: {str(e)}"}), 500


@hr_portal_bp.route('/api/cost-analytics/date-details', methods=['GET'])
@service_access_required('hr_portal')
def get_date_details():
    """
    Get detailed department-wise breakdown for a specific date
    
    Query params:
    - date: YYYY-MM-DD
    
    Returns:
    {
        "date": "2026-01-19",
        "total_cost": 75377.82,
        "total_hours": 1176,
        "workers_present": 110,
        "total_workers": 147,
        "departments": [
            {
                "department": "Production",
                "total_cost": 45200.50,
                "workers_present": 65,
                "total_workers": 90,
                "percentage_of_total": 60.1
            },
            ...
        ]
    }
    """
    try:
        date_str = request.args.get('date')
        
        if not date_str:
            return jsonify({"error": "date parameter is required (YYYY-MM-DD)"}), 400
        
        # Validate date format
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        bucket = get_gcs_bucket()
        if not bucket:
            return jsonify({"error": "Could not connect to storage"}), 500
        
        # Construct path to the specific date's cost file
        # Format: hr_cost/YYYY/MM/YYYY-MM-DD.json
        year = date_obj.year
        month = date_obj.month
        blob_path = f"{HR_COST_FOLDER}{year}/{month:02d}/{date_str}.json"
        
        print(f"[DATE DETAILS] Fetching from: gs://kbi-first/{blob_path}")
        
        # Read the cost calculation file
        cost_data = read_from_gcs(bucket, blob_path)
        
        if not cost_data:
            return jsonify({"error": f"No cost data found for {date_str}"}), 404
        
        # Extract summary data
        summary = cost_data.get('summary', {})
        metadata = cost_data.get('calculation_metadata', {})
        workers = cost_data.get('workers', [])
        
        # Group workers by department
        dept_breakdown = {}
        
        for worker in workers:
            dept_name = worker.get('department', 'Unknown')
            attendance_info = worker.get('attendance_info', {})
            hours_worked = attendance_info.get('hours_worked', 0)
            todays_salary = worker.get('todays_salary', 0)
            
            # Initialize department if not exists
            if dept_name not in dept_breakdown:
                dept_breakdown[dept_name] = {
                    'department': dept_name,
                    'total_cost': 0,
                    'workers_present': 0,
                    'total_workers': 0,
                    'worker_details': []
                }
            
            # Aggregate data
            dept_breakdown[dept_name]['total_cost'] += todays_salary
            dept_breakdown[dept_name]['total_workers'] += 1
            
            if hours_worked > 0:
                dept_breakdown[dept_name]['workers_present'] += 1
            
            # Store worker detail for potential future use
            dept_breakdown[dept_name]['worker_details'].append({
                'name': worker.get('worker_name', ''),
                'employee_code': worker.get('employee_code', ''),
                'hours_worked': hours_worked,
                'status': 'PRESENT' if hours_worked > 0 else 'ABSENT',
                'salary': round(todays_salary, 2)
            })
        
        # Convert to list and calculate percentages
        total_cost = summary.get('total_company_cost', 0)
        departments = []
        
        for dept_name, dept_data in dept_breakdown.items():
            percentage = (dept_data['total_cost'] / total_cost * 100) if total_cost > 0 else 0
            
            departments.append({
                'department': dept_name,
                'total_cost': round(dept_data['total_cost'], 2),
                'workers_present': dept_data['workers_present'],
                'total_workers': dept_data['total_workers'],
                'percentage_of_total': round(percentage, 1),
                'worker_details': dept_data['worker_details']  # Include for detailed view
            })
        
        # Sort departments by cost (descending)
        departments.sort(key=lambda x: x['total_cost'], reverse=True)
        
        # Build response
        response = {
            'date': date_str,
            'total_cost': round(summary.get('total_company_cost', 0), 2),
            'total_hours': round(summary.get('total_attendance_hours', 0), 2),
            'workers_present': metadata.get('present_workers', 0),
            'total_workers': metadata.get('total_workers', 0),
            'departments': departments
        }
        
        print(f"[DATE DETAILS] Found {len(departments)} departments for {date_str}")
        
        return jsonify(response), 200
        
    except Exception as e:
        print(f"[DATE DETAILS] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to get date details: {str(e)}"}), 500