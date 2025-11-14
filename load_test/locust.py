from locust import HttpUser, task, between

class RAGUser(HttpUser):
    wait_time = between(1, 3)

    host = "https://fvnuhvmnrvfqlf5urz6piu2kwu0vhxbw.lambda-url.us-east-1.on.aws"

    @task
    def test_lambda(self):
        payload = {
            "query": "This is a test query for load testing"
        }
        self.client.post("/", json=payload)  
