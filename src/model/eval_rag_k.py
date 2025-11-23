import os
import time
import json
import boto3
import requests

from rag_llm_judge.judge.judge_model import ImmigrationJudge
from .training_data.questions import QUESTIONS_DATA        # expected = 1
from .training_data.questions import NEGATIVE_QUESTIONS    # expected = 0


LAMBDA_URL = "https://<your-id>.lambda-url.us-east-1.on.aws/"
LAMBDA_NAME = "<your-lambda-name>"

lambda_client = boto3.client("lambda")

# -----------------------------
# CALL RAG API
# -----------------------------
def call_rag_lambda(query: str, k: int, use_facet: bool, use_rerank: bool) -> dict:
    r = requests.post(LAMBDA_URL, json={"query": query, "k": k, "use_facet": use_facet, "use_rerank": use_rerank})
    r.raise_for_status()
    return r.json()


# -----------------------------
# EVALUATION FUNCTION
# -----------------------------
def evaluate_config(k: int, use_facet: bool, use_rerank: bool, judge: ImmigrationJudge):

    # Build combined dataset
    dataset = []

    for q in QUESTIONS_DATA:
        dataset.append({"question": q, "expected": 1})

    for n in NEGATIVE_QUESTIONS:
        dataset.append(n)

    correct = 0
    total = len(dataset)

    print(f"\n===== Evaluating (k={k}, facet={use_facet}, rerank={use_rerank}) =====")

    for item in dataset:
        q = item["question"]
        expected = item["expected"]

        resp = call_rag_lambda(q, k, use_facet, use_rerank)
        answer = resp.get("answer", "")

        pred, _ = judge.judge_single(q, answer)

        if pred == expected:
            correct += 1

        print(f"\nQ: {q}")
        print(f"A: {answer[:200]} ...")
        print(f"Judge prediction: {pred}, Expected: {expected}")

    acc = correct / total
    print(f"\n=== Accuracy (k={k}, facet={use_facet}, rerank={use_rerank}): {acc:.4f} ===\n")
    return acc


# -----------------------------
# MAIN EXECUTION
# -----------------------------
if __name__ == "__main__":
    judge = ImmigrationJudge(quantize=True)

    ks = [3, 5, 8, 12]
    facet_options = [True, False]
    rerank_options = [True, False]

    # Store results in dict
    results = {}

    for k in ks:
        for facet in facet_options:
            for rerank in rerank_options:

                key = f"k={k},facet={facet},rerank={rerank}"
                acc = evaluate_config(k, facet, rerank, judge)
                results[key] = acc

    print("\n========== FINAL RESULTS ==========")
    print(json.dumps(results, indent=2))
