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

def update_stock_details(conn, ticker, market_cap, sector, is_sp500):
    """Updates a single stock's details in the database using an existing connection."""
    if not conn: return
    cursor = conn.cursor()
    try:
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

def run_enrichment():
    """
    Goes through all securities in the 'stocks' table and enriches them
    with market cap, sector, and S&P 500 status, using a single DB connection.
    """
    print("--- Starting Data Enrichment Pipeline ---")

    sp500_tickers = scrape_sp500_tickers()

    print("Fetching all existing tickers from database...")
    all_db_tickers = set()
    # Note: get_tickers_by_category opens and closes a connection for each category.
    # This could be further optimized, but for now, we focus on the main N+1 issue.
    categories = ['sp500', 'penny', 'monthly_dividend', 'high_yield', 'etf', 'generic_stock', 'bond']
    for category in categories:
        all_db_tickers.update(get_tickers_by_category(category))

    print(f"Found {len(all_db_tickers)} total unique tickers to enrich.")
    enriched_count = 0

    conn = get_db_connection()
    if not conn:
        print("Could not establish database connection. Aborting enrichment.")
        return

    try:
        for ticker in all_db_tickers:
            try:
                print(f"Enriching {ticker}...")
                stock_info = yf.Ticker(ticker).info

                market_cap = stock_info.get('marketCap')
                sector = stock_info.get('sector')
                is_sp500 = ticker in sp500_tickers

                if market_cap or sector or is_sp500:
                    # Pass the single connection object to the update function
                    update_stock_details(conn, ticker, market_cap, sector, is_sp500)
                    enriched_count += 1
                else:
                    print(f"  -> No new info found for {ticker}.")

                # Add a delay to avoid rate limiting with the yfinance API
                time.sleep(2)

            except Exception as e:
                print(f"  -> Error processing {ticker}: {e}")
                # Also sleep on error to avoid hammering the API
                time.sleep(2)
    finally:
        if conn.is_connected():
            conn.close()
            print("Database connection closed.")

    print(f"--- Data Enrichment Pipeline Finished. Enriched {enriched_count} tickers. ---")

if __name__ == '__main__':
    run_enrichment()
