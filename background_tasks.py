import os
from datetime import datetime, timedelta, timezone
import threading
import time
import schedule
import requests
from flask import url_for
from models import User, StepLog, db, get_active_event, is_in_active_event
from utils.time_utils import get_points_multiplier
from utils.logging_config import log_activity
import logging

logger = logging.getLogger('background_tasks')

# Utility function to ensure datetime objects are timezone-aware
def ensure_tz_aware(dt):
    """Make sure a datetime object is timezone-aware (UTC)"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

# Add this function to convert SQLAlchemy datetime results to timezone-aware
def ensure_db_times_are_tz_aware(query_result):
    """Ensure all datetime attributes in SQLAlchemy query results have timezone information"""
    if not query_result:
        return query_result
        
    # For single objects
    if hasattr(query_result, '__table__'):
        for column in query_result.__table__.columns:
            if isinstance(column.type, db.DateTime) or isinstance(column.type, db.TIMESTAMP):
                value = getattr(query_result, column.name)
                if value and value.tzinfo is None:
                    setattr(query_result, column.name, value.replace(tzinfo=timezone.utc))
        return query_result
    
    # For lists of objects
    if isinstance(query_result, list):
        for item in query_result:
            ensure_db_times_are_tz_aware(item)
    
    return query_result

def sync_google_fit_for_user(user):
    """Sync Google Fit data for a specific user"""
    if not user.google_fit_token or not user.google_refresh_token:
        logger.info(f"User {user.id} has no Google Fit tokens")
        return False
        
    try:
        # Refresh token if needed
        current_time = datetime.now(timezone.utc)
        
        # Make sure google_token_expiry is timezone-aware before comparison
        token_expiry = ensure_tz_aware(user.google_token_expiry)
            
        if token_expiry and current_time > token_expiry:
            refresh_successful = refresh_google_fit_token(user)
            if not refresh_successful:
                return False
                
        # Calculate date range - only fetch recent data (last 24 hours)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=1)
        
        # Convert to milliseconds for Google Fit API
        end_time_ms = int(end_time.timestamp() * 1000)
        start_time_ms = int(start_time.timestamp() * 1000)
        
        # Build Google Fit API request
        headers = {
            'Authorization': f'Bearer {user.google_fit_token}'
        }
        
        # Use Google Fit REST API to fetch step count
        url = "https://www.googleapis.com/fitness/v1/users/me/dataset:aggregate"
        body = {
            "aggregateBy": [{
                "dataTypeName": "com.google.step_count.delta",
                "dataSourceId": "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps"
            }],
            "bucketByTime": {"durationMillis": 86400000},  # 24 hours
            "startTimeMillis": start_time_ms,
            "endTimeMillis": end_time_ms
        }
        
        response = requests.post(url, json=body, headers=headers)
        if response.status_code != 200:
            logger.error(f"Google Fit API error for user {user.id}: {response.status_code} - {response.text}")
            return False
            
        data = response.json()
        
        # Process the response to get step count
        steps = 0
        if 'bucket' in data:
            for bucket in data['bucket']:
                if 'dataset' in bucket:
                    for dataset in bucket['dataset']:
                        if 'point' in dataset:
                            for point in dataset['point']:
                                if 'value' in point:
                                    for value in point['value']:
                                        if 'intVal' in value:
                                            steps += value['intVal']
        
        if steps == 0:
            logger.info(f"No new steps found for user {user.id}")
            return False
            
        # Compare with existing step logs to avoid double counting
        # Get the most recent step log for today
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        
        latest_log = StepLog.query.filter(
            StepLog.user_id == user.id,
            StepLog.timestamp >= today,
            StepLog.timestamp < tomorrow,
            StepLog.source == 'google_fit'
        ).order_by(StepLog.steps.desc()).first()
        
        # Make sure latest_log timestamps are timezone-aware
        latest_log = ensure_db_times_are_tz_aware(latest_log)

        # If we already have more steps logged today, don't update
        if latest_log and latest_log.steps >= steps:
            logger.info(f"User {user.id} already has more steps ({latest_log.steps}) than Google Fit ({steps})")
            return False
        
        # Calculate incremental steps if we have existing logs
        incremental_steps = steps
        if latest_log:
            incremental_steps = steps - latest_log.steps
            
        if incremental_steps <= 0:
            logger.info(f"No new steps to log for user {user.id}")
            return False
            
        # Calculate points (1 point per 100 steps)
        multiplier = get_points_multiplier()
        points = (incremental_steps // 100) * multiplier
        
        # Create new step log
        log = StepLog(
            user_id=user.id, 
            steps=steps, 
            points=points,
            source='google_fit'
        )
        
        # Update user stats with only the incremental steps
        user.total_steps = (user.total_steps or 0) + incremental_steps
        user.total_points += points
        
        # Only update house points if within active event or no event exists
        # Convert timestamp to timezone-aware before checking
        current_time_aware = datetime.now(timezone.utc)
        event_active = is_in_active_event(current_time_aware)
        
        if event_active:
            # Update house points
            house = user.get_house()
            if house:
                house.total_points += points
                # Make sure the house has total_steps attribute before updating
                if hasattr(house, 'total_steps'):
                    house.total_steps = (house.total_steps or 0) + incremental_steps
        
        db.session.add(log)
        db.session.commit()
        
        # Log activity
        log_activity(logger, user.id, 'Google Fit Sync', f'Added {incremental_steps} steps automatically')
        
        logger.info(f"Successfully synced {incremental_steps} steps for user {user.id}")
        return True
        
    except Exception as e:
        logger.error(f"Error syncing Google Fit for user {user.id}: {str(e)}")
        return False

def refresh_google_fit_token(user):
    """Refresh Google Fit access token using refresh token"""
    try:
        refresh_token = user.google_refresh_token
        client_id = os.environ.get('GOOGLE_CLIENT_ID')
        client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
        
        if not refresh_token or not client_id or not client_secret:
            logger.error(f"Missing refresh token or client credentials for user {user.id}")
            return False
        
        # Make token refresh request
        response = requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token'
            }
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to refresh token for user {user.id}: {response.status_code} - {response.text}")
            return False
        
        data = response.json()
        
        # Update user tokens
        user.google_fit_token = data.get('access_token')
        expires_in = data.get('expires_in', 3600)  # Default to 1 hour if not provided
        user.google_token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        db.session.commit()
        logger.info(f"Refreshed Google Fit token for user {user.id}")
        return True
    except Exception as e:
        logger.error(f"Error refreshing token for user {user.id}: {str(e)}")
        return False

def sync_all_google_fit_users():
    """Sync Google Fit data for all users with Google Fit integration"""
    try:
        # Get all users with Google Fit tokens
        users = User.query.filter(User.google_fit_token.isnot(None)).all()
        logger.info(f"Starting Google Fit sync for {len(users)} users")
        
        success_count = 0
        for user in users:
            if sync_google_fit_for_user(user):
                success_count += 1
                
        logger.info(f"Google Fit sync completed. Successful syncs: {success_count}/{len(users)}")
    except Exception as e:
        logger.error(f"Error in sync_all_google_fit_users: {str(e)}")

def start_background_tasks():
    """Start background tasks for syncing fitness data"""
    # Schedule Google Fit sync to run every 2 hours
    schedule.every(2).hours.do(sync_all_google_fit_users)
    
    # Run the scheduler in a separate thread
    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True  # Allow the thread to exit when the main program exits
    scheduler_thread.start()
    
    logger.info("Background tasks started")