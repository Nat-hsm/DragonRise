from datetime import datetime, time

def is_peak_hour():
    """
    Check if the current time is within peak hours.
    Peak hours are: 8:45am-9:15am, 11:30am-1:00pm, and 5:30pm-6:30pm
    
    Returns:
        bool: True if current time is within peak hours, False otherwise
    """
    now = datetime.now().time()
    
    # Define peak hour ranges
    morning_peak_start = time(8, 45)
    morning_peak_end = time(9, 15)
    
    lunch_peak_start = time(11, 30)
    lunch_peak_end = time(13, 0)  # 1:00 PM
    
    evening_peak_start = time(17, 30)  # 5:30 PM
    evening_peak_end = time(18, 30)  # 6:30 PM
    
    # Check if current time is within any peak hour range
    if (morning_peak_start <= now <= morning_peak_end or
        lunch_peak_start <= now <= lunch_peak_end or
        evening_peak_start <= now <= evening_peak_end):
        return True
    
    return False

def get_points_multiplier():
    """
    Get the current points multiplier based on time of day.
    
    Returns:
        int: Points multiplier (2 during peak hours, 1 otherwise)
    """
    return 2 if is_peak_hour() else 1

def get_peak_hours_message():
    """
    Get a formatted message describing the peak hours.
    
    Returns:
        str: Description of peak hours
    """
    return "Peak Hours (2x points): 8:45am-9:15am, 11:30am-1:00pm, and 5:30pm-6:30pm"