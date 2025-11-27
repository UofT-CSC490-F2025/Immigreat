import io
import json
import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

# Target module path
from model import rag_pipeline

class TestRagPipelineAdvanced:
    @patch.object(rag_pipeline, 'bedrock_runtime')
    def test_invoke_bedrock_with_backoff_throttling_success(self, mock_runtime):
        """Simulate two throttling errors then success to exercise retry + success log path."""
        # Build side effects: two throttling ClientErrors then a success dict
        def throttling_error():
            raise ClientError({'Error': {'Code': 'ThrottlingException'}}, 'InvokeModel')
        success_resp = {'body': io.BytesIO(b'{"content": [{"type": "text", "text": "ok"}]}')}
        # Need actual exceptions, not callables stored
        mock_runtime.invoke_model.side_effect = [
            ClientError({'Error': {'Code': 'ThrottlingException'}}, 'InvokeModel'),
            ClientError({'Error': {'Code': 'ThrottlingException'}}, 'InvokeModel'),
            success_resp
        ]
        resp = rag_pipeline.invoke_bedrock_with_backoff(model_id='test-model', body='{}', max_retries=5)
        assert resp == success_resp
        assert mock_runtime.invoke_model.call_count == 3

    @patch.object(rag_pipeline, 'bedrock_runtime')
    def test_invoke_bedrock_with_backoff_non_throttling_error(self, mock_runtime):
        """Non-throttling error should raise immediately (no retry loop)."""
        mock_runtime.invoke_model.side_effect = ClientError({'Error': {'Code': 'ValidationException'}}, 'InvokeModel')
        with pytest.raises(ClientError):
            rag_pipeline.invoke_bedrock_with_backoff(model_id='bad-model', body='{}', max_retries=4)
        assert mock_runtime.invoke_model.call_count == 1

    @patch.object(rag_pipeline, 'invoke_bedrock_with_backoff')
    def test_generate_answer_unexpected_format_raises(self, mock_invoke):
        """Response lacking 'content' list should raise ValueError (format guard)."""
        mock_invoke.return_value = {'body': io.BytesIO(b'{"no_content": true}')}  # wrong shape triggers ValueError
        with pytest.raises(ValueError):
            rag_pipeline.generate_answer('prompt here')

    @patch.object(rag_pipeline, 'invoke_bedrock_with_backoff')
    def test_rerank_chunks_fallback_on_exception(self, mock_invoke):
        """Exception during rerank leads to similarity-order fallback path."""
        mock_invoke.side_effect = Exception('bedrock fail')
        chunks = [
            (1, 'alpha content', 'src1', 'title1', 0.9),
            (2, 'beta content', 'src2', 'title2', 0.8),
        ]
        ranked = rag_pipeline.rerank_chunks('query', chunks)
        assert ranked == chunks  # fallback preserves original order truncated to CONTEXT_MAX_CHUNKS

    def test_handler_invalid_query_returns_400(self):
        """Blank query in event body returns 400 error response path."""
        event = {'body': json.dumps({'query': '   '})}
        result = rag_pipeline.handler(event, context=None)
        assert result['statusCode'] == 400
        assert 'error' in json.loads(result['body'])

    @patch.object(rag_pipeline, 'invoke_bedrock_with_backoff')
    def test_handler_minimal_happy_path(self, mock_invoke):
        """Exercise handler happy path with mocked embedding, retrieval, facet expansion, rerank, and chat."""
        # Mock embedding response
        embed_vec = [0.1, 0.2, 0.3]
        def fake_invoke(model_id, body, **kwargs):
            # Distinguish model usage by body shape heuristically
            data = json.loads(body)
            if 'inputText' in data:
                return {'body': io.BytesIO(b'{"embedding": [0.1,0.2,0.3]}')}
            if 'documents' in data:  # rerank
                return {'body': io.BytesIO(b'{"results": [{"index":0, "relevance_score":0.95},{"index":1, "relevance_score":0.9}]}')}
            # chat payload
            return {'body': io.BytesIO(b'{"content": [{"type":"text","text":"answer here"}]}')}
        mock_invoke.side_effect = fake_invoke

        # Stub DB connection and cursor behavior
        class FakeCursor:
            def __init__(self):
                self.calls = []
            def execute(self, sql, params):
                self.calls.append((sql, params))
            def fetchall(self):
                # Provide two seed rows (id, content, source, title, similarity placeholder)
                if 'SELECT id, content' in self.calls[-1][0]:
                    return [
                        (1, 'seed one', 'sourceA', 'titleA', 0.91),
                        (2, 'seed two', 'sourceB', 'titleB', 0.89)
                    ]
                # Facet expansion sections query
                if 'SELECT section' in self.calls[-1][0]:
                    return [('Section1',), ('Section1',), ('Section2',)]
                # Expansion query returning similar extra rows
                if 'WHERE id <> ALL' in self.calls[-1][0]:
                    return [
                        (3, 'extra three', 'sourceA', 'titleC', 0.88),
                        (4, 'extra four', 'sourceB', 'titleD', 0.87)
                    ]
                return []
            def close(self):
                pass
            # Context manager support
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
        class FakeConn:
            def cursor(self):
                return FakeCursor()
            def close(self):
                pass
        # Patch get_db_connection
        with patch.object(rag_pipeline, 'get_db_connection', return_value=FakeConn()):
            # Ensure section facet is active
            with patch.dict('os.environ', {'FE_RAG_FACETS': 'source,title,section'}):
                result = rag_pipeline.handler({'query': 'Test query'}, context=None)
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['answer'] == 'answer here'
        assert len(body['sources']) >= 2

