"""
Daily HR Cost Calculation Service for Google Cloud Platform
Reads worker data from kbi-first/hr_workers/
Reads attendance from kbi-first/hr_attendance_v1/
Reads settings from kbi-first/hr_portal/settings.json
Calculates costs and stores to kbi-first/hr_cost/

UPDATED: 
- Added date range recalculation functionality
- Skips Sundays and Indian public holidays
"""

import os
import json
from datetime import datetime, timedelta
from google.cloud import storage
import calendar
from typing import List, Dict, Optional
import traceback
import holidays

# ============================================================================
# CONFIGURATION
# ============================================================================

# Environment variables with defaults
HOURS_PER_DAY = float(os.getenv('HOURS_PER_DAY', '8'))
GCS_BUCKET = os.getenv('GCS_BUCKET', 'kbi-first')

# Source folders
WORKERS_FOLDER = os.getenv('WORKERS_FOLDER', 'hr_workers')
ATTENDANCE_FOLDER = os.getenv('ATTENDANCE_FOLDER', 'hr_attendance_v1')
OUTPUT_FOLDER = os.getenv('OUTPUT_FOLDER', 'hr_cost')
SETTINGS_FILE = os.getenv('SETTINGS_FILE', 'hr_portal/settings.json')

# Global settings cache (loaded at runtime)
_cached_settings = None

# Initialize Indian holidays calendar
INDIAN_HOLIDAYS = holidays.India()

# ============================================================================
# HOLIDAY & WEEKEND CHECKING
# ============================================================================

def is_sunday(date_obj: datetime) -> bool:
    """Check if date is a Sunday (weekday 6)"""
    return date_obj.weekday() == 6


def is_indian_holiday(date_obj: datetime) -> bool:
    """Check if date is an Indian public holiday"""
    return date_obj.date() in INDIAN_HOLIDAYS


def is_non_working_day(date_obj: datetime) -> bool:
    """
    Check if date is a non-working day (Sunday or Indian public holiday)
    Returns: (is_non_working, reason)
    """
    if is_sunday(date_obj):
        return True, "Sunday"
    
    if is_indian_holiday(date_obj):
        holiday_name = INDIAN_HOLIDAYS.get(date_obj.date())
        return True, f"Holiday: {holiday_name}"
    
    return False, None

# ============================================================================
# SETTINGS FUNCTIONS
# ============================================================================

def load_settings_from_gcs(bucket_name: str) -> Dict:
    """
    Load settings from GCS hr_portal/settings.json
    Returns settings with unfrozen_days, default_shift_hours, etc.
    """
    global _cached_settings
    
    # Return cached if already loaded
    if _cached_settings is not None:
        return _cached_settings
    
    try:
        print(f"⚙️  Loading settings from gs://{bucket_name}/{SETTINGS_FILE}")
        
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(SETTINGS_FILE)
        
        if not blob.exists():
            print(f"   ⚠️  Settings file not found, using defaults")
            _cached_settings = {
                'unfrozen_days': 2,
                'default_shift_hours': 8,
                'total_shifts_available': 2
            }
            return _cached_settings
        
        content = blob.download_as_text()
        settings = json.loads(content)
        
        # Ensure unfrozen_days exists
        if 'unfrozen_days' not in settings:
            settings['unfrozen_days'] = 2
        
        _cached_settings = settings
        print(f"   ✅ Loaded settings: unfrozen_days={settings.get('unfrozen_days')}, hours={settings.get('default_shift_hours')}")
        
        return settings
        
    except Exception as e:
        print(f"   ⚠️  Error loading settings: {e}")
        print(f"   ℹ️  Using default settings")
        _cached_settings = {
            'unfrozen_days': 2,
            'default_shift_hours': 8,
            'total_shifts_available': 2
        }
        return _cached_settings


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_days_in_month(year: int, month: int) -> int:
    """Get actual days in a specific month (handles leap years)"""
    return calendar.monthrange(year, month)[1]


def calculate_frozen_date(bucket_name: str) -> datetime:
    """Calculate which date becomes frozen today based on settings"""
    settings = load_settings_from_gcs(bucket_name)
    unfrozen_days = settings.get('unfrozen_days', 2)
    
    today = datetime.now()
    frozen_date = today - timedelta(days=unfrozen_days)
    return frozen_date.replace(hour=0, minute=0, second=0, microsecond=0)


def check_if_already_processed(bucket_name: str, date_obj: datetime) -> bool:
    """Check if calculation already exists for this date"""
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        
        blob_path = f"{OUTPUT_FOLDER}/{date_obj.year}/{date_obj.month:02d}/{date_obj.strftime('%Y-%m-%d')}.json"
        blob = bucket.blob(blob_path)
        
        exists = blob.exists()
        if exists:
            print(f"   ℹ️  Found existing calculation at: {blob_path}")
        return exists
        
    except Exception as e:
        print(f"   ⚠️  Error checking processed status: {e}")
        return False


# ============================================================================
# DATA FETCHING FROM GCS
# ============================================================================

def fetch_worker_data_from_gcs(bucket_name: str) -> List[Dict]:
    """
    Fetch all active workers from GCS bucket
    Source: kbi-first/hr_workers/<employee_code>.json
    """
    try:
        print(f"📡 Fetching worker data from gs://{bucket_name}/{WORKERS_FOLDER}/")
        
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        
        # List all blobs in hr_workers folder
        blobs = bucket.list_blobs(prefix=f"{WORKERS_FOLDER}/")
        
        workers = []
        inactive_count = 0
        error_count = 0
        
        for blob in blobs:
            # Skip if not a JSON file
            if not blob.name.endswith('.json'):
                continue
            
            try:
                # Download and parse JSON
                content = blob.download_as_text()
                worker_data = json.loads(content)
                
                # Skip inactive workers
                if not worker_data.get('is_active', True):
                    inactive_count += 1
                    continue
                
                # Skip deleted workers
                if worker_data.get('deleted_at') is not None:
                    inactive_count += 1
                    continue
                
                # Extract remuneration (current active salary)
                remuneration = worker_data.get('remuneration', {})
                history = remuneration.get('history', [])
                
                # Find active salary version
                active_salary = None
                for salary_record in history:
                    if salary_record.get('is_active', False):
                        active_salary = salary_record
                        break
                
                if not active_salary:
                    print(f"   ⚠️  No active salary for {worker_data.get('employee_code')}")
                    error_count += 1
                    continue
                
                # Build worker record
                workers.append({
                    'worker_id': worker_data.get('unique_worker_id'),
                    'employee_code': worker_data.get('employee_code'),
                    'name': worker_data.get('operator_name', ''),
                    'department': worker_data.get('department', ''),
                    'designation': worker_data.get('designation', ''),
                    'basic': float(active_salary.get('basic_salary', 0)),
                    'hra': float(active_salary.get('hra', 0)),
                    'date_of_joining': worker_data.get('date_of_joining'),
                    'salary_version': active_salary.get('version', 1),
                    'salary_effective_date': active_salary.get('effective_date')
                })
                
            except json.JSONDecodeError as e:
                print(f"   ⚠️  JSON decode error for {blob.name}: {e}")
                error_count += 1
            except Exception as e:
                print(f"   ⚠️  Error processing {blob.name}: {e}")
                error_count += 1
        
        print(f"✅ Fetched {len(workers)} active workers")
        print(f"   ℹ️  Skipped {inactive_count} inactive/deleted workers")
        if error_count > 0:
            print(f"   ⚠️  {error_count} workers had errors")
        
        return workers
        
    except Exception as e:
        print(f"❌ Error fetching worker data: {e}")
        raise


def fetch_attendance_data_from_gcs(bucket_name: str, date_str: str) -> List[Dict]:
    """
    Fetch attendance data for a specific date from GCS
    Source: kbi-first/hr_attendance_v1/<date>/<employee_code>.json
    """
    try:
        print(f"📡 Fetching attendance for {date_str} from gs://{bucket_name}/{ATTENDANCE_FOLDER}/")
        
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        
        # Construct prefix for the date folder
        attendance_prefix = f"{ATTENDANCE_FOLDER}/{date_str}/"
        
        # List all attendance files for this date
        blobs = bucket.list_blobs(prefix=attendance_prefix)
        
        attendance_records = []
        error_count = 0
        
        for blob in blobs:
            # Skip if not a JSON file
            if not blob.name.endswith('.json'):
                continue
            
            try:
                # Download and parse JSON
                content = blob.download_as_text()
                attendance_data = json.loads(content)
                
                # Extract attendance info
                attendance_records.append({
                    'employee_code': attendance_data.get('employee_code'),
                    'worker_id': attendance_data.get('worker_id'),
                    'worker_name': attendance_data.get('worker_name', ''),
                    'department': attendance_data.get('department', ''),
                    'date': attendance_data.get('date'),
                    'status': attendance_data.get('status', 'UNKNOWN'),
                    'hours_worked': float(attendance_data.get('hours_worked', 0)),
                    'shifts_worked': attendance_data.get('shifts_worked', 0),
                    'remarks': attendance_data.get('remarks', ''),
                    'auto_marked': attendance_data.get('auto_marked', False)
                })
                
            except json.JSONDecodeError as e:
                print(f"   ⚠️  JSON decode error for {blob.name}: {e}")
                error_count += 1
            except Exception as e:
                print(f"   ⚠️  Error processing {blob.name}: {e}")
                error_count += 1
        
        print(f"✅ Fetched {len(attendance_records)} attendance records")
        if error_count > 0:
            print(f"   ⚠️  {error_count} records had errors")
        
        return attendance_records
        
    except Exception as e:
        print(f"❌ Error fetching attendance data: {e}")
        raise


# ============================================================================
# CALCULATION LOGIC
# ============================================================================

def calculate_daily_costs(workers: List[Dict], attendance: List[Dict], frozen_date: datetime) -> Dict:
    """
    Calculate daily costs for all workers
    """
    days_in_month = get_days_in_month(frozen_date.year, frozen_date.month)
    
    # Create attendance lookup by employee_code
    attendance_map = {
        rec['employee_code']: rec 
        for rec in attendance 
        if rec.get('employee_code')
    }
    
    print(f"💰 Calculating costs for {len(workers)} workers...")
    print(f"   📅 Days in month: {days_in_month}")
    print(f"   ⏰ Hours per day: {HOURS_PER_DAY}")
    
    worker_calculations = []
    total_cost = 0
    total_hours = 0
    present_count = 0
    absent_count = 0
    
    for worker in workers:
        employee_code = worker['employee_code']
        monthly_salary = worker['basic'] + worker['hra']
        
        # Calculate hourly rate
        hourly_salary = monthly_salary / (days_in_month * HOURS_PER_DAY)
        
        # Get attendance record
        attendance_rec = attendance_map.get(employee_code)
        
        if attendance_rec:
            hours_worked = attendance_rec['hours_worked']
            status = attendance_rec['status']
            remarks = attendance_rec.get('remarks', '')
        else:
            # No attendance record means absent
            hours_worked = 0
            status = 'NO_RECORD'
            remarks = 'No attendance record found'
        
        # Calculate today's salary
        todays_salary = hours_worked * hourly_salary
        
        # Build worker calculation record
        worker_calculations.append({
            'employee_code': employee_code,
            'worker_id': worker['worker_id'],
            'worker_name': worker['name'],
            'department': worker['department'],
            'designation': worker['designation'],
            'salary_info': {
                'monthly_salary': round(monthly_salary, 2),
                'basic': round(worker['basic'], 2),
                'hra': round(worker['hra'], 2),
                'hourly_rate': round(hourly_salary, 2),
                'salary_version': worker['salary_version'],
                'effective_date': worker['salary_effective_date']
            },
            'attendance_info': {
                'status': status,
                'hours_worked': hours_worked,
                'shifts_worked': attendance_rec.get('shifts_worked', 0) if attendance_rec else 0,
                'remarks': remarks,
                'auto_marked': attendance_rec.get('auto_marked', False) if attendance_rec else False
            },
            'todays_salary': round(todays_salary, 2)
        })
        
        total_cost += todays_salary
        total_hours += hours_worked
        
        if hours_worked > 0:
            present_count += 1
        else:
            absent_count += 1
    
    print(f"   ✅ Present: {present_count}, Absent: {absent_count}")
    print(f"   💵 Total cost: ₹{total_cost:,.2f}")
    print(f"   ⏱️  Total hours: {total_hours:.2f}")
    
    return {
        'date': frozen_date.strftime('%Y-%m-%d'),
        'calculation_metadata': {
            'days_in_month': days_in_month,
            'hours_per_day': HOURS_PER_DAY,
            'unfrozen_days': load_settings_from_gcs(GCS_BUCKET).get('unfrozen_days', 2),
            'total_workers': len(workers),
            'present_workers': present_count,
            'absent_workers': absent_count
        },
        'summary': {
            'total_company_cost': round(total_cost, 2),
            'total_attendance_hours': round(total_hours, 2),
            'average_hours_per_worker': round(total_hours / len(workers), 2) if workers else 0,
            'average_cost_per_worker': round(total_cost / len(workers), 2) if workers else 0
        },
        'workers': worker_calculations,
        'created_at': datetime.now().isoformat(),
        'processed_by': 'daily-hr-cost-calculator-v2',
        'source_buckets': {
            'workers': f'gs://{GCS_BUCKET}/{WORKERS_FOLDER}/',
            'attendance': f'gs://{GCS_BUCKET}/{ATTENDANCE_FOLDER}/{frozen_date.strftime("%Y-%m-%d")}/'
        }
    }


def store_to_gcs(bucket_name: str, data: Dict, frozen_date: datetime):
    """Store calculation results to Google Cloud Storage"""
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        
        # Construct hierarchical path
        blob_path = f"{OUTPUT_FOLDER}/{frozen_date.year}/{frozen_date.month:02d}/{frozen_date.strftime('%Y-%m-%d')}.json"
        blob = bucket.blob(blob_path)
        
        # Upload with proper content type
        blob.upload_from_string(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type='application/json'
        )
        
        print(f"✅ Successfully stored data to: gs://{bucket_name}/{blob_path}")
        return blob_path
        
    except Exception as e:
        print(f"❌ Error storing to GCS: {e}")
        raise


# ============================================================================
# MAIN HANDLER
# ============================================================================

def get_last_processed_date(bucket_name: str) -> Optional[datetime]:
    """Find the most recent date that has been processed"""
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        
        # List all files in the output folder
        blobs = list(bucket.list_blobs(prefix=f"{OUTPUT_FOLDER}/"))
        
        if not blobs:
            return None
        
        # Extract dates from blob paths (format: hr_cost/YYYY/MM/YYYY-MM-DD.json)
        dates = []
        for blob in blobs:
            if blob.name.endswith('.json'):
                try:
                    # Extract filename (YYYY-MM-DD.json)
                    filename = blob.name.split('/')[-1]
                    date_str = filename.replace('.json', '')
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    dates.append(date_obj)
                except (ValueError, IndexError):
                    continue
        
        if not dates:
            return None
        
        # Return the most recent date
        last_date = max(dates)
        print(f"   📅 Last processed date found: {last_date.strftime('%Y-%m-%d')}")
        return last_date
        
    except Exception as e:
        print(f"   ⚠️  Error finding last processed date: {e}")
        return None


def process_single_date(date_obj: datetime, force_recalculate: bool = False) -> Dict:
    """Process calculation for a single date"""
    date_str = date_obj.strftime('%Y-%m-%d')
    
    print(f"\n{'='*80}")
    print(f"📅 Processing date: {date_str}")
    print(f"{'='*80}")
    
    # Check if it's a non-working day (Sunday or Indian holiday)
    is_non_working, reason = is_non_working_day(date_obj)
    if is_non_working:
        print(f"   🚫 Skipping: {reason}")
        return {
            'date': date_str,
            'status': 'skipped',
            'reason': reason.lower().replace(' ', '_'),
            'message': f'Skipped - {reason}'
        }
    
    # Check if already processed (skip if not forcing recalculation)
    if not force_recalculate and check_if_already_processed(GCS_BUCKET, date_obj):
        print(f"   ⏭️  Already processed. Skipping...")
        return {
            'date': date_str,
            'status': 'skipped',
            'reason': 'already_processed'
        }
    
    if force_recalculate:
        print(f"   🔄 Force recalculate enabled")
    
    # Fetch worker data
    print(f"\n👥 Fetching worker data...")
    workers = fetch_worker_data_from_gcs(GCS_BUCKET)
    
    if not workers:
        return {
            'date': date_str,
            'status': 'error',
            'error': 'No active workers found'
        }
    
    # Fetch attendance data
    print(f"\n📋 Fetching attendance data...")
    attendance = fetch_attendance_data_from_gcs(GCS_BUCKET, date_str)
    
    # Calculate costs
    print(f"\n💰 Calculating costs...")
    calculation_result = calculate_daily_costs(workers, attendance, date_obj)
    
    # Store to GCS
    print(f"\n💾 Storing results...")
    output_path = store_to_gcs(GCS_BUCKET, calculation_result, date_obj)
    
    print(f"\n✅ Completed for {date_str}")
    print(f"   Total Cost: ₹{calculation_result['summary']['total_company_cost']:,.2f}")
    print(f"   Present: {calculation_result['calculation_metadata']['present_workers']}")
    
    return {
        'date': date_str,
        'status': 'success',
        'summary': calculation_result['summary'],
        'metadata': calculation_result['calculation_metadata'],
        'output_path': f'gs://{GCS_BUCKET}/{output_path}'
    }


def main(request=None):
    """
    Main entry point for Cloud Function or Cloud Run
    
    Supports three modes:
    1. AUTO MODE (default): Calculate from last processed date to last unfrozen day
    2. MANUAL MODE: Recalculate a specific date
    3. RANGE MODE: Recalculate a range of dates
    
    Query parameters:
    - date: Specific date to process (format: YYYY-MM-DD)
    - start_date: Start date for range processing (format: YYYY-MM-DD)
    - end_date: End date for range processing (format: YYYY-MM-DD)
    - force: Set to 'true' to recalculate even if already processed
    
    Examples:
    - Auto mode: GET /
    - Manual mode: GET /?date=2026-01-15
    - Range mode: GET /?start_date=2026-01-01&end_date=2026-01-15
    - Force recalculate: GET /?date=2026-01-15&force=true
    - Force range recalculate: GET /?start_date=2026-01-01&end_date=2026-01-15&force=true
    """
    try:
        print("=" * 80)
        print("🚀 Daily HR Cost Calculation Service - STARTING")
        print(f"   📅 Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
        print("=" * 80)
        
        # Parse query parameters
        specific_date = None
        start_date_param = None
        end_date_param = None
        force_recalculate = False
        
        if request:
            request_json = request.get_json(silent=True)
            request_args = request.args
            
            # Check for date parameter (from JSON or query string)
            if request_json and 'date' in request_json:
                specific_date = request_json.get('date')
            elif request_args and 'date' in request_args:
                specific_date = request_args.get('date')
            
            # Check for start_date and end_date parameters
            if request_json:
                start_date_param = request_json.get('start_date')
                end_date_param = request_json.get('end_date')
            elif request_args:
                start_date_param = request_args.get('start_date')
                end_date_param = request_args.get('end_date')
            
            # Check for force parameter
            if request_json and request_json.get('force') in ['true', True]:
                force_recalculate = True
            elif request_args and request_args.get('force') == 'true':
                force_recalculate = True
        
        # RANGE MODE: Process date range
        if start_date_param and end_date_param:
            print(f"\n📅 RANGE MODE: Processing date range")
            print(f"   Start date: {start_date_param}")
            print(f"   End date: {end_date_param}")
            print(f"   Force recalculate: {force_recalculate}")
            
            try:
                start_date = datetime.strptime(start_date_param, '%Y-%m-%d')
                end_date = datetime.strptime(end_date_param, '%Y-%m-%d')
            except ValueError as e:
                return {
                    'status': 'error',
                    'message': f'Invalid date format. Use YYYY-MM-DD. Error: {str(e)}'
                }, 400
            
            # Validate date range
            if start_date > end_date:
                return {
                    'status': 'error',
                    'message': f'start_date ({start_date_param}) cannot be after end_date ({end_date_param})'
                }, 400
            
            # Calculate all dates in range
            dates_to_process = []
            current_date = start_date
            while current_date <= end_date:
                dates_to_process.append(current_date)
                current_date += timedelta(days=1)
            
            print(f"\n📋 Dates to process: {len(dates_to_process)}")
            if len(dates_to_process) <= 10:
                for d in dates_to_process:
                    print(f"   - {d.strftime('%Y-%m-%d')}")
            else:
                print(f"   - {dates_to_process[0].strftime('%Y-%m-%d')} to {dates_to_process[-1].strftime('%Y-%m-%d')}")
            
            # Process each date in range
            results = []
            for date_obj in dates_to_process:
                try:
                    result = process_single_date(date_obj, force_recalculate)
                    results.append(result)
                except Exception as e:
                    print(f"\n❌ Error processing {date_obj.strftime('%Y-%m-%d')}: {e}")
                    results.append({
                        'date': date_obj.strftime('%Y-%m-%d'),
                        'status': 'error',
                        'error': str(e)
                    })
            
            # Summary
            successful = [r for r in results if r['status'] == 'success']
            skipped = [r for r in results if r['status'] == 'skipped']
            errors = [r for r in results if r['status'] == 'error']
            
            # Break down skipped reasons
            skipped_holidays = [r for r in skipped if 'holiday' in r.get('reason', '')]
            skipped_sundays = [r for r in skipped if 'sunday' in r.get('reason', '')]
            skipped_already_processed = [r for r in skipped if r.get('reason') == 'already_processed']
            
            # Calculate total costs
            total_cost = sum(r['summary']['total_company_cost'] for r in successful if 'summary' in r)
            
            print("\n" + "=" * 80)
            print("✅ RANGE CALCULATION COMPLETED")
            print("=" * 80)
            print(f"📊 Summary:")
            print(f"   Date Range: {start_date_param} to {end_date_param}")
            print(f"   Total dates: {len(results)}")
            print(f"   Successful: {len(successful)}")
            print(f"   Skipped: {len(skipped)}")
            if skipped_sundays:
                print(f"      - Sundays: {len(skipped_sundays)}")
            if skipped_holidays:
                print(f"      - Holidays: {len(skipped_holidays)}")
            if skipped_already_processed:
                print(f"      - Already processed: {len(skipped_already_processed)}")
            print(f"   Errors: {len(errors)}")
            print(f"   Total Cost: ₹{total_cost:,.2f}")
            print("=" * 80)
            
            return {
                'status': 'success',
                'message': f'Processed {len(results)} dates from {start_date_param} to {end_date_param}',
                'start_date': start_date_param,
                'end_date': end_date_param,
                'force_recalculate': force_recalculate,
                'summary': {
                    'total': len(results),
                    'successful': len(successful),
                    'skipped': len(skipped),
                    'skipped_sundays': len(skipped_sundays),
                    'skipped_holidays': len(skipped_holidays),
                    'skipped_already_processed': len(skipped_already_processed),
                    'errors': len(errors),
                    'total_cost': round(total_cost, 2)
                },
                'results': results
            }, 200
        
        # MANUAL MODE: Process specific date
        if specific_date:
            print(f"\n🎯 MANUAL MODE: Processing specific date")
            print(f"   Requested date: {specific_date}")
            print(f"   Force recalculate: {force_recalculate}")
            
            try:
                date_obj = datetime.strptime(specific_date, '%Y-%m-%d')
            except ValueError:
                return {
                    'status': 'error',
                    'message': f'Invalid date format: {specific_date}. Use YYYY-MM-DD'
                }, 400
            
            result = process_single_date(date_obj, force_recalculate)
            
            print("\n" + "=" * 80)
            print("✅ MANUAL CALCULATION COMPLETED")
            print("=" * 80)
            
            return result, 200
        
        # AUTO MODE: Process from last processed date to last unfrozen day
        print(f"\n🤖 AUTO MODE: Backfill from last processed date")
        
        # Calculate last unfrozen date (today - unfrozen_days)
        last_unfrozen_date = calculate_frozen_date(GCS_BUCKET)
        unfrozen_days_setting = load_settings_from_gcs(GCS_BUCKET).get('unfrozen_days', 2)
        print(f"\n📅 Last unfrozen date: {last_unfrozen_date.strftime('%Y-%m-%d')}")
        print(f"   (Current date - {unfrozen_days_setting} unfrozen days)")
        
        # Find last processed date
        print(f"\n🔍 Finding last processed date...")
        last_processed_date = get_last_processed_date(GCS_BUCKET)
        
        if last_processed_date is None:
            print(f"   ⚠️  No previous calculations found!")
            print(f"   📍 Will start from: {last_unfrozen_date.strftime('%Y-%m-%d')}")
            start_date = last_unfrozen_date
        else:
            # Start from day after last processed
            start_date = last_processed_date + timedelta(days=1)
            print(f"   📍 Will start from: {start_date.strftime('%Y-%m-%d')}")
        
        # Check if there's anything to process
        if start_date > last_unfrozen_date:
            message = f"✅ All dates up to {last_unfrozen_date.strftime('%Y-%m-%d')} are already processed!"
            print(f"\n{message}")
            print("=" * 80)
            return {
                'status': 'success',
                'message': message,
                'last_processed': last_processed_date.strftime('%Y-%m-%d') if last_processed_date else None,
                'last_unfrozen': last_unfrozen_date.strftime('%Y-%m-%d'),
                'dates_processed': []
            }, 200
        
        # Calculate all dates to process
        dates_to_process = []
        current_date = start_date
        while current_date <= last_unfrozen_date:
            dates_to_process.append(current_date)
            current_date += timedelta(days=1)
        
        print(f"\n📋 Dates to process: {len(dates_to_process)}")
        for d in dates_to_process:
            print(f"   - {d.strftime('%Y-%m-%d')}")
        
        # Process each date
        results = []
        for date_obj in dates_to_process:
            try:
                result = process_single_date(date_obj, force_recalculate=False)
                results.append(result)
            except Exception as e:
                print(f"\n❌ Error processing {date_obj.strftime('%Y-%m-%d')}: {e}")
                results.append({
                    'date': date_obj.strftime('%Y-%m-%d'),
                    'status': 'error',
                    'error': str(e)
                })
        
        # Summary
        successful = [r for r in results if r['status'] == 'success']
        skipped = [r for r in results if r['status'] == 'skipped']
        errors = [r for r in results if r['status'] == 'error']
        
        # Break down skipped reasons
        skipped_holidays = [r for r in skipped if 'holiday' in r.get('reason', '')]
        skipped_sundays = [r for r in skipped if 'sunday' in r.get('reason', '')]
        skipped_already_processed = [r for r in skipped if r.get('reason') == 'already_processed']
        
        print("\n" + "=" * 80)
        print("✅ AUTO BACKFILL COMPLETED")
        print("=" * 80)
        print(f"📊 Summary:")
        print(f"   Total dates: {len(results)}")
        print(f"   Successful: {len(successful)}")
        print(f"   Skipped: {len(skipped)}")
        if skipped_sundays:
            print(f"      - Sundays: {len(skipped_sundays)}")
        if skipped_holidays:
            print(f"      - Holidays: {len(skipped_holidays)}")
        if skipped_already_processed:
            print(f"      - Already processed: {len(skipped_already_processed)}")
        print(f"   Errors: {len(errors)}")
        print("=" * 80)
        
        return {
            'status': 'success',
            'message': f'Processed {len(results)} dates',
            'last_processed': last_processed_date.strftime('%Y-%m-%d') if last_processed_date else None,
            'last_unfrozen': last_unfrozen_date.strftime('%Y-%m-%d'),
            'summary': {
                'total': len(results),
                'successful': len(successful),
                'skipped': len(skipped),
                'skipped_sundays': len(skipped_sundays),
                'skipped_holidays': len(skipped_holidays),
                'skipped_already_processed': len(skipped_already_processed),
                'errors': len(errors)
            },
            'results': results
        }, 200
        
    except Exception as e:
        print("\n" + "=" * 80)
        print(f"❌ FATAL ERROR: {str(e)}")
        print("=" * 80)
        traceback.print_exc()
        
        return {
            'status': 'error',
            'message': str(e),
            'error_type': type(e).__name__
        }, 500


# ============================================================================
# ENTRY POINTS
# ============================================================================

# For Cloud Functions (Gen 2)
def calculate_daily_cost(request):
    """Cloud Functions HTTP entry point"""
    return main(request)


# For Cloud Run
if __name__ == "__main__":
    import sys
    
    # Local testing
    print("🧪 Running in LOCAL TEST MODE")
    result, status_code = main()
    print(f"\n📊 Final Result (Status {status_code}):")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    sys.exit(0 if status_code == 200 else 1)