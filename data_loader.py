import requests
import csv
import io
from database import get_db_connection
from datetime import datetime

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query?function=LISTING_STATUS&apikey=demo"

def load_stock_universe():
    print("Fetching stock universe from Alpha Vantage...")
    try:
        response = requests.get(ALPHA_VANTAGE_URL)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Failed to fetch data: {e}")
        return

    # Decode content
    content = response.content.decode('utf-8')
    csv_reader = csv.DictReader(io.StringIO(content))

    conn = get_db_connection()
    if not conn:
        print("Database connection failed.")
        return

    cursor = conn.cursor()
    print("Inserting data into stock_universe table...")

    # Prepare query
    sql = """
        INSERT INTO stock_universe (symbol, name, exchange, asset_type, ipo_date, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            exchange = VALUES(exchange),
            asset_type = VALUES(asset_type),
            ipo_date = VALUES(ipo_date),
            status = VALUES(status)
    """

    batch_size = 1000
    batch = []
    count = 0

    for row in csv_reader:
        # Handle dates
        ipo_date = row['ipoDate']
        if not ipo_date or ipo_date == 'null':
            ipo_date = None

        # Map CSV fields to DB columns
        # CSV: symbol,name,exchange,assetType,ipoDate,delistingDate,status
        batch.append((
            row['symbol'],
            row['name'],
            row['exchange'],
            row['assetType'],
            ipo_date,
            row['status']
        ))

        if len(batch) >= batch_size:
            cursor.executemany(sql, batch)
            conn.commit()
            count += len(batch)
            print(f"Processed {count} records...")
            batch = []

    if batch:
        cursor.executemany(sql, batch)
        conn.commit()
        count += len(batch)

    print(f"Successfully loaded {count} records into stock_universe.")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    load_stock_universe()
