"""
Balanced Lambda function to process immigration documents from S3 with:
- Data quality validation
- Text cleaning and normalization
- Semantic chunking (built-in Python - no LangChain)
- Generate embeddings and store in pgvector
- Save to /cleaned and /curated for observability

Trigger: S3 ObjectCreated events on /raw prefix
Output: Cleaned data in /cleaned, curated chunks in /curated, embeddings in pgvector
"""

import json
import boto3
import psycopg2
from psycopg2.extras import execute_values
import os
import re
import uuid
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

# Initialize AWS clients
s3_client = boto3.client('s3')
secretsmanager_client = boto3.client('secretsmanager')
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

# Configuration from environment variables
PGVECTOR_SECRET_ARN = os.environ['PGVECTOR_SECRET_ARN']
EMBEDDING_MODEL = os.environ.get('BEDROCK_EMBEDDING_MODEL', 'amazon.titan-embed-text-v1')
EMBEDDING_DIMENSIONS = int(os.environ.get('EMBEDDING_DIMENSIONS', '1536'))
CHUNK_SIZE = int(os.environ.get('CHUNK_SIZE', '1000'))
CHUNK_OVERLAP = int(os.environ.get('CHUNK_OVERLAP', '200'))

# Processing configuration
REQUIRED_FIELDS = ['id', 'content']


def validate_documents(documents: List[Dict[str, Any]]) -> Tuple[List[Dict], int]:
    """
    Validate document data quality.

    Args:
        documents: List of document dictionaries

    Returns:
        Tuple of (valid_documents, error_count)
    """
    valid_docs = []
    errors = 0
    seen_ids = set()

    for doc in documents:
        # Check required fields
        if not all(field in doc for field in REQUIRED_FIELDS):
            errors += 1
            continue

        # Check ID uniqueness
        if doc['id'] in seen_ids:
            errors += 1
            continue

        # Check content validity
        content = doc.get('content', '')
        if not content or len(content) < 10:
            errors += 1
            continue

        seen_ids.add(doc['id'])
        valid_docs.append(doc)

    print(f"Validation: {len(valid_docs)} valid, {errors} invalid")
    return valid_docs, errors


def clean_text(text: str) -> str:
    """
    Clean and normalize text content.

    Args:
        text: Raw text content

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)

    # Normalize quotes
    text = text.replace('"', '"').replace('"', '"').replace("'", "'").replace("'", "'")

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def normalize_date(date_str: str) -> Optional[str]:
    """Normalize date to YYYY-MM-DD format."""
    if not date_str:
        return None

    date_formats = ['%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d']
    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            return parsed_date.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return date_str  # Return original if can't parse


def clean_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean entire document.

    Args:
        doc: Raw document

    Returns:
        Cleaned document
    """
    cleaned = doc.copy()

    # Clean content
    if 'content' in cleaned:
        cleaned['content'] = clean_text(cleaned['content'])

    # Clean text fields
    for field in ['title', 'section', 'source', 'granularity']:
        if field in cleaned and cleaned[field]:
            cleaned[field] = str(cleaned[field]).strip()

    # Normalize dates
    for date_field in ['date_published', 'date_scraped']:
        if date_field in cleaned and cleaned[date_field]:
            cleaned[date_field] = normalize_date(cleaned[date_field])

    return cleaned


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """
    Simple text chunking with overlap (no external dependencies).
    Tries to break at sentence boundaries for better semantic coherence.

    Why it's important: This runs for every document and can handle very large texts; inefficient chunking
    or bad overlap logic can significantly slow ingestion and even risk infinite loops.

    Optimization notes:
    - Ensure forward progress even if overlap >= chunk_size (avoid infinite loop).
    - Reduce repeated global lookups and slicing overhead by keeping indices tight.
    - Keep the sentence-boundary search bounded and cheap.

    Args:
        text: Text to chunk
        chunk_size: Target size of each chunk
        overlap: Characters to overlap between chunks

    Returns:
        List of text chunks
    """
    n = len(text)
    if n == 0:
        return []
    if n <= chunk_size:
        return [text.strip()]

    # Guarantee forward progress: overlap can't cancel out the window advance
    effective_overlap = min(overlap, chunk_size - 1)

    chunks: List[str] = []
    start = 0
    # limit the sentence boundary search range to at most 100 characters for speed
    lookback = 100

    while start < n:
        end = min(start + chunk_size, n)

        # Try to break at sentence boundary within [end-lookback, end)
        if end < n:
            lb = max(start, end - lookback)
            cut = text.rfind('. ', lb, end)
            if cut > start:
                end = cut + 1  # include period

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start forward; ensure at least +1 progress
        next_start = end - effective_overlap
        if next_start <= start:
            next_start = start + 1
        start = next_start

        # Early exit if the remaining tail is tiny
        if n - start <= 0:
            break

    return chunks


def chunk_document(doc: Dict[str, Any], chunk_size: int, chunk_overlap: int) -> List[Dict[str, Any]]:
    """
    Chunk a single document into smaller pieces.

    Args:
        doc: Cleaned document
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks

    Returns:
        List of chunk dictionaries
    """
    content = doc.get('content', '')

    if not content or len(content) < 100:
        # Don't chunk very small documents
        chunk_id = f"{doc.get('id')}_chunk_1"
        return [{
            'id': chunk_id,
            'document_id': doc.get('id'),
            'content': content,
            'title': doc.get('title'),
            'section': doc.get('section'),
            'source': doc.get('source'),
            'date_published': doc.get('date_published'),
            'date_scraped': doc.get('date_scraped'),
            'granularity': doc.get('granularity')
        }]

    # Split into chunks
    text_chunks = chunk_text(content, chunk_size, chunk_overlap)

    # Convert to chunk dictionaries efficiently
    # Why it's important: This loop runs for every chunk of every document. Avoid repeated dict lookups
    # by hoisting common fields and only varying id/content per chunk.
    base = {
        'document_id': doc.get('id'),
        'title': doc.get('title'),
        'section': doc.get('section'),
        'source': doc.get('source'),
        'date_published': doc.get('date_published'),
        'date_scraped': doc.get('date_scraped'),
        'granularity': doc.get('granularity'),
    }
    chunk_dicts: List[Dict[str, Any]] = []
    doc_id = base['document_id']
    for idx, text_chunk in enumerate(text_chunks, 1):
        chunk_dicts.append({
            'id': f"{doc_id}_chunk_{idx}",
            'content': text_chunk,
            **base,
        })

    return chunk_dicts


def save_to_s3(data: Any, bucket: str, key: str):
    """
    Save data to S3 (DISABLED - keeping function for compatibility).

    Args:
        data: Data to save (will be JSON serialized)
        bucket: S3 bucket name
        key: S3 object key
    """
    # S3 writes disabled
    print(f"[SKIPPED] Would save to s3://{bucket}/{key}")
    return


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


def get_embedding(text: str, max_retries: int = 5, base_delay: float = 1.0) -> List[float]:
    """
    Generate embedding vector using Amazon Titan Embeddings G1 - Text with exponential backoff retry.

    Args:
        text: Input text to embed
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff

    Returns:
        List of floats representing the embedding vector
    """
    # Truncate if too long (Titan has limits)
    max_length = 8000
    if len(text) > max_length:
        text = text[:max_length]
        print(f"Warning: Text truncated to {max_length} characters for embedding")

    # Titan Embeddings G1 - Text request format
    request_body = json.dumps({
        "inputText": text
    })

    for attempt in range(max_retries):
        try:
            response = bedrock_runtime.invoke_model(
                modelId=EMBEDDING_MODEL,
                contentType='application/json',
                accept='application/json',
                body=request_body
            )

            response_body = json.loads(response['body'].read())
            embedding = response_body['embedding']

            return embedding

        except Exception as e:
            error_str = str(e)

            # Check if it's a throttling error
            if 'ThrottlingException' in error_str or 'Too many requests' in error_str:
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                    delay = base_delay * (2 ** attempt)
                    print(f"ThrottlingException on attempt {attempt + 1}/{max_retries}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    print(f"Error generating embedding after {max_retries} attempts: {error_str}")
                    raise
            else:
                # Non-throttling error, raise immediately
                print(f"Error generating embedding: {error_str}")
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

        # Drop existing table if schema is wrong
        cursor.execute("DROP TABLE IF EXISTS documents;")

        # Create documents table with VARCHAR id (not UUID)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS documents (
                id VARCHAR PRIMARY KEY,
                title VARCHAR,
                section VARCHAR,
                content TEXT,
                source VARCHAR,
                date_published DATE,
                date_scraped TIMESTAMP,
                granularity VARCHAR,
                embedding VECTOR({EMBEDDING_DIMENSIONS})
            );
        """)

        # Create IVFFlat index for vector similarity search
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS documents_embedding_ivf
            ON documents USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
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


def insert_chunks(cursor, chunks: List[Dict[str, Any]]):
    """
    Insert chunks with embeddings into the database using upsert.

    Args:
        cursor: Database cursor object
        chunks: List of processed chunks with embeddings
    """
    try:
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
                embedding = EXCLUDED.embedding;
        """

        values = []
        for chunk in chunks:
            if chunk and chunk.get('embedding'):
                # Convert date_scraped to timestamp if it's a date string
                date_scraped = chunk.get('date_scraped')
                if isinstance(date_scraped, str):
                    try:
                        date_scraped = datetime.strptime(date_scraped, '%Y-%m-%d').isoformat()
                    except:
                        date_scraped = datetime.now().isoformat()

                values.append((
                    chunk.get('id'),
                    chunk.get('title'),
                    chunk.get('section'),
                    chunk.get('content'),
                    chunk.get('source'),
                    chunk.get('date_published'),
                    date_scraped,
                    chunk.get('granularity'),
                    chunk.get('embedding')
                ))

        if values:
            execute_values(cursor, insert_query, values)
            print(f"Successfully inserted/updated {len(values)} chunks")
        else:
            print("No valid chunks to insert")

    except Exception as e:
        print(f"Error inserting chunks: {str(e)}")
        raise


def handler(event, context):
    """
    Lambda handler with balanced processing pipeline and batch processing.

    Pipeline stages:
    1. Load raw data from S3
    2. Validate data quality
    3. Clean and normalize → save to /cleaned
    4. Chunk semantically → save to /curated
    5. Generate embeddings (in batches to fit Lambda timeout)
    6. Store in pgvector

    Args:
        event: S3 event containing bucket and object information
        context: Lambda context object

    Returns:
        Dict with status code and processing results
    """
    print(f"Received event: {json.dumps(event)}")

    # Lambda timeout management - leave 60 seconds buffer
    lambda_timeout_seconds = context.get_remaining_time_in_millis() / 1000 - 60
    start_time = datetime.now()

    try:
        # Extract S3 information from event
        s3_event = event['Records'][0]['s3']
        bucket_name = s3_event['bucket']['name']
        object_key = s3_event['object']['key']

        print(f"Processing file: s3://{bucket_name}/{object_key}")
        print(f"Lambda timeout: {lambda_timeout_seconds}s available")

        # Extract date and filename for output paths
        date_path = datetime.now().strftime('%Y-%m-%d')
        filename = os.path.basename(object_key).replace('.json', '')

        # ========== STAGE 1: LOAD RAW DATA ==========
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        file_content = response['Body'].read().decode('utf-8')
        documents = json.loads(file_content)

        print(f"Loaded {len(documents)} documents from S3")

        # ========== STAGE 2: VALIDATE DATA ==========
        valid_documents, error_count = validate_documents(documents)

        if not valid_documents:
            raise ValueError(f"No valid documents after validation. Errors: {error_count}")

        # ========== STAGE 3: CLEAN AND NORMALIZE ==========
        cleaned_documents = [clean_document(doc) for doc in valid_documents]

        print(f"Cleaned {len(cleaned_documents)} documents")

        # ========== STAGE 4: SEMANTIC CHUNKING ==========
        all_chunks = []
        for doc in cleaned_documents:
            chunks = chunk_document(doc, CHUNK_SIZE, CHUNK_OVERLAP)
            all_chunks.extend(chunks)

        print(f"Created {len(all_chunks)} chunks from {len(cleaned_documents)} documents")

        # ========== STAGE 5: GENERATE EMBEDDINGS ==========

        # First, check which chunks already exist in database
        connection = get_db_connection()
        cursor = connection.cursor()
        initialize_database(cursor)

        # Get list of already processed chunk IDs
        chunk_ids = [chunk.get('id') for chunk in all_chunks]
        cursor.execute(
            "SELECT id FROM documents WHERE id = ANY(%s)",
            (chunk_ids,)
        )
        existing_ids = set(row[0] for row in cursor.fetchall())
        print(f"Found {len(existing_ids)} chunks already in database, will skip those")

        chunks_with_embeddings = []
        total_chunks = len(all_chunks)
        chunks_to_process = [c for c in all_chunks if c.get('id') not in existing_ids]

        print(
            f"Total chunks: {total_chunks}, Already processed: {len(existing_ids)}, To process: {len(chunks_to_process)}")

        # Faster rate limiting to fit within Lambda timeout
        # With these settings: ~800-900 chunks in 15 minutes
        EMBEDDING_DELAY = 0.2  # 200ms = ~5 req/second (faster but still safe)
        BATCH_SIZE = 25  # Process in batches of 25
        BATCH_DELAY = 1.0  # 1s pause every 25 chunks

        chunks_processed = 0

        print(f"Starting embedding generation with timeout-aware processing...")
        print(f"Rate limit: {EMBEDDING_DELAY}s delay, batch pause every {BATCH_SIZE} chunks")

        for idx, chunk in enumerate(chunks_to_process, 1):
            # Check if we're running out of time
            elapsed = (datetime.now() - start_time).total_seconds()
            remaining = lambda_timeout_seconds - elapsed

            if remaining < 120:  # Less than 2 minutes left
                print(f"⚠️  Approaching timeout! Processed {chunks_processed}/{len(chunks_to_process)} new chunks")
                print(
                    f"Total in DB: {len(existing_ids) + chunks_processed}, Remaining: {len(chunks_to_process) - chunks_processed}")
                break

            try:
                content = chunk.get('content', '')
                if content:
                    embedding = get_embedding(content)
                    chunk['embedding'] = embedding
                    chunks_with_embeddings.append(chunk)
                    chunks_processed += 1

                    # Progress tracking
                    if idx % 50 == 0 or idx == len(chunks_to_process):
                        elapsed_min = elapsed / 60
                        rate = chunks_processed / elapsed if elapsed > 0 else 0
                        eta_min = (len(chunks_to_process) - chunks_processed) / rate / 60 if rate > 0 else 0
                        total_in_db = len(existing_ids) + chunks_processed
                        print(
                            f"Progress: {idx}/{len(chunks_to_process)} new chunks ({idx * 100 // len(chunks_to_process) if len(chunks_to_process) > 0 else 0}%) | "
                            f"Total in DB: {total_in_db}/{total_chunks} | "
                            f"Rate: {rate:.1f} chunks/s | Elapsed: {elapsed_min:.1f}m | ETA: {eta_min:.1f}m")

                    # Rate limiting strategy:
                    if idx < len(chunks_to_process):
                        # Normal delay between each request
                        time.sleep(EMBEDDING_DELAY)

                        # Extra delay every BATCH_SIZE chunks
                        if idx % BATCH_SIZE == 0:
                            time.sleep(BATCH_DELAY)

            except Exception as e:
                error_msg = str(e)
                print(f"Error embedding chunk {chunk.get('id')}: {error_msg}")

                # If still hitting throttling after retries, increase delay
                if 'ThrottlingException' in error_msg or 'Too many requests' in error_msg:
                    print(f"Still throttled after retries. Increasing delay...")
                    time.sleep(5.0)  # Extra cooldown before continuing

                continue

        print(f"Generated embeddings for {len(chunks_with_embeddings)} chunks")

        # ========== STAGE 6: STORE IN PGVECTOR ==========
        # Connection already established earlier for duplicate check

        # Insert chunks into database
        if chunks_with_embeddings:
            insert_chunks(cursor, chunks_with_embeddings)

        # Commit and close
        connection.commit()
        cursor.close()
        connection.close()

        # ========== SUCCESS ==========
        total_in_db = len(existing_ids) + len(chunks_with_embeddings)
        print("=" * 80)
        print("PIPELINE COMPLETED")
        print(f"Raw documents: {len(documents)}")
        print(f"Valid documents: {len(valid_documents)}")
        print(f"Total chunks created: {len(all_chunks)}")
        print(f"Already in database: {len(existing_ids)}")
        print(f"Newly processed: {len(chunks_with_embeddings)}")
        print(f"Total in database: {total_in_db}/{len(all_chunks)}")
        if total_in_db < len(all_chunks):
            remaining = len(all_chunks) - total_in_db
            print(f"⚠️  Partial processing: {remaining} chunks remaining")
            print(f"💡 File will be reprocessed automatically on next S3 trigger")
        else:
            print(f"✅ All chunks processed successfully!")
        print("=" * 80)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Pipeline completed" if total_in_db == len(
                    all_chunks) else "Partial processing - will continue on retry",
                "documents_processed": len(valid_documents),
                "chunks_created": len(all_chunks),
                "chunks_already_in_db": len(existing_ids),
                "chunks_newly_stored": len(chunks_with_embeddings),
                "chunks_total_in_db": total_in_db,
                "chunks_remaining": len(all_chunks) - total_in_db
            })
        }

    except Exception as e:
        error_msg = f"Pipeline failed: {str(e)}"
        print(error_msg)

        return {
            "statusCode": 500,
            "body": json.dumps({"error": error_msg})
        }
