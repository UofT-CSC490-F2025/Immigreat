import json
import os
from uuid import uuid4
from typing import List
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# Initialize Chroma client
chroma_client = chromadb.Client(Settings(persist_directory="./immigration_rag_db"))
collection = chroma_client.get_or_create_collection(name="immigration_sections")

# -----------------------------
# Load local embedding model
# -----------------------------
# You can change this to 'intfloat/e5-base-v2' or 'all-MiniLM-L6-v2' for faster performance
embedding_model = SentenceTransformer('BAAI/bge-large-en')

# -----------------------------
# Load your data
# -----------------------------
with open("irpr_irpa_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# -----------------------------
# Helper: Chunk text
# -----------------------------
def chunk_text(text: str, max_length: int = 500, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks by words."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_length, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += max_length - overlap
    return chunks

# -----------------------------
# Helper: Embed text locally
# -----------------------------
def embed_texts(texts: List[str]) -> List[List[float]]:
    """Create embeddings using local SentenceTransformer model."""
    embeddings = embedding_model.encode(texts, batch_size=32, show_progress_bar=True)
    return [e.tolist() for e in embeddings]

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

print(f"Ingested {len(data)} sections into ChromaDB using local embeddings.")
print("Database stored in ./immigration_rag_db")
