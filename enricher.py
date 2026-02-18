import pandas as pd
import yfinance as yf
import time
from database import get_tickers_by_category, get_db_connection
from dotenv import load_dotenv
import requests

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

def update_stock_details_batch(updates):
    """
    Updates multiple stocks' details in the database in a single transaction.
    updates: list of tuples (market_cap, sector, is_sp500, ticker)
    """
    if not updates:
        return

    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        sql = """
            UPDATE stocks
            SET market_cap = %s, sector = %s, is_sp500 = %s
            WHERE ticker = %s
        """
        cursor.executemany(sql, updates)
        conn.commit()
        print(f"Successfully batch updated {len(updates)} stocks.")
    except Exception as e:
        print(f"Error during batch update: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

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
    updates_buffer = []
    BATCH_SIZE = 10

    for ticker in all_db_tickers:
        try:
            print(f"Enriching {ticker}...")
            stock_info = yf.Ticker(ticker).info

            market_cap = stock_info.get('marketCap')
            sector = stock_info.get('sector')
            is_sp500 = ticker in sp500_tickers

            if market_cap or sector or is_sp500:
                # Add to buffer instead of updating immediately
                updates_buffer.append((market_cap, sector, 1 if is_sp500 else 0, ticker))
                enriched_count += 1

                if len(updates_buffer) >= BATCH_SIZE:
                    update_stock_details_batch(updates_buffer)
                    updates_buffer = []
            else:
                print(f"  -> No new info found for {ticker}.")

            # Add a delay to avoid rate limiting
            time.sleep(2)

        except Exception as e:
            print(f"  -> Error processing {ticker}: {e}")
            # Also sleep on error to avoid hammering the API
            time.sleep(2)

    # Process any remaining updates
    if updates_buffer:
        update_stock_details_batch(updates_buffer)

    print(f"--- Data Enrichment Pipeline Finished. Enriched {enriched_count} tickers. ---")

if __name__ == '__main__':
    run_enrichment()
