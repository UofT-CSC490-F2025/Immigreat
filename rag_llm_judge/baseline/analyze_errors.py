# analyze_errors.py
import json
from collections import Counter

def load_preds(path):
    return [json.loads(line) for line in open(path)]

def print_stats(data, method_key):
    correct = sum(1 for ex in data if ex[method_key] == ex['label'])
    total = len(data)
    acc = correct / total
    print(f"{method_key} Accuracy: {acc:.2%} ({correct}/{total})")

def show_examples(data, method_key, n=5):
    print(f"\nExamples where {method_key} was wrong:")
    wrong = [ex for ex in data if ex[method_key] != ex['label']]
    for ex in wrong[:n]:
        print(f"\nQ: {ex['question']}\nA: {ex['answer']}\nLabel: {ex['label']} | Predicted: {ex[method_key]}")

def main(llm_file, logreg_file):
    llm_data = load_preds(llm_file)
    logreg_data = load_preds(logreg_file)

    print_stats(llm_data, 'llm_prediction')
    print_stats(logreg_data, 'logreg_prediction')

    show_examples(llm_data, 'llm_prediction')
    show_examples(logreg_data, 'logreg_prediction')
