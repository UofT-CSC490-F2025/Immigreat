"""
Enhanced analysis script with visualization support.

Usage:
    python scripts/analyze_results_enhanced.py --results_dir outputs/ --make_plots
"""

import argparse
import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np


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

    print("\n" + "=" * 80)
    print("Test Results Comparison")
    print("=" * 80)
    print(f"{'Run Name':<30} {'Accuracy':<12} {'Precision':<12} {'Recall':<12} {'F1':<12}")
    print("-" * 80)

    sorted_results = sorted(results.items(), key=lambda x: x[1]['accuracy'], reverse=True)

    for run_name, metrics in sorted_results:
        print(f"{run_name:<30} "
              f"{metrics['accuracy']:<12.4f} "
              f"{metrics['precision']:<12.4f} "
              f"{metrics['recall']:<12.4f} "
              f"{metrics['f1']:<12.4f}")

    print("=" * 80)


def analyze_ablation_groups(results):
    """Analyze results grouped by ablation type."""
    groups = {
        'Learning Rate': [],
        'Epochs': [],
        'LoRA Rank': [],
        'Batch Size': [],
        'Other': []
    }

    for run_name, metrics in results.items():
        # Parse ablation type from run name
        if 'lr_' in run_name.lower():
            groups['Learning Rate'].append((run_name, metrics))
        elif 'ep_' in run_name.lower():
            groups['Epochs'].append((run_name, metrics))
        elif 'lora_r' in run_name.lower():
            groups['LoRA Rank'].append((run_name, metrics))
        elif 'bs_' in run_name.lower():
            groups['Batch Size'].append((run_name, metrics))
        else:
            groups['Other'].append((run_name, metrics))

    print("\n" + "=" * 80)
    print("Ablation Group Analysis")
    print("=" * 80)

    for group_name, group_results in groups.items():
        if not group_results:
            continue

        print(f"\n{group_name}:")
        print("-" * 40)

        sorted_group = sorted(group_results, key=lambda x: x[1]['accuracy'], reverse=True)
        for run_name, metrics in sorted_group:
            print(f"  {run_name:<30} Acc: {metrics['accuracy']:.4f}  F1: {metrics['f1']:.4f}")

    return groups


def plot_ablation_comparison(results, output_dir="plots"):
    """Create comparison plots for ablation studies."""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    # Group results
    groups = {
        'Learning Rate': {},
        'Epochs': {},
        'LoRA Rank': {}
    }

    for run_name, metrics in results.items():
        if 'lr_' in run_name.lower():
            # Extract learning rate value
            lr_val = run_name.lower().split('lr_')[1].split('_')[0]
            groups['Learning Rate'][lr_val] = metrics
        elif 'ep_' in run_name.lower():
            # Extract epoch value
            ep_val = run_name.lower().split('ep_')[1].split('_')[0]
            groups['Epochs'][ep_val] = metrics
        elif 'lora_r' in run_name.lower():
            # Extract LoRA rank value
            r_val = run_name.lower().split('lora_r')[1].split('_')[0]
            groups['LoRA Rank'][r_val] = metrics

    # Create plots for each ablation type
    for group_name, group_data in groups.items():
        if not group_data:
            continue

        # Sort by parameter value
        sorted_items = sorted(group_data.items())
        params = [item[0] for item in sorted_items]
        accuracies = [item[1]['accuracy'] for item in sorted_items]
        f1_scores = [item[1]['f1'] for item in sorted_items]

        # Create plot
        fig, ax = plt.subplots(figsize=(10, 6))

        x = np.arange(len(params))
        width = 0.35

        ax.bar(x - width / 2, accuracies, width, label='Accuracy', alpha=0.8)
        ax.bar(x + width / 2, f1_scores, width, label='F1 Score', alpha=0.8)

        ax.set_xlabel(group_name, fontsize=12)
        ax.set_ylabel('Score', fontsize=12)
        ax.set_title(f'Ablation Study: {group_name}', fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(params)
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        ax.set_ylim([0, 1])

        # Add value labels on bars
        for i, (acc, f1) in enumerate(zip(accuracies, f1_scores)):
            ax.text(i - width / 2, acc + 0.02, f'{acc:.3f}', ha='center', fontsize=9)
            ax.text(i + width / 2, f1 + 0.02, f'{f1:.3f}', ha='center', fontsize=9)

        plt.tight_layout()

        # Save plot
        plot_name = group_name.lower().replace(' ', '_')
        plot_path = output_dir / f'ablation_{plot_name}.png'
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✓ Saved plot: {plot_path}")


def plot_overall_comparison(results, output_dir="plots"):
    """Create overall comparison bar chart."""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    # Sort by accuracy
    sorted_results = sorted(results.items(), key=lambda x: x[1]['accuracy'], reverse=True)

    # Take top 10 if more than 10 runs
    if len(sorted_results) > 10:
        sorted_results = sorted_results[:10]

    run_names = [item[0] for item in sorted_results]
    accuracies = [item[1]['accuracy'] for item in sorted_results]

    # Create plot
    fig, ax = plt.subplots(figsize=(12, 6))

    colors = ['#2ecc71' if acc >= 0.9 else '#3498db' if acc >= 0.8 else '#e74c3c'
              for acc in accuracies]

    bars = ax.barh(run_names, accuracies, color=colors, alpha=0.8)

    ax.set_xlabel('Accuracy', fontsize=12)
    ax.set_title('Overall Performance Comparison (Top 10 Runs)', fontsize=14, fontweight='bold')
    ax.set_xlim([0, 1])
    ax.grid(axis='x', alpha=0.3)

    # Add value labels
    for i, (bar, acc) in enumerate(zip(bars, accuracies)):
        ax.text(acc + 0.01, i, f'{acc:.4f}', va='center', fontsize=9)

    plt.tight_layout()

    plot_path = output_dir / 'overall_comparison.png'
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"✓ Saved plot: {plot_path}")


def plot_metrics_heatmap(results, output_dir="plots"):
    """Create heatmap of all metrics across runs."""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    # Prepare data
    run_names = list(results.keys())
    metrics_names = ['Accuracy', 'Precision', 'Recall', 'F1']

    data = np.array([[results[run]['accuracy'],
                      results[run]['precision'],
                      results[run]['recall'],
                      results[run]['f1']]
                     for run in run_names])

    # Create heatmap
    fig, ax = plt.subplots(figsize=(8, len(run_names) * 0.5))

    im = ax.imshow(data, cmap='RdYlGn', aspect='auto', vmin=0, vmax=1)

    # Set ticks
    ax.set_xticks(np.arange(len(metrics_names)))
    ax.set_yticks(np.arange(len(run_names)))
    ax.set_xticklabels(metrics_names)
    ax.set_yticklabels(run_names)

    # Rotate x labels
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

    # Add values
    for i in range(len(run_names)):
        for j in range(len(metrics_names)):
            text = ax.text(j, i, f'{data[i, j]:.3f}',
                           ha="center", va="center", color="black", fontsize=8)

    ax.set_title("Metrics Heatmap Across All Runs", fontsize=14, fontweight='bold')
    fig.colorbar(im, ax=ax, label='Score')

    plt.tight_layout()

    plot_path = output_dir / 'metrics_heatmap.png'
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"✓ Saved plot: {plot_path}")


def export_latex_table(results, output_file="results_table.tex"):
    """Export results as LaTeX table."""
    with open(output_file, 'w') as f:
        f.write("\\begin{table}[h]\n")
        f.write("\\centering\n")
        f.write("\\caption{Ablation study results}\n")
        f.write("\\begin{tabular}{lcccc}\n")
        f.write("\\toprule\n")
        f.write("Configuration & Accuracy & Precision & Recall & F1 \\\\\n")
        f.write("\\midrule\n")

        sorted_results = sorted(results.items(), key=lambda x: x[1]['accuracy'], reverse=True)
        for run_name, metrics in sorted_results:
            clean_name = run_name.replace('_', '\\_')
            f.write(f"{clean_name} & "
                    f"{metrics['accuracy']:.3f} & "
                    f"{metrics['precision']:.3f} & "
                    f"{metrics['recall']:.3f} & "
                    f"{metrics['f1']:.3f} \\\\\n")

        f.write("\\bottomrule\n")
        f.write("\\end{tabular}\n")
        f.write("\\label{tab:ablation_results}\n")
        f.write("\\end{table}\n")

    print(f"\n✓ LaTeX table exported to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Analyze training results with visualizations")
    parser.add_argument("--results_dir", type=str, default="outputs/",
                        help="Directory containing training output folders")
    parser.add_argument("--make_plots", action="store_true",
                        help="Generate visualization plots")
    parser.add_argument("--export_latex", action="store_true",
                        help="Export results as LaTeX table")
    parser.add_argument("--output_dir", type=str, default="plots/",
                        help="Directory to save plots")

    args = parser.parse_args()

    # Load results
    print(f"Loading results from {args.results_dir}...")
    results = load_results(args.results_dir)

    if not results:
        print(f"No results found in {args.results_dir}")
        print("Make sure you have test_results.json files in subdirectories!")
        return

    print(f"Found {len(results)} runs\n")

    # Print analyses
    print_comparison_table(results)

    groups = analyze_ablation_groups(results)

    # Find best/worst
    sorted_by_acc = sorted(results.items(), key=lambda x: x[1]['accuracy'], reverse=True)
    best = sorted_by_acc[0]
    worst = sorted_by_acc[-1]

    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"\n🥇 Best: {best[0]} → Accuracy: {best[1]['accuracy']:.4f}, F1: {best[1]['f1']:.4f}")
    print(f"📉 Worst: {worst[0]} → Accuracy: {worst[1]['accuracy']:.4f}, F1: {worst[1]['f1']:.4f}")
    print(
        f"📊 Range: {best[1]['accuracy'] - worst[1]['accuracy']:.4f} ({best[1]['accuracy'] / worst[1]['accuracy'] - 1:.1%} improvement)")

    # Generate plots
    if args.make_plots:
        print("\n" + "=" * 80)
        print("Generating Plots")
        print("=" * 80)

        try:
            plot_ablation_comparison(results, args.output_dir)
            plot_overall_comparison(results, args.output_dir)
            plot_metrics_heatmap(results, args.output_dir)

            print(f"\n✓ All plots saved to {args.output_dir}/")
        except Exception as e:
            print(f"❌ Error creating plots: {e}")
            print("Make sure matplotlib is installed: pip install matplotlib")

    # Export LaTeX
    if args.export_latex:
        export_latex_table(results)

    print("\n" + "=" * 80)
    print("Analysis Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
