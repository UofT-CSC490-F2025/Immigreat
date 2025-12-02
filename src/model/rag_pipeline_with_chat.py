"""
Enhanced RAG Pipeline with Chat History Support - DeepSeek-R1 Edition

This module extends the base RAG pipeline with conversational context management.
Chat history is stored in DynamoDB and included in prompts for contextual responses.

Updated to use DeepSeek-R1 for better reasoning and to avoid throttling issues.
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

# ============================================================================
# UPDATED: Using DeepSeek-R1 instead of Claude
# ============================================================================
DEEPSEEK_MODEL_ID = os.environ.get('BEDROCK_CHAT_MODEL', 'us.deepseek.r1-v1:0')
ANTHROPIC_VERSION = os.environ.get('ANTHROPIC_VERSION', 'bedrock-2023-05-31')  # Keep for compatibility
# ============================================================================

DYNAMODB_CHAT_TABLE = os.environ.get('DYNAMODB_CHAT_TABLE')
DEBUG_BEDROCK_LOG = True
SIMILARITY_THRESHOLD = float(os.environ.get('SIMILARITY_THRESHOLD', '0.3'))  # Minimum similarity score
FE_RAG_ENABLE = True
FE_RAG_FACETS = [c.strip() for c in os.environ.get('FE_RAG_FACETS', 'source,title,section').split(',') if c.strip()]
FE_RAG_MAX_FACET_VALUES = int(os.environ.get('FE_RAG_MAX_FACET_VALUES', '2'))
FE_RAG_EXTRA_LIMIT = int(os.environ.get('FE_RAG_EXTRA_LIMIT', '5'))
RERANK_ENABLE = True
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


def parse_deepseek_response(response_text: str):
    """
    Parse DeepSeek R1 response to separate thinking and answer.

    DeepSeek R1 ALWAYS returns: [thinking]</think>\n\n[answer]
    The </think> tag is the reliable delimiter.

    Returns:
        dict with 'thinking' and 'answer' keys
    """
    thinking = None
    answer = response_text

    # Split on </think> - this is the reliable delimiter
    if '</think>' in response_text:
        parts = response_text.split('</think>', 1)  # Split only on first occurrence

        if len(parts) == 2:
            thinking_raw = parts[0].strip()
            answer = parts[1].strip()

            # Remove the opening <think> tag if present
            if thinking_raw.startswith('<think>'):
                thinking_raw = thinking_raw[7:].strip()  # Remove '<think>'

            # Only include thinking if it has actual content
            if thinking_raw and len(thinking_raw) >= 10:
                thinking = thinking_raw

    # Clean up answer - remove common prefixes
    if answer.startswith('**Answer:**'):
        answer = answer[11:].strip()
    elif answer.startswith('Answer:'):
        answer = answer[7:].strip()

    # Remove meta-commentary phrases
    answer = answer.replace("Based on the context provided, ", "")
    answer = answer.replace("According to the documentation, ", "")
    answer = answer.replace("The context indicates that ", "")

    return {
        'thinking': thinking,
        'answer': answer.strip()
    }


def invoke_bedrock_with_backoff(model_id, body, content_type="application/json", accept="application/json",
                                max_retries=None):
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

        except Exception as e:
            print(f"Unexpected error invoking {model_id}: {str(e)}")
            raise

    if last_exception:
        raise last_exception
    raise Exception(f"Failed to invoke {model_id} after {max_retries} attempts")


def get_secret(secret_arn: str):
    """Retrieve secret from AWS Secrets Manager."""
    response = secretsmanager_client.get_secret_value(SecretId=secret_arn)
    return json.loads(response['SecretString'])


def get_db_connection():
    """Create a connection to PostgreSQL using credentials from Secrets Manager."""
    secret = get_secret(PGVECTOR_SECRET_ARN)
    conn = psycopg2.connect(
        host=secret['host'],
        port=secret.get('port', 5432),
        dbname=secret['dbname'],
        user=secret['username'],
        password=secret['password']
    )
    return conn


def get_embedding(text: str):
    """Generate embedding using AWS Bedrock Titan embeddings."""
    body_str = json.dumps({"inputText": text.strip()})
    response = invoke_bedrock_with_backoff(
        model_id=EMBEDDING_MODEL,
        body=body_str
    )
    data = json.loads(response['body'].read())
    return data['embedding']


def retrieve_similar_chunks(conn, query_emb, k=10):
    """Retrieve similar document chunks using pgvector."""
    emb_str = "[" + ",".join(map(str, query_emb)) + "]"
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            content,
            source,
            title,
            (1 - (embedding <=> %s::vector)) AS similarity
        FROM documents
        WHERE (1 - (embedding <=> %s::vector)) >= %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (emb_str, emb_str, SIMILARITY_THRESHOLD, emb_str, k)
    )
    results = cursor.fetchall()
    cursor.close()

    if DEBUG_BEDROCK_LOG:
        total = len(results)
        above = len([r for r in results if r[4] >= SIMILARITY_THRESHOLD])
        print(f"Retrieved {total} chunks, {above} above threshold {SIMILARITY_THRESHOLD}")
        if results:
            print(f"Top 3 similarity scores: {[round(r[4], 4) for r in results[:3]]}")

    return results


def expand_via_facets(conn, initial_chunks, query_emb, extra_limit=5):
    """
    Facet Expansion (FE-RAG): expand retrieval by finding common facets in top results
    and pulling more chunks with those facet values.
    """
    if not FE_RAG_ENABLE or not initial_chunks:
        return []

    facet_map = {}
    for c in initial_chunks:
        doc_id, content, source, title = c[0], c[1], c[2], c[3]
        metadata = {'source': source, 'title': title, 'section': ''}
        for facet_name in FE_RAG_FACETS:
            val = metadata.get(facet_name, '')
            if val:
                if facet_name not in facet_map:
                    facet_map[facet_name] = Counter()
                facet_map[facet_name][val] += 1

    common = []
    for fn, cnt in facet_map.items():
        for val, freq in cnt.most_common(FE_RAG_MAX_FACET_VALUES):
            common.append((fn, val))

    if not common:
        return []

    cursor = conn.cursor()
    emb_str = "[" + ",".join(map(str, query_emb)) + "]"
    seen_ids = {r[0] for r in initial_chunks}

    extras = []
    for fn, fv in common:
        col = fn
        query_sql = f"""
            SELECT
                id,
                content,
                source,
                title,
                (1 - (embedding <=> %s::vector)) AS similarity
            FROM documents
            WHERE {col} = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        cursor.execute(query_sql, (emb_str, fv, emb_str, extra_limit))
        rows = cursor.fetchall()
        for r in rows:
            if r[0] not in seen_ids:
                extras.append(r)
                seen_ids.add(r[0])

    cursor.close()

    # Filter by similarity threshold
    filtered_extras = [r for r in extras if r[4] >= SIMILARITY_THRESHOLD]

    if DEBUG_BEDROCK_LOG and filtered_extras:
        print(f"Facet expansion: {len(extras)} retrieved, {len(filtered_extras)} above threshold")

    return filtered_extras[:extra_limit]


def rerank_chunks(query: str, chunks):
    """Reranking using Cohere Rerank (Bedrock) if enabled."""
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
            print(f"Rerank scores: {[round(x[-1], 4) for x in ranked]}")
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
        print(f"Saved {role} message to history (session: {session_id})")

    except Exception as e:
        print(f"Error saving message to history: {e}")


def format_chat_history(history: list) -> str:
    """Format chat history into a readable string."""
    if not history:
        return ""

    formatted = "Previous conversation:\n"
    for msg in history:
        role = msg['role'].capitalize()
        content = msg['content']
        formatted += f"{role}: {content}\n"

    formatted += "\n"
    return formatted


# ============================================================================
# UPDATED: DeepSeek-R1 Answer Generation with Improved Prompting
# ============================================================================
def generate_answer_with_deepseek(user_query: str, context: str, history: list) -> str:
    """Generate answer using DeepSeek-R1 with AWS Bedrock format.

    DeepSeek on Bedrock uses special tokens: <｜begin▁of▁sentence｜><｜User｜>...<｜Assistant｜>

    Args:
        user_query: The current user question
        context: Retrieved documentation context (may be empty or irrelevant)
        history: List of previous messages [{'role': 'user'/'assistant', 'content': '...'}]
    """

    # Build the prompt parts
    prompt_parts = []

    # System instructions
    system_instructions = """You are an expert Canadian immigration consultant with comprehensive knowledge of IRCC policies, procedures, and requirements.

Your approach:
- Answer immigration questions directly and confidently
- Use your expertise to provide accurate, practical guidance
- When relevant documentation is available, naturally incorporate that information
- If you're less certain about specifics, provide your best professional assessment and suggest verification with IRCC
- Never say phrases like "based on the context provided" or "according to the documentation" - just answer naturally
- Be conversational and helpful, not robotic
- Provide step-by-step guidance for procedures
- Include important requirements, deadlines, and considerations

Remember: You're a knowledgeable consultant having a conversation, not a search engine reading documents aloud.

"""

    prompt_parts.append(system_instructions)

    # Add conversation history if available
    if history:
        prompt_parts.append("Previous conversation:\n")
        for msg in history[-MAX_HISTORY_MESSAGES:]:
            role = "User" if msg['role'] == 'user' else "Assistant"
            prompt_parts.append(f"{role}: {msg['content']}\n")
        prompt_parts.append("\n")

    # Add context if available
    if context and context.strip():
        prompt_parts.append("Reference information:\n")
        prompt_parts.append(context)
        prompt_parts.append("\n\n")

    # Add current question
    prompt_parts.append(f"Question: {user_query}")

    # Combine into full prompt
    full_prompt = "".join(prompt_parts)

    # Format with DeepSeek's special tokens
    # Note: Using special unicode characters as shown in AWS docs
    formatted_prompt = f"""<｜begin▁of▁sentence｜><｜User｜>{full_prompt}<｜Assistant｜><think>
"""

    # DeepSeek-R1 payload format for Bedrock
    payload = {
        "prompt": formatted_prompt,
        "max_tokens": 8192,  # AWS docs show max_tokens, not max_tokens_to_sample
        "temperature": 0.3,
        "top_p": 0.9
    }

    try:
        response = invoke_bedrock_with_backoff(
            model_id=DEEPSEEK_MODEL_ID,
            body=json.dumps(payload)
        )
        data = json.loads(response["body"].read())

        if DEBUG_BEDROCK_LOG:
            print(f"DeepSeek raw response: {json.dumps(data)[:2000]}")

        # DeepSeek response format: {"choices": [{"text": "..."}]}
        choices = data.get("choices", [])
        if not choices or len(choices) == 0:
            raise ValueError(f"No choices in DeepSeek response: {data}")

        answer_text = choices[0].get("text", "")

        if not answer_text:
            raise ValueError(f"Empty text in DeepSeek response: {data}")

        # Parse the response to separate thinking and answer
        parsed = parse_deepseek_response(answer_text)

        return parsed  # Returns dict with 'thinking' and 'answer'


    except Exception as e:
        print(f"Error invoking DeepSeek model: {e}")
        raise


# ============================================================================


def handler(event, context):
    """
    Enhanced RAG handler with chat history support using DeepSeek-R1.

    Expected input:
    {
        "query": "Your question here",
        "session_id": "optional-uuid-for-chat-continuity"
    }

    If session_id is not provided, a new one is generated (stateless mode).
    """
    print('Starting RAG pipeline with DeepSeek-R1 and chat support')

    # Extract query and session_id
    user_query = None
    session_id = None

    if isinstance(event, dict):
        if 'query' in event:  # Direct invoke
            user_query = event.get('query')
            session_id = event.get('session_id')
            k = event.get('k', 10)
            use_facets = event.get('use_facets', FE_RAG_ENABLE)
            use_rerank = event.get('use_rerank', RERANK_ENABLE)
        elif 'body' in event:  # HTTP invoke
            raw_body = event.get('body')
            if raw_body:
                try:
                    parsed = json.loads(raw_body)
                    user_query = parsed.get('query')
                    session_id = parsed.get('session_id')
                    k = parsed.get('k', 10)
                    use_facets = parsed.get('use_facets', FE_RAG_ENABLE)
                    use_rerank = parsed.get('use_rerank', RERANK_ENABLE)
                except Exception as e:
                    print(f"Failed to parse JSON body: {e}")
    print(
        f"Received Query: {user_query[:100] if isinstance(user_query, str) else 'None'}, Session ID: {session_id}, k={k}, use_facets={use_facets}, use_rerank={use_rerank}")

    if not user_query or not isinstance(user_query, str) or not user_query.strip():
        return {
            'statusCode': 400,
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

        # Build context from retrieved chunks
        query_context = "\n\n".join([r[1] for r in chunks]) if chunks else ""

        print(f"Context: {len(query_context)} chars, {len(chunks)} chunks, History: {len(chat_history)} msgs")

        # Generate answer with DeepSeek-R1
        t_llm_start = time.time()

        # Prepare history for DeepSeek (only user/assistant messages)
        formatted_history = []
        for msg in chat_history[-MAX_HISTORY_MESSAGES:]:
            formatted_history.append({
                'role': msg['role'],
                'content': msg['content']
            })

        # generate_answer_with_deepseek now returns dict with 'thinking' and 'answer'
        result = generate_answer_with_deepseek(user_query, query_context, formatted_history)
        timings['llm_ms'] = round((time.time() - t_llm_start) * 1000, 2)

        thinking = result.get('thinking')
        answer = result.get('answer', '')

        print(f"Generated answer: {answer[:200]}...")
        if thinking:
            print(f"Thinking length: {len(thinking)} chars")

    finally:
        conn.close()

    # Save current exchange to history (only save the answer, not the thinking)
    t_save_start = time.time()
    save_message_to_history(session_id, 'user', user_query)
    save_message_to_history(session_id, 'assistant', answer)
    timings['save_history_ms'] = round((time.time() - t_save_start) * 1000, 2)

    timings['total_ms'] = round((time.time() - t0) * 1000, 2)

    response_body = {
        'query': user_query,
        'answer': answer,
        'thinking': thinking,  # Add thinking as separate field
        'session_id': session_id,
        'model': DEEPSEEK_MODEL_ID,
        'sources': [dict(id=r[0], source=r[2], title=r[3], similarity=r[4]) for r in chunks],
        'timings': timings,
        'history_length': len(chat_history)
    }

    return {
        'statusCode': 200,
        'body': json.dumps(response_body)
    }
