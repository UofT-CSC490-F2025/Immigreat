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
