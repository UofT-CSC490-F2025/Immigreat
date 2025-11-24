"""Integration tests for the RAG pipeline end-to-end."""
import pytest
import json
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, 'src')
sys.path.insert(0, 'src/model')


@pytest.mark.integration
@pytest.mark.slow
class TestRagPipelineIntegration:
    """Integration tests for complete RAG pipeline."""

    @patch('model.rag_pipeline.secretsmanager_client')
    @patch('model.rag_pipeline.bedrock_runtime')
    @patch('model.rag_pipeline.psycopg2.connect')
    def test_complete_query_flow(self, mock_connect, mock_bedrock, 
                                 mock_secrets, mock_env_vars):
        """Test complete query flow from input to output."""
        from model.rag_pipeline import handler
        
        # Mock secrets
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
        
        # Mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('chunk-1', 'Visitor visa requirements content', 'IRCC', 'Visitor Visa', 0.95),
            ('chunk-2', 'Application process content', 'Forms', 'IMM5257', 0.90)
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        # Mock Bedrock calls
        def bedrock_side_effect(*args, **kwargs):
            model_id = kwargs.get('modelId', '')
            if 'embed' in model_id.lower():
                # Embedding response
                response = MagicMock()
                response.read.return_value = json.dumps({'embedding': [0.1] * 1536}).encode()
                return {'body': response}
            elif 'rerank' in model_id.lower():
                # Rerank response
                response = MagicMock()
                response.read.return_value = json.dumps({
                    'results': [
                        {'index': 0, 'relevance_score': 0.95},
                        {'index': 1, 'relevance_score': 0.88}
                    ]
                }).encode()
                return {'body': response}
            else:
                # Claude response
                response = MagicMock()
                response.read.return_value = json.dumps({
                    'content': [{'type': 'text', 'text': 'To apply for a Canadian visitor visa, you need...'}]
                }).encode()
                return {'body': response}
        
        mock_bedrock.invoke_model.side_effect = bedrock_side_effect
        
        # Execute query
        event = {'query': 'What are the requirements for a Canadian visitor visa?'}
        mock_context = MagicMock()
        mock_context.get_remaining_time_in_millis.return_value = 300000
        result = handler(event, mock_context)
        
        # Verify response
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        
        assert 'answer' in body
        assert 'sources' in body
        assert 'timings' in body
        assert len(body['sources']) > 0
        assert 'visitor visa' in body['answer'].lower() or len(body['answer']) > 0

    @patch('model.rag_pipeline.get_db_connection')
    def test_error_propagation(self, mock_get_db, mock_env_vars):
        """Test that errors are properly propagated and handled."""
        from model.rag_pipeline import handler
        
        mock_get_db.side_effect = Exception("Database connection failed")
        
        event = {'query': 'test query'}
        result = handler(event, None)
        
        # Should return error response, not crash
        assert result['statusCode'] == 500
        assert 'error' in json.loads(result['body']) or 'body' in result


@pytest.mark.integration
class TestDataIngestionIntegration:
    """Integration tests for data ingestion pipeline."""

    @patch('data_ingestion.s3_client')
    @patch('data_ingestion.secretsmanager_client')
    @patch('data_ingestion.bedrock_runtime')
    @patch('data_ingestion.psycopg2.connect')
    def test_complete_ingestion_flow(self, mock_connect, mock_bedrock,
                                     mock_secrets, mock_s3, mock_env_vars,
                                     sample_s3_event, mock_lambda_context, sample_documents):
        """Test complete document ingestion flow."""
        from data_ingestion import handler
        
        # Mock S3
        mock_s3.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(sample_documents).encode())
        }
        
        # Mock secrets
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
        
        # Mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        # Mock Bedrock embedding
        embedding_response = MagicMock()
        embedding_response.read.return_value = json.dumps({'embedding': [0.1] * 1536}).encode()
        mock_bedrock.invoke_model.return_value = {'body': embedding_response}
        
        # Execute handler
        result = handler(sample_s3_event, mock_lambda_context)
        
        # Verify processing
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'processed' in body
        assert body['processed'] > 0
