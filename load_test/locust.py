from locust import HttpUser, task, between

class RAGUser(HttpUser):
    wait_time = between(1, 3)

    host = "https://e3r43imacumt3txigpboq7uhbe0kyybv.lambda-url.us-east-1.on.aws"

    @task
    def test_lambda(self):
        payload = {
            "query": "This is a test query for load testing"
        }
        self.client.post("/", json=payload)  
