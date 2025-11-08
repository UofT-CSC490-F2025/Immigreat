"""
Analyze and compare results from multiple training runs.

Usage:
    python scripts/analyze_results.py --results_dir outputs/
"""

import argparse
import json
from pathlib import Path
import sys


def load_results(results_dir):
    """Load all test_results.json files from subdirectories."""
    results_dir = Path(results_dir)
    results = {}

    for test_file in results_dir.glob("*/test_results.json"):
        run_name = test_file.parent.name
        with open(test_file) as f:
            results[run_name] = json.load(f)

    return results


def load_training_logs(results_dir):
    """Load training logs."""
    results_dir = Path(results_dir)
    logs = {}

    for log_file in results_dir.glob("*/logs/training_log.json"):
        run_name = log_file.parent.parent.name
        with open(log_file) as f:
            logs[run_name] = json.load(f)

    return logs


def print_comparison_table(results):
    """Print comparison table of all runs."""
    if not results:
        print("No results found!")
        return

    # Header
    print("\n" + "=" * 80)
    print("Test Results Comparison")
    print("=" * 80)
    print(f"{'Run Name':<30} {'Accuracy':<12} {'Precision':<12} {'Recall':<12} {'F1':<12}")
    print("-" * 80)

    # Sort by accuracy
    sorted_results = sorted(results.items(), key=lambda x: x[1]['accuracy'], reverse=True)

    # Rows
    for run_name, metrics in sorted_results:
        print(f"{run_name:<30} "
              f"{metrics['accuracy']:<12.4f} "
              f"{metrics['precision']:<12.4f} "
              f"{metrics['recall']:<12.4f} "
              f"{metrics['f1']:<12.4f}")

    print("=" * 80)


def print_best_worst(results):
    """Print best and worst performing runs."""
    if not results:
        return

    sorted_by_acc = sorted(results.items(), key=lambda x: x[1]['accuracy'], reverse=True)
    best = sorted_by_acc[0]
    worst = sorted_by_acc[-1]

    print("\n" + "=" * 80)
    print("Best and Worst Runs")
    print("=" * 80)

    print(f"\n🥇 Best Run: {best[0]}")
    print(f"   Accuracy: {best[1]['accuracy']:.4f}")
    print(f"   F1 Score: {best[1]['f1']:.4f}")
    print(f"   Precision: {best[1]['precision']:.4f}")
    print(f"   Recall: {best[1]['recall']:.4f}")

    print(f"\n📉 Worst Run: {worst[0]}")
    print(f"   Accuracy: {worst[1]['accuracy']:.4f}")
    print(f"   F1 Score: {worst[1]['f1']:.4f}")
    print(f"   Precision: {worst[1]['precision']:.4f}")
    print(f"   Recall: {worst[1]['recall']:.4f}")

    print("\n" + "=" * 80)


def analyze_ablation_groups(results):
    """Analyze results grouped by ablation type."""
    groups = {}

    for run_name, metrics in results.items():
        # Parse ablation type from run name
        if 'lr' in run_name.lower():
            group = 'Learning Rate'
        elif 'bs' in run_name.lower():
            group = 'Batch Size'
        elif 'ep' in run_name.lower():
            group = 'Epochs'
        elif 'reward' in run_name.lower():
            group = 'Reward Scale'
        else:
            group = 'Other'

        if group not in groups:
            groups[group] = []
        groups[group].append((run_name, metrics))

    print("\n" + "=" * 80)
    print("Ablation Group Analysis")
    print("=" * 80)

    for group_name, group_results in sorted(groups.items()):
        print(f"\n{group_name}:")
        print("-" * 40)

        sorted_group = sorted(group_results, key=lambda x: x[1]['accuracy'], reverse=True)
        for run_name, metrics in sorted_group:
            print(f"  {run_name:<30} Acc: {metrics['accuracy']:.4f}  F1: {metrics['f1']:.4f}")


def print_training_summary(logs):
    """Print training summary from logs."""
    if not logs:
        return

    print("\n" + "=" * 80)
    print("Training Summary")
    print("=" * 80)

    for run_name, log_entries in logs.items():
        if not log_entries:
            continue

        print(f"\n{run_name}:")

        # Get final metrics
        final = log_entries[-1]

        print(f"  Total steps: {final['step']}")
        print(f"  Final loss: {final['loss']:.4f}")
        print(f"  Final accuracy: {final['accuracy']:.4f}")
        print(f"  Final reward: {final['reward_mean']:.4f}")

        # Calculate average metrics
        avg_loss = sum(e['loss'] for e in log_entries) / len(log_entries)
        avg_acc = sum(e['accuracy'] for e in log_entries) / len(log_entries)

        print(f"  Average loss: {avg_loss:.4f}")
        print(f"  Average accuracy: {avg_acc:.4f}")


def export_latex_table(results, output_file="results_table.tex"):
    """Export results as LaTeX table for report."""
    with open(output_file, 'w') as f:
        f.write("\\begin{table}[h]\n")
        f.write("\\centering\n")
        f.write("\\begin{tabular}{lcccc}\n")
        f.write("\\hline\n")
        f.write("Run & Accuracy & Precision & Recall & F1 \\\\\n")
        f.write("\\hline\n")

        sorted_results = sorted(results.items(), key=lambda x: x[1]['accuracy'], reverse=True)
        for run_name, metrics in sorted_results:
            f.write(f"{run_name.replace('_', ' ')} & "
                    f"{metrics['accuracy']:.3f} & "
                    f"{metrics['precision']:.3f} & "
                    f"{metrics['recall']:.3f} & "
                    f"{metrics['f1']:.3f} \\\\\n")

        f.write("\\hline\n")
        f.write("\\end{tabular}\n")
        f.write("\\caption{Ablation study results comparing different hyperparameter settings.}\n")
        f.write("\\label{tab:ablation_results}\n")
        f.write("\\end{table}\n")

    print(f"\n✓ LaTeX table exported to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Analyze training results")
    parser.add_argument("--results_dir", type=str, default="outputs/",
                        help="Directory containing training output folders")
    parser.add_argument("--export_latex", action="store_true",
                        help="Export results as LaTeX table")

    args = parser.parse_args()

    # Load results
    print(f"Loading results from {args.results_dir}...")
    results = load_results(args.results_dir)
    logs = load_training_logs(args.results_dir)

    if not results:
        print(f"No results found in {args.results_dir}")
        print("Make sure you have run training and have test_results.json files!")
        return

    print(f"Found {len(results)} runs")

    # Print analyses
    print_comparison_table(results)
    print_best_worst(results)
    analyze_ablation_groups(results)

    if logs:
        print_training_summary(logs)

    # Export LaTeX if requested
    if args.export_latex:
        export_latex_table(results)

    print("\n" + "=" * 80)
    print("Analysis complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
