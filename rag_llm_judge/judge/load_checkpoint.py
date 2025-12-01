"""
Helper function to load judge checkpoints correctly.

Use this in your eval_rag_k.py instead of manual loading.
"""

import torch
from pathlib import Path
import json
from judge.judge_model import ImmigrationJudge


def load_trained_judge(checkpoint_dir: str, quantize: bool = True, device: str = "cuda"):
    """
    Load a trained judge model with proper checkpoint handling.

    Args:
        checkpoint_dir: Path to outputs directory (e.g., "outputs/baseline")
        quantize: Whether to use quantization
        device: Device to load on

    Returns:
        ImmigrationJudge instance with trained weights loaded
    """
    checkpoint_dir = Path(checkpoint_dir)

    # Check for LoRA adapters (preferred for quantized models)
    best_lora = checkpoint_dir / "checkpoints" / "best_model_lora_adapters"
    best_json = checkpoint_dir / "checkpoints" / "best_model.json"
    best_pt = checkpoint_dir / "checkpoints" / "best_model.pt"

    print(f"Loading judge from: {checkpoint_dir}")

    # Method 1: LoRA adapters exist (works with quantization)
    if best_lora.exists():
        print("  → Found LoRA adapters")
        from peft import PeftModel

        # Load base model
        judge = ImmigrationJudge(
            quantize=quantize,
            use_lora=False,  # Don't init LoRA, we'll load it
            device=device
        )

        # Load LoRA adapters on top
        judge.model = PeftModel.from_pretrained(judge.model, str(best_lora))
        print("  ✅ LoRA adapters loaded successfully!")
        return judge

    # Method 2: Check JSON metadata
    elif best_json.exists():
        print("  → Found checkpoint metadata")
        with open(best_json) as f:
            metadata = json.load(f)

        if metadata.get("type") == "lora_adapters":
            adapter_path = metadata.get("path")
            from peft import PeftModel

            judge = ImmigrationJudge(
                quantize=quantize,
                use_lora=False,
                device=device
            )
            judge.model = PeftModel.from_pretrained(judge.model, adapter_path)
            print(f"  ✅ Loaded from: {adapter_path}")
            return judge

    # Method 3: Try regular checkpoint (only works without quantization)
    elif best_pt.exists():
        print("  → Found .pt checkpoint")

        if quantize:
            print("  ⚠️  WARNING: Can't load .pt checkpoint with quantization!")
            print("     Using base model. For trained model, retrain without --quantize")
            judge = ImmigrationJudge(quantize=True, use_lora=True, device=device)
            return judge
        else:
            judge = ImmigrationJudge(
                quantize=False,
                use_lora=True,
                device=device
            )

            try:
                state_dict = torch.load(best_pt, map_location=device)
                judge.model.load_state_dict(state_dict)
                print("  ✅ Checkpoint loaded successfully!")
                return judge
            except Exception as e:
                print(f"  ❌ Failed to load checkpoint: {e}")
                print("     Using base model")
                return judge

    # Method 4: No checkpoint found
    else:
        print("  ⚠️  No checkpoint found")
        print(f"     Looked for:")
        print(f"       - {best_lora}")
        print(f"       - {best_pt}")
        print("     Using base model (untrained)")
        judge = ImmigrationJudge(quantize=quantize, use_lora=True, device=device)
        return judge


# Example usage
if __name__ == "__main__":
    # Simple usage:
    judge = load_trained_judge("outputs/baseline", quantize=True)

    # Test it:
    pred, resp = judge.judge_single(
        "Is IELTS required?",
        "Yes, language test required"
    )
    print(f"\nTest prediction: {pred}")
    print(f"Response: {resp}")
