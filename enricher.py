import pandas as pd
import yfinance as yf
import time
from database import get_tickers_by_category, get_db_connection
from dotenv import load_dotenv
import requests
import concurrent.futures

load_dotenv()

def scrape_sp500_tickers():
    """
    Scrapes the Wikipedia page for the list of S&P 500 companies.
    Returns a set of ticker symbols.
    """
    print("Scraping Wikipedia for S&P 500 component list...")
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        tables = pd.read_html(response.text)
        sp500_table = tables[0]
        tickers = set(sp500_table['Symbol'].tolist())
        print(f"Successfully scraped {len(tickers)} S&P 500 tickers.")
        return tickers
    except Exception as e:
        print(f"Could not scrape S&P 500 list: {e}")
        return set()

def update_stock_details(ticker, market_cap, sector, is_sp500):
    """Updates a single stock's details in the database."""
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        # Check if a row for this ticker already exists, if not, this will fail gracefully.
        # A better approach would be to INSERT...ON DUPLICATE KEY UPDATE if the primary key was just the ticker.
        # Given the composite key, a simple UPDATE is safer.
        sql = """
            UPDATE stocks
            SET market_cap = %s, sector = %s, is_sp500 = %s
            WHERE ticker = %s
        """
        cursor.execute(sql, (market_cap, sector, 1 if is_sp500 else 0, ticker))
        conn.commit()
    except Exception as e:
        print(f"Error updating details for {ticker}: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def process_ticker(ticker, sp500_tickers):
    """
    Fetches data for a single ticker and updates the database.
    Returns True if the ticker was enriched (updated), False otherwise.
    """
    try:
        print(f"Enriching {ticker}...")
        stock_info = yf.Ticker(ticker).info

        market_cap = stock_info.get('marketCap')
        sector = stock_info.get('sector')
        is_sp500 = ticker in sp500_tickers

        updated = False
        if market_cap or sector or is_sp500:
            update_stock_details(ticker, market_cap, sector, is_sp500)
            updated = True
        else:
            print(f"  -> No new info found for {ticker}.")

        # Add a small delay to respect rate limits, but distributed across threads
        time.sleep(1)
        return updated

    except Exception as e:
        print(f"  -> Error processing {ticker}: {e}")
        # Also sleep on error
        time.sleep(1)
        return False

def run_enrichment():
    """
    Goes through all securities in the 'stocks' table and enriches them
    with market cap, sector, and S&P 500 status.
    """
    print("--- Starting Data Enrichment Pipeline ---")

    sp500_tickers = scrape_sp500_tickers()

    print("Fetching all existing tickers from database...")
    all_db_tickers = set()
    categories = ['sp500', 'penny', 'monthly_dividend', 'high_yield', 'etf', 'generic_stock', 'bond']
    for category in categories:
        all_db_tickers.update(get_tickers_by_category(category))

    print(f"Found {len(all_db_tickers)} total unique tickers to enrich.")
    enriched_count = 0

    # We use a ThreadPoolExecutor to parallelize the enrichment.
    # We limit max_workers to avoid overwhelming the API or the database.
    MAX_WORKERS = 3

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_ticker = {executor.submit(process_ticker, ticker, sp500_tickers): ticker for ticker in all_db_tickers}

        for future in concurrent.futures.as_completed(future_to_ticker):
            # ticker = future_to_ticker[future]
            try:
                if future.result():
                    enriched_count += 1
            except Exception as exc:
                print(f'Ticker generated an exception: {exc}')

    print(f"--- Data Enrichment Pipeline Finished. Enriched {enriched_count} tickers. ---")

if __name__ == '__main__':
    run_enrichment()
