import json
import os
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# ----------------------------

# AWS Clients

# ----------------------------

secrets_client = boto3.client("secretsmanager")
bedrock_client = boto3.client("bedrock-runtime")

# ----------------------------

# Environment Variables

# ----------------------------

PGVECTOR_SECRET_ARN = os.environ.get("PGVECTOR_SECRET_ARN")
EMBEDDING_MODEL = os.environ.get("BEDROCK_EMBEDDING_MODEL", "amazon.titan-embed-text-v1")

# ----------------------------

# Database Utilities

# ----------------------------

def get_db_connection():
    """Retrieve database credentials from Secrets Manager and connect to Postgres."""
    secret = secrets_client.get_secret_value(SecretId=PGVECTOR_SECRET_ARN)
    creds = json.loads(secret["SecretString"])
    return psycopg2.connect(
        host=creds["host"],
        port=creds["port"],
        dbname=creds["dbname"],
        user=creds["username"],
        password=creds["password"]
        )

def get_embedding(text: str):
    """Generate an embedding using Amazon Titan."""
    body = json.dumps({"inputText": text})
    resp = bedrock_client.invoke_model(
        modelId=EMBEDDING_MODEL,
        contentType="application/json",
        accept="application/json",
        body=body
        )
    return json.loads(resp["body"].read())["embedding"]

def retrieve_similar_chunks(conn, embedding, k=5):
    """Retrieve the top-k most similar chunks from the database."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, content, source, title, 1 - (embedding <=> %s::vector) AS similarity
            FROM documents
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
            """,
            (embedding, embedding, k),
            )
    return cur.fetchall()

# ----------------------------

# Generation Utility

# ----------------------------

def generate_bedrock_answer(prompt):
    """Generate an answer using Claude via Bedrock."""
    try:
        response = bedrock_client.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",   # REQUIRED
                "max_tokens": 512,
                "temperature": 0.7,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt}
                        ]
                    }
                ]
            })
        )

        result = json.loads(response["body"].read())
        return result["content"][0]["text"]

    except Exception as e:
        print(f"Error generating answer: {e}")
        raise

# ----------------------------

# Lambda Handler

# ----------------------------

def handler(event, context):
    """Lambda handler for dynamic RAG query with adjustable parameters."""
    body = event.get("body")
    if isinstance(body, str):
        body = json.loads(body)

        user_query = body.get("query", "What are the steps to apply for a Canadian work visa?")
        k = int(body.get("top_k", 5))
        custom_context = body.get("context", None)

        conn = get_db_connection()
        try:
            query_emb = get_embedding(user_query)

            if custom_context:
                context_text = custom_context
                retrieved_chunks = []
            else:
                retrieved_chunks = retrieve_similar_chunks(conn, query_emb, k=k)
                context_text = "\n\n".join([r["content"] for r in retrieved_chunks])

            prompt = f"Context:\n{context_text}\n\nQuestion: {user_query}\nAnswer:"

            answer = generate_bedrock_answer(prompt)

            return {
                "statusCode": 200,
                "body": json.dumps({
                    "query": user_query,
                    "answer": answer,
                    "top_k": k,
                    "context_used": bool(custom_context),
                    "sources": [
                        dict(id=r["id"], source=r["source"], title=r["title"], similarity=r["similarity"])
                        for r in retrieved_chunks
                    ]
                })
            }
        finally:
            conn.close()

# ----------------------------

# Local Test Entry Point

# ----------------------------

if __name__ == "__main__":
    test_event = {
        "body": json.dumps({
            "query": "What documents are required for a study permit in Canada?",
            "top_k": 3
            })
        }
    print(json.dumps(handler(test_event, None), indent=2))
