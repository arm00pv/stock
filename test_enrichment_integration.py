
import unittest
from unittest.mock import MagicMock, patch
import concurrent.futures

# Import the code to test
# Since we can't easily import from enricher.py because it runs code on import (if not careful) or has side effects
# We will mock the dependencies before importing
import sys

# Mock modules
sys.modules['yfinance'] = MagicMock()
sys.modules['database'] = MagicMock()
sys.modules['requests'] = MagicMock()

from enricher import fetch_ticker_data, run_enrichment
import database
import yfinance as yf

class TestEnrichment(unittest.TestCase):

    def setUp(self):
        # Reset mocks
        database.get_tickers_by_category.reset_mock()
        database.update_stock_details_batch.reset_mock()
        yf.Ticker.reset_mock()

    def test_fetch_ticker_data_success(self):
        # Setup mock
        mock_ticker = MagicMock()
        mock_ticker.info = {'marketCap': 1000, 'sector': 'Tech'}
        yf.Ticker.return_value = mock_ticker

        sp500_tickers = {'AAPL'}

        # Test
        result = fetch_ticker_data('AAPL', sp500_tickers)

        # Verify
        self.assertEqual(result, (1000, 'Tech', 1, 'AAPL'))
        yf.Ticker.assert_called_with('AAPL')

    def test_fetch_ticker_data_no_info(self):
         # Setup mock
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        yf.Ticker.return_value = mock_ticker

        sp500_tickers = set()

        # Test
        result = fetch_ticker_data('UNKNOWN', sp500_tickers)

        # Verify - should return None if no relevant info
        self.assertIsNone(result)

    @patch('enricher.scrape_sp500_tickers')
    def test_run_enrichment_flow(self, mock_scrape):
        # Setup
        mock_scrape.return_value = {'AAPL'}
        database.get_tickers_by_category.side_effect = [['AAPL', 'MSFT'], [], [], [], [], [], []] # Return tickers only for first category call

        # Mock fetch_ticker_data inside run_enrichment is hard because it is imported?
        # No, fetch_ticker_data is defined in enricher.py, so we can patch it.

        with patch('enricher.fetch_ticker_data') as mock_fetch:
            mock_fetch.side_effect = [
                (1000, 'Tech', 1, 'AAPL'),
                (2000, 'Tech', 0, 'MSFT')
            ]

            run_enrichment()

            # Verify database calls
            # We expect get_tickers_by_category to be called for each category
            self.assertTrue(database.get_tickers_by_category.called)

            # We expect update_stock_details_batch to be called with our results
            database.update_stock_details_batch.assert_called()
            call_args = database.update_stock_details_batch.call_args[0][0]
            # Verify the batch content (order might vary due to thread pool but we mocked side_effect so maybe sequential in mock?)
            # Wait, ThreadPoolExecutor with mock might be tricky.
            # But we can check if the items are in the call args.
            self.assertIn((1000, 'Tech', 1, 'AAPL'), call_args)
            self.assertIn((2000, 'Tech', 0, 'MSFT'), call_args)

if __name__ == '__main__':
    unittest.main()
