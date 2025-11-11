import json
import os
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# AWS Clients
secrets_client = boto3.client("secretsmanager")
bedrock_client = boto3.client("bedrock-runtime")
sagemaker_runtime = boto3.client("sagemaker-runtime", region_name="us-east-1")

# Environment variables
PGVECTOR_SECRET_ARN = os.environ.get("PGVECTOR_SECRET_ARN")
EMBEDDING_MODEL = os.environ.get("BEDROCK_EMBEDDING_MODEL", "amazon.titan-embed-text-v1")
LORA_ENDPOINT = os.environ.get("LORA_ENDPOINT", "immigration-policy-lora-endpoint")


# ----------------------------
# Database and Embedding Utils
# ----------------------------

def get_db_connection():
    """Retrieve database credentials from Secrets Manager and connect."""
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
    """Generate an embedding using Bedrock Titan."""
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
# Generation Utilities
# ----------------------------

def generate_lora_answer(prompt):
    """Call a fine-tuned LoRA model hosted on SageMaker."""
    response = sagemaker_runtime.invoke_endpoint(
        EndpointName=LORA_ENDPOINT,
        ContentType="application/json",
        Body=json.dumps({"inputs": prompt})
    )
    result = json.loads(response["Body"].read())
    return result[0].get("generated_text", "")


def generate_bedrock_answer(prompt):
    """Fallback to Claude or another Bedrock model if LoRA isn't available."""
    response = bedrock_client.invoke_model(
        modelId="anthropic.claude-3-5-sonnet-20240620-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500
        })
    )
    return json.loads(response["body"].read())["content"][0]["text"]


# ----------------------------
# Lambda Entry Point
# ----------------------------

def handler(event, context):
    """Lambda handler that performs dynamic RAG query with flexible parameters."""

    # Parse request body (accepts JSON event from API Gateway or local test)
    body = event.get("body")
    if isinstance(body, str):
        body = json.loads(body)

    user_query = body.get("query", "What are the steps to apply for a Canadian work visa?")
    k = int(body.get("top_k", 5))
    custom_context = body.get("context", None)

    # Connect to pgvector DB
    conn = get_db_connection()
    try:
        # Get embeddings for the query
        query_emb = get_embedding(user_query)

        # Retrieve relevant chunks (unless context is manually provided)
        if custom_context:
            context_text = custom_context
            retrieved_chunks = []
        else:
            retrieved_chunks = retrieve_similar_chunks(conn, query_emb, k=k)
            context_text = "\n\n".join([r["content"] for r in retrieved_chunks])

        # Construct prompt dynamically
        prompt = f"Context:\n{context_text}\n\nQuestion: {user_query}\nAnswer:"

        # Use LoRA endpoint if defined; fallback to Bedrock
        if LORA_ENDPOINT:
            answer = generate_lora_answer(prompt)
        else:
            answer = generate_bedrock_answer(prompt)

        # Format response
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


# For local testing
if __name__ == "__main__":
    test_event = {
        "body": json.dumps({
            "query": "What documents are required for a study permit in Canada?",
            "top_k": 3
        })
    }
    print(json.dumps(handler(test_event, None), indent=2))
