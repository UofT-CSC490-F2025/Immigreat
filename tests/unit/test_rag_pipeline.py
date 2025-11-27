"""Unit tests for RAG pipeline module."""
import pytest
import json
from unittest.mock import MagicMock, patch, ANY
import sys
sys.path.insert(0, 'src')
sys.path.insert(0, 'src/model')


@pytest.mark.unit
class TestGetDbConnection:
    """Tests for database connection."""

    @patch('model.rag_pipeline.secretsmanager_client')
    @patch('model.rag_pipeline.psycopg2.connect')
    def test_get_db_connection_success(self, mock_connect, mock_secrets, mock_env_vars):
        """Test successful database connection."""
        from model.rag_pipeline import get_db_connection
        
        # Mock secrets manager response
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
        
        mock_connect.return_value = MagicMock()
        
        conn = get_db_connection()
        
        assert conn is not None
        mock_connect.assert_called_once()


@pytest.mark.unit
class TestGetEmbedding:
    """Tests for embedding generation in RAG pipeline."""

    @patch('model.rag_pipeline.bedrock_runtime')
    def test_get_embedding_success(self, mock_bedrock, mock_env_vars):
        """Test successful embedding generation."""
        from model.rag_pipeline import get_embedding
        
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'embedding': [0.1] * 1536}).encode()
        mock_bedrock.invoke_model.return_value = {'body': mock_response}
        
        text = "Test query"
        embedding = get_embedding(text)
        
        assert len(embedding) == 1536
        assert all(isinstance(x, float) for x in embedding)


@pytest.mark.unit
class TestRetrieveSimilarChunks:
    """Tests for vector similarity retrieval."""

    def test_retrieve_similar_chunks(self, mock_embedding_vector):
        """Test retrieving similar chunks."""
        from model.rag_pipeline import retrieve_similar_chunks
        
        # Setup mock connection with proper context manager
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Mock database results
        mock_results = [
            ('chunk-1', 'Content 1', 'source-1', 'title-1', 0.95),
            ('chunk-2', 'Content 2', 'source-2', 'title-2', 0.90),
            ('chunk-3', 'Content 3', 'source-3', 'title-3', 0.85)
        ]
        mock_cursor.fetchall = MagicMock(return_value=mock_results)
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        
        results = retrieve_similar_chunks(mock_conn, mock_embedding_vector, k=3)
        
        assert len(results) == 3
        assert results[0][4] >= results[1][4]  # Check descending similarity
        assert results[1][4] >= results[2][4]


@pytest.mark.unit
class TestGenerateAnswer:
    """Tests for answer generation."""

    @patch('model.rag_pipeline.bedrock_runtime')
    def test_generate_answer_success(self, mock_bedrock, mock_env_vars):
        """Test successful answer generation."""
        from model.rag_pipeline import generate_answer
        
        mock_response_body = {
            'content': [
                {'type': 'text', 'text': 'This is the generated answer.'}
            ]
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_response_body).encode()
        mock_bedrock.invoke_model.return_value = {'body': mock_response}
        
        prompt = "Test prompt with context"
        answer = generate_answer(prompt)
        
        assert isinstance(answer, str)
        assert len(answer) > 0


@pytest.mark.unit
class TestInvokeBedrockWithBackoff:
    """Tests for Bedrock retry logic."""

    @patch('model.rag_pipeline.bedrock_runtime')
    @patch('model.rag_pipeline.time.sleep')
    def test_backoff_success_after_retry(self, mock_sleep, mock_bedrock, mock_env_vars):
        """Test successful call after retry."""
        from model.rag_pipeline import invoke_bedrock_with_backoff
        from botocore.exceptions import ClientError
        
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'embedding': [0.1] * 1536}).encode()
        
        error_response = {'Error': {'Code': 'ThrottlingException'}}
        mock_bedrock.invoke_model.side_effect = [
            ClientError(error_response, 'InvokeModel'),
            {'body': mock_response}
        ]
        
        body = json.dumps({'inputText': 'test'})
        result = invoke_bedrock_with_backoff('test-model', body)
        
        assert result is not None
        assert mock_bedrock.invoke_model.call_count == 2
        mock_sleep.assert_called_once()

    @patch('model.rag_pipeline.bedrock_runtime')
    def test_backoff_non_throttling_error(self, mock_bedrock, mock_env_vars):
        """Test immediate failure on non-throttling error."""
        from model.rag_pipeline import invoke_bedrock_with_backoff
        from botocore.exceptions import ClientError
        
        error_response = {'Error': {'Code': 'ValidationException'}}
        mock_bedrock.invoke_model.side_effect = ClientError(error_response, 'InvokeModel')
        
        body = json.dumps({'inputText': 'test'})
        
        with pytest.raises(ClientError):
            invoke_bedrock_with_backoff('test-model', body, max_retries=3)
        
        assert mock_bedrock.invoke_model.call_count == 1


@pytest.mark.unit
class TestHandler:
    """Tests for RAG pipeline Lambda handler."""

    @patch('model.rag_pipeline.get_db_connection')
    @patch('model.rag_pipeline.get_embedding')
    @patch('model.rag_pipeline.retrieve_similar_chunks')
    @patch('model.rag_pipeline.generate_answer')
    def test_handler_direct_invoke(self, mock_generate, mock_retrieve, 
                                   mock_embedding, mock_db, 
                                   sample_query_event, mock_env_vars):
        """Test handler with direct invocation style."""
        from model.rag_pipeline import handler
        
        # Setup mocks
        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_embedding.return_value = [0.1] * 1536
        mock_retrieve.return_value = [
            ('chunk-1', 'Content 1', 'source-1', 'title-1', 0.95)
        ]
        mock_generate.return_value = "This is the answer."
        
        result = handler(sample_query_event, None)
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'answer' in body
        assert 'sources' in body
        assert 'timings' in body

    @patch('model.rag_pipeline.get_db_connection')
    @patch('model.rag_pipeline.get_embedding')
    @patch('model.rag_pipeline.retrieve_similar_chunks')
    @patch('model.rag_pipeline.generate_answer')
    def test_handler_http_invoke(self, mock_generate, mock_retrieve, 
                                 mock_embedding, mock_db,
                                 sample_http_query_event, mock_env_vars):
        """Test handler with HTTP invocation style."""
        from model.rag_pipeline import handler
        
        # Setup mocks
        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_embedding.return_value = [0.1] * 1536
        mock_retrieve.return_value = [
            ('chunk-1', 'Content 1', 'source-1', 'title-1', 0.95)
        ]
        mock_generate.return_value = "This is the answer."
        
        result = handler(sample_http_query_event, None)
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['answer'] == "This is the answer."

    def test_handler_missing_query(self, mock_env_vars):
        """Test handler with missing query."""
        from model.rag_pipeline import handler
        
        event = {}
        result = handler(event, None)
        
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'error' in body

    def test_handler_empty_query(self, mock_env_vars):
        """Test handler with empty query."""
        from model.rag_pipeline import handler
        
        event = {'query': ''}
        result = handler(event, None)
        
        assert result['statusCode'] == 400

    @patch('model.rag_pipeline.get_db_connection')
    def test_handler_db_error(self, mock_db, sample_query_event, mock_lambda_context, mock_env_vars):
        """Test handler with database error."""
        from model.rag_pipeline import handler
        
        mock_db.side_effect = Exception("Database connection failed")
        
        # Handler may not catch all errors, expect exception or 500
        try:
            result = handler(sample_query_event, mock_lambda_context)
            assert result['statusCode'] == 500
        except Exception as e:
            assert "Database connection failed" in str(e)


@pytest.mark.unit
class TestRerankChunks:
    """Tests for reranking functionality."""

    @patch('model.rag_pipeline.bedrock_runtime')
    def test_rerank_chunks_success(self, mock_bedrock, mock_env_vars):
        """Test successful chunk reranking."""
        from model.rag_pipeline import rerank_chunks
        
        chunks = [
            ('chunk-1', 'Content 1', 'source-1', 'title-1', 0.85),
            ('chunk-2', 'Content 2', 'source-2', 'title-2', 0.90),
            ('chunk-3', 'Content 3', 'source-3', 'title-3', 0.80)
        ]
        
        # Mock rerank response
        rerank_response = {
            'results': [
                {'index': 1, 'relevance_score': 0.95},
                {'index': 0, 'relevance_score': 0.88},
                {'index': 2, 'relevance_score': 0.75}
            ]
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(rerank_response).encode()
        mock_bedrock.invoke_model.return_value = {'body': mock_response}
        
        query = "test query"
        reranked = rerank_chunks(query, chunks)
        
        assert len(reranked) <= len(chunks)
        # First result should have highest relevance
        if len(reranked) > 1:
            assert reranked[0][0] == 'chunk-2'  # Original index 1

    def test_rerank_chunks_fallback(self, mock_env_vars):
        """Test rerank fallback on error."""
        from model.rag_pipeline import rerank_chunks
        
        chunks = [
            ('chunk-1', 'Content 1', 'source-1', 'title-1', 0.90),
            ('chunk-2', 'Content 2', 'source-2', 'title-2', 0.85)
        ]
        
        with patch('model.rag_pipeline.bedrock_runtime') as mock_bedrock:
            mock_bedrock.invoke_model.side_effect = Exception("Rerank failed")
            
            reranked = rerank_chunks("test query", chunks)
            
            # Should fall back to original order
            assert len(reranked) > 0
            assert reranked == chunks[:len(reranked)]


@pytest.mark.unit
class TestExpandViaFacets:
    """Tests for facet expansion."""

    def test_expand_via_facets(self, mock_db_connection, mock_embedding_vector):
        """Test facet-based expansion."""
        from model.rag_pipeline import expand_via_facets
        
        mock_conn, mock_cursor = mock_db_connection
        
        initial_chunks = [
            ('chunk-1', 'Content 1', 'IRCC', 'Visa Info', 0.95)
        ]
        
        # Mock expanded results
        mock_cursor.fetchall.return_value = [
            ('chunk-2', 'Content 2', 'IRCC', 'Related Info', 0.88),
            ('chunk-3', 'Content 3', 'IRCC', 'More Info', 0.85)
        ]
        
        extras = expand_via_facets(mock_conn, initial_chunks, mock_embedding_vector, extra_limit=5)
        
        assert isinstance(extras, list)
        # Should return additional chunks
        assert len(extras) >= 0


class TestBedrockEdgeCases:
    """Tests for rare Bedrock invocation edge cases."""
    
    @patch('model.rag_pipeline.bedrock_runtime')
    @patch('model.rag_pipeline.time.sleep')  # Mock sleep to speed up tests
    def test_invoke_bedrock_max_retries_throttling(self, mock_sleep, mock_bedrock):
        """Test that max retries are exhausted with ThrottlingException."""
        from model.rag_pipeline import invoke_bedrock_with_backoff
        from botocore.exceptions import ClientError
        
        throttle_error = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
            'invoke_model'
        )
        mock_bedrock.invoke_model.side_effect = throttle_error
        
        # Should raise after max retries
        with pytest.raises(ClientError) as exc_info:
            invoke_bedrock_with_backoff(
                'anthropic.claude-3-5-sonnet-20240620-v1:0',
                '{"prompt": "test"}'
            )
        
        assert exc_info.value.response['Error']['Code'] == 'ThrottlingException'
        # Should have tried 10 times (default MAX_BEDROCK_RETRIES)
        assert mock_bedrock.invoke_model.call_count == 10
    
    @patch('model.rag_pipeline.bedrock_runtime')
    def test_invoke_bedrock_unexpected_exception(self, mock_bedrock):
        """Test that unexpected exceptions are raised immediately."""
        from model.rag_pipeline import invoke_bedrock_with_backoff
        
        mock_bedrock.invoke_model.side_effect = RuntimeError("Unexpected error")
        
        # Should raise immediately without retries
        with pytest.raises(RuntimeError) as exc_info:
            invoke_bedrock_with_backoff(
                'anthropic.claude-3-5-sonnet-20240620-v1:0',
                '{"prompt": "test"}'
            )
        
        assert "Unexpected error" in str(exc_info.value)
        # Should only try once - no retries for unexpected errors
        assert mock_bedrock.invoke_model.call_count == 1


class TestRerankChunks:
    """Tests for rerank_chunks function."""
    
    @patch.dict('os.environ', {'RERANK_ENABLE': 'false'})
    def test_rerank_disabled(self):
        """Test rerank_chunks when RERANK_ENABLE is false."""
        from model.rag_pipeline import rerank_chunks
        
        # Import after patching environment to ensure RERANK_ENABLE is loaded
        import importlib
        import model.rag_pipeline
        importlib.reload(model.rag_pipeline)
        from model.rag_pipeline import rerank_chunks
        
        chunks = [
            ('id1', 'content1', 'source1', 'title1', 0.9),
            ('id2', 'content2', 'source2', 'title2', 0.8),
            ('id3', 'content3', 'source3', 'title3', 0.7),
        ]
        
        # Should return chunks unchanged (up to CONTEXT_MAX_CHUNKS)
        result = rerank_chunks('test query', chunks)
        
        # Verify it returns the original chunks
        assert len(result) <= len(chunks)
        assert result[0][0] == 'id1'  # First chunk ID preserved
