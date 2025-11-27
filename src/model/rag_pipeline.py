import json
import os
import time
import random
import boto3
import psycopg2
from collections import Counter
from botocore.exceptions import ClientError

bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')
secretsmanager_client = boto3.client('secretsmanager')

PGVECTOR_SECRET_ARN = os.environ['PGVECTOR_SECRET_ARN']
EMBEDDING_MODEL = os.environ.get('BEDROCK_EMBEDDING_MODEL', 'amazon.titan-embed-text-v1')
# Make Claude model configurable via env; keep existing default if not set.
CLAUDE_MODEL_ID = os.environ.get('BEDROCK_CHAT_MODEL', 'anthropic.claude-3-5-sonnet-20240620-v1:0')
ANTHROPIC_VERSION = os.environ.get('ANTHROPIC_VERSION', 'bedrock-2023-05-31')
DEBUG_BEDROCK_LOG = True
# Comma-separated facet columns from the documents table to expand on
FE_RAG_FACETS = [c.strip() for c in os.environ.get('FE_RAG_FACETS', 'source,title,section').split(',') if c.strip()]
FE_RAG_MAX_FACET_VALUES = int(os.environ.get('FE_RAG_MAX_FACET_VALUES', '2'))  # per facet
FE_RAG_EXTRA_LIMIT = int(os.environ.get('FE_RAG_EXTRA_LIMIT', '5'))
RERANK_MODEL_ID = os.environ.get('RERANK_MODEL', 'cohere.rerank-v3-5:0')  # Bedrock Cohere Rerank
# Bedrock Cohere Re-rank requires an API version (integer) in the payload. Default to 2.
# Accept env as string and coerce; fallback to 2 if invalid.
try:
    RERANK_API_VERSION = int(os.environ.get('RERANK_API_VERSION', '2'))
except ValueError:
    RERANK_API_VERSION = 2
CONTEXT_MAX_CHUNKS = int(os.environ.get('CONTEXT_MAX_CHUNKS', '12'))

# Retry configuration for Bedrock API calls
MAX_BEDROCK_RETRIES = int(os.environ.get('MAX_BEDROCK_RETRIES', '10'))
BEDROCK_BASE_DELAY = float(os.environ.get('BEDROCK_BASE_DELAY', '1.0'))  # seconds
BEDROCK_MAX_JITTER = float(os.environ.get('BEDROCK_MAX_JITTER', '1.0'))  # seconds

def invoke_bedrock_with_backoff(model_id, body, content_type="application/json", accept="application/json", max_retries=None):
    """
    Invoke Bedrock model with exponential backoff and jitter to handle throttling.
    
    Args:
        model_id: The Bedrock model ID to invoke
        body: JSON string of the request body
        content_type: Content type header
        accept: Accept header
        max_retries: Maximum number of retry attempts (defaults to MAX_BEDROCK_RETRIES)
    
    Returns:
        Bedrock response object
        
    Raises:
        Exception if max retries exceeded or non-throttling error occurs
    """
    if max_retries is None:
        max_retries = MAX_BEDROCK_RETRIES
    
    last_exception = None
    
    # Tests referencing this block:
    # - tests/unit/test_rag_pipeline.py::test_bedrock_invoke_success
    #   Positive path: first call succeeds, returns response immediately.
    # - tests/unit/test_rag_pipeline_advanced.py::test_bedrock_throttling_retries
    #   Edge/failure mode: ThrottlingException triggers exponential backoff and eventual success.
    # - tests/unit/test_rag_pipeline_advanced.py::test_bedrock_non_throttling_raises
    #   Failure mode: Non-throttling error raises immediately without retry.
    # Rationale: Bedrock can throttle or return hard errors; retrying only on throttling preserves reliability while surfacing real faults quickly.
    for attempt in range(max_retries):
        try:
            response = bedrock_runtime.invoke_model(
                modelId=model_id,
                contentType=content_type,
                accept=accept,
                body=body
            )
            # Success - return immediately
            if attempt > 0:
                print(f"Successfully invoked {model_id} after {attempt + 1} attempts")
            return response
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            last_exception = e
            
            # Check if it's a throttling error
            if error_code == 'ThrottlingException':
                if attempt == max_retries - 1:
                    # Last attempt - don't sleep, just raise
                    print(f"Max retries ({max_retries}) exceeded for {model_id}")
                    raise
                
                # Calculate exponential backoff with jitter
                exponential_delay = (2 ** attempt) * BEDROCK_BASE_DELAY
                jitter = random.uniform(0, BEDROCK_MAX_JITTER)
                total_delay = exponential_delay + jitter
                
                print(f"ThrottlingException on attempt {attempt + 1}/{max_retries} for {model_id}, "
                      f"retrying in {total_delay:.2f}s (base: {exponential_delay:.2f}s + jitter: {jitter:.2f}s)")
                
                time.sleep(total_delay)
            else:
                # Non-throttling error - raise immediately
                print(f"Non-throttling error from {model_id}: {error_code} - {str(e)}")
                raise

def get_db_connection():
    # Tests referencing this block:
    # - tests/unit/test_rag_pipeline.py::test_get_db_connection_uses_secret
    #   Positive: Secrets Manager returns JSON; psycopg2.connect called with parsed creds.
    # - tests/unit/test_rag_pipeline_edges.py::test_get_db_connection_missing_fields_raises_keyerror
    #   Negative: missing required secret keys -> KeyError; connect not attempted.
    # Rationale: Secrets can drift; fail-fast prevents partial/incorrect DB connections and highlights config issues early.
    secret = secretsmanager_client.get_secret_value(SecretId=PGVECTOR_SECRET_ARN)
    creds = json.loads(secret['SecretString'])
    return psycopg2.connect(
        host=creds['host'], port=creds['port'], database=creds['dbname'],
        user=creds['username'], password=creds['password']
    )


def get_embedding(text: str):
    """Generate embedding for text using Bedrock with retry logic."""
    # Tests:
    # - tests/unit/test_rag_pipeline.py::test_get_embedding_success
    #   Positive: invokes embed model and returns parsed embedding.
    # - tests/unit/test_rag_pipeline_advanced.py::test_get_embedding_throttling_backoff
    #   Edge: throttling triggers backoff in invoke_bedrock_with_backoff.
    # Rationale: Embedding generation must be resilient under transient throttling to avoid cascading failures upstream.
    body = json.dumps({"inputText": text})
    resp = invoke_bedrock_with_backoff(
        model_id=EMBEDDING_MODEL,
        body=body
    )
    return json.loads(resp["body"].read())["embedding"]

def retrieve_similar_chunks(conn, embedding, k=5):
    # Tests:
    # - tests/unit/test_rag_pipeline.py::test_retrieve_similar_chunks_returns_rows
    #   Positive: cursor returns rows with expected tuple shape.
    # - tests/unit/test_rag_pipeline_edges.py::test_retrieve_similar_chunks_empty_rows_end_to_end_still_200
    #   Edge: empty result set propagates to handler; still returns 200 with empty sources.
    # Rationale: When no matches are found, API contract remains stable with graceful empty outputs.
    cur = conn.cursor()
    cur.execute("""
        SELECT id, content, source, title, 1 - (embedding <=> %s::vector) AS similarity
        FROM documents
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
    """, (embedding, embedding, k))
    rows = cur.fetchall()
    cur.close()
    return rows

def _top_values(rows, idx, n):
    """Return up to n most common non-empty values from rows at column idx."""
    # Tests:
    # - tests/unit/test_rag_pipeline.py::test_top_values_filters_empty
    #   Edge: empty values filtered; counts computed correctly.
    vals = [r[idx] for r in rows if r[idx]]
    return [v for v, _ in Counter(vals).most_common(n)]

def expand_via_facets(conn, seed_rows, query_embedding, extra_limit=5):
    """Facet-Expanded retrieval: treat shared metadata as lightweight graph edges.

    Strategy (minimal-changes version):
    - Take the top-k seed results by vector similarity.
    - Identify their most frequent facet values (e.g., source, title, section).
    - Pull additional chunks that match any of these facet values, ranked by similarity to the query.
    - Exclude already selected ids.
    """
    # Tests:
    # - tests/unit/test_rag_pipeline.py::test_expand_via_facets_empty_seed
    #   Edge: no seed_rows -> returns [].
    # - tests/unit/test_rag_pipeline.py::test_expand_via_facets_with_section_toggle
    #   Edge: FE_RAG_FACETS includes 'section' vs not; ensures clause and params handled.
    # - tests/unit/test_rag_pipeline_edges.py::test_expand_via_facets_empty_facets_env_returns_no_extras
    #   Edge: empty FE_RAG_FACETS env yields no extras; SQL executes with empty arrays.
    # Rationale: Config toggles should not break SQL execution; disabling facets must produce a safe no-op.
    if not seed_rows:
        return []

    # Map facet name to its column index in seed_rows (id, content, source, title, sim)
    col_idx = {"source": 2, "title": 3, "section": None}

    # We don't have section in the selected columns; fetch it during expansion if requested
    top_sources = _top_values(seed_rows, col_idx["source"], FE_RAG_MAX_FACET_VALUES) if "source" in FE_RAG_FACETS else []
    top_titles = _top_values(seed_rows, col_idx["title"], FE_RAG_MAX_FACET_VALUES) if "title" in FE_RAG_FACETS else []

    # Prepare arrays for SQL (empty arrays are fine)
    seed_ids = [r[0] for r in seed_rows]

    sql = """
        SELECT id, content, source, title, 1 - (embedding <=> %s::vector) AS similarity
        FROM documents
        WHERE id <> ALL(%s) AND (
            source = ANY(%s) OR
            title = ANY(%s)
            {section_clause}
        )
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
    """

    params = [query_embedding, seed_ids]

    # For source and title arrays
    params += [top_sources, top_titles]

    # Optional section facet support
    section_clause = ""
    top_sections = []
    if "section" in FE_RAG_FACETS:
        # Fetch sections from DB for the seed ids in one shot
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT section
                FROM documents
                WHERE id = ANY(%s)
                """,
                (seed_ids,)
            )
            sections = [r[0] for r in cur.fetchall() if r[0]]
            top_sections = [v for v, _ in Counter(sections).most_common(FE_RAG_MAX_FACET_VALUES)]
    section_clause = " OR section = ANY(%s)"
    params += [top_sections]

    # Fill final params for ranking and limit
    params += [query_embedding, extra_limit]

    full_sql = sql.format(section_clause=section_clause)

    # Tests:
    # - tests/unit/test_rag_pipeline.py::test_expand_via_facets_returns_extras
    #   Positive: executes SQL and fetches extras.
    with conn.cursor() as cur:
        cur.execute(full_sql, params)
        extras = cur.fetchall()
    return extras

def generate_answer(prompt: str) -> str:
    """Send a chat prompt to Claude on Bedrock and return the assistant text.

    Bedrock Anthropic models require:
      - anthropic_version field
      - messages: list of { role, content:[{type: "text", text: ...}] }
    """
    payload = {
        "anthropic_version": ANTHROPIC_VERSION,
        "max_tokens": 500,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    }

    # Tests:
    # - tests/unit/test_rag_pipeline.py::test_generate_answer_success
    #   Positive: returns text from first content block.
    # - tests/unit/test_rag_pipeline_advanced.py::test_generate_answer_unexpected_format_raises
    #   Failure mode: response lacks expected shape -> raises ValueError.
    # - tests/unit/test_rag_pipeline_edges.py::test_generate_answer_non_text_blocks_raises_value_error
    #   Failure mode: non-text content blocks -> raise ValueError.
    # Rationale: Non-text content (e.g., tool calls/images) should surface as errors to avoid silently returning empty or misleading answers.
    try:
        response = invoke_bedrock_with_backoff(
            model_id=CLAUDE_MODEL_ID,
            body=json.dumps(payload)
        )
        data = json.loads(response["body"].read())
        if DEBUG_BEDROCK_LOG:
            print(f"Claude raw response: {json.dumps(data)[:2000]}")
        # Expected shape: data['content'] is a list of content blocks
        content_blocks = data.get("content", [])
        for block in content_blocks:
            if block.get("type") == "text":
                return block.get("text", "")
        # Fallback: raise if format unexpected
        raise ValueError(f"Unexpected Claude response format: {data}")
    except Exception as e:
        print(f"Error invoking Claude model: {e}")
        raise

def rerank_chunks(query: str, chunks):
    """Reranking using Cohere Rerank (Bedrock).

    chunks: list of tuples (id, content, source, title, similarity)
    Returns reordered list (may truncate to CONTEXT_MAX_CHUNKS).
    """
    # Tests:
    # - tests/unit/test_rag_pipeline.py::test_rerank_chunks_empty
    #   Edge: no chunks -> returns [].
    # - tests/unit/test_rag_pipeline.py::test_rerank_chunks_valid_results
    #   Positive: orders by relevance_score and truncates to CONTEXT_MAX_CHUNKS.
    # - tests/unit/test_rag_pipeline_advanced.py::test_rerank_chunks_malformed_results_fallback
    #   Failure mode: missing/bad indices -> fallback to similarity order.
    # - tests/unit/test_rag_pipeline_edges.py::test_rerank_chunks_duplicate_and_invalid_indices_dedup_and_fallback
    #   Edge: duplicated and out-of-range indices ignored; fallback fills remaining slots.
    # Rationale: External rerankers can return noisy indices; dedupe/ignore invalid entries and fill via similarity ensures deterministic top-K.
    if not chunks:
        return []
    try:
        docs = [r[1] for r in chunks]
        body = json.dumps({
            "api_version": RERANK_API_VERSION,
            "query": query,
            "documents": docs,
            "top_n": min(CONTEXT_MAX_CHUNKS, len(docs))
        })
        resp = invoke_bedrock_with_backoff(
            model_id=RERANK_MODEL_ID,
            body=body
        )
        data = json.loads(resp['body'].read())
        results = data.get('results', [])
        # results items expected: {index: int, relevance_score: float}
        order = sorted(results, key=lambda x: x.get('relevance_score', 0), reverse=True)
        ranked = []
        seen_idx = set()
        for item in order:
            idx = item.get('index')
            if idx is not None and 0 <= idx < len(chunks) and idx not in seen_idx:
                ranked.append(chunks[idx] + (item.get('relevance_score'),))
                seen_idx.add(idx)
        # Append any missing (fallback) preserving original similarity
        for i, r in enumerate(chunks):
            if i not in seen_idx and len(ranked) < CONTEXT_MAX_CHUNKS:
                ranked.append(r + (r[4],))  # reuse similarity as relevance
        if DEBUG_BEDROCK_LOG:
            print(f"Rerank scores: {[round(x[-1],4) for x in ranked]}")
        # Strip appended relevance score before returning
        return [r[:-1] for r in ranked[:CONTEXT_MAX_CHUNKS]]
    except Exception as e:
        print(f"Rerank error, falling back to similarity ordering: {e}")
        return chunks[:CONTEXT_MAX_CHUNKS]

def handler(event, context):
    """Universal handler supporting both direct Lambda invocation and HTTP (Function URL/API Gateway).

    Accepted input shapes:
    - Direct invocation: {"query": "..."}
    - HTTP (Lambda Function URL / API Gateway proxy): {"body": "{\"query\": \"...\"}"}

    Returns a JSON body with answer and source metadata plus stage timings for latency analysis.
    """
    print('Starting rag pipeline')

    # Extract query from possible event shapes
    user_query = None
    if isinstance(event, dict):
        if 'query' in event:  # direct invoke style
            user_query = event.get('query')
        elif 'body' in event:  # HTTP invoke style
            raw_body = event.get('body')
            if raw_body:
                try:
                    parsed = json.loads(raw_body)
                    user_query = parsed.get('query')
                except Exception as e:
                    print(f"Failed to parse JSON body: {e}")
    # Tests:
    # - tests/unit/test_rag_pipeline.py::test_handler_missing_query_returns_400
    #   Negative: missing/invalid query -> 400 with CORS.
    # - tests/unit/test_rag_pipeline.py::test_handler_http_event_parsing
    #   Positive: parses body JSON to extract query.
    # - tests/unit/test_rag_pipeline_edges.py::test_handler_invalid_json_body_returns_400
    #   Negative: invalid JSON in body -> 400 with CORS; parse error logged.
    # Rationale: Bad client input should produce a predictable 400 with CORS, preventing opaque server errors.
    if not user_query or not isinstance(user_query, str) or not user_query.strip():
        return {
            'statusCode': 400,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST,OPTIONS'
            },
            'body': json.dumps({'error': "Missing or invalid 'query'"})
        }
    user_query = user_query.strip()

    timings = {}
    t0 = time.time()
    conn = get_db_connection()
    try:
        # Embedding stage
        t_emb_start = time.time()
        # Tests:
        # - tests/unit/test_rag_pipeline.py::test_timings_recorded
        #   Positive: timings keys (embedding_ms, primary_retrieval_ms, facet_expansion_ms, rerank_ms, llm_ms) present.
        # - tests/unit/test_rag_pipeline_edges.py::test_retrieve_similar_chunks_empty_rows_end_to_end_still_200
        #   Edge: empty retrieval -> prompt may be minimal; still returns 200.
        # Rationale: End-to-end behavior remains consistent even when primary retrieval yields no context.
        query_emb = get_embedding(user_query)
        timings['embedding_ms'] = round((time.time() - t_emb_start) * 1000, 2)

        # Initial vector retrieval
        t_ret_start = time.time()
        chunks = retrieve_similar_chunks(conn, query_emb, k=5)
        timings['primary_retrieval_ms'] = round((time.time() - t_ret_start) * 1000, 2)

        # Facet expansion
        t_facet_start = time.time()
        facet_extras = expand_via_facets(conn, chunks, query_emb, extra_limit=FE_RAG_EXTRA_LIMIT)
        timings['facet_expansion_ms'] = round((time.time() - t_facet_start) * 1000, 2)
        # Deduplicate by id while preserving original order
        seen = {r[0] for r in chunks}
        for r in facet_extras:
            if r[0] not in seen:
                chunks.append(r)
                seen.add(r[0])
        print(f"Retrieved {len(chunks)} chunks from vector DB (after facet expansion)")

        # Rerank (optional)
        t_rerank_start = time.time()
        # Tests:
        # - tests/unit/test_rag_pipeline_advanced.py::test_context_max_chunks_enforced
        #   Edge: CONTEXT_MAX_CHUNKS limit respected after rerank/fallback.
        chunks = rerank_chunks(user_query, chunks)
        timings['rerank_ms'] = round((time.time() - t_rerank_start) * 1000, 2)
        print(f"Final chunk count after rerank + truncation: {len(chunks)}")

        # Prompt assembly & generation
        query_context = "\n\n".join([r[1] for r in chunks])
        prompt = f"Context:\n{query_context}\n\nQuestion: {user_query}\nAnswer:"
        print(f"Prompt length: {len(prompt)} characters")
        t_llm_start = time.time()
        # Tests:
        # - tests/unit/test_rag_pipeline.py::test_handler_returns_structured_response
        #   Positive: response contains answer, sources with fields, timings, and 200 status.
        answer = generate_answer(prompt)
        timings['llm_ms'] = round((time.time() - t_llm_start) * 1000, 2)
        print(f"Model answer (full answer): {answer}")
    finally:
        conn.close()

    timings['total_ms'] = round((time.time() - t0) * 1000, 2)

    response_body = {
        'query': user_query,
        'answer': answer,
        'sources': [dict(id=r[0], source=r[2], title=r[3], similarity=r[4]) for r in chunks],
        'timings': timings
    }

    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'POST,OPTIONS'
        },
        'body': json.dumps(response_body)
    }