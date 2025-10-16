from openai import OpenAI
import chromadb

client = OpenAI()
chroma_client = chromadb.Client()
collection = chroma_client.get_collection("immigration_sections")

query = "Who is responsible for administering the IRPA?"
embedding = client.embeddings.create(
    input=query,
    model="text-embedding-3-large"
).data[0].embedding

results = collection.query(
    query_embeddings=[embedding],
    n_results=3
)

for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
    print("----")
    print(f"Source: {meta['source']} ({meta['section']})")
    print(doc[:400], "...")
