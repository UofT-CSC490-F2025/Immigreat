# Q4: Training an RLVR Judge for Immigration Q&A

This directory contains the implementation of an RLVR (Reinforcement Learning with Verifiable Rewards) system to train a judge model that evaluates the factual correctness of immigration-related answers.

## Overview

**Metric**: Factual Correctness (binary classification: 0=incorrect, 1=correct)

**Base Model**: Qwen/Qwen2.5-1.5B-Instruct (optimized for 8GB VRAM)

**RL Algorithm**: Reward-Weighted Supervised Learning
- Simple yet effective approach to RLVR
- Uses verifiable rewards (correct/incorrect predictions) to weight training loss
- Emphasizes learning from correct predictions while penalizing mistakes

## Project Structure

```
q4_rlvr_judge/
├── README.md                 # This file
├── requirements.txt          # Python dependencies
│
├── judge/                    # Core implementation
│   ├── __init__.py
│   ├── judge_model.py       # LLM judge wrapper (Qwen model)
│   ├── reward_model.py      # Reward computation (factual correctness)
│   ├── data_loader.py       # Data loading utilities
│   └── rl_trainer.py        # RLVR training loop
│
├── scripts/
│   └── train.py             # Main training script
│
└── outputs/                 # Generated during training
    ├── checkpoints/         # Model checkpoints
    ├── logs/               # Training logs
    └── test_results.json   # Final test metrics
```

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Prepare Data

Ensure you have the split data from Q3:
```
../baseline/
├── train.jsonl
├── val.jsonl
└── test.jsonl
```

Each line should be: `{"question": "...", "answer": "...", "label": 0 or 1}`

## Training

### Basic Training

```bash
python scripts/train.py
```

### With Custom Settings

```bash
python scripts/train.py \
    --data_dir ../baseline \
    --model_name Qwen/Qwen2.5-1.5B-Instruct \
    --learning_rate 2e-5 \
    --num_epochs 3 \
    --batch_size 4 \
    --output_dir ./outputs \
    --quantize  # Use 4-bit quantization to save memory
```

### Reference Settings for Hardware (3070Ti 8GB)

```bash
python scripts/train.py \
    --quantize \
    --batch_size 2 \
    --learning_rate 1e-5 \
    --num_epochs 5
```

## How It Works

### 1. **Judge Model**
- Takes a question + answer pair as input
- Outputs a judgment: "YES" (correct) or "NO" (incorrect)
- Uses instruction-tuned Qwen model with specialized prompting

### 2. **Reward Model**
- Compares judge's prediction with ground truth label
- Reward = +1 for correct predictions
- Reward = -1 for incorrect predictions

### 3. **RLVR Training**
- Forward pass: Judge predicts correctness
- Reward computation: Compare with ground truth
- Loss weighting: Higher weight for high-reward samples
- Backward pass: Update model to maximize rewards

### Training Flow

```
Input: (question, answer, label)
    ↓
Judge Model: Predict 0 or 1
    ↓
Reward Model: Compute reward based on correctness
    ↓
Weighted Loss: weight = f(reward)
    ↓
Backpropagation: Update judge to maximize rewards
```

## Ablation Studies

To run ablations, modify hyperparameters:

```bash
# Ablation 1: Learning Rate
python scripts/train.py --learning_rate 1e-5
python scripts/train.py --learning_rate 2e-5
python scripts/train.py --learning_rate 5e-5

# Ablation 2: Batch Size
python scripts/train.py --batch_size 2
python scripts/train.py --batch_size 4
python scripts/train.py --batch_size 8

# Ablation 3: Reward Scale
python scripts/train.py --positive_reward 1.0 --negative_reward -1.0
python scripts/train.py --positive_reward 2.0 --negative_reward -0.5
```

## Outputs

After training, check:

1. **Checkpoints**: `outputs/checkpoints/best_model.pt`
2. **Training Logs**: `outputs/logs/training_log.json`
3. **Test Results**: `outputs/test_results.json`
4. **TensorBoard Logs**: `outputs/tensorboard/`

### Viewing TensorBoard

To visualize training metrics in real-time:

```bash
# In a separate terminal
tensorboard --logdir outputs/tensorboard

# Then open your browser to: http://localhost:6006
```

You'll see interactive plots for:
- Training loss over time
- Validation accuracy/F1/precision/recall
- Learning rate schedule
- Epoch-wise metrics

### TensorBoard Screenshot for Report

1. Run TensorBoard
2. Take screenshots of the loss and accuracy curves
3. Include in your report's "Training Logs & Metrics" section

## Expected Results

On the 200-sample immigration dataset:
- **Baseline** (untrained): ~50-60% accuracy (random guessing)
- **After RLVR training**: 75-85% accuracy (depends on data quality)

## Next Steps

1. **Try GRPO**: Implement full GRPO algorithm for comparison
2. **Data augmentation**: Generate more training examples
3. **Ensemble**: Combine multiple judge models
4. **Error analysis**: Analyze common failure patterns

## Troubleshooting

### Out of Memory (OOM)
```bash
# Use quantization
python scripts/train.py --quantize

# Reduce batch size
python scripts/train.py --batch_size 1
```

### Slow Training
```bash
# Reduce eval frequency
python scripts/train.py --eval_steps 100 --save_steps 200
```

## References

- Shao et al. (2024): "DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models" (GRPO algorithm)
- Qwen Team: "Qwen2.5: A Party of Foundation Models"
