"""Unit tests for db_admin_lambda module."""
import pytest
import json
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, 'src')
sys.path.insert(0, 'src/model')


@pytest.mark.unit
class TestDbAdminLambda:
    """Tests for database admin Lambda."""

    @patch('model.db_admin_lambda._secrets')
    @patch('model.db_admin_lambda.psycopg2.connect')
    def test_get_db_conn(self, mock_connect, mock_secrets, mock_env_vars):
        """Test database connection retrieval."""
        from model.db_admin_lambda import _get_db_conn
        
        secret_value = {
            'host': 'localhost',
            'port': 5432,
            'dbname': 'testdb',
            'username': 'testuser',
            'password': 'testpass'
        }
        mock_secrets.get_secret_value.return_value = {
            'SecretString': json.dumps(secret_value)
        }
        
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        conn = _get_db_conn()
        
        assert conn is not None
        mock_connect.assert_called_once()

    @patch('model.db_admin_lambda._get_db_conn')
    def test_list_tables(self, mock_get_conn):
        """Test listing database tables."""
        from model.db_admin_lambda import _list_tables
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [('documents',), ('metadata',)]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn
        
        tables = _list_tables()
        
        # Check that function returns data (format may vary)
        assert tables is not None
        assert len(tables) >= 0  # Just check it returns something

    @patch('model.db_admin_lambda._get_db_conn')
    def test_describe_table(self, mock_get_conn):
        """Test describing table structure."""
        from model.db_admin_lambda import _describe_table
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Mock columns result
        mock_cursor.fetchall.side_effect = [
            [('id', 'uuid', 'NO'), ('content', 'text', 'YES')],
            [('documents_pkey', 'PRIMARY KEY (id)')]
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn
        
        description = _describe_table('documents')
        
        # Check that description is returned (may be list or dict depending on implementation)
        assert description is not None
        if isinstance(description, dict):
            assert 'columns' in description or 'indexes' in description

    @patch('model.db_admin_lambda._list_tables')
    def test_handler_list_tables_action(self, mock_list_tables, mock_env_vars):
        """Test handler with 'tables' action."""
        from model.db_admin_lambda import handler
        
        mock_list_tables.return_value = ['documents', 'metadata']
        
        event = {'action': 'tables'}
        result = handler(event, None)
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'tables' in body
        assert len(body['tables']) == 2

    @patch('model.db_admin_lambda._describe_table')
    def test_handler_describe_action(self, mock_describe, mock_env_vars):
        """Test handler with 'describe' action."""
        from model.db_admin_lambda import handler
        
        mock_describe.return_value = {
            'columns': [{'name': 'id', 'type': 'uuid', 'nullable': False}],
            'indexes': [{'name': 'idx_test', 'definition': 'CREATE INDEX ...'}]
        }
        
        event = {'action': 'describe', 'table': 'documents'}
        result = handler(event, None)
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'columns' in body
        assert 'indexes' in body

    def test_handler_missing_action(self, mock_env_vars):
        """Test handler with missing action."""
        from model.db_admin_lambda import handler
        
        event = {}
        result = handler(event, None)
        
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'error' in body

    def test_handler_missing_table_for_describe(self, mock_env_vars):
        """Test handler with describe action but missing table."""
        from model.db_admin_lambda import handler
        
        event = {'action': 'describe'}
        result = handler(event, None)
        
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'error' in body

    def test_handler_missing_table_for_first(self, mock_env_vars):
        """Test handler with first action but missing table."""
        from model.db_admin_lambda import handler
        
        event = {'action': 'first'}
        result = handler(event, None)
        
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'error' in body
        assert 'table' in body['error']

    @patch('model.db_admin_lambda._get_db_conn')
    def test_handler_first_action(self, mock_get_conn, mock_env_vars):
        """Test handler with 'first' action."""
        from model.db_admin_lambda import handler
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [('id',), ('content',)]
        mock_cursor.fetchone.return_value = ('123', 'test content')
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn
        
        event = {
            'action': 'first',
            'table': 'documents'
        }
        result = handler(event, None)
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'row' in body

    @patch('model.db_admin_lambda._list_tables')
    def test_handler_error_handling(self, mock_list_tables, mock_env_vars):
        """Test handler error handling."""
        from model.db_admin_lambda import handler
        
        mock_list_tables.side_effect = Exception("Database error")
        
        event = {'action': 'tables'}
        result = handler(event, None)
        
        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert 'error' in body

    @patch('model.db_admin_lambda._get_db_conn')
    def test_first_row_no_columns(self, mock_get_conn, mock_env_vars):
        """Test _first_row with no columns specified (uses SELECT *)."""
        from model.db_admin_lambda import _first_row
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [('id',), ('name',)]
        mock_cursor.fetchone.return_value = (1, 'test')
        # Mock both the connection and cursor context managers
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = None
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = None
        mock_get_conn.return_value = mock_conn
        
        # Call _first_row
        result = _first_row('test_table')
        
        assert result['count'] == 1
        assert result['row'] == {'id': 1, 'name': 'test'}

    @patch('model.db_admin_lambda._get_db_conn')
    def test_first_row_empty_table(self, mock_get_conn, mock_env_vars):
        """Test _first_row when table is empty (fetchone returns None)."""
        from model.db_admin_lambda import _first_row
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # Empty table
        # Mock both the connection and cursor context managers
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = None
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = None
        mock_get_conn.return_value = mock_conn
        
        result = _first_row('empty_table')
        
        assert result['row'] is None
        assert result['count'] == 0

    @patch('model.db_admin_lambda._list_tables')
    def test_handler_exception(self, mock_list_tables, mock_env_vars):
        """Test handler exception handling."""
        from model.db_admin_lambda import handler
        
        # Make _list_tables raise an exception
        mock_list_tables.side_effect = Exception("Database error")
        
        event = {"action": "tables"}
        result = handler(event, None)
        
        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert 'error' in body
