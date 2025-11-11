import json
import os
import boto3
import psycopg2

bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')
secretsmanager_client = boto3.client('secretsmanager')

PGVECTOR_SECRET_ARN = os.environ['PGVECTOR_SECRET_ARN']
EMBEDDING_MODEL = os.environ.get('BEDROCK_EMBEDDING_MODEL', 'amazon.titan-embed-text-v1')
# Make Claude model configurable via env; keep existing default if not set.
CLAUDE_MODEL_ID = os.environ.get('BEDROCK_CHAT_MODEL', 'anthropic.claude-3-5-sonnet-20240620-v1:0')
ANTHROPIC_VERSION = os.environ.get('ANTHROPIC_VERSION', 'bedrock-2023-05-31')
DEBUG_BEDROCK_LOG = os.environ.get('DEBUG_BEDROCK_LOG', 'false').lower() in ('1', 'true', 'yes')

def get_db_connection():
    secret = secretsmanager_client.get_secret_value(SecretId=PGVECTOR_SECRET_ARN)
    creds = json.loads(secret['SecretString'])
    return psycopg2.connect(
        host=creds['host'], port=creds['port'], database=creds['dbname'],
        user=creds['username'], password=creds['password']
    )

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

def handler(event, context):
    print('Starting test rag pipeline')
    print('test message')
    user_query = event["query"]
    print(f"User query: {user_query}")

    conn = get_db_connection()
    query_emb = get_embedding(user_query)
    chunks = retrieve_similar_chunks(conn, query_emb, k=5)
    print(f"Retrieved {len(chunks)} chunks from vector DB")

    query_context = "\n\n".join([r[1] for r in chunks])
    prompt = f"Context:\n{query_context}\n\nQuestion: {user_query}\nAnswer:"
    print(f"Prompt length: {len(prompt)} characters")
    answer = generate_answer(prompt)
    print(f"Model answer (first 300 chars): {answer[:300]}")

    conn.close()

    return {
        "statusCode": 200,
        "body": json.dumps({
            "query": user_query,
            "answer": answer,
            "sources": [dict(id=r[0], source=r[2], title=r[3], similarity=r[4]) for r in chunks]
        })
    }