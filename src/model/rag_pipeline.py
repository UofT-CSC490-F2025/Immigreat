import json
import os
import boto3
import psycopg2
from collections import Counter

bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')
secretsmanager_client = boto3.client('secretsmanager')

PGVECTOR_SECRET_ARN = os.environ['PGVECTOR_SECRET_ARN']
EMBEDDING_MODEL = os.environ.get('BEDROCK_EMBEDDING_MODEL', 'amazon.titan-embed-text-v1')
# Make Claude model configurable via env; keep existing default if not set.
CLAUDE_MODEL_ID = os.environ.get('BEDROCK_CHAT_MODEL', 'anthropic.claude-3-5-sonnet-20240620-v1:0')
ANTHROPIC_VERSION = os.environ.get('ANTHROPIC_VERSION', 'bedrock-2023-05-31')
DEBUG_BEDROCK_LOG = True
FE_RAG_ENABLE = True
# Comma-separated facet columns from the documents table to expand on
FE_RAG_FACETS = [c.strip() for c in os.environ.get('FE_RAG_FACETS', 'source,title,section').split(',') if c.strip()]
FE_RAG_MAX_FACET_VALUES = int(os.environ.get('FE_RAG_MAX_FACET_VALUES', '2'))  # per facet
FE_RAG_EXTRA_LIMIT = int(os.environ.get('FE_RAG_EXTRA_LIMIT', '5'))
RERANK_ENABLE = True
RERANK_MODEL_ID = os.environ.get('RERANK_MODEL', 'cohere.rerank-v3-5:0')  # Bedrock Cohere Rerank
# Bedrock Cohere Re-rank requires an API version (integer) in the payload. Default to 2.
# Accept env as string and coerce; fallback to 2 if invalid.
try:
    RERANK_API_VERSION = int(os.environ.get('RERANK_API_VERSION', '2'))
except ValueError:
    RERANK_API_VERSION = 2
CONTEXT_MAX_CHUNKS = int(os.environ.get('CONTEXT_MAX_CHUNKS', '12'))

def get_db_connection():
    secret = secretsmanager_client.get_secret_value(SecretId=PGVECTOR_SECRET_ARN)
    creds = json.loads(secret['SecretString'])
    return psycopg2.connect(
        host=creds['host'], port=creds['port'], database=creds['dbname'],
        user=creds['username'], password=creds['password']
    )

def list_tables(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type='BASE TABLE'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name;
    """)
    tables = cur.fetchall()
    cur.close()
    return [{"schema": s, "table": t} for s, t in tables]


def get_embedding(text: str):
    body = json.dumps({"inputText": text})
    resp = bedrock_runtime.invoke_model(
        modelId=EMBEDDING_MODEL,
        contentType="application/json",
        accept="application/json",
        body=body
    )
    return json.loads(resp["body"].read())["embedding"]

def retrieve_similar_chunks(conn, embedding, k=5):
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

    try:
        response = bedrock_runtime.invoke_model(
            modelId=CLAUDE_MODEL_ID,
            contentType="application/json",
            accept="application/json",
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
    """Reranking using Cohere Rerank (Bedrock) if enabled.

    chunks: list of tuples (id, content, source, title, similarity)
    Returns reordered list (may truncate to CONTEXT_MAX_CHUNKS).
    """
    if not RERANK_ENABLE or not chunks:
        return chunks[:CONTEXT_MAX_CHUNKS]
    try:
        docs = [r[1] for r in chunks]
        body = json.dumps({
            "api_version": RERANK_API_VERSION,
            "query": query,
            "documents": docs,
            "top_n": min(CONTEXT_MAX_CHUNKS, len(docs))
        })
        resp = bedrock_runtime.invoke_model(
            modelId=RERANK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
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
    print('Starting rag pipeline')
    
    # Handle Lambda Function URL events (HTTP requests)
    if 'body' in event:
        try:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
            user_query = body.get("query")
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Error parsing request body: {e}")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Invalid JSON in request body"})
            }
    else:
        # Direct invocation (for testing)
        user_query = event.get("query")
    
    if not user_query:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing 'query' parameter"})
        }

    conn = get_db_connection()
    query_emb = get_embedding(user_query)
    chunks = retrieve_similar_chunks(conn, query_emb, k=5)
    if FE_RAG_ENABLE:
        facet_extras = expand_via_facets(conn, chunks, query_emb, extra_limit=FE_RAG_EXTRA_LIMIT)
        # Dedup by id, keep original order
        seen = {r[0] for r in chunks}
        for r in facet_extras:
            if r[0] not in seen:
                chunks.append(r)
                seen.add(r[0])
    print(f"Retrieved {len(chunks)} chunks from vector DB")
    # Rerank (optional)
    chunks = rerank_chunks(user_query, chunks)
    print(f"Final chunk count after rerank + truncation: {len(chunks)}")

    query_context = "\n\n".join([r[1] for r in chunks])
    prompt = f"Context:\n{query_context}\n\nQuestion: {user_query}\nAnswer:"
    print(f"Prompt length: {len(prompt)} characters")
    answer = generate_answer(prompt)
    print(f"Model answer (full answer): {answer}")

    conn.close()

    return {
        "statusCode": 200,
        "body": json.dumps({
            "query": user_query,
            "answer": answer,
            "sources": [dict(id=r[0], source=r[2], title=r[3], similarity=r[4]) for r in chunks]
        })
    }