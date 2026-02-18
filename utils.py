import pandas_market_calendars as mcal
import pandas as pd
from datetime import datetime
import pytz
from functools import lru_cache

# Instantiate the NYSE calendar globally to avoid repeated overhead
_nyse = mcal.get_calendar('NYSE')
_ny_tz = pytz.timezone('America/New_York')

@lru_cache(maxsize=1)
def _is_market_open_on_date(date_obj):
    """
    Helper function to check if market is open on a specific date.
    Cached to prevent recalculation for the same day.
    """
    # Check strict date. If the schedule is empty, the market is closed.
    schedule = _nyse.schedule(start_date=date_obj, end_date=date_obj)
    return not schedule.empty

def is_market_open():
    """
    Checks if the NYSE is open on the current date, accounting for weekends and holidays.
    Uses the America/New_York timezone.
    """
    # Get the current date in the New York timezone
    today = datetime.now(_ny_tz).date()
    return _is_market_open_on_date(today)
