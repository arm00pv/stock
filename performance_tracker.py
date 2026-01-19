import yfinance as yf
from datetime import datetime, timedelta, date
import concurrent.futures
from database import get_untracked_picks, add_performance_record
from dotenv import load_dotenv

load_dotenv()

def calculate_performance(ticker, start_date, end_date):
    """Calculates the percentage performance of a ticker between two dates."""
    try:
        # Convert date objects to datetime if necessary
        if isinstance(start_date, date) and not isinstance(start_date, datetime):
            start_date = datetime.combine(start_date, datetime.min.time())
        if isinstance(end_date, date) and not isinstance(end_date, datetime):
            end_date = datetime.combine(end_date, datetime.min.time())

        # Fetch data for a slightly wider range to ensure we get the start/end dates
        hist = yf.Ticker(ticker).history(start=start_date - timedelta(days=3), end=end_date + timedelta(days=3))

        # Ensure index is tz-naive for comparison
        hist.index = hist.index.tz_localize(None)

        # Find the closest available closing prices for the start and end dates
        start_price = hist.loc[hist.index <= start_date].iloc[-1]['Close']
        end_price = hist.loc[hist.index >= end_date].iloc[0]['Close']

        if start_price and end_price:
            return ((end_price - start_price) / start_price) * 100
    except Exception as e:
        print(f"Could not calculate performance for {ticker} from {start_date} to {end_date}: {e}")
    return None

def run_performance_check():
    """
    Checks for untracked picks and calculates their performance at 7, 30, and 90-day intervals.
    """
    print("--- Starting Performance Tracking Pipeline ---")

    picks_to_check = get_untracked_picks()
    if not picks_to_check:
        print("No new picks to track performance for.")
        return

    print(f"Found {len(picks_to_check)} picks that need performance tracking.")

    today = datetime.now().date()

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_pick_data = {}
        for pick in picks_to_check:
            pick_id = pick['id']
            ticker = pick['ticker']
            pick_date = pick['pick_date']

            intervals_to_check = [7, 30, 90]
            for days in intervals_to_check:
                # Check if this interval is due for tracking
                if pick_date + timedelta(days=days) <= today:
                    # Check if this specific interval has already been tracked
                    # This is a simple check; a more robust one would query the DB.
                    # The DB has a UNIQUE constraint, so it will prevent duplicates anyway.

                    target_date = pick_date + timedelta(days=days)
                    # Submit task to executor
                    future = executor.submit(calculate_performance, ticker, pick_date, target_date)
                    future_to_pick_data[future] = (pick_id, ticker, days)

        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_pick_data):
            pick_id, ticker, days = future_to_pick_data[future]
            try:
                performance = future.result()
                if performance is not None:
                    print(f"  -> Tracking {ticker}: {days}-day performance is {performance:.2f}%")
                    add_performance_record(pick_id, days, performance)
                else:
                    print(f"  -> Failed to track {ticker} for {days}-day interval.")
            except Exception as exc:
                print(f"  -> Exception tracking {ticker} for {days}-day interval: {exc}")

    print("--- Performance Tracking Pipeline Finished ---")

if __name__ == '__main__':
    run_performance_check()
