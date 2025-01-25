from datetime import datetime, timedelta

def get_beijing_time(date: datetime) -> datetime:
    # Convert to UTC time
    utc = date.astimezone(datetime.timezone.utc)
    # Convert to Beijing time (UTC+8)
    beijing_tz = datetime.timezone(timedelta(hours=8))
    return utc.astimezone(beijing_tz)

def format_beijing_time(date: datetime, with_zone: bool = True) -> str:
    # Convert to Beijing time (UTC+8)
    beijing_date = get_beijing_time(date)
    
    # Format year, month, day, hours, minutes, seconds
    base_format = beijing_date.strftime("%Y-%m-%d %H:%M:%S")
    return f"{base_format}+08" if with_zone else base_format 