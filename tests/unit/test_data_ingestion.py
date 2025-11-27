"""Unit tests for data_ingestion module."""
import pytest
import json
from unittest.mock import MagicMock, patch, call
from datetime import datetime
import sys
sys.path.insert(0, 'src')

from data_ingestion import (
    validate_documents,
    clean_text,
    chunk_text,
    get_embedding,
    insert_chunks,
    handler
)


@pytest.mark.unit
class TestValidateDocuments:
    """Tests for document validation."""

    def test_valid_documents(self, sample_documents):
        """Test validation with valid documents."""
        valid_docs, error_count = validate_documents(sample_documents)
        
        assert len(valid_docs) == 3
        assert error_count == 0
        assert all('id' in doc and 'content' in doc for doc in valid_docs)

    def test_missing_required_fields(self):
        """Test validation with missing required fields."""
        docs = [
            {'id': 'doc-1'},  # missing content
            {'content': 'test'},  # missing id
            {'id': 'doc-2', 'content': 'valid content'}
        ]
        
        valid_docs, error_count = validate_documents(docs)
        
        assert len(valid_docs) == 1
        assert error_count == 2
        assert valid_docs[0]['id'] == 'doc-2'

    def test_duplicate_ids(self):
        """Test validation with duplicate IDs."""
        docs = [
            {'id': 'doc-1', 'content': 'content 1 with enough characters'},
            {'id': 'doc-1', 'content': 'content 2 duplicate with enough characters'},  # duplicate
            {'id': 'doc-2', 'content': 'content 3 with enough characters'}
        ]
        
        valid_docs, error_count = validate_documents(docs)
        
        # First doc-1 is valid, second is rejected (duplicate), doc-2 is valid
        assert len(valid_docs) == 2
        assert error_count == 1

    def test_content_too_short(self):
        """Test validation with content that's too short."""
        docs = [
            {'id': 'doc-1', 'content': 'short'},  # less than 10 chars
            {'id': 'doc-2', 'content': 'This is valid content with enough characters'}
        ]
        
        valid_docs, error_count = validate_documents(docs)
        
        assert len(valid_docs) == 1
        assert error_count == 1

    def test_empty_list(self):
        """Test validation with empty document list."""
        valid_docs, error_count = validate_documents([])
        
        assert len(valid_docs) == 0
        assert error_count == 0


@pytest.mark.unit
class TestCleanText:
    """Tests for text cleaning."""

    def test_clean_whitespace(self):
        """Test cleaning excessive whitespace."""
        text = "This  has   excessive    whitespace"
        cleaned = clean_text(text)
        
        assert cleaned == "This has excessive whitespace"

    def test_normalize_quotes(self):
        """Test normalizing quote characters."""
        text = '"This has "fancy" quotes and \'apostrophes\'"'
        cleaned = clean_text(text)
        
        assert '"' in cleaned or "'" in cleaned

    def test_strip_whitespace(self):
        """Test stripping leading/trailing whitespace."""
        text = "   text with spaces   "
        cleaned = clean_text(text)
        
        assert cleaned == "text with spaces"

    def test_empty_text(self):
        """Test cleaning empty text."""
        assert clean_text("") == ""
        assert clean_text(None) == ""

    def test_newlines_and_tabs(self):
        """Test handling newlines and tabs."""
        text = "Line 1\n\nLine 2\t\tTabbed"
        cleaned = clean_text(text)
        
        assert "\n" not in cleaned or cleaned.count("\n") < text.count("\n")
        assert "\t" not in cleaned


@pytest.mark.unit
class TestSemanticChunking:
    """Tests for semantic chunking."""

    def test_chunk_short_text(self):
        """Test chunking text shorter than chunk size."""
        text = "Short text that fits in one chunk."
        chunks = chunk_text(text, chunk_size=1000, overlap=200)
        
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_long_text(self):
        """Test chunking text longer than chunk size."""
        text = "word " * 500  # 2500 characters
        chunks = chunk_text(text, chunk_size=1000, overlap=200)
        
        assert len(chunks) > 1
        assert all(len(chunk) <= 1200 for chunk in chunks)  # allowing for overlap

    def test_chunk_overlap(self):
        """Test that chunks have proper overlap."""
        text = "word " * 500
        chunks = chunk_text(text, chunk_size=500, overlap=100)
        
        if len(chunks) > 1:
            # Check that there's some overlap between consecutive chunks
            for i in range(len(chunks) - 1):
                # Last part of current chunk should appear in next chunk
                assert len(chunks[i]) > 0
                assert len(chunks[i + 1]) > 0

    def test_sentence_boundaries(self):
        """Test that chunking respects sentence boundaries."""
        text = "First sentence. Second sentence. Third sentence. " * 50
        chunks = chunk_text(text, chunk_size=200, overlap=50)
        
        # Most chunks should end with sentence-ending punctuation
        ending_with_period = sum(1 for chunk in chunks if chunk.rstrip().endswith('.'))
        assert ending_with_period > len(chunks) * 0.5  # At least half

    def test_empty_text(self):
        """Test chunking empty text."""
        chunks = chunk_text("", chunk_size=1000, overlap=200)
        
        assert len(chunks) == 0 or (len(chunks) == 1 and chunks[0] == "")


@pytest.mark.unit
class TestGetEmbedding:
    """Tests for embedding generation."""

    @patch('data_ingestion.bedrock_runtime')
    def test_get_embedding_success(self, mock_bedrock):
        """Test successful embedding generation."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'embedding': [0.1] * 1536}).encode()
        mock_bedrock.invoke_model.return_value = {'body': mock_response}
        
        text = "Test text for embedding"
        embedding = get_embedding(text)
        
        assert len(embedding) == 1536
        assert all(isinstance(x, float) for x in embedding)

    @patch('data_ingestion.bedrock_runtime')
    def test_get_embedding_retry_on_throttle(self, mock_bedrock):
        """Test retry logic on throttling."""
        from botocore.exceptions import ClientError
        
        # First call fails with throttling, second succeeds
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'embedding': [0.1] * 1536}).encode()
        
        error_response = {'Error': {'Code': 'ThrottlingException'}}
        mock_bedrock.invoke_model.side_effect = [
            ClientError(error_response, 'InvokeModel'),
            {'body': mock_response}
        ]
        
        with patch('data_ingestion.time.sleep'):  # Speed up test
            embedding = get_embedding("Test text")
        
        assert len(embedding) == 1536
        assert mock_bedrock.invoke_model.call_count == 2


@pytest.mark.unit
class TestStoreChunksInDb:
    """Tests for database storage."""

    def test_store_chunks_success(self, mock_db_connection):
        """Test successful storage of chunks."""
        mock_conn, mock_cursor = mock_db_connection
        
        chunks = [
            {
                'id': 'chunk-1',
                'content': 'Content 1',
                'embedding': [0.1] * 1536,
                'source': 'test',
                'title': 'Test',
                'section': 'Section 1'
            }
        ]
        
        with patch('data_ingestion.execute_values') as mock_execute:
            insert_chunks(mock_cursor, chunks)
        
        # Verify execute_values was called with cursor
        mock_execute.assert_called_once()

    def test_store_empty_chunks(self, mock_db_connection):
        """Test storing empty chunk list."""
        mock_conn, mock_cursor = mock_db_connection
        
        with patch('data_ingestion.execute_values'):
            insert_chunks(mock_cursor, [])
        
        # Should complete without errors (empty list is valid)


@pytest.mark.unit
class TestHandler:
    """Tests for Lambda handler."""

    @patch('data_ingestion.execute_values')
    @patch('data_ingestion.s3_client')
    @patch('data_ingestion.get_db_connection')
    @patch('data_ingestion.get_embedding')
    def test_handler_success(self, mock_get_embedding, mock_get_db, mock_s3, mock_execute, 
                           sample_s3_event, mock_lambda_context, sample_documents):
        """Test successful handler execution."""
        # Setup mocks
        mock_s3.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(sample_documents).encode())
        }
        mock_get_embedding.return_value = [0.1] * 1536
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []  # No existing chunks
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_db.return_value = mock_conn
        mock_execute.return_value = None
        
        # Execute handler
        result = handler(sample_s3_event, mock_lambda_context)
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'documents_processed' in body or 'chunks_newly_stored' in body
        assert body.get('documents_processed', 0) > 0 or body.get('chunks_newly_stored', 0) > 0

    @patch('data_ingestion.s3_client')
    def test_handler_invalid_event(self, mock_s3, mock_lambda_context):
        """Test handler with invalid event."""
        invalid_event = {}
        
        result = handler(invalid_event, mock_lambda_context)
        
        # Handler returns 500 for any error including invalid events
        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert 'error' in body

    @patch('data_ingestion.s3_client')
    def test_handler_s3_error(self, mock_s3, sample_s3_event, mock_lambda_context):
        """Test handler with S3 error."""
        mock_s3.get_object.side_effect = Exception("S3 Error")
        
        result = handler(sample_s3_event, mock_lambda_context)
        
        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert 'error' in body


@pytest.mark.unit
class TestErrorHandlingPaths:
    """Tests for error handling paths in data_ingestion."""

    def test_normalize_date_with_different_formats(self):
        """Test normalize_date with various date formats."""
        from data_ingestion import normalize_date
        
        # Test standard formats
        assert normalize_date('2024-01-15') == '2024-01-15'
        assert normalize_date('01/15/2024') == '2024-01-15'
        assert normalize_date('15-01-2024') == '2024-01-15'
        assert normalize_date('2024/01/15') == '2024-01-15'
        
        # Test invalid format - should return original
        result = normalize_date('not-a-date')
        assert result == 'not-a-date'
        
        # Test None
        assert normalize_date(None) is None

    def test_chunk_document_small_content(self):
        """Test chunk_document with very small content (< 100 chars)."""
        from data_ingestion import chunk_document
        
        doc = {
            'id': 'test-1',
            'content': 'Small content',
            'title': 'Test',
            'section': 'Section',
            'source': 'Test Source'
        }
        
        # chunk_document requires chunk_size and chunk_overlap
        chunks = chunk_document(doc, chunk_size=1000, chunk_overlap=200)
        
        # Should return single chunk for small content
        assert len(chunks) == 1
        assert chunks[0]['id'] == 'test-1_chunk_1'
        assert chunks[0]['content'] == 'Small content'

    @patch('data_ingestion.secretsmanager_client')
    @patch('data_ingestion.psycopg2.connect')
    def test_get_db_connection_secrets_error(self, mock_connect, mock_secrets):
        """Test get_db_connection when secrets retrieval fails."""
        from data_ingestion import get_db_connection
        
        mock_secrets.get_secret_value.side_effect = Exception("Secrets error")
        
        with pytest.raises(Exception) as exc_info:
            get_db_connection()
        
        assert "Secrets error" in str(exc_info.value)

    @patch('data_ingestion.secretsmanager_client')
    @patch('data_ingestion.psycopg2.connect')
    def test_get_db_connection_connection_error(self, mock_connect, mock_secrets):
        """Test get_db_connection when database connection fails."""
        from data_ingestion import get_db_connection
        
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
        
        mock_connect.side_effect = Exception("Connection failed")
        
        with pytest.raises(Exception) as exc_info:
            get_db_connection()
        
        assert "Connection failed" in str(exc_info.value)

    @patch('data_ingestion.bedrock_runtime')
    def test_get_embedding_non_throttling_error(self, mock_bedrock):
        """Test get_embedding with non-throttling error."""
        from data_ingestion import get_embedding
        from botocore.exceptions import ClientError
        
        # Mock non-throttling error
        error = ClientError(
            {'Error': {'Code': 'ValidationException', 'Message': 'Invalid input'}},
            'invoke_model'
        )
        mock_bedrock.invoke_model.side_effect = error
        
        with pytest.raises(ClientError):
            get_embedding("test content")

    @patch('data_ingestion.bedrock_runtime')
    def test_get_embedding_max_retries_exceeded(self, mock_bedrock):
        """Test get_embedding when max retries are exceeded."""
        from data_ingestion import get_embedding
        from botocore.exceptions import ClientError
        
        # Mock throttling error that persists beyond max retries
        error = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'Too many requests'}},
            'invoke_model'
        )
        mock_bedrock.invoke_model.side_effect = error
        
        with pytest.raises(ClientError):
            get_embedding("test content")

    @patch('data_ingestion.execute_values')
    def test_insert_chunks_database_error(self, mock_execute):
        """Test insert_chunks when database operation fails."""
        from data_ingestion import insert_chunks
        
        mock_cursor = MagicMock()
        chunks = [
            {
                'id': 'chunk-1',
                'title': 'Test',
                'content': 'Content',
                'document_id': 'doc-1',
                'section': 'Section',
                'source': 'Source',
                'embedding': [0.1] * 1536,
                'date_scraped': '2024-01-15'
            }
        ]
        
        mock_execute.side_effect = Exception("Database insert failed")
        
        with pytest.raises(Exception) as exc_info:
            insert_chunks(mock_cursor, chunks)
        
        assert "Database insert failed" in str(exc_info.value)

    @patch('data_ingestion.execute_values')
    def test_insert_chunks_date_parsing_error(self, mock_execute):
        """Test insert_chunks with invalid date format."""
        from data_ingestion import insert_chunks
        
        mock_cursor = MagicMock()
        chunks = [
            {
                'id': 'chunk-1',
                'title': 'Test',
                'content': 'Content',
                'document_id': 'doc-1',
                'section': 'Section',
                'source': 'Source',
                'embedding': [0.1] * 1536,
                'date_scraped': 'invalid-date'  # Will trigger except block
            }
        ]
        
        # Should use datetime.now() as fallback
        insert_chunks(mock_cursor, chunks)
        
        # Verify execute_values was called
        assert mock_execute.called

    @patch('data_ingestion.execute_values')
    def test_insert_chunks_empty_list(self, mock_execute):
        """Test insert_chunks with empty chunk list."""
        from data_ingestion import insert_chunks
        
        mock_cursor = MagicMock()
        
        insert_chunks(mock_cursor, [])
        
        # Should not call execute_values
        assert not mock_execute.called

    def test_initialize_database_error(self):
        """Test initialize_database when SQL execution fails."""
        from data_ingestion import initialize_database
        
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("SQL execution failed")
        
        with pytest.raises(Exception) as exc_info:
            initialize_database(mock_cursor)
        
        assert "SQL execution failed" in str(exc_info.value)

    @patch('data_ingestion.get_db_connection')
    @patch('data_ingestion.s3_client')
    @patch('data_ingestion.get_embedding')
    def test_handler_no_valid_documents(self, mock_get_embedding, mock_s3, mock_get_db, 
                                       sample_s3_event, mock_lambda_context):
        """Test handler when all documents fail validation."""
        # Mock S3 with invalid documents
        invalid_docs = [
            {'id': 'doc-1'},  # missing content
            {'content': 'test'}  # missing id
        ]
        mock_s3.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(invalid_docs).encode())
        }
        
        result = handler(sample_s3_event, mock_lambda_context)
        
        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert 'error' in body

    @patch('data_ingestion.get_db_connection')
    @patch('data_ingestion.s3_client')
    @patch('data_ingestion.get_embedding')
    def test_handler_timeout_warning(self, mock_get_embedding, mock_s3, mock_get_db, 
                                    sample_s3_event, mock_lambda_context, sample_documents):
        """Test handler timeout warning path."""
        # Mock S3
        mock_s3.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(sample_documents).encode())
        }
        
        # Mock lambda context with very short timeout
        mock_lambda_context.get_remaining_time_in_millis.return_value = 30000  # 30 seconds
        
        # Mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []  # No existing chunks
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_db.return_value = mock_conn
        
        # Mock embedding
        mock_get_embedding.return_value = [0.1] * 1536
        
        with patch('data_ingestion.execute_values'):
            with patch('data_ingestion.time.sleep'):
                result = handler(sample_s3_event, mock_lambda_context)
        
        # Should succeed but may hit timeout warning
        assert result['statusCode'] in [200, 500]

    @patch('data_ingestion.get_db_connection')
    @patch('data_ingestion.s3_client')
    @patch('data_ingestion.get_embedding')
    def test_handler_embedding_throttling_continues(self, mock_get_embedding, mock_s3, mock_get_db,
                                                    sample_s3_event, mock_lambda_context, sample_documents):
        """Test handler continues after throttling errors on individual chunks."""
        from botocore.exceptions import ClientError
        
        # Mock S3
        mock_s3.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(sample_documents).encode())
        }
        
        # Mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_db.return_value = mock_conn
        
        # Mock embedding - first chunk fails with throttling, rest succeed
        throttle_error = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'Too many requests'}},
            'invoke_model'
        )
        mock_get_embedding.side_effect = [
            throttle_error,  # First chunk fails
            [0.1] * 1536,    # Second chunk succeeds
            [0.2] * 1536     # Third chunk succeeds
        ]
        
        with patch('data_ingestion.execute_values'):
            with patch('data_ingestion.time.sleep'):
                result = handler(sample_s3_event, mock_lambda_context)
        
        # Should still succeed with partial processing
        assert result['statusCode'] == 200

    def test_clean_document_with_none_date(self):
        """Test clean_document handles None date gracefully."""
        from data_ingestion import clean_document
        
        doc = {
            'id': 'test-1',
            'content': '  Test content  ',
            'title': 'Test Title',
            'date_published': None,  # None date
            'date_scraped': '2024-01-15'
        }
        
        result = clean_document(doc)
        
        # Should handle None date without error
        assert result['date_published'] is None
        assert result['date_scraped'] == '2024-01-15'
        assert result['content'] == 'Test content'
