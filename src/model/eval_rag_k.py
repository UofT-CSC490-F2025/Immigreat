import json
import boto3
import requests

from rag_llm_judge.judge.judge_model import ImmigrationJudge
from .testing_data.questions import QUESTIONS_DATA        # expected = 1
from .testing_data.questions import NEGATIVE_QUESTIONS    # expected = 0


LAMBDA_URL = "https://pym5mhopdyechc5a2pp6eim5mq0otoly.lambda-url.us-east-1.on.aws/"
LAMBDA_NAME = "rag_pipeline-function-prod"

lambda_client = boto3.client("lambda")

# -----------------------------
# CALL RAG API
# -----------------------------
def call_rag_lambda(query: str, k: int, use_facet: bool, use_rerank: bool) -> dict:
    r = requests.post(LAMBDA_URL, json={"query": query, "k": k, "use_facets": use_facet, "use_rerank": use_rerank})
    r.raise_for_status()
    return r.json()

def extract_deepseek_answer(raw: str) -> str:
    if raw is None:
        return ""
    if "</think>" in raw:
        return raw.split("</think>", 1)[1].strip()
    return raw.strip()

# -----------------------------
# EVALUATION FUNCTION
# -----------------------------
def evaluate_config(k: int, use_facet: bool, use_rerank: bool, judge: ImmigrationJudge):

    # Build combined dataset (same as before)
    dataset = []

    for q in QUESTIONS_DATA:
        dataset.append(q)

    for n in NEGATIVE_QUESTIONS:
        dataset.append(n)

    total = len(dataset)
    count_yes = 0  # Count of judge == 1

    print(f"\n===== Evaluating (k={k}, facet={use_facet}, rerank={use_rerank}) =====")

    for item in dataset:
        print("\n----------------------------------------",  flush=True)
        q = str(item["question"])
        if not isinstance(q, str) or not q.strip():
            raise ValueError(f"Invalid question in dataset: {q}")

        resp = call_rag_lambda(q, k, use_facet, use_rerank)
        raw_answer = resp.get("answer", "")

        answer = extract_deepseek_answer(raw_answer)

        pred, _ = judge.judge_single(q, answer)

        if pred == 1:
            count_yes += 1

        print(f"\nQ: {q}")
        print(f"A: {answer[:200]} ...")
        print(f"Judge prediction: {pred}")

    print(f"\n=== Judge predicted '1' {count_yes} times out of {total} questions ===\n")

    # Return the count, not accuracy
    return count_yes


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
