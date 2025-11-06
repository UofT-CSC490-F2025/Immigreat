"""
Main training script for RLVR judge.

Usage:
    python scripts/train.py --data_dir ../baseline --output_dir ./outputs

    Or from root:
    python q4_rlvr_judge/scripts/train.py --data_dir baseline --output_dir q4_rlvr_judge/outputs
"""

import sys
from pathlib import Path

script_dir = Path(__file__).resolve().parent
project_dir = script_dir.parent
sys.path.insert(0, str(project_dir))

import argparse
import torch

# Import our modules
from judge.judge_model import ImmigrationJudge
from judge.reward_model import FactualCorrectnessReward
from judge.data_loader import create_dataloaders
from judge.sft_trainer import SimpleSFTTrainer

def parse_args():
    parser = argparse.ArgumentParser(description="Train RLVR judge for immigration Q&A")

    # Data args
    parser.add_argument("--data_dir", type=str, default="baseline",
                        help="Directory containing train.jsonl, val.jsonl, test.jsonl")

    # Model args
    parser.add_argument("--model_name", type=str, default="Qwen/Qwen2.5-1.5B-Instruct",
                        help="Base model to fine-tune")
    parser.add_argument("--quantize", action="store_true",
                        help="Use 4-bit quantization")
    parser.add_argument("--use_lora", action="store_true", default=False,
                        help="Use LoRA adapters (recommended with quantization)")
    parser.add_argument("--lora_r", type=int, default=16,
                        help="LoRA rank")
    parser.add_argument("--lora_alpha", type=int, default=32,
                        help="LoRA alpha")

    # Training args
    parser.add_argument("--learning_rate", type=float, default=2e-5,
                        help="Learning rate")
    parser.add_argument("--num_epochs", type=int, default=3,
                        help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=4,
                        help="Batch size for training")
    parser.add_argument("--max_grad_norm", type=float, default=1.0,
                        help="Gradient clipping threshold")

    # Reward args
    parser.add_argument("--positive_reward", type=float, default=1.0,
                        help="Reward for correct predictions")
    parser.add_argument("--negative_reward", type=float, default=-1.0,
                        help="Reward for incorrect predictions")

    # Logging args
    parser.add_argument("--output_dir", type=str, default="./outputs",
                        help="Output directory for checkpoints and logs")
    parser.add_argument("--logging_steps", type=int, default=10,
                        help="Log every N steps")
    parser.add_argument("--eval_steps", type=int, default=50,
                        help="Evaluate every N steps")
    parser.add_argument("--save_steps", type=int, default=100,
                        help="Save checkpoint every N steps")

    # Device
    parser.add_argument("--device", type=str, default="cuda",
                        help="Device to train on (cuda/cpu)")

    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print("RLVR Judge Training")
    print("=" * 60)
    print(f"\nConfiguration:")
    for arg, value in vars(args).items():
        print(f"  {arg}: {value}")
    print()

    # Set device
    device = args.device if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    # Load data
    print("\nLoading data...")
    train_loader, val_loader, test_loader = create_dataloaders(
        train_path=f"{args.data_dir}/train.jsonl",
        val_path=f"{args.data_dir}/val.jsonl",
        test_path=f"{args.data_dir}/test.jsonl",
        batch_size=args.batch_size
    )

    # Initialize judge model
    print("\nInitializing judge model...")
    judge = ImmigrationJudge(
        model_name=args.model_name,
        quantize=args.quantize,
        use_lora=args.use_lora,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        device=device
    )

    # Initialize reward model
    print("\nInitializing reward model...")
    reward_model = FactualCorrectnessReward(
        positive_reward=args.positive_reward,
        negative_reward=args.negative_reward
    )

    # Initialize trainer
    print("\nInitializing trainer...")
    trainer = SimpleSFTTrainer(
        model=judge.model,
        tokenizer=judge.tokenizer,
        reward_model=reward_model,
        train_loader=train_loader,
        val_loader=val_loader,
        learning_rate=args.learning_rate,
        num_epochs=args.num_epochs,
        max_grad_norm=args.max_grad_norm,
        output_dir=args.output_dir,
        logging_steps=args.logging_steps,
        eval_steps=args.eval_steps,
        save_steps=args.save_steps,
        device=device
    )

    # Train!
    print("\nStarting training...")
    best_accuracy = trainer.train()

    # Final evaluation on test set
    print("\n" + "=" * 60)
    print("Final Test Set Evaluation")
    print("=" * 60)

    # Load best model
    best_checkpoint = Path(args.output_dir) / "checkpoints" / "best_model.pt"
    if best_checkpoint.exists() and not args.quantize:
        print(f"\nLoading best model from {best_checkpoint}")
        try:
            judge.model.load_state_dict(torch.load(best_checkpoint, map_location=device))
            print("Checkpoint loaded!")
        except Exception as e:
            print(f"Warning: Could not load checkpoint: {e}")
            print("Using final model instead.")
    elif args.quantize:
        print("\nNote: Using final model (quantized models use in-place training)")

    # Evaluate on test set
    from judge.data_loader import load_jsonl
    test_data = load_jsonl(f"{args.data_dir}/test.jsonl")

    print(f"\nEvaluating on {len(test_data)} test examples...")
    test_metrics = judge.evaluate(test_data)

    print("\nTest Results:")
    print(f"  Accuracy: {test_metrics['accuracy']:.4f}")
    print(f"  Precision: {test_metrics['precision']:.4f}")
    print(f"  Recall: {test_metrics['recall']:.4f}")
    print(f"  F1 Score: {test_metrics['f1']:.4f}")

    # Save test results
    import json
    results_path = Path(args.output_dir) / "test_results.json"
    with open(results_path, 'w') as f:
        json.dump(test_metrics, f, indent=2)
    print(f"\nTest results saved to {results_path}")

    print("\n" + "=" * 60)
    print("Training Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
