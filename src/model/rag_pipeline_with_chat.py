"""
Enhanced RAG Pipeline with Chat History Support

This module extends the base RAG pipeline with conversational context management.
Chat history is stored in DynamoDB and included in prompts for contextual responses.
"""

import json
import os
import time
import random
import uuid
from datetime import datetime, timedelta
import boto3
import psycopg2
from collections import Counter
from botocore.exceptions import ClientError
from decimal import Decimal

bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')
secretsmanager_client = boto3.client('secretsmanager')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

PGVECTOR_SECRET_ARN = os.environ['PGVECTOR_SECRET_ARN']
EMBEDDING_MODEL = os.environ.get('BEDROCK_EMBEDDING_MODEL', 'amazon.titan-embed-text-v1')
CLAUDE_MODEL_ID = os.environ.get('BEDROCK_CHAT_MODEL', 'anthropic.claude-3-5-sonnet-20240620-v1:0')
ANTHROPIC_VERSION = os.environ.get('ANTHROPIC_VERSION', 'bedrock-2023-05-31')
DYNAMODB_CHAT_TABLE = os.environ.get('DYNAMODB_CHAT_TABLE')
DEBUG_BEDROCK_LOG = True
FE_RAG_ENABLE = os.environ.get('FE_RAG_ENABLE', 'true').lower() == 'true'
RERANK_ENABLE = os.environ.get('RERANK_ENABLE', 'true').lower() == 'true'
FE_RAG_FACETS = [c.strip() for c in os.environ.get('FE_RAG_FACETS', 'source,title,section').split(',') if c.strip()]
FE_RAG_MAX_FACET_VALUES = int(os.environ.get('FE_RAG_MAX_FACET_VALUES', '2'))
FE_RAG_EXTRA_LIMIT = int(os.environ.get('FE_RAG_EXTRA_LIMIT', '5'))
RERANK_MODEL_ID = os.environ.get('RERANK_MODEL', 'cohere.rerank-v3-5:0')
try:
    RERANK_API_VERSION = int(os.environ.get('RERANK_API_VERSION', '2'))
except ValueError:
    RERANK_API_VERSION = 2
CONTEXT_MAX_CHUNKS = int(os.environ.get('CONTEXT_MAX_CHUNKS', '12'))
MAX_HISTORY_MESSAGES = int(os.environ.get('MAX_HISTORY_MESSAGES', '10'))  # Keep last N messages
CHAT_SESSION_TTL_DAYS = int(os.environ.get('CHAT_SESSION_TTL_DAYS', '7'))  # Auto-expire after N days

# Retry configuration
MAX_BEDROCK_RETRIES = int(os.environ.get('MAX_BEDROCK_RETRIES', '10'))
BEDROCK_BASE_DELAY = float(os.environ.get('BEDROCK_BASE_DELAY', '1.0'))
BEDROCK_MAX_JITTER = float(os.environ.get('BEDROCK_MAX_JITTER', '1.0'))

# Initialize DynamoDB table
chat_table = dynamodb.Table(DYNAMODB_CHAT_TABLE) if DYNAMODB_CHAT_TABLE else None


def invoke_bedrock_with_backoff(model_id, body, content_type="application/json", accept="application/json", max_retries=None):
    """Invoke Bedrock model with exponential backoff and jitter to handle throttling."""
    if max_retries is None:
        max_retries = MAX_BEDROCK_RETRIES
    
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            response = bedrock_runtime.invoke_model(
                modelId=model_id,
                contentType=content_type,
                accept=accept,
                body=body
            )
            if attempt > 0:
                print(f"Successfully invoked {model_id} after {attempt + 1} attempts")
            return response
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            last_exception = e
            
            if error_code == 'ThrottlingException':
                if attempt == max_retries - 1:
                    print(f"Max retries ({max_retries}) exceeded for {model_id}")
                    raise
                
                exponential_delay = (2 ** attempt) * BEDROCK_BASE_DELAY
                jitter = random.uniform(0, BEDROCK_MAX_JITTER)
                total_delay = exponential_delay + jitter
                
                print(f"ThrottlingException on attempt {attempt + 1}/{max_retries} for {model_id}, "
                      f"retrying in {total_delay:.2f}s")
                
                time.sleep(total_delay)
            else:
                print(f"Non-throttling error from {model_id}: {error_code} - {str(e)}")
                raise

def get_db_connection():
    secret = secretsmanager_client.get_secret_value(SecretId=PGVECTOR_SECRET_ARN)
    creds = json.loads(secret['SecretString'])
    return psycopg2.connect(
        host=creds['host'], port=creds['port'], database=creds['dbname'],
        user=creds['username'], password=creds['password']
    )


def get_embedding(text: str):
    """Generate embedding for text using Bedrock with retry logic."""
    body = json.dumps({"inputText": text})
    resp = invoke_bedrock_with_backoff(
        model_id=EMBEDDING_MODEL,
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
    """Facet-Expanded retrieval: treat shared metadata as lightweight graph edges."""
    if not seed_rows:
        return []

    col_idx = {"source": 2, "title": 3, "section": None}
    top_sources = _top_values(seed_rows, col_idx["source"], FE_RAG_MAX_FACET_VALUES) if "source" in FE_RAG_FACETS else []
    top_titles = _top_values(seed_rows, col_idx["title"], FE_RAG_MAX_FACET_VALUES) if "title" in FE_RAG_FACETS else []

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

    params = [query_embedding, seed_ids, top_sources, top_titles]

    section_clause = ""
    top_sections = []
    if "section" in FE_RAG_FACETS:
        with conn.cursor() as cur:
            cur.execute("SELECT section FROM documents WHERE id = ANY(%s)", (seed_ids,))
            sections = [r[0] for r in cur.fetchall() if r[0]]
            top_sections = [v for v, _ in Counter(sections).most_common(FE_RAG_MAX_FACET_VALUES)]
        section_clause = " OR section = ANY(%s)"
        params += [top_sections]

    params += [query_embedding, extra_limit]
    full_sql = sql.format(section_clause=section_clause)

    with conn.cursor() as cur:
        cur.execute(full_sql, params)
        extras = cur.fetchall()
    return extras


def rerank_chunks(query: str, chunks):
    """Reranking using Cohere Rerank (Bedrock)."""
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
        order = sorted(results, key=lambda x: x.get('relevance_score', 0), reverse=True)
        ranked = []
        seen_idx = set()
        for item in order:
            idx = item.get('index')
            if idx is not None and 0 <= idx < len(chunks) and idx not in seen_idx:
                ranked.append(chunks[idx] + (item.get('relevance_score'),))
                seen_idx.add(idx)
        for i, r in enumerate(chunks):
            if i not in seen_idx and len(ranked) < CONTEXT_MAX_CHUNKS:
                ranked.append(r + (r[4],))
        if DEBUG_BEDROCK_LOG:
            print(f"Rerank scores: {[round(x[-1],4) for x in ranked]}")
        return [r[:-1] for r in ranked[:CONTEXT_MAX_CHUNKS]]
    except Exception as e:
        print(f"Rerank error, falling back to similarity ordering: {e}")
        return chunks[:CONTEXT_MAX_CHUNKS]


# ========================
# Chat History Management
# ========================

def get_chat_history(session_id: str, max_messages: int = MAX_HISTORY_MESSAGES):
    """Retrieve recent chat history for a session from DynamoDB."""
    if not chat_table or not session_id:
        return []
    
    try:
        response = chat_table.query(
            KeyConditionExpression='session_id = :sid',
            ExpressionAttributeValues={':sid': session_id},
            ScanIndexForward=False,  # Most recent first
            Limit=max_messages
        )
        
        items = response.get('Items', [])
        # Reverse to get chronological order (oldest first)
        items.reverse()
        
        history = []
        for item in items:
            history.append({
                'role': item.get('role', 'user'),
                'content': item.get('message', ''),
                'timestamp': int(item.get('timestamp', 0))
            })
        
        print(f"Retrieved {len(history)} messages for session {session_id}")
        return history
        
    except Exception as e:
        print(f"Error retrieving chat history: {e}")
        return []


def save_message_to_history(session_id: str, role: str, message: str):
    """Save a message to chat history in DynamoDB."""
    if not chat_table or not session_id:
        return
    
    try:
        timestamp = int(time.time() * 1000)  # milliseconds
        ttl = int((datetime.now() + timedelta(days=CHAT_SESSION_TTL_DAYS)).timestamp())
        
        chat_table.put_item(
            Item={
                'session_id': session_id,
                'timestamp': timestamp,
                'role': role,
                'message': message,
                'ttl': ttl
            }
        )
        print(f"Saved {role} message to session {session_id}")
        
    except Exception as e:
        print(f"Error saving message to history: {e}")


def format_chat_history_for_prompt(history):
    """Format chat history for inclusion in the prompt."""
    if not history:
        return ""
    
    formatted = "Previous conversation:\n"
    for msg in history:
        role = msg['role'].capitalize()
        content = msg['content']
        formatted += f"{role}: {content}\n"
    
    formatted += "\n"
    return formatted


def generate_answer_with_history(prompt: str, history: list) -> str:
    """Send a chat prompt to Claude with conversation history.
    
    Args:
        prompt: The current user question with context
        history: List of previous messages [{'role': 'user'/'assistant', 'content': '...'}]
    """
    # Build messages array with history
    messages = []
    
    # Add historical messages (alternating user/assistant)
    for msg in history:
        messages.append({
            "role": msg['role'],
            "content": [{"type": "text", "text": msg['content']}]
        })
    
    # Add current prompt as latest user message
    messages.append({
        "role": "user",
        "content": [{"type": "text", "text": prompt}]
    })
    
    payload = {
        "anthropic_version": ANTHROPIC_VERSION,
        "max_tokens": 1000,
        "messages": messages,
        "system": "You are an expert Canadian immigration assistant. Do not mention the context provided if not relevant. Use any relevant provided context to answer questions accurately, or find the answer yourself otherwise. If referencing previous conversation, acknowledge it naturally."
    }

    try:
        response = invoke_bedrock_with_backoff(
            model_id=CLAUDE_MODEL_ID,
            body=json.dumps(payload)
        )
        data = json.loads(response["body"].read())
        if DEBUG_BEDROCK_LOG:
            print(f"Claude raw response: {json.dumps(data)[:2000]}")
        
        content_blocks = data.get("content", [])
        for block in content_blocks:
            if block.get("type") == "text":
                return block.get("text", "")
        
        raise ValueError(f"Unexpected Claude response format: {data}")
    except Exception as e:
        print(f"Error invoking Claude model: {e}")
        raise


def handler(event, context):
    """
    Enhanced RAG handler with chat history support.
    
    Expected input:
    {
        "query": "Your question here",
        "session_id": "optional-uuid-for-chat-continuity"
    }
    
    If session_id is not provided, a new one is generated (stateless mode).
    """
    print('Starting RAG pipeline with chat support')

    # Extract query and session_id
    user_query = None
    session_id = None
    k = 5
    use_facets = FE_RAG_ENABLE
    use_rerank = RERANK_ENABLE
    
    if isinstance(event, dict):
        if 'query' in event:  # Direct invoke
            user_query = event.get('query')
            session_id = event.get('session_id')
            k = event.get('k', 5)
            use_facets = event.get('use_facets', FE_RAG_ENABLE)
            use_rerank = event.get('use_rerank', RERANK_ENABLE)
        elif 'body' in event:  # HTTP invoke
            raw_body = event.get('body')
            if raw_body:
                try:
                    parsed = json.loads(raw_body)
                    user_query = parsed.get('query')
                    session_id = parsed.get('session_id')
                    k = parsed.get('k', 5)
                    use_facets = parsed.get('use_facets', FE_RAG_ENABLE)
                    use_rerank = parsed.get('use_rerank', RERANK_ENABLE)
                except Exception as e:
                    print(f"Failed to parse JSON body: {e}")
    print(f"Received Query: {(user_query[:100] if isinstance(user_query, str) else 'None')}, Session ID: {session_id}, k={k}, use_facets={use_facets}, use_rerank={use_rerank}")
    
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
    
    # Generate session_id if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
        print(f"Generated new session_id: {session_id}")
    else:
        print(f"Using existing session_id: {session_id}")

    timings = {}
    t0 = time.time()
    
    # Retrieve chat history
    t_history_start = time.time()
    chat_history = get_chat_history(session_id)
    timings['history_retrieval_ms'] = round((time.time() - t_history_start) * 1000, 2)
    
    conn = get_db_connection()
    try:
        # Embedding stage
        t_emb_start = time.time()
        query_emb = get_embedding(user_query)
        timings['embedding_ms'] = round((time.time() - t_emb_start) * 1000, 2)

        # Initial vector retrieval
        t_ret_start = time.time()
        chunks = retrieve_similar_chunks(conn, query_emb, k)
        timings['primary_retrieval_ms'] = round((time.time() - t_ret_start) * 1000, 2)

        # Facet expansion
        if use_facets:
            t_facet_start = time.time()
            facet_extras = expand_via_facets(conn, chunks, query_emb, extra_limit=FE_RAG_EXTRA_LIMIT)
            timings['facet_expansion_ms'] = round((time.time() - t_facet_start) * 1000, 2)
            seen = {r[0] for r in chunks}
            for r in facet_extras:
                if r[0] not in seen:
                    chunks.append(r)
                    seen.add(r[0])
        print(f"Retrieved {len(chunks)} chunks from vector DB")

        # Rerank
        if use_rerank:
            t_rerank_start = time.time()
            chunks = rerank_chunks(user_query, chunks)
            timings['rerank_ms'] = round((time.time() - t_rerank_start) * 1000, 2)
            print(f"Final chunk count after rerank: {len(chunks)}")

        # Build prompt with context
        query_context = "\n\n".join([r[1] for r in chunks])
        
        # Format: Context + Current Question
        prompt = f"Context from knowledge base:\n{query_context}\n\nCurrent Question: {user_query}\n\nAnswer based on the context provided:"
        
        print(f"Prompt length: {len(prompt)} characters, History items: {len(chat_history)}")
        
        # Generate answer with history
        t_llm_start = time.time()
        
        # Prepare history for Claude (only user/assistant messages, not the RAG context)
        # We'll use a simpler approach: just pass the question-answer pairs
        formatted_history = []
        for msg in chat_history[-MAX_HISTORY_MESSAGES:]:
            formatted_history.append({
                'role': msg['role'],
                'content': msg['content']
            })
        
        answer = generate_answer_with_history(prompt, formatted_history)
        timings['llm_ms'] = round((time.time() - t_llm_start) * 1000, 2)
        print(f"Generated answer: {answer[:200]}...")
        
    finally:
        conn.close()

    # Save current exchange to history
    t_save_start = time.time()
    save_message_to_history(session_id, 'user', user_query)
    save_message_to_history(session_id, 'assistant', answer)
    timings['save_history_ms'] = round((time.time() - t_save_start) * 1000, 2)

    timings['total_ms'] = round((time.time() - t0) * 1000, 2)

    response_body = {
        'query': user_query,
        'answer': answer,
        'session_id': session_id,
        'sources': [dict(id=r[0], source=r[2], title=r[3], similarity=r[4]) for r in chunks],
        'timings': timings,
        'history_length': len(chat_history)
    }

    return {
        'statusCode': 200,
        'body': json.dumps(response_body)
    }


