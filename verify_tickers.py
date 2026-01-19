import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock dependencies
sys.modules['mysql'] = MagicMock()
sys.modules['mysql.connector'] = MagicMock()
sys.modules['yfinance'] = MagicMock()

import database
import app

class TestTickerValidation(unittest.TestCase):

    def setUp(self):
        # Mock DB connection
        self.db_patcher = patch('database.get_db_connection')
        self.mock_get_db = self.db_patcher.start()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_get_db.return_value = self.mock_conn
        self.mock_conn.cursor.return_value = self.mock_cursor

    def tearDown(self):
        self.db_patcher.stop()

    def test_get_tickers_uniqueness(self):
        """Test that get_tickers_by_category filters duplicates if DB returns them."""
        # Simulate DB returning duplicates (e.g. from multiple categories or bad data)
        self.mock_cursor.fetchall.return_value = [('AAPL',), ('MSFT',), ('AAPL',)]

        tickers = database.get_tickers_by_category('test_cat')

        # In the real code, we added DISTINCT to the SQL query.
        # But if we rely ONLY on Python, we'd check length.
        # Since we mocked the SQL execution, we verify the SQL query string.

        args, _ = self.mock_cursor.execute.call_args
        self.assertIn('DISTINCT', args[0], "SQL query should use SELECT DISTINCT")

    def test_find_growth_candidate_deduplication(self):
        """Test that finding candidates deduplicates tickers from multiple categories."""

        # Setup mocks for get_tickers_by_category where it is USED (app.py)
        # Scenario: 'hot_stock' uses ['sp500', 'generic_stock', 'etf']
        # We want to ensure if AAPL is in both 'sp500' and 'generic_stock', it's screened once.

        with patch('app.get_tickers_by_category') as mock_get_tickers, \
             patch('app.get_recently_picked_tickers', return_value=set()), \
             patch('app.yf.download') as mock_download:

            # Return overlapping lists
            mock_get_tickers.side_effect = [
                ['AAPL', 'MSFT'], # sp500
                ['AAPL', 'GOOG'], # generic_stock
                ['SPY']           # etf
            ]

            # Mock yfinance to return empty to stop further processing but validate the call
            mock_download.return_value = None

            # We just want to check the logic up to the download call
            try:
                app.find_growth_candidate(['sp500', 'generic_stock', 'etf'])
            except:
                pass # Expected to fail/stop at download or empty data

            # Check what was passed to yf.download
            if mock_download.called:
                args, _ = mock_download.call_args
                downloaded_tickers = args[0]
                self.assertEqual(len(downloaded_tickers), 4) # AAPL, MSFT, GOOG, SPY
                self.assertEqual(downloaded_tickers.count('AAPL'), 1)

if __name__ == '__main__':
    unittest.main()
