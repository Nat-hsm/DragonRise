from datetime import datetime, time, timedelta
from flask import current_app

def is_peak_hour():
    """
    Check if the current time is within peak hours.
    Uses settings from the database if available, otherwise falls back to defaults.
    
    Returns:
        tuple: (bool, int) - (True if current time is within peak hours, multiplier value)
    """
    # Get current time in local timezone (UTC+8)
    now = (datetime.utcnow() + timedelta(hours=8)).time()
    
    try:
        # Try to get peak hour settings from database
        from models import get_peak_hour_settings
        peak_hours = get_peak_hour_settings()
        
        # If no settings found, use defaults
        if not peak_hours:
            return _is_peak_hour_default(now)
        
        # Check if current time is within any peak hour range
        for setting in peak_hours:
            if setting.is_active and setting.start_time <= now <= setting.end_time:
                return (True, setting.multiplier)
        
        return (False, 1)
    except Exception as e:
        # If there's an error (e.g., database not initialized), fall back to defaults
        current_app.logger.warning(f"Error getting peak hour settings: {str(e)}. Using defaults.")
        return _is_peak_hour_default(now)

def _is_peak_hour_default(now):
    """
    Default implementation of peak hour check using hardcoded values.
    
    Args:
        now: Current time object
        
    Returns:
        tuple: (bool, int) - (True if current time is within peak hours, multiplier value)
    """
    # Define peak hour ranges
    morning_peak_start = time(8, 45)
    morning_peak_end = time(9, 15)
    
    lunch_peak_start = time(11, 30)
    lunch_peak_end = time(13, 0)  # 1:00 PM
    
    evening_peak_start = time(17, 30)  # 5:30 PM
    evening_peak_end = time(18, 30)  # 6:30 PM
    
    # Check if current time is within any peak hour range
    if morning_peak_start <= now <= morning_peak_end:
        return (True, 2)
    elif lunch_peak_start <= now <= lunch_peak_end:
        return (True, 2)
    elif evening_peak_start <= now <= evening_peak_end:
        return (True, 2)
    
    return (False, 1)

def get_points_multiplier():
    """
    Get the current points multiplier based on time of day.
    Uses settings from the database if available, otherwise falls back to default.
    
    Returns:
        int: Points multiplier (typically 2 during peak hours, 1 otherwise)
    """
    try:
        # Try to get peak hour settings from database
        from models import get_peak_hour_settings
        peak_hours = get_peak_hour_settings()
        
        # Get current time in local timezone (UTC+8)
        now = (datetime.utcnow() + timedelta(hours=8)).time()
        
        # If no settings found, use default
        if not peak_hours:
            is_peak, multiplier = _is_peak_hour_default(now)
            return multiplier
        
        # Check if current time is within any peak hour range
        for setting in peak_hours:
            if setting.is_active and setting.start_time <= now <= setting.end_time:
                return setting.multiplier
        
        return 1  # Default multiplier when not in peak hours
    except Exception as e:
        # If there's an error, fall back to default
        current_app.logger.warning(f"Error getting peak hour settings: {str(e)}. Using default multiplier.")
        is_peak, multiplier = is_peak_hour()
        return multiplier

def get_current_peak_hour_info():
    """
    Get information about the current peak hour if active.
    
    Returns:
        tuple: (bool, int, str) - (is_peak_hour, multiplier, name of peak hour)
    """
    # Get current time in local timezone (UTC+8)
    now = (datetime.utcnow() + timedelta(hours=8)).time()
    current_app.logger.info(f"Current time (UTC+8): {now.strftime('%H:%M:%S')}")
    
    try:
        # Try to get peak hour settings from database
        from models import get_peak_hour_settings
        peak_hours = get_peak_hour_settings()
        
        # If no settings found, use defaults
        if not peak_hours:
            is_peak, multiplier = _is_peak_hour_default(now)
            name = "Peak Hour" if is_peak else ""
            current_app.logger.info(f"Using default peak hour settings: {is_peak}, {multiplier}, {name}")
            return (is_peak, multiplier, name)
        
        # Check if current time is within any peak hour range
        for setting in peak_hours:
            if setting.is_active and setting.start_time <= now <= setting.end_time:
                current_app.logger.info(f"Found active peak hour: {setting.name}, {setting.multiplier}x")
                return (True, setting.multiplier, setting.name)
        
        current_app.logger.info("No active peak hour found")
        return (False, 1, "")
    except Exception as e:
        # If there's an error, fall back to defaults
        current_app.logger.warning(f"Error getting peak hour settings: {str(e)}. Using defaults.")
        is_peak, multiplier = _is_peak_hour_default(now)
        name = "Peak Hour" if is_peak else ""
        return (is_peak, multiplier, name)

def get_peak_hours_message():
    """
    Get a formatted message describing the peak hours.
    Uses settings from the database if available, otherwise falls back to default.
    
    Returns:
        str: Description of peak hours
    """
    try:
        # Try to get peak hour settings from database
        from models import get_peak_hour_settings
        peak_hours = get_peak_hour_settings()
        
        # If no settings found, use default
        if not peak_hours:
            return "Peak Hours (2x points): 8:45am-9:15am, 11:30am-1:00pm, and 5:30pm-6:30pm"
        
        # Build message from settings
        active_settings = [s for s in peak_hours if s.is_active]
        if not active_settings:
            return "No peak hours currently configured"
        
        # Format message
        ranges = [f"{s.formatted_time_range} ({s.multiplier}x)" for s in active_settings]
        if len(ranges) == 1:
            time_str = ranges[0]
        elif len(ranges) == 2:
            time_str = f"{ranges[0]} and {ranges[1]}"
        else:
            time_str = ", ".join(ranges[:-1]) + f", and {ranges[-1]}"
        
        return f"Peak Hours: {time_str}"
    except Exception as e:
        # If there's an error, fall back to default
        current_app.logger.warning(f"Error getting peak hour settings: {str(e)}. Using default message.")
        return "Peak Hours (2x points): 8:45am-9:15am, 11:30am-1:00pm, and 5:30pm-6:30pm"

def get_local_time(utc_time):
    """
    Convert UTC time to local time (UTC+8)
    
    Args:
        utc_time: UTC datetime object
        
    Returns:
        datetime: Local time (UTC+8)
    """
    return utc_time + timedelta(hours=8)