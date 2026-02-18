import unittest
from unittest.mock import MagicMock, patch
import json
import sys

# Mock dependencies
sys.modules['mysql'] = MagicMock()
sys.modules['mysql.connector'] = MagicMock()
sys.modules['yfinance'] = MagicMock()

# Patch yfinance inside modules
import yfinance as yf

# Import app after mocking
import app
from app import app as flask_app

class TestFeatureAdditions(unittest.TestCase):
    def setUp(self):
        flask_app.testing = True
        self.client = flask_app.test_client()

        # Mock database connection
        self.db_patcher = patch('database.get_db_connection')
        self.mock_get_db = self.db_patcher.start()
        self.mock_conn = MagicMock()
        self.mock_get_db.return_value = self.mock_conn

    def tearDown(self):
        self.db_patcher.stop()

    def test_news_endpoint(self):
        with patch('beta_features.get_stock_news', return_value=[{'title': 'Test News'}]):
            response = self.client.get('/api/news/AAPL')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]['title'], 'Test News')

    def test_volume_spikes_endpoint(self):
        with patch('beta_features.scan_volume_spikes', return_value=[{'ticker': 'TSLA', 'ratio': 2.0}]):
            response = self.client.get('/api/beta/volume_spikes')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data[0]['ticker'], 'TSLA')

    def test_export_endpoint(self):
        holdings = [{'ticker': 'AAPL', 'shares': 10, 'purchase_price': 100, 'purchase_date': '2023-01-01', 'sell_flag': 0}]
        with patch('app.get_portfolio_holdings', return_value=holdings):
            response = self.client.get('/api/portfolio/main/export')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'text/csv')
            self.assertIn(b'Ticker,Shares', response.data)
            self.assertIn(b'AAPL,10', response.data)

if __name__ == '__main__':
    unittest.main()
