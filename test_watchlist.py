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

class TestWatchlist(unittest.TestCase):
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

    def test_watchlist_crud(self):
        # Mock add - patch where it is USED in app.py
        with patch('app.add_to_watchlist', return_value=True):
            response = self.client.post('/api/watchlist', json={'ticker': 'NVDA'})
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Added NVDA', response.data)

        # Mock list
        with patch('app.get_watchlist', return_value=[{'ticker': 'NVDA', 'date_added': '2023-01-01'}]):
            response = self.client.get('/api/watchlist')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]['ticker'], 'NVDA')

        # Mock delete
        with patch('app.remove_from_watchlist', return_value=True):
            response = self.client.delete('/api/watchlist', json={'ticker': 'NVDA'})
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Removed NVDA', response.data)

    def test_market_status(self):
        with patch('utils.is_market_open', return_value=True):
            response = self.client.get('/api/market-status')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(json.loads(response.data)['status'], 'Open')

if __name__ == '__main__':
    unittest.main()
