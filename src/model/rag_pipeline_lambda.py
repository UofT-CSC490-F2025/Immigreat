import json
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# AWS clients
secrets_client = boto3.client("secretsmanager")
bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")

def get_db_credentials():
    """Retrieve connection credentials from AWS Secrets Manager."""
    secret_name = "pgvector-db-secret"
    response = secrets_client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response["SecretString"])
    return secret

def connect_db():
    creds = get_db_credentials()
    return psycopg2.connect(
        host=creds["host"],
        port=creds["port"],
        dbname=creds["dbname"],
        user=creds["username"],
        password=creds["password"],
        connect_timeout=10
    )

def get_embedding(text):
    """Generate Titan embeddings using Bedrock."""
    body = json.dumps({"inputText": text})
    resp = bedrock_client.invoke_model(
        modelId="amazon.titan-embed-text-v1",
        body=body
    )
    response_body = json.loads(resp["body"].read())
    return response_body["embedding"]

def retrieve_similar_chunks(conn, query_emb):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT content, metadata
            FROM documents
            ORDER BY embedding <-> %s
            LIMIT 5;
        """, (query_emb,))
        return cur.fetchall()

def generate_answer(prompt):
    """Use Claude 3 Sonnet for generation."""
    body = json.dumps({
        "modelId": "anthropic.claude-3-sonnet-20240229-v1:0",
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        "maxTokens": 500,
    })
    resp = bedrock_client.invoke_model(body=body)
    response_body = json.loads(resp["body"].read())
    return response_body["output"]["message"]["content"][0]["text"]

def lambda_handler(event, context):
    """Main Lambda entrypoint."""
    query = event.get("query", "What does the document say about climate policy?")
    print(f"Received query: {query}")

    conn = connect_db()
    try:
        query_emb = get_embedding(query)
        results = retrieve_similar_chunks(conn, query_emb)

        context_text = "\n".join([r["content"] for r in results])
        prompt = f"Answer based on the following context:\n{context_text}\n\nQuestion: {query}"
        answer = generate_answer(prompt)

        return {"answer": answer, "sources": [r["metadata"] for r in results]}
    finally:
        conn.close()
