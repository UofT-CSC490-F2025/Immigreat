"""Test configuration and fixtures."""
import pytest
import os
import json
from unittest.mock import MagicMock, patch
import boto3
from moto import mock_aws

# Set up environment variables before any imports that need them
os.environ.setdefault('PGVECTOR_SECRET_ARN', 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret')
os.environ.setdefault('BEDROCK_EMBEDDING_MODEL', 'amazon.titan-embed-text-v1')
os.environ.setdefault('EMBEDDING_DIMENSIONS', '1536')
os.environ.setdefault('CHUNK_SIZE', '1000')
os.environ.setdefault('CHUNK_OVERLAP', '200')
os.environ.setdefault('PGVECTOR_DB_HOST', 'localhost')
os.environ.setdefault('PGVECTOR_DB_NAME', 'testdb')
os.environ.setdefault('PGVECTOR_DB_PORT', '5432')
os.environ.setdefault('BEDROCK_CHAT_MODEL', 'anthropic.claude-3-5-sonnet-20240620-v1:0')
os.environ.setdefault('ANTHROPIC_VERSION', 'bedrock-2023-05-31')
os.environ.setdefault('TARGET_S3_BUCKET', 'test-bucket')
os.environ.setdefault('TARGET_S3_KEY', 'test-key')


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for testing."""
    env_vars = {
        'PGVECTOR_SECRET_ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret',
        'BEDROCK_EMBEDDING_MODEL': 'amazon.titan-embed-text-v1',
        'EMBEDDING_DIMENSIONS': '1536',
        'CHUNK_SIZE': '1000',
        'CHUNK_OVERLAP': '200',
        'PGVECTOR_DB_HOST': 'localhost',
        'PGVECTOR_DB_NAME': 'testdb',
        'PGVECTOR_DB_PORT': '5432',
        'BEDROCK_CHAT_MODEL': 'anthropic.claude-3-5-sonnet-20240620-v1:0',
        'ANTHROPIC_VERSION': 'bedrock-2023-05-31',
        'TARGET_S3_BUCKET': 'test-bucket',
        'TARGET_S3_KEY': 'test-key',
    }
    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


@pytest.fixture
def mock_db_connection():
    """Mock database connection."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    return mock_conn, mock_cursor


@pytest.fixture
def mock_secrets_manager():
    """Mock AWS Secrets Manager."""
    with mock_aws():
        client = boto3.client('secretsmanager', region_name='us-east-1')
        secret_value = {
            'host': 'localhost',
            'port': 5432,
            'dbname': 'testdb',
            'username': 'testuser',
            'password': 'testpass'
        }
        client.create_secret(
            Name='test-secret',
            SecretString=json.dumps(secret_value)
        )
        yield client


@pytest.fixture
def mock_s3():
    """Mock S3 client."""
    with mock_aws():
        client = boto3.client('s3', region_name='us-east-1')
        client.create_bucket(Bucket='test-bucket')
        yield client


@pytest.fixture
def sample_document():
    """Sample document for testing."""
    return {
        'id': 'test-doc-123',
        'content': 'This is a test document about Canadian immigration requirements.',
        'source': 'test-source',
        'title': 'Test Document',
        'section': 'Test Section',
        'metadata': {
            'url': 'https://test.example.com',
            'date': '2025-11-24'
        }
    }


@pytest.fixture
def sample_documents():
    """Multiple sample documents for testing."""
    return [
        {
            'id': 'doc-1',
            'content': 'Immigration document content 1' * 10,
            'source': 'IRCC',
            'title': 'Visitor Visa Requirements',
            'section': 'Application Process'
        },
        {
            'id': 'doc-2',
            'content': 'Immigration document content 2' * 10,
            'source': 'Forms',
            'title': 'IMM 5710 Form',
            'section': 'Instructions'
        },
        {
            'id': 'doc-3',
            'content': 'Immigration document content 3' * 10,
            'source': 'IRPR',
            'title': 'Regulations Section 5',
            'section': 'Eligibility'
        }
    ]


@pytest.fixture
def sample_s3_event():
    """Sample S3 event for Lambda testing."""
    return {
        'Records': [
            {
                'eventVersion': '2.1',
                'eventSource': 'aws:s3',
                'eventName': 'ObjectCreated:Put',
                's3': {
                    'bucket': {
                        'name': 'test-bucket'
                    },
                    'object': {
                        'key': 'document/test-doc.json'
                    }
                }
            }
        ]
    }


@pytest.fixture
def sample_query_event():
    """Sample query event for RAG pipeline testing."""
    return {
        'query': 'What are the requirements for a Canadian visitor visa?'
    }


@pytest.fixture
def sample_http_query_event():
    """Sample HTTP query event for RAG pipeline testing."""
    return {
        'body': json.dumps({
            'query': 'What are the requirements for a Canadian visitor visa?'
        }),
        'headers': {
            'Content-Type': 'application/json'
        }
    }


@pytest.fixture
def mock_bedrock_runtime():
    """Mock Bedrock runtime client."""
    mock_client = MagicMock()
    
    # Mock embedding response
    embedding_response = {
        'embedding': [0.1] * 1536
    }
    mock_client.invoke_model.return_value = {
        'body': MagicMock(read=lambda: json.dumps(embedding_response).encode())
    }
    
    return mock_client


@pytest.fixture
def mock_embedding_vector():
    """Mock embedding vector."""
    return [0.1] * 1536


@pytest.fixture
def mock_lambda_context():
    """Mock Lambda context object."""
    context = MagicMock()
    context.get_remaining_time_in_millis.return_value = 300000  # 5 minutes
    context.function_name = 'test-function'
    context.function_version = '$LATEST'
    context.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:test-function'
    context.memory_limit_in_mb = '128'
    context.aws_request_id = 'test-request-id-12345'
    context.log_group_name = '/aws/lambda/test-function'
    context.log_stream_name = '2025/11/24/[$LATEST]test123'
    return context
