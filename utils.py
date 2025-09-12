import pandas_market_calendars as mcal
import pandas as pd
from datetime import datetime
import pytz

def is_market_open():
    """
    Checks if the NYSE is open on the current date, accounting for weekends and holidays.
    Uses the America/New_York timezone.
    """
    # Get the NYSE calendar
    nyse = mcal.get_calendar('NYSE')

    # Get the current date in the New York timezone
    ny_tz = pytz.timezone('America/New_York')
    today = datetime.now(ny_tz).date()

    # Get the schedule for a period around today to be safe
    schedule = nyse.schedule(start_date=today - mcal.pd.Timedelta(days=5), end_date=today + mcal.pd.Timedelta(days=5))

    # The schedule's index is a DatetimeIndex of valid market days.
    # We need to check if today's date is in that index.
    # The dates in the index are timezone-aware, so we use `today` which is a simple date object.
    return today in schedule.index.date
