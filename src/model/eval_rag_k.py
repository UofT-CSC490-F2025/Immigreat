import json
import boto3
import requests
import sys
from pathlib import Path
from datetime import datetime

# Get paths
script_dir = Path(__file__).resolve().parent
model_dir = script_dir
src_dir = script_dir.parent
immigreat_dir = src_dir.parent
rag_judge_dir = immigreat_dir / "rag_llm_judge"

# Add BOTH paths
sys.path.insert(0, str(rag_judge_dir))
sys.path.insert(0, str(model_dir))

from rag_llm_judge.judge.judge_model import ImmigrationJudge
from peft import PeftModel
from testing_data.questions import QUESTIONS_DATA, NEGATIVE_QUESTIONS

LAMBDA_URL = "https://pym5mhopdyechc5a2pp6eim5mq0otoly.lambda-url.us-east-1.on.aws/"
LAMBDA_NAME = "rag_pipeline-function-prod"

lambda_client = boto3.client("lambda")


def call_rag_lambda(query: str, k: int, use_facet: bool, use_rerank: bool) -> dict:
    r = requests.post(LAMBDA_URL, json={"query": query, "k": k, "use_facets": use_facet, "use_rerank": use_rerank})
    r.raise_for_status()
    return r.json()


def extract_answer_from_response(text: str) -> str:
    """
    Extract only the answer part from DeepSeek response.
    Split on </think> delimiter - same logic as frontend.

    Format: [thinking]</think>\n\n[answer]

    The RL judge should only evaluate the answer, not the thinking process.
    """
    if not text:
        return ""

    # Check for </think> delimiter
    if '</think>' in text:
        # Get position of </think>
        think_end_index = text.find('</think>')

        # Everything after </think> is the answer
        answer = text[think_end_index + 8:].strip()  # 8 = length of '</think>'

        # Remove "Answer:" prefix if present
        if answer.startswith('**Answer:**'):
            answer = answer[11:].strip()
        elif answer.startswith('Answer:'):
            answer = answer[7:].strip()

        return answer

    # No </think> tag found, return the whole text
    return text.strip()


def evaluate_config(k: int, use_facet: bool, use_rerank: bool, judge: ImmigrationJudge):
    """
    Evaluate RAG configuration using ONLY judge's assessment.
    No ground truth labels - pure relative comparison.

    Returns:
        tuple: (judge_approval_rate, detailed_results)
    """
    # Combine all questions (ignore the "expected" labels - they're wrong anyway!)
    all_questions = []

    # Add questions from QUESTIONS_DATA
    for q in QUESTIONS_DATA:
        all_questions.append(q["question"])

    # Add questions from NEGATIVE_QUESTIONS
    for q in NEGATIVE_QUESTIONS:
        all_questions.append(q["question"])

    approved = 0
    total = len(all_questions)
    detailed_results = []

    print(f"\n===== Evaluating (k={k}, facet={use_facet}, rerank={use_rerank}) =====")

    for question in all_questions:
        # Get RAG answer
        resp = call_rag_lambda(question, k, use_facet, use_rerank)
        raw_answer = resp.get("answer", "")

        # Extract only the answer part (remove thinking process)
        # The RL judge should only evaluate the answer, not the thinking
        answer = extract_answer_from_response(raw_answer)

        # Judge evaluates (no ground truth comparison!)
        pred, judge_response = judge.judge_single(question, answer)

        if pred == 1:
            approved += 1

        # Store detailed result
        detailed_results.append({
            "question": question,
            "rag_answer": answer,  # Store the clean answer
            "rag_answer_raw": raw_answer,  # Store raw for debugging
            "judge_approved": bool(pred),
            "judge_prediction": int(pred),
            "judge_response": judge_response
        })

        status = "✓" if pred == 1 else "✗"
        print(
            f"{status} Q: {question[:60]}... | A: {answer[:100]}... | Judge: {'APPROVED' if pred == 1 else 'REJECTED'}")

    approval_rate = approved / total
    print(f"\n=== Judge Approval Rate: {approval_rate:.4f} ({approved}/{total}) ===\n")

    return approval_rate, detailed_results


def save_results(results, detailed_results, output_dir="rag_eval_results"):
    """Save results to JSON files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save summary results
    summary_file = output_dir / f"summary_{timestamp}.json"
    with open(summary_file, 'w') as f:
        json.dump({
            "note": "Judge approval rates - no ground truth labels used",
            "results": results
        }, f, indent=2)
    print(f"✓ Summary saved to: {summary_file}")

    # Save detailed results
    detailed_file = output_dir / f"detailed_{timestamp}.json"
    with open(detailed_file, 'w') as f:
        json.dump(detailed_results, f, indent=2)
    print(f"✓ Detailed results saved to: {detailed_file}")

    # Save analysis
    analysis = analyze_results(detailed_results)
    analysis_file = output_dir / f"analysis_{timestamp}.json"
    with open(analysis_file, 'w') as f:
        json.dump(analysis, f, indent=2)
    print(f"✓ Analysis saved to: {analysis_file}")


def analyze_results(all_detailed_results):
    """Analyze detailed results to find patterns."""
    analysis = {}

    for config_name, details in all_detailed_results.items():
        approved = [d for d in details if d["judge_approved"]]
        rejected = [d for d in details if not d["judge_approved"]]

        # Find common patterns in rejections
        rejection_samples = [
            {
                "question": r["question"][:80] + "...",
                "rag_answer_preview": r["rag_answer"][:100] + "..."
            }
            for r in rejected[:5]  # First 5 rejections
        ]

        analysis[config_name] = {
            "total_questions": len(details),
            "approved": len(approved),
            "rejected": len(rejected),
            "approval_rate": len(approved) / len(details) if details else 0,
            "sample_rejections": rejection_samples
        }

    return analysis


if __name__ == "__main__":
    print("=" * 80)
    print("RAG Evaluation - Relative Comparison Mode")
    print("Using RL Judge for Quality Assessment (No Ground Truth)")
    print("=" * 80)

    # Load trained judge
    print("\nLoading trained judge model...")
    judge = ImmigrationJudge(quantize=True, use_lora=False, device="cpu")

    adapter_path = rag_judge_dir / "outputs" / "ep_5" / "checkpoints" / "best_model_lora_adapters"
    judge.model = PeftModel.from_pretrained(judge.model, adapter_path)

    print("✅ Trained judge loaded (93.3% validation accuracy)")
    print("\nNote: Evaluating RAG using ONLY judge's assessment.")
    print("      No ground truth labels - pure relative comparison between configs.\n")

    # Configuration to test
    ks = [3, 8, 12]
    facet_options = [True, False]
    rerank_options = [True, False]

    # Store results
    results = {}
    all_detailed_results = {}

    total_configs = len(ks) * len(facet_options) * len(rerank_options)
    print(f"Testing {total_configs} configurations...")
    print("This may take a while (~20-30 minutes)...\n")

    # Run evaluations
    config_num = 0
    for k in ks:
        for facet in facet_options:
            for rerank in rerank_options:
                config_num += 1
                config_key = f"k={k},facet={facet},rerank={rerank}"

                print(f"\n[{config_num}/{total_configs}] Testing: {config_key}")

                # Evaluate and get detailed results
                approval_rate, detailed = evaluate_config(k, facet, rerank, judge)

                results[config_key] = approval_rate
                all_detailed_results[config_key] = detailed

    # Print final summary
    print("\n" + "=" * 80)
    print("FINAL RESULTS - Judge Approval Rates")
    print("=" * 80)

    # Sort by approval rate
    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)

    print(f"\n{'Rank':<6} {'Configuration':<35} {'Approval Rate':<15} {'Approved/Total'}")
    print("-" * 80)
    for rank, (config, rate) in enumerate(sorted_results, 1):
        total_q = len(all_detailed_results[config])
        approved_q = int(rate * total_q)
        print(f"{rank:<6} {config:<35} {rate:.4f} ({rate:.1%})<8> {approved_q}/{total_q}")

    # Find best configuration
    best_config = sorted_results[0]
    worst_config = sorted_results[-1]

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"🥇 Best Configuration:  {best_config[0]}")
    print(f"   Judge Approval: {best_config[1]:.4f} ({best_config[1]:.1%})")
    print(f"\n📉 Worst Configuration: {worst_config[0]}")
    print(f"   Judge Approval: {worst_config[1]:.4f} ({worst_config[1]:.1%})")
    print(
        f"\n📊 Improvement: {best_config[1] - worst_config[1]:.4f} ({(best_config[1] / worst_config[1] - 1) * 100:.1f}% relative gain)")

    # Save all results
    print("\n" + "=" * 80)
    print("SAVING RESULTS")
    print("=" * 80)
    save_results(results, all_detailed_results)

    print("\n" + "=" * 80)
    print("EVALUATION COMPLETE!")
    print("=" * 80)
    print("\nResults saved to: rag_eval_results/")
    print("\nInterpretation:")
    print("  - Approval rates show relative RAG quality as judged by the model")
    print("  - Higher approval = judge finds more answers factually acceptable")
    print("  - Use for comparing configurations, not absolute correctness claims")
    print("  - Judge validation accuracy: 93.3% on held-out test set")
