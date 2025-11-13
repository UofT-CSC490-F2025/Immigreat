from locust import HttpUser, task, between
import random
import json

# Example queries for testing
SAMPLE_QUERIES = [
    "What are the immigration requirements for Canada?",
    "Explain how neural networks work.",
    "Summarize the Privacy Act in simple terms.",
    "Who won the 2024 US election?",
    "How does quantum computing differ from classical computing?"
]

class RagUser(HttpUser):
    wait_time = between(1, 3)  # seconds between requests per simulated user

    @task
    def query_rag(self):
        query = random.choice(SAMPLE_QUERIES)
        payload = {"query": query}

        with self.client.post(
            "/rag",  # <-- replace with your actual endpoint (e.g. API Gateway or FastAPI path)
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(f"Failed with {response.status_code}")
            elif len(response.text) < 50:
                response.failure("Response too short — potential timeout or truncation.")
            else:
                response.success()