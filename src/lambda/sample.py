"""
Lambda function to process JSON documents from S3, generate embeddings using 
Amazon Titan Embeddings G1, and store them in Aurora PostgreSQL with pgvector.

Trigger: S3 ObjectCreated events
Input: JSON array with documents containing id, title, section, content, etc.
Output: Documents stored in pgvector database with embeddings
"""

import json
import boto3
import psycopg2
from psycopg2.extras import execute_values
import os
from datetime import datetime
from typing import List, Dict, Any

# Initialize AWS clients
s3_client = boto3.client('s3')
secretsmanager_client = boto3.client('secretsmanager')
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

# Configuration from environment variables
PGVECTOR_SECRET_ARN = os.environ['PGVECTOR_SECRET_ARN']
EMBEDDING_MODEL = os.environ.get('BEDROCK_EMBEDDING_MODEL', 'amazon.titan-embed-text-v1')
EMBEDDING_DIMENSIONS = int(os.environ.get('EMBEDDING_DIMENSIONS', '1536'))


def get_db_connection():
    """
    Retrieve database credentials from Secrets Manager and establish connection.
    
    Returns:
        psycopg2.connection: Database connection object
    """
    try:
        secret_response = secretsmanager_client.get_secret_value(SecretId=PGVECTOR_SECRET_ARN)
        credentials = json.loads(secret_response['SecretString'])
        
        connection = psycopg2.connect(
            host=credentials['host'],
            port=credentials['port'],
            database=credentials['dbname'],
            user=credentials['username'],
            password=credentials['password'],
            connect_timeout=10
        )
        
        print(f"Successfully connected to database: {credentials['host']}")
        return connection
        
    except Exception as e:
        print(f"Error connecting to database: {str(e)}")
        raise


def get_embedding(text: str) -> List[float]:
    """
    Generate embedding vector using Amazon Titan Embeddings G1 - Text.
    
    Args:
        text: Input text to embed
        
    Returns:
        List of floats representing the embedding vector
    """
    try:
        # Titan Embeddings G1 - Text request format
        request_body = json.dumps({
            "inputText": text
        })
        
        response = bedrock_runtime.invoke_model(
            modelId=EMBEDDING_MODEL,
            contentType='application/json',
            accept='application/json',
            body=request_body
        )
        
        response_body = json.loads(response['body'].read())
        embedding = response_body['embedding']
        
        print(f"Generated embedding with {len(embedding)} dimensions")
        return embedding
        
    except Exception as e:
        print(f"Error generating embedding: {str(e)}")
        raise


def initialize_database(cursor):
    """
    Initialize database with pgvector extension and documents table.
    
    Args:
        cursor: Database cursor object
    """
    try:
        # Enable pgvector extension
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        # Create documents table with vector column
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS documents (
                id UUID PRIMARY KEY,
                title TEXT,
                section TEXT,
                content TEXT NOT NULL,
                source TEXT,
                date_published DATE,
                date_scraped DATE,
                granularity TEXT,
                embedding vector({EMBEDDING_DIMENSIONS}),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Create HNSW index for fast vector similarity search
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS documents_embedding_hnsw_idx 
            ON documents USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        """)
        
        # Create index on source for filtering
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS documents_source_idx 
            ON documents (source);
        """)
        
        print("Database initialized successfully")
        
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
        raise


def process_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single document: generate embedding and prepare for insertion.
    
    Args:
        doc: Document dictionary from JSON
        
    Returns:
        Document with embedding added
    """
    try:
        # Extract content for embedding
        content = doc.get('content', '')
        
        if not content:
            print(f"Warning: Document {doc.get('id')} has no content, skipping")
            return None
        
        # Generate embedding
        embedding = get_embedding(content)
        
        # Add embedding to document
        doc['embedding'] = embedding
        
        return doc
        
    except Exception as e:
        print(f"Error processing document {doc.get('id')}: {str(e)}")
        return None


def insert_documents(cursor, documents: List[Dict[str, Any]]):
    """
    Insert documents with embeddings into the database using upsert.
    
    Args:
        cursor: Database cursor object
        documents: List of processed documents with embeddings
    """
    try:
        # Prepare data for batch insert
        insert_query = f"""
            INSERT INTO documents (
                id, title, section, content, source, 
                date_published, date_scraped, granularity, embedding
            ) VALUES %s
            ON CONFLICT (id) 
            DO UPDATE SET
                title = EXCLUDED.title,
                section = EXCLUDED.section,
                content = EXCLUDED.content,
                source = EXCLUDED.source,
                date_published = EXCLUDED.date_published,
                date_scraped = EXCLUDED.date_scraped,
                granularity = EXCLUDED.granularity,
                embedding = EXCLUDED.embedding,
                updated_at = CURRENT_TIMESTAMP;
        """
        
        # Prepare values tuples
        values = []
        for doc in documents:
            if doc and doc.get('embedding'):
                values.append((
                    doc.get('id'),
                    doc.get('title'),
                    doc.get('section'),
                    doc.get('content'),
                    doc.get('source'),
                    doc.get('date_published'),
                    doc.get('date_scraped'),
                    doc.get('granularity'),
                    doc.get('embedding')
                ))
        
        if values:
            execute_values(cursor, insert_query, values)
            print(f"Successfully inserted/updated {len(values)} documents")
        else:
            print("No valid documents to insert")
            
    except Exception as e:
        print(f"Error inserting documents: {str(e)}")
        raise


def handler(event, context):
    """
    Lambda handler function triggered by S3 events.
    
    Args:
        event: S3 event containing bucket and object information
        context: Lambda context object
        
    Returns:
        Dict with status code and processing results
    """
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Extract S3 information from event
        s3_event = event['Records'][0]['s3']
        bucket_name = s3_event['bucket']['name']
        object_key = s3_event['object']['key']
        
        print(f"Processing file: s3://{bucket_name}/{object_key}")
        
        # Download and parse JSON file from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        file_content = response['Body'].read().decode('utf-8')
        documents = json.loads(file_content)
        
        print(f"Loaded {len(documents)} documents from S3")
        
        
        # Connect to database
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Initialize database (creates table and extension if not exists)
        initialize_database(cursor)
        
        # Process documents in parallel
        processed_docs = []
        for doc in documents:
            processed_doc = process_document(doc)
            if processed_doc:
                processed_docs.append(processed_doc)
        
        # Insert documents into database
        if processed_docs:
            insert_documents(cursor, processed_docs)
        
        # Commit changes and close connection
        connection.commit()
        cursor.close()
        connection.close()
        
        print("Successfully processed and inserted all documents")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Successfully processed {len(processed_docs)} documents"
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
        
        