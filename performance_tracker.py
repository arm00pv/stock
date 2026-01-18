import yfinance as yf
from datetime import datetime, timedelta, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from database import get_untracked_picks, add_performance_record
from dotenv import load_dotenv

load_dotenv()

def calculate_performance(ticker, start_date, end_date):
    """Calculates the percentage performance of a ticker between two dates."""
    try:
        # Ensure start_date and end_date are datetime objects
        if isinstance(start_date, date) and not isinstance(start_date, datetime):
            start_date = datetime.combine(start_date, datetime.min.time())
        if isinstance(end_date, date) and not isinstance(end_date, datetime):
            end_date = datetime.combine(end_date, datetime.min.time())

        # Fetch data for a slightly wider range to ensure we get the start/end dates
        hist = yf.Ticker(ticker).history(start=start_date - timedelta(days=3), end=end_date + timedelta(days=3))

        if hist.empty:
            print(f"No history found for {ticker}")
            return None

        # Ensure index is timezone-naive for comparison
        hist.index = hist.index.tz_localize(None)

        # Find the closest available closing prices for the start and end dates
        start_price = hist.loc[hist.index <= start_date].iloc[-1]['Close']
        end_price = hist.loc[hist.index >= end_date].iloc[0]['Close']

        if start_price and end_price:
            return ((end_price - start_price) / start_price) * 100
    except Exception as e:
        print(f"Could not calculate performance for {ticker} from {start_date} to {end_date}: {e}")
    return None

def process_pick_interval(pick, days, today):
    """
    Helper function to process a single interval for a pick.
    """
    pick_id = pick['id']
    ticker = pick['ticker']
    pick_date = pick['pick_date']

    # Check if this interval is due for tracking
    if pick_date + timedelta(days=days) <= today:
        target_date = pick_date + timedelta(days=days)
        performance = calculate_performance(ticker, pick_date, target_date)

        if performance is not None:
            print(f"  -> Tracking {ticker}: {days}-day performance is {performance:.2f}%")
            add_performance_record(pick_id, days, performance)
        else:
            print(f"  -> Failed to track {ticker} for {days}-day interval.")

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
    intervals_to_check = [7, 30, 90]

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for pick in picks_to_check:
            for days in intervals_to_check:
                futures.append(executor.submit(process_pick_interval, pick, days, today))

        # Wait for all futures to complete
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"An error occurred during performance check: {e}")

    print("--- Performance Tracking Pipeline Finished ---")

if __name__ == '__main__':
    run_performance_check()
