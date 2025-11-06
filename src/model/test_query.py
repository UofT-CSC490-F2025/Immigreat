from test_rag_pipeline import handler
import json

event = {"body": json.dumps({"query": "What are the steps to apply for a Canadian work visa?"})}
print(handler(event, None))
