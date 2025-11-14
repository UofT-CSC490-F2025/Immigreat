from locust import HttpUser, task, between

class RAGUser(HttpUser):
    wait_time = between(1, 3)

    host = "https://pym5mhopdyechc5a2pp6eim5mq0otoly.lambda-url.us-east-1.on.aws"

    @task
    def test_lambda(self):
        payload = {
            "query": "This is a test query for load testing"
        }
        self.client.post("/", json=payload)  
