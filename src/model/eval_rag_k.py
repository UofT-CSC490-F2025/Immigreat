import os
import time
import json
import boto3
import requests

from rag_llm_judge.judge.judge_model import ImmigrationJudge  
from .training_data.questions import QUESTIONS_DATA        # expected = 1
from .training_data.questions import NEGATIVE_QUESTIONS  # expected = 0

LAMBDA_URL = "https://<your-id>.lambda-url.us-east-1.on.aws/"
LAMBDA_NAME = "<your-lambda-name>"

lambda_client = boto3.client("lambda")


def call_rag_lambda(query: str, k: int) -> dict:
    """Call the RAG Lambda via Function URL."""
    r = requests.post(LAMBDA_URL, json={"query": query, "k": k})
    r.raise_for_status()
    return r.json()


def evaluate_k(k: int, judge: ImmigrationJudge):
    """Evaluate RAG performance for a given top-k retrieval."""

    # Merge datasets:
    # POSITIVE (expected=1) + NEGATIVE (expected=0)
    dataset = []

    for q in QUESTIONS_DATA:
        dataset.append({"question": q, "expected": 1})

    for n in NEGATIVE_QUESTIONS:
        dataset.append(n)

    correct = 0
    total = len(dataset)

    print(f"\n===== Evaluating top-k = {k}  ({total} questions) =====")

    for item in dataset:
        q = item["question"]
        expected = item["expected"]

        # Call your RAG system
        resp = call_rag_lambda(q, k)
        answer = resp.get("answer", "")

        # Judge the response
        pred, _ = judge.judge_single(q, answer)

        # Count correct judgments
        if pred == expected:
            correct += 1

        print(f"\nQ: {q}")
        print(f"A: {answer[:200]} ...")
        print(f"Judge prediction: {pred}, Expected: {expected}")

    accuracy = correct / total
    print(f"\n=== Top-k = {k} Accuracy: {accuracy:.4f} ===\n")
    return accuracy


if __name__ == "__main__":
    judge = ImmigrationJudge(quantize=True)

    ks = [3, 5, 8, 12]
    results = {}

    for k in ks:
        acc = evaluate_k(k, judge)
        results[k] = acc

    print("\nFinal Results:")
    print(json.dumps(results, indent=2))
