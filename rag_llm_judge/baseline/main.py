# main.py (optional)
from make_datasets import split_dataset
from classifier_logreg import run_logreg
from classifier_llm import run_llm_classifier
from analyze_errors import main as analyze

if __name__ == "__main__":
    split_dataset("baseline/sample_data.jsonl")
    run_logreg("baseline/train.jsonl", "baseline/test.jsonl", "baseline/logreg_preds.jsonl")
    run_llm_classifier("baseline/test.jsonl", "baseline/llm_preds.jsonl")
    analyze("baseline/llm_preds.jsonl", "baseline/logreg_preds.jsonl")

# Run with: python baseline/main.py at rag_llm_judge directory
