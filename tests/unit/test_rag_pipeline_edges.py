import json
import types
import builtins
import os
import io
import pytest

import src.model.rag_pipeline as rp


def _mock_bedrock_response(payload_dict):
    body = io.BytesIO(json.dumps(payload_dict).encode("utf-8"))
    return {"body": body}


def test_handler_invalid_json_body_returns_400(monkeypatch):
    # No need to reach external services
    event = {"body": "not-json"}
    result = rp.handler(event, context=None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert "error" in body


def test_generate_answer_non_text_blocks_raises_value_error(monkeypatch):
    def fake_invoke(model_id, body, content_type="application/json", accept="application/json", max_retries=None):
        return _mock_bedrock_response({"content": [{"type": "tool_use", "id": "x"}]})

    monkeypatch.setattr(rp, "invoke_bedrock_with_backoff", fake_invoke)

    with pytest.raises(ValueError):
        rp.generate_answer("prompt")


def test_rerank_chunks_duplicate_and_invalid_indices_dedup_and_fallback(monkeypatch):
    chunks = [
        (1, "c1", "s1", "t1", 0.9),
        (2, "c2", "s2", "t2", 0.8),
        (3, "c3", "s3", "t3", 0.7),
    ]

    def fake_invoke(model_id, body, content_type="application/json", accept="application/json", max_retries=None):
        # Duplicate, invalid negative, and out-of-bounds indices
        return _mock_bedrock_response({
            "results": [
                {"index": 1, "relevance_score": 0.5},
                {"index": 1, "relevance_score": 0.49},
                {"index": -1, "relevance_score": 0.6},
                {"index": 10, "relevance_score": 0.7},
            ]
        })

    monkeypatch.setattr(rp, "invoke_bedrock_with_backoff", fake_invoke)
    ranked = rp.rerank_chunks("q", chunks)
    # Expect unique valid index 1 first, then fallback fills remaining preserving order
    assert [r[0] for r in ranked] == [2, 1, 3]


def test_expand_via_facets_empty_facets_env_returns_no_extras(monkeypatch):
    # Temporarily force empty facets
    monkeypatch.setenv("FE_RAG_FACETS", "")
    # Re-import env-derived config
    import importlib
    import src.model.rag_pipeline as rp_reload
    importlib.reload(rp_reload)

    seed_rows = [
        (10, "seed content", "sourceA", "titleA", 0.99)
    ]

    class Cursor:
        def execute(self, *_):
            pass
        def fetchall(self):
            return []
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    class Conn:
        def cursor(self):
            return Cursor()

    extras = rp_reload.expand_via_facets(Conn(), seed_rows, [0.1, 0.2, 0.3], extra_limit=5)
    assert extras == []


def test_get_db_connection_missing_fields_raises_keyerror(monkeypatch):
    class FakeSecrets:
        def get_secret_value(self, SecretId):
            return {"SecretString": json.dumps({"host": "h", "port": 5432, "username": "u"})}

    called = {"connect": False}

    def fake_connect(**kwargs):
        called["connect"] = True
        return object()

    monkeypatch.setattr(rp, "secretsmanager_client", FakeSecrets())
    monkeypatch.setattr(rp, "psycopg2", types.SimpleNamespace(connect=fake_connect))

    with pytest.raises(KeyError):
        rp.get_db_connection()
    assert called["connect"] is False


def test_retrieve_similar_chunks_empty_rows_end_to_end_still_200(monkeypatch):
    # Mock DB returns no rows
    class Cursor:
        def execute(self, *_):
            pass
        def fetchall(self):
            return []
        def close(self):
            pass

    class Conn:
        def cursor(self):
            return Cursor()
        def close(self):
            pass

    # get_db_connection returns our fake connection
    monkeypatch.setattr(rp, "get_db_connection", lambda: Conn())

    # get_embedding returns dummy vector
    monkeypatch.setattr(rp, "get_embedding", lambda q: [0.0, 0.0, 0.0])

    # generate_answer returns a fixed string
    monkeypatch.setattr(rp, "generate_answer", lambda prompt: "ok")

    event = {"query": "hello"}
    result = rp.handler(event, context=None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["answer"] == "ok"
    # No sources since retrieval returned empty
    assert body["sources"] == []
    # Timings present - only check for keys that should always be present
    # When use_facets=False and use_rerank=False (defaults), only these timing keys are included
    assert set(["embedding_ms", "primary_retrieval_ms", "llm_ms", "total_ms"]).issubset(body["timings"].keys())
