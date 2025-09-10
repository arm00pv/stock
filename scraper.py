import requests
from bs4 import BeautifulSoup
import re

def scrape_monthly_dividend_stocks():
    """
    Scrapes a list of monthly dividend stock tickers from the simplysafedividends article.
    Includes enhanced error handling and logging.
    """
    URL = "https://www.simplysafedividends.com/world-of-dividends/posts/42-2025-monthly-dividend-stocks-list-all-76-ranked-and-analyzed"
    print(f"Attempting to scrape primary source: {URL}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(URL, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching primary URL: {e}")
        return None # Return None on failure

    soup = BeautifulSoup(response.content, 'html.parser')

    all_tickers = set()
    ticker_regex = re.compile(r'\(([A-Z]{1,5})\)')

    content = soup.find('div', class_='trix-content')
    if not content:
        print("Error: Could not find the main content div with class 'trix-content'. The page structure may have changed.")
        return None

    # --- Scrape the main list of stocks ---
    main_headings = content.find_all('h2')
    if not main_headings:
        print("Warning: Could not find any `h2` tags for the main stock list.")

    found_main = False
    for heading in main_headings:
        if "Monthly Dividend Stock #" in heading.get_text():
            found_in_section = False
            for sibling in heading.find_next_siblings(limit=5):
                if sibling.name == 'div':
                    strong_tag = sibling.find('strong')
                    if strong_tag:
                        match = ticker_regex.search(strong_tag.get_text())
                        if match:
                            all_tickers.add(match.group(1))
                            found_in_section = True
                            break
                if sibling.name == 'h2':
                    break
            if found_in_section:
                found_main = True

    if not found_main:
        print("Warning: No tickers were found in the main 'Monthly Dividend Stock #' sections.")

    # --- Scrape the Micro-Cap and OTC list ---
    micro_cap_heading = content.find('h2', string=re.compile(r'Micro-Cap and OTC Monthly Dividend Stocks'))
    if micro_cap_heading:
        found_micro = False
        for sibling in micro_cap_heading.find_next_siblings():
            if sibling.name == 'ul':
                li = sibling.find('li')
                if li:
                    strong_tag = li.find('strong')
                    if strong_tag:
                        match = ticker_regex.search(strong_tag.get_text())
                        if match:
                            all_tickers.add(match.group(1))
                            found_micro = True
            if sibling.name == 'h2':
                break
        if not found_micro:
            print("Warning: Found the Micro-Cap heading but extracted no tickers from the list.")
    else:
        print("Warning: Could not find the 'Micro-Cap and OTC Monthly Dividend Stocks' heading.")

    return sorted(list(all_tickers))

from database import init_db, add_tickers_to_db

def get_backup_monthly_dividend_tickers():
    """
    Returns a hardcoded list of known monthly dividend tickers as a fallback.
    """
    print("Using hardcoded backup list for monthly dividend stocks.")
    return [
        'O', 'MAIN', 'ADC', 'STAG', 'RIOCF', 'GAIN', 'DOC', 'LAND', 'PECO',
        'EPR', 'SLG', 'APLE', 'SILA', 'PFLT', 'GOOD', 'GLAD', 'LTC', 'HRZN',
        'PSEC', 'WSR', 'SCM', 'EFC', 'EARN', 'OXSQ', 'DX', 'PNNT', 'AGNC',
        'ARR', 'ORC', 'SBR', 'GWRS', 'SRRTF', 'BSRTF', 'CTRRF', 'FRMUF',
        'SISXF', 'BEVFF', 'GROW', 'MDV', 'MHCUF', 'PMREF', 'TBCRF', 'FTCO',
        'PIFYF', 'PRMRF', 'ALPS', 'TNEYF'
    ]

if __name__ == '__main__':
    # Initialize the database and table first
    init_db()

    print("--- Starting Scraper ---")

    # Try the primary scraper first
    scraped_tickers = scrape_monthly_dividend_stocks()

    # If the primary scraper fails or returns no tickers, use the backup
    if not scraped_tickers:
        print("Primary scraper failed or found no tickers. Falling back to backup list.")
        scraped_tickers = get_backup_monthly_dividend_tickers()

    if scraped_tickers:
        print(f"Found {len(scraped_tickers)} tickers for category 'monthly_dividend'.")
        add_tickers_to_db(scraped_tickers, 'monthly_dividend')
    else:
        print("Error: Both primary scraper and backup failed. No tickers were added.")
