from locust import HttpUser, task, between
import os
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
    # Use LOCUST_HOST env var to set base URL (e.g., https://xxxxx.lambda-url.us-east-1.on.aws)
    host = os.getenv("LOCUST_HOST", None)
    wait_time = between(1, 3)  # seconds between requests per simulated user

    @task
    def query_rag(self):
        # Include a few adversarial/red-team prompts if provided via env var
        red_team = os.getenv("RED_TEAM", "false").lower() == "true"
        queries = SAMPLE_QUERIES.copy()
        if red_team:
            queries.extend([
                " ",  # empty/whitespace
                "x" * 8000,  # very long input
                "\u0000\u0001\u0002\u0003",  # odd characters
                json.dumps({"nested": {"object": "not a question"}}),
                "; DROP TABLE documents; --",  # SQL-ish junk
            ])

        query = random.choice(queries)
        payload = {"query": query}

        # Lambda Function URL invokes handler at '/'
        with self.client.post(
            "/",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            catch_response=True,
            name="rag_query"
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}: {response.text[:200]}")
                return

            # Validate minimal schema
            try:
                body = response.json()
                if not body.get("answer"):
                    response.failure("Missing 'answer' in response")
                    return
            except Exception:
                if len(response.text) < 50:
                    response.failure("Response too short or not JSON")
                    return

            response.success()