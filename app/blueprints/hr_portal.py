"""
HR Portal Blueprint - Workspace-scoped HR management
All routes require login and workspace context.
URL pattern: /hr/<workspace_id>/...

Supports dynamic hierarchy fields, configurable salary components,
auto-generated employee codes, and dynamic contact info.
"""
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user

from app.models.workspace_membership import WorkspaceMembership
from app.services.hr_service import HRService

hr_portal_bp = Blueprint('hr_portal', __name__,
                          template_folder='../templates/hr_portal',
                          url_prefix='/hr')


# ==================== ACCESS CONTROL ====================

def _check_workspace_access(workspace_id: str):
    """Verify current user has access to this workspace."""
    membership = WorkspaceMembership.get_membership(current_user.id, workspace_id)
    if not membership or not membership.is_active:
        return None, (jsonify({"error": "You don't have access to this workspace"}), 403)
    return membership, None


def _check_workspace_admin(workspace_id: str):
    """Verify current user is admin/manager of this workspace."""
    membership = WorkspaceMembership.get_membership(current_user.id, workspace_id)
    if not membership or not membership.is_active:
        return None, (jsonify({"error": "You don't have access to this workspace"}), 403)
    if membership.workspace_role.value not in ('admin', 'manager'):
        return None, (jsonify({"error": "Insufficient permissions"}), 403)
    return membership, None


# ==================== PAGES ====================

@hr_portal_bp.route('/<workspace_id>/')
@login_required
def hr_home(workspace_id):
    """HR Portal dashboard"""
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    stats = HRService.get_dashboard_stats(workspace_id)
    settings = HRService.get_settings(workspace_id)
    return render_template('hr_dashboard.html',
                           workspace_id=workspace_id,
                           stats=stats,
                           settings=settings,
                           user=current_user)


@hr_portal_bp.route('/<workspace_id>/hierarchy/<field_key>')
@login_required
def manage_hierarchy_values(workspace_id, field_key):
    """Generic hierarchy value management page"""
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    settings = HRService.get_settings(workspace_id)
    # Find the field config to get its label
    field_config = None
    for f in settings.get('hierarchy_fields', []):
        if f['key'] == field_key:
            field_config = f
            break
    if not field_config:
        return jsonify({"error": f"Hierarchy field '{field_key}' not found"}), 404
    return render_template('hierarchy_values.html',
                           workspace_id=workspace_id,
                           field_key=field_key,
                           field_label=field_config['label'],
                           user=current_user)


@hr_portal_bp.route('/<workspace_id>/attendance')
@login_required
def daily_attendance(workspace_id):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    today = datetime.utcnow().strftime('%Y-%m-%d')
    return render_template('hr_attendance.html',
                           workspace_id=workspace_id,
                           selected_date=today,
                           user=current_user)


@hr_portal_bp.route('/<workspace_id>/settings')
@login_required
def hr_settings(workspace_id):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    settings = HRService.get_settings(workspace_id)
    return render_template('hr_settings.html',
                           workspace_id=workspace_id,
                           settings=settings,
                           user=current_user)


@hr_portal_bp.route('/<workspace_id>/reports')
@login_required
def hr_reports(workspace_id):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    return render_template('hr_reports.html', workspace_id=workspace_id, user=current_user)


@hr_portal_bp.route('/<workspace_id>/workers')
@login_required
def manage_workers(workspace_id):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    settings = HRService.get_settings(workspace_id)
    return render_template('hr_addworker.html',
                           workspace_id=workspace_id,
                           settings=settings,
                           user=current_user)


@hr_portal_bp.route('/<workspace_id>/cost-analytics')
@login_required
def cost_analytics(workspace_id):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    return render_template('hr_cost_analytics.html', workspace_id=workspace_id, user=current_user)


# ==================== HIERARCHY VALUES API ====================

@hr_portal_bp.route('/<workspace_id>/api/hierarchy/<field_key>', methods=['GET'])
@login_required
def get_hierarchy_values(workspace_id, field_key):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        values = HRService.get_hierarchy_values(workspace_id, field_key)
        return jsonify(values), 200
    except Exception as e:
        return jsonify({"error": f"Failed to load values: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/hierarchy/<field_key>', methods=['POST'])
@login_required
def create_hierarchy_value(workspace_id, field_key):
    membership, err = _check_workspace_admin(workspace_id)
    if err:
        return err
    try:
        data = request.get_json()
        value, error = HRService.create_hierarchy_value(
            workspace_id=workspace_id,
            field_key=field_key,
            name=data.get('name', ''),
            created_by=current_user.email,
            description=data.get('description', ''),
        )
        if error:
            return jsonify({"error": error}), 400
        return jsonify({"message": "Value created successfully", "value": value}), 201
    except Exception as e:
        return jsonify({"error": f"Failed to create value: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/hierarchy/<field_key>/<value_id>', methods=['PUT'])
@login_required
def update_hierarchy_value(workspace_id, field_key, value_id):
    membership, err = _check_workspace_admin(workspace_id)
    if err:
        return err
    try:
        data = request.get_json()
        success, error = HRService.update_hierarchy_value(
            value_id=value_id,
            workspace_id=workspace_id,
            name=data.get('name', ''),
            updated_by=current_user.email,
            description=data.get('description', ''),
        )
        if error:
            return jsonify({"error": error}), 400
        return jsonify({"message": "Value updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to update value: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/hierarchy/<field_key>/<value_id>', methods=['DELETE'])
@login_required
def delete_hierarchy_value(workspace_id, field_key, value_id):
    membership, err = _check_workspace_admin(workspace_id)
    if err:
        return err
    try:
        success, error = HRService.archive_hierarchy_value(value_id, workspace_id, current_user.email)
        if error:
            return jsonify({"error": error}), 404
        return jsonify({"message": "Value archived successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to archive value: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/hierarchy-all', methods=['GET'])
@login_required
def get_all_hierarchy_values(workspace_id):
    """Get all hierarchy values grouped by field_key"""
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        grouped = HRService.get_all_hierarchy_values(workspace_id)
        return jsonify(grouped), 200
    except Exception as e:
        return jsonify({"error": f"Failed to load hierarchy values: {str(e)}"}), 500


# ==================== WORKER API ====================

@hr_portal_bp.route('/<workspace_id>/api/workers', methods=['GET'])
@login_required
def get_workers(workspace_id):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        workers = HRService.get_workers(workspace_id)
        return jsonify(workers), 200
    except Exception as e:
        return jsonify({"error": f"Failed to load workers: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/workers', methods=['POST'])
@login_required
def add_worker(workspace_id):
    membership, err = _check_workspace_admin(workspace_id)
    if err:
        return err
    try:
        data = request.get_json()
        worker, error = HRService.create_worker(workspace_id, data, current_user.email)
        if error:
            return jsonify({"error": error}), 400
        return jsonify({"message": "Worker added successfully", "worker": worker}), 201
    except Exception as e:
        return jsonify({"error": f"Failed to add worker: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/workers/<worker_id>', methods=['GET'])
@login_required
def get_worker(workspace_id, worker_id):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        worker = HRService.get_worker(workspace_id, worker_id)
        if not worker:
            return jsonify({"error": "Worker not found"}), 404
        return jsonify(worker), 200
    except Exception as e:
        return jsonify({"error": f"Failed to load worker: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/workers/<employee_code>', methods=['PUT'])
@login_required
def update_worker(workspace_id, employee_code):
    membership, err = _check_workspace_admin(workspace_id)
    if err:
        return err
    try:
        data = request.get_json()
        worker, error = HRService.update_worker(workspace_id, employee_code, data, current_user.email)
        if error:
            return jsonify({"error": error}), 400
        return jsonify({"message": "Worker updated successfully", "worker": worker}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to update worker: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/workers/<worker_id>', methods=['DELETE'])
@login_required
def delete_worker(workspace_id, worker_id):
    membership, err = _check_workspace_admin(workspace_id)
    if err:
        return err
    try:
        success, error = HRService.delete_worker(workspace_id, worker_id, current_user.email)
        if error:
            return jsonify({"error": error}), 404
        return jsonify({"message": "Worker deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to delete worker: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/workers/<employee_code>/remuneration/history', methods=['GET'])
@login_required
def get_remuneration_history(workspace_id, employee_code):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        history = HRService.get_remuneration_history(workspace_id, employee_code)
        if not history:
            return jsonify({"error": "Worker not found"}), 404
        return jsonify(history), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get remuneration history: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/workers/bulk', methods=['POST'])
@login_required
def bulk_upload_workers(workspace_id):
    membership, err = _check_workspace_admin(workspace_id)
    if err:
        return err
    try:
        data = request.get_json()
        workers_data = data.get('workers', [])
        if not workers_data or not isinstance(workers_data, list):
            return jsonify({"error": "workers array is required"}), 400
        results = HRService.bulk_upload_workers(workspace_id, workers_data, current_user.email)
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": f"Bulk upload failed: {str(e)}"}), 500


# ==================== ATTENDANCE API ====================

@hr_portal_bp.route('/<workspace_id>/api/v1/attendance', methods=['POST'])
@login_required
def create_attendance(workspace_id):
    membership, err = _check_workspace_admin(workspace_id)
    if err:
        return err
    try:
        data = request.get_json()
        attendance, error, metadata = HRService.mark_attendance(
            workspace_id, data, current_user.email
        )
        if error:
            return jsonify({"error": error}), 400

        if metadata.get('should_send_email'):
            email_sent = HRService.send_attendance_notification(
                workspace_id=workspace_id,
                worker_name=attendance.get('worker_name', ''),
                employee_code=attendance.get('employee_code', ''),
                date=attendance.get('date', ''),
                status=attendance.get('status', ''),
                is_update=metadata['is_update'],
                user_email=current_user.email,
            )
            metadata['email_sent'] = email_sent

        if metadata['is_frozen'] and metadata['should_send_email']:
            message = f"Frozen date attendance updated - notification {'sent' if metadata.get('email_sent') else 'failed'}"
        elif metadata['is_frozen']:
            message = "Frozen date attendance updated - no changes detected"
        elif metadata.get('days_ago', 0) > 0:
            settings = HRService.get_settings(workspace_id)
            message = f"Attendance marked successfully (within {settings.get('unfrozen_days', 5)}-day editable period)"
        else:
            message = "Attendance marked successfully"

        status_code = 200 if metadata['is_update'] else 201
        return jsonify({
            "message": message,
            "attendance": attendance,
            "email_sent": metadata.get('email_sent', False),
            "is_frozen": metadata['is_frozen'],
            "days_ago": metadata['days_ago'],
        }), status_code

    except Exception as e:
        current_app.logger.error(f"Attendance error: {e}")
        return jsonify({"error": f"Failed to create attendance: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/v1/attendance/<employee_code>/<date>', methods=['GET'])
@login_required
def get_worker_attendance(workspace_id, employee_code, date):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        from app.models.hr_attendance import HRAttendance
        record = HRAttendance.get_worker_attendance(workspace_id, employee_code.upper(), date)
        if not record:
            return jsonify({"error": f"Attendance not found for {employee_code} on {date}"}), 404
        return jsonify(record.to_dict()), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get attendance: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/v1/attendance/date/<date>', methods=['GET'])
@login_required
def get_attendance_by_date(workspace_id, date):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400
        records = HRService.get_attendance_by_date(workspace_id, date)
        return jsonify(records), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get attendance: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/v1/summary/<date>', methods=['GET'])
@login_required
def get_daily_summary(workspace_id, date):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400
        summary = HRService.get_daily_summary(workspace_id, date)
        return jsonify(summary), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get summary: {str(e)}"}), 500


# ==================== SETTINGS API ====================

@hr_portal_bp.route('/<workspace_id>/api/v1/settings', methods=['GET'])
@login_required
def get_settings(workspace_id):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        settings = HRService.get_settings(workspace_id)
        return jsonify(settings), 200
    except Exception as e:
        return jsonify({"error": f"Failed to load settings: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/v1/settings', methods=['POST'])
@login_required
def update_shift_settings(workspace_id):
    """Update shift-related settings"""
    membership, err = _check_workspace_admin(workspace_id)
    if err:
        return err
    try:
        data = request.get_json()
        settings, error = HRService.update_shift_settings(workspace_id, data, current_user.email)
        if error:
            return jsonify({"error": error}), 400
        return jsonify(settings), 200
    except Exception as e:
        return jsonify({"error": f"Failed to update settings: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/v1/settings/hierarchy', methods=['POST'])
@login_required
def update_hierarchy_config(workspace_id):
    """Update hierarchy field configuration"""
    membership, err = _check_workspace_admin(workspace_id)
    if err:
        return err
    try:
        data = request.get_json()
        hierarchy_fields = data.get('hierarchy_fields', [])
        settings, error = HRService.update_hierarchy_config(workspace_id, hierarchy_fields, current_user.email)
        if error:
            return jsonify({"error": error}), 400
        return jsonify(settings), 200
    except Exception as e:
        return jsonify({"error": f"Failed to update hierarchy config: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/v1/settings/salary', methods=['POST'])
@login_required
def update_salary_config(workspace_id):
    """Update salary component configuration"""
    membership, err = _check_workspace_admin(workspace_id)
    if err:
        return err
    try:
        data = request.get_json()
        salary_components = data.get('salary_components', [])
        settings, error = HRService.update_salary_config(workspace_id, salary_components, current_user.email)
        if error:
            return jsonify({"error": error}), 400
        return jsonify(settings), 200
    except Exception as e:
        return jsonify({"error": f"Failed to update salary config: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/v1/settings/cost', methods=['POST'])
@login_required
def update_cost_config(workspace_id):
    """Update cost calculation configuration"""
    membership, err = _check_workspace_admin(workspace_id)
    if err:
        return err
    try:
        data = request.get_json()
        settings, error = HRService.update_cost_config(workspace_id, data, current_user.email)
        if error:
            return jsonify({"error": error}), 400
        return jsonify(settings), 200
    except Exception as e:
        return jsonify({"error": f"Failed to update cost config: {str(e)}"}), 500


# ==================== COST CALCULATION CRON ====================

@hr_portal_bp.route('/api/cron/calculate-cost', methods=['POST'])
def cron_calculate_cost():
    """
    HTTP endpoint for the 1 AM daily scheduler.
    No auth required (called by Cloud Scheduler).
    Calculates daily cost for all workspaces with workers.
    """
    try:
        data = request.get_json(silent=True) or {}
        date = data.get('date')
        if not date:
            # Default to yesterday (since cron runs at 1 AM, calculate previous day)
            from datetime import timedelta
            date = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')

        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400

        results = HRService.calculate_all_workspaces_cost(date)
        return jsonify({
            "message": f"Cost calculation completed for {date}",
            "date": date,
            "results": results,
        }), 200
    except Exception as e:
        return jsonify({"error": f"Cost calculation failed: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/cron/calculate-cost', methods=['POST'])
def cron_calculate_workspace_cost(workspace_id):
    """
    HTTP endpoint to calculate cost for a single workspace.
    No auth required (called by Cloud Scheduler or admin tools).
    """
    try:
        data = request.get_json(silent=True) or {}
        date = data.get('date')
        if not date:
            from datetime import timedelta
            date = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')

        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400

        result = HRService.calculate_daily_cost(workspace_id, date)
        return jsonify({
            "message": f"Cost calculated for workspace {workspace_id} on {date}",
            "date": date,
            "summary": result.get('summary', {}),
            "metadata": result.get('calculation_metadata', {}),
        }), 200
    except Exception as e:
        return jsonify({"error": f"Cost calculation failed: {str(e)}"}), 500


# ==================== COST ANALYTICS API ====================

@hr_portal_bp.route('/<workspace_id>/api/cost-analytics/summary', methods=['GET'])
@login_required
def get_cost_summary(workspace_id):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        if not start_date or not end_date:
            return jsonify({"error": "start_date and end_date are required"}), 400
        summary = HRService.get_cost_summary(workspace_id, start_date, end_date)
        return jsonify(summary), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get cost summary: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/cost-analytics/hierarchy-breakdown', methods=['GET'])
@login_required
def get_hierarchy_breakdown(workspace_id):
    """Get cost breakdown by any hierarchy field. Pass ?field_key=department (default)"""
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        field_key = request.args.get('field_key', 'department')
        if not start_date or not end_date:
            return jsonify({"error": "start_date and end_date are required"}), 400
        breakdown = HRService.get_hierarchy_breakdown(workspace_id, start_date, end_date, field_key)
        return jsonify(breakdown), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get breakdown: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/cost-analytics/daily-breakdown', methods=['GET'])
@login_required
def get_daily_breakdown(workspace_id):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        if not start_date or not end_date:
            return jsonify({"error": "start_date and end_date are required"}), 400
        daily = HRService.get_daily_cost_breakdown(workspace_id, start_date, end_date)
        return jsonify(daily), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get daily breakdown: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/cost-analytics/worker-cost', methods=['GET'])
@login_required
def get_worker_cost(workspace_id):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        employee_code = request.args.get('employee_code', '').strip().upper()
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        if not employee_code or not start_date or not end_date:
            return jsonify({"error": "employee_code, start_date and end_date are required"}), 400
        result = HRService.get_worker_cost(workspace_id, employee_code, start_date, end_date)
        if not result:
            return jsonify({"error": f"No cost data found for {employee_code}"}), 404
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get worker cost: {str(e)}"}), 500


@hr_portal_bp.route('/<workspace_id>/api/cost-analytics/workers-list', methods=['GET'])
@login_required
def get_workers_list_for_analytics(workspace_id):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        workers = HRService.get_workers(workspace_id)
        return jsonify(workers), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get workers list: {str(e)}"}), 500


# ==================== REPORTS API ====================

@hr_portal_bp.route('/<workspace_id>/api/reports/summary', methods=['GET'])
@login_required
def get_summary_report(workspace_id):
    membership, err = _check_workspace_access(workspace_id)
    if err:
        return err
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        if not start_date or not end_date:
            return jsonify({"error": "start_date and end_date are required"}), 400

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

        if start > end:
            return jsonify({"error": "start_date must be before end_date"}), 400

        from datetime import timedelta
        report_data = []
        current_date = start
        while current_date <= end:
            date_str = current_date.strftime('%Y-%m-%d')
            summary = HRService.get_daily_summary(workspace_id, date_str)
            if summary.get('total_workers', 0) > 0:
                report_data.append(summary)
            current_date += timedelta(days=1)

        return jsonify({
            'start_date': start_date,
            'end_date': end_date,
            'data': report_data,
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed to generate report: {str(e)}"}), 500
