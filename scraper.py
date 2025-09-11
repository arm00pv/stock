import requests
from bs4 import BeautifulSoup
import re
import time
from database import init_db, update_tickers_from_source, prune_old_tickers

# --- Parser for simplysafedividends.com ---
def parse_simplysafedividends(soup):
    all_tickers = set()
    ticker_regex = re.compile(r'\(([A-Z]{1,5})\)')
    content = soup.find('div', class_='trix-content')
    if not content:
        print("Error (simplysafedividends): Could not find the main content div.")
        return set()

    # Main list
    main_headings = content.find_all('h2')
    for heading in main_headings:
        if "Monthly Dividend Stock #" in heading.get_text():
            for sibling in heading.find_next_siblings(limit=5):
                if sibling.name == 'div' and sibling.find('strong'):
                    match = ticker_regex.search(sibling.find('strong').get_text())
                    if match:
                        all_tickers.add(match.group(1))
                        break
                if sibling.name == 'h2':
                    break

    # Micro-Cap list
    micro_cap_heading = content.find('h2', string=re.compile(r'Micro-Cap and OTC Monthly Dividend Stocks'))
    if micro_cap_heading:
        for sibling in micro_cap_heading.find_next_siblings():
            if sibling.name == 'ul' and sibling.find('li') and sibling.find('li').find('strong'):
                match = ticker_regex.search(sibling.find('li').find('strong').get_text())
                if match:
                    all_tickers.add(match.group(1))
            if sibling.name == 'h2':
                break
    return all_tickers

# --- Parser for kiplinger.com ---
def parse_kiplinger(soup):
    try:
        all_tickers = set()
        ticker_regex = re.compile(r'\(([A-Z]{1,5})\)')

        # --- DEBUGGING KIPLINGER ---
        # print(soup.prettify())
        # --- END DEBUGGING ---

        # Find the container for the main article body
        body = soup.find('div', id='article-body')
        if not body:
            print("Error (kiplinger): Could not find the article body div.")
            return set()

        # Tickers are in `<a>` tags with a specific href pattern
        links = body.find_all('a', href=re.compile(r'/tfn/ticker\.html\?ticker='))
        if not links:
            print("Warning (kiplinger): Could not find any ticker links with the expected href pattern.")

        for link in links:
            # The ticker is sometimes in the link text, sometimes in the href itself.
            # Let's prioritize the href as it's more reliable.
            href = link.get('href', '')
            match = re.search(r'ticker=([A-Z]{1,5})', href)
            if match:
                all_tickers.add(match.group(1))

        if not all_tickers:
            print("Warning (kiplinger): No tickers found via href. Trying text search as fallback.")
            # Fallback to searching text if no links were found
            text_matches = ticker_regex.findall(body.get_text())
            for ticker in text_matches:
                all_tickers.add(ticker)

        return all_tickers
    except Exception as e:
        print(f"An unexpected error occurred in parse_kiplinger: {e}")
        return set()

# --- Generic Scraper ---
def scrape_website(url, parser_func):
    print(f"Attempting to scrape source: {url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        return parser_func(soup)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None

# --- Main Execution ---
def main():
    init_db()
    print("--- Starting Scraper ---")

    sources = [
        {
            "category": "monthly_dividend",
            "url": "https://www.simplysafedividends.com/world-of-dividends/posts/42-2025-monthly-dividend-stocks-list-all-76-ranked-and-analyzed",
            "parser": parse_simplysafedividends
        },
        {
            "category": "high_yield",
            "url": "https://www.kiplinger.com/investing/stocks-with-the-highest-dividend-yields-in-the-sandp-500",
            "parser": parse_kiplinger
        }
    ]

    for source in sources:
        print(f"\n--- Processing: {source['category']} from {source['url']} ---")
        scraped_tickers = scrape_website(source['url'], source['parser'])

        if scraped_tickers is not None and len(scraped_tickers) > 0:
            update_tickers_from_source(list(scraped_tickers), source['category'], source['url'])
        else:
            print(f"Scraping failed or returned no tickers for source: {source['url']}. No updates will be made from this source.")

        time.sleep(3)

    print("\n--- Pruning old tickers ---")
    prune_old_tickers(days_old=90) # Remove any ticker not seen in 90 days

if __name__ == '__main__':
    main()
