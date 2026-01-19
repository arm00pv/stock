import yfinance as yf
from datetime import datetime, timedelta
from database import get_untracked_picks, add_performance_records_batch
from dotenv import load_dotenv

load_dotenv()

def calculate_performance(ticker, start_date, end_date):
    """Calculates the percentage performance of a ticker between two dates."""
    try:
        # Fetch data for a slightly wider range to ensure we get the start/end dates
        hist = yf.Ticker(ticker).history(start=start_date - timedelta(days=3), end=end_date + timedelta(days=3))

        # Find the closest available closing prices for the start and end dates
        start_price = hist.loc[hist.index.to_pydatetime() <= start_date.replace(tzinfo=None)].iloc[-1]['Close']
        end_price = hist.loc[hist.index.to_pydatetime() >= end_date.replace(tzinfo=None)].iloc[0]['Close']

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
    performance_records_to_add = []

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
                performance = calculate_performance(ticker, pick_date, target_date)

                if performance is not None:
                    print(f"  -> Calculated {ticker}: {days}-day performance is {performance:.2f}%")
                    performance_records_to_add.append((pick_id, days, performance))
                else:
                    print(f"  -> Failed to track {ticker} for {days}-day interval.")

    if performance_records_to_add:
        print(f"\nAdding {len(performance_records_to_add)} performance records to the database...")
        add_performance_records_batch(performance_records_to_add)
        print("Batch insert of performance records complete.")
    else:
        print("No new performance records to add.")

    print("--- Performance Tracking Pipeline Finished ---")

if __name__ == '__main__':
    run_performance_check()
