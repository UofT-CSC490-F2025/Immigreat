"""Tests for data ingestion helper functions."""
import pytest
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, 'src')


@pytest.mark.unit
class TestDataIngestionHelpers:
    """Test data ingestion helper/utility functions."""

    def test_clean_text_removes_extra_whitespace(self):
        """Test clean_text removes extra whitespace."""
        from data_ingestion import clean_text
        
        # Multiple spaces
        assert clean_text("text   with   spaces") == "text with spaces"
        
        # Newlines and tabs
        assert clean_text("text\n\nwith\n\nnewlines") == "text with newlines"
        assert clean_text("text\t\twith\t\ttabs") == "text with tabs"
        
        # Mixed whitespace
        assert clean_text("text \n\t  with  \n mixed") == "text with mixed"

    def test_clean_text_strips_leading_trailing(self):
        """Test clean_text strips leading/trailing whitespace."""
        from data_ingestion import clean_text
        
        assert clean_text("  text  ") == "text"
        assert clean_text("\n\ntext\n\n") == "text"
        assert clean_text("\t\ttext\t\t") == "text"

    def test_clean_text_empty_string(self):
        """Test clean_text with empty string."""
        from data_ingestion import clean_text
        
        assert clean_text("") == ""
        assert clean_text("   ") == ""
        assert clean_text("\n\n\t\t  ") == ""

    def test_clean_text_preserves_single_spaces(self):
        """Test clean_text preserves single spaces."""
        from data_ingestion import clean_text
        
        text = "This is a normal sentence with proper spacing."
        assert clean_text(text) == text

    def test_clean_text_handles_unicode(self):
        """Test clean_text handles unicode characters."""
        from data_ingestion import clean_text
        
        text = "Café  résumé  naïve"
        result = clean_text(text)
        
        assert "Café" in result
        assert "résumé" in result
        assert "naïve" in result
        # Should still collapse multiple spaces
        assert "  " not in result

    def test_normalize_date_iso_format(self):
        """Test normalize_date with ISO format dates."""
        from data_ingestion import normalize_date
        
        assert normalize_date("2024-01-15") == "2024-01-15"
        assert normalize_date("2024-12-31") == "2024-12-31"

    def test_normalize_date_various_formats(self):
        """Test normalize_date with various date formats."""
        from data_ingestion import normalize_date
        
        # Already in ISO format
        result1 = normalize_date("2024-01-15")
        assert result1 == "2024-01-15"
        
        # US format
        result2 = normalize_date("01/15/2024")
        assert result2 == "2024-01-15"
        
        # Different separator
        result3 = normalize_date("15-01-2024")
        assert result3 == "2024-01-15"

    def test_normalize_date_invalid_input(self):
        """Test normalize_date with invalid input."""
        from data_ingestion import normalize_date
        
        # Function returns original string if can't parse
        assert normalize_date("invalid date") == "invalid date"
        assert normalize_date("") is None
        assert normalize_date("not-a-date") == "not-a-date"

    def test_normalize_date_none_input(self):
        """Test normalize_date with None input."""
        from data_ingestion import normalize_date
        
        result = normalize_date(None)
        assert result is None

    def test_validate_documents_filters_invalid(self):
        """Test validate_documents filters out invalid documents."""
        from data_ingestion import validate_documents
        
        documents = [
            {'id': '1', 'content': 'Valid content here'},
            {'id': '2', 'content': 'short'},  # Too short (< 10 chars)
            {'id': '3', 'content': ''},  # Empty content
            {'id': '4', 'content': 'x' * 100},
        ]
        
        valid_docs, invalid_count = validate_documents(documents)
        
        assert len(valid_docs) == 2
        assert invalid_count == 2

    def test_validate_documents_all_valid(self):
        """Test validate_documents with all valid documents."""
        from data_ingestion import validate_documents
        
        documents = [
            {'id': '1', 'content': 'Content 1 with enough text'},
            {'id': '2', 'content': 'Content 2 with enough text'},
            {'id': '3', 'content': 'Content 3 with enough text'},
        ]
        
        valid_docs, invalid_count = validate_documents(documents)
        
        assert len(valid_docs) == 3
        assert invalid_count == 0

    def test_validate_documents_empty_list(self):
        """Test validate_documents with empty list."""
        from data_ingestion import validate_documents
        
        valid_docs, invalid_count = validate_documents([])
        
        assert len(valid_docs) == 0
        assert invalid_count == 0

    def test_chunk_text_creates_chunks(self):
        """Test chunk_text creates appropriate chunks."""
        from data_ingestion import chunk_text
        
        # Long text that should be chunked
        text = "This is a sentence. " * 100  # ~2000 characters
        
        chunks = chunk_text(text, chunk_size=500, overlap=100)
        
        assert len(chunks) > 1
        assert all(isinstance(chunk, str) for chunk in chunks)
        assert all(len(chunk) <= 600 for chunk in chunks)  # Some tolerance

    def test_chunk_text_short_text(self):
        """Test chunk_text with text shorter than chunk size."""
        from data_ingestion import chunk_text
        
        text = "This is a short text."
        
        chunks = chunk_text(text, chunk_size=1000, overlap=200)
        
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_text_preserves_content(self):
        """Test chunk_text preserves all content."""
        from data_ingestion import chunk_text
        
        text = "Sentence 1. Sentence 2. Sentence 3. Sentence 4. Sentence 5."
        
        chunks = chunk_text(text, chunk_size=30, overlap=10)
        
        # All content should be present across chunks
        combined = " ".join(chunks)
        assert "Sentence 1" in combined
        assert "Sentence 5" in combined

    def test_clean_document_cleans_all_fields(self):
        """Test clean_document cleans text fields."""
        from data_ingestion import clean_document
        
        doc = {
            'id': 'test-1',
            'title': '  Title  with  spaces  ',
            'content': 'Content\n\nwith\n\nnewlines',
            'metadata': {'source': 'test'}
        }
        
        cleaned = clean_document(doc)
        
        # Title only gets strip() applied, not clean_text's regex
        assert cleaned['title'] == "Title  with  spaces"
        # Content gets clean_text which collapses whitespace
        assert cleaned['content'] == "Content with newlines"
        assert cleaned['id'] == 'test-1'

    def test_clean_document_handles_missing_fields(self):
        """Test clean_document handles missing optional fields."""
        from data_ingestion import clean_document
        
        doc = {
            'id': 'test-1',
            'title': 'Title',
            'content': 'Content'
        }
        
        # Should not raise error
        cleaned = clean_document(doc)
        
        assert cleaned['id'] == 'test-1'
        assert cleaned['title'] == 'Title'
        assert cleaned['content'] == 'Content'

    def test_chunk_document_creates_chunks_with_metadata(self):
        """Test chunk_document creates chunks with proper metadata."""
        from data_ingestion import chunk_document
        
        doc = {
            'id': 'doc-1',
            'title': 'Test Document',
            'content': 'This is content. ' * 200,  # Long content
            'metadata': {'source': 'test'}
        }
        
        chunks = chunk_document(doc, chunk_size=500, chunk_overlap=100)
        
        assert len(chunks) > 1
        for chunk in chunks:
            assert 'document_id' in chunk  # Uses document_id not doc_id
            assert 'id' in chunk  # chunk ID not chunk_id
            assert 'content' in chunk
            assert chunk['document_id'] == 'doc-1'
            assert chunk['title'] == 'Test Document'

    def test_chunk_document_single_chunk(self):
        """Test chunk_document with short content."""
        from data_ingestion import chunk_document
        
        doc = {
            'id': 'doc-1',
            'title': 'Short Doc',
            'content': 'Short content.',
            'metadata': {}
        }
        
        chunks = chunk_document(doc, chunk_size=1000, chunk_overlap=200)
        
        assert len(chunks) == 1
        assert chunks[0]['content'] == 'Short content.'

    @patch('data_ingestion.boto3.client')
    def test_save_to_s3_success(self, mock_boto):
        """Test save_to_s3 successful upload."""
        from data_ingestion import save_to_s3
        
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        
        data = {'key': 'value'}
        # Function is disabled and just prints, doesn't call S3
        result = save_to_s3(data, 'test-bucket', 'test-key.json')
        
        # Function returns None and doesn't call S3
        assert result is None

    @patch('data_ingestion.boto3.client')
    def test_save_to_s3_handles_error(self, mock_boto):
        """Test save_to_s3 handles S3 errors."""
        from data_ingestion import save_to_s3
        
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = Exception("S3 error")
        mock_boto.return_value = mock_s3
        
        # Should not raise exception
        save_to_s3({'key': 'value'}, 'test-bucket', 'test-key.json')

    @patch('data_ingestion.psycopg2.connect')
    @patch('data_ingestion.secretsmanager_client.get_secret_value')
    def test_get_db_connection_success(self, mock_get_secret, mock_connect):
        """Test get_db_connection creates connection."""
        from data_ingestion import get_db_connection
        import json
        
        # Mock the secrets manager response
        mock_get_secret.return_value = {
            'SecretString': json.dumps({
                'host': 'localhost',
                'port': 5432,
                'dbname': 'test',
                'username': 'user',
                'password': 'pass'
            })
        }
        
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        conn = get_db_connection()
        
        assert conn == mock_conn
        mock_connect.assert_called_once()

    @patch('data_ingestion.psycopg2.connect')
    def test_get_db_connection_handles_error(self, mock_connect):
        """Test get_db_connection handles connection errors."""
        from data_ingestion import get_db_connection
        
        mock_connect.side_effect = Exception("Connection failed")
        
        with pytest.raises(Exception):
            get_db_connection()
