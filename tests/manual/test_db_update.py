import unittest
import unittest.mock as mock
import sys
import os

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import database

class TestDatabase(unittest.TestCase):
    def test_update_tickers_from_source(self):
        tickers = ['AAPL', 'GOOG']
        category = 'test_cat'
        source_url = 'http://test.com'

        with mock.patch('database.get_db_connection') as mock_get_db:
            mock_conn = mock.Mock()
            mock_cursor = mock.Mock()
            mock_get_db.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            database.update_tickers_from_source(tickers, category, source_url)

            self.assertTrue(mock_cursor.executemany.called)

            args, _ = mock_cursor.executemany.call_args
            self.assertIn("INSERT INTO stocks", args[0])
            self.assertEqual(len(args[1]), 2)
            self.assertEqual(args[1][0][0], 'AAPL')

if __name__ == '__main__':
    unittest.main()
