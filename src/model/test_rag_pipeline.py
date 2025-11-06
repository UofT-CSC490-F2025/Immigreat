import json
import os
import boto3
import psycopg2

bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')
secretsmanager_client = boto3.client('secretsmanager')

PGVECTOR_SECRET_ARN = os.environ['PGVECTOR_SECRET_ARN']
EMBEDDING_MODEL = os.environ.get('BEDROCK_EMBEDDING_MODEL', 'amazon.titan-embed-text-v1')

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

def generate_answer(prompt):
    response = bedrock_runtime.invoke_model(
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500
        })
    )
    return json.loads(response["body"].read())["content"][0]["text"]

def handler(event, context):
    body = json.loads(event["body"])
    user_query = body["query"]

    conn = get_db_connection()
    query_emb = get_embedding(user_query)
    chunks = retrieve_similar_chunks(conn, query_emb, k=5)

    context = "\n\n".join([r[1] for r in chunks])
    prompt = f"Context:\n{context}\n\nQuestion: {user_query}\nAnswer:"
    answer = generate_answer(prompt)

    conn.close()

    return {
        "statusCode": 200,
        "body": json.dumps({
            "query": user_query,
            "answer": answer,
            "sources": [dict(id=r[0], source=r[2], title=r[3], similarity=r[4]) for r in chunks]
        })
    }