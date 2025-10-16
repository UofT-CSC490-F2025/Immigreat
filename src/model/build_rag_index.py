import json
import os
from typing import List, Dict
from uuid import uuid4
import tiktoken
from openai import OpenAI
import chromadb
from chromadb.config import Settings

# Initialize OpenAI and Chroma clients
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
chroma_client = chromadb.Client(Settings(persist_directory="./immigration_rag_db"))

# Create or get a collection (our vector index)
collection = chroma_client.get_or_create_collection(name="immigration_sections")

# -----------------------------
# Load data
# -----------------------------
with open("irpa_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# -----------------------------
# Helper: Chunk text
# -----------------------------
def chunk_text(text: str, max_tokens: int = 500, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks using token count."""
    tokenizer = tiktoken.get_encoding("cl100k_base")
    tokens = tokenizer.encode(text)

    chunks = []
    start = 0
    while start < len(tokens):
        end = start + max_tokens
        chunk = tokens[start:end]
        chunk_text = tokenizer.decode(chunk)
        chunks.append(chunk_text)
        start += max_tokens - overlap

    return chunks

# -----------------------------
# Helper: Create embeddings
# -----------------------------
def embed_texts(texts: List[str]) -> List[List[float]]:
    """Create embeddings for a list of texts using OpenAI API."""
    response = client.embeddings.create(
        input=texts,
        model="text-embedding-3-large"
    )
    return [d.embedding for d in response.data]

# -----------------------------
# Process and store chunks
# -----------------------------
for entry in data:
    content = entry.get("content", "").strip()
    if not content:
        continue

    chunks = chunk_text(content)
    embeddings = embed_texts(chunks)

    for i, emb in enumerate(embeddings):
        collection.add(
            ids=[str(uuid4())],
            embeddings=[emb],
            documents=[chunks[i]],
            metadatas=[{
                "source": entry.get("source", ""),
                "section": entry.get("section", ""),
                "title": entry.get("title", ""),
                "date_scraped": entry.get("date_scraped", ""),
                "granularity": entry.get("granularity", "")
            }]
        )

print(f"Ingested {len(data)} sections into ChromaDB.")
print(f"Database stored in ./immigration_rag_db")
