"""
Simple and working supervised fine-tuning trainer for judge model.
Uses standard causal language modeling approach.
"""

import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.utils.tensorboard import SummaryWriter
from transformers import get_linear_schedule_with_warmup, DataCollatorForLanguageModeling
from typing import Dict, List
from tqdm import tqdm
import json
from pathlib import Path
import numpy as np


class SimpleSFTTrainer:
    """
    Simple supervised fine-tuning trainer.
    Trains the model to output YES or NO given a prompt.
    """

    def __init__(
            self,
            model,
            tokenizer,
            reward_model,
            train_loader,
            val_loader,
            learning_rate: float = 2e-5,
            num_epochs: int = 3,
            max_grad_norm: float = 1.0,
            output_dir: str = "./outputs",
            logging_steps: int = 10,
            eval_steps: int = 50,
            save_steps: int = 100,
            device: str = "cuda" if torch.cuda.is_available() else "cpu"
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.tokenizer.padding_side = 'left'  # Important for decoder models
        self.reward_model = reward_model
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.learning_rate = learning_rate
        self.num_epochs = num_epochs
        self.max_grad_norm = max_grad_norm
        self.output_dir = Path(output_dir)
        self.logging_steps = logging_steps
        self.eval_steps = eval_steps
        self.save_steps = save_steps
        self.device = device

        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "checkpoints").mkdir(exist_ok=True)
        (self.output_dir / "logs").mkdir(exist_ok=True)

        # Setup optimizer
        self.optimizer = AdamW(
            [p for p in self.model.parameters() if p.requires_grad],
            lr=learning_rate
        )

        total_steps = len(train_loader) * num_epochs
        self.scheduler = get_linear_schedule_with_warmup(
            self.optimizer,
            num_warmup_steps=int(0.1 * total_steps),
            num_training_steps=total_steps
        )

        self.global_step = 0
        self.training_logs = []

        # Initialize TensorBoard
        self.writer = SummaryWriter(log_dir=str(self.output_dir / "tensorboard"))
        print(f"TensorBoard logging to: {self.output_dir / 'tensorboard'}")

        print(f"Simple SFT Trainer initialized:")
        print(f"  - Learning rate: {learning_rate}")
        print(f"  - Epochs: {num_epochs}")
        print(f"  - Total steps: {total_steps}")
        print(f"  - Device: {device}")

    def create_prompt(self, question: str, answer: str) -> str:
        """Create evaluation prompt."""
        prompt = f"""You are an expert immigration judge. Evaluate whether the following answer to an immigration question is factually correct.

Question: {question}

Answer: {answer}

Is this answer factually correct? Respond with ONLY "YES" or "NO".

Judgment:"""
        return prompt

    def train_step(self, batch: Dict) -> Dict[str, float]:
        """Single training step."""
        self.model.train()

        questions = batch['questions']
        answers = batch['answers']
        labels = batch['labels'].to(self.device)

        total_loss = 0.0
        batch_size = len(questions)

        # Process each example individually (simpler and more reliable)
        for q, a, label in zip(questions, answers, labels.tolist()):
            prompt = self.create_prompt(q, a)
            response = " YES" if label == 1 else " NO"
            full_text = prompt + response

            # Tokenize
            encodings = self.tokenizer(
                full_text,
                return_tensors="pt",
                truncation=True,
                max_length=512
            ).to(self.device)

            # Get input_ids
            input_ids = encodings['input_ids']

            # Create labels - shift by one for causal LM
            labels_for_loss = input_ids.clone()

            # Mask prompt tokens (only train on response)
            prompt_ids = self.tokenizer(prompt, add_special_tokens=False)['input_ids']
            prompt_len = len(prompt_ids)
            labels_for_loss[0, :prompt_len] = -100

            # Forward pass
            outputs = self.model(
                input_ids=input_ids,
                labels=labels_for_loss
            )

            loss = outputs.loss

            if not torch.isnan(loss):
                total_loss += loss.item()
                loss.backward()

        # Average loss
        avg_loss = total_loss / batch_size

        # Gradient step
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.max_grad_norm)
        self.optimizer.step()
        self.scheduler.step()
        self.optimizer.zero_grad()

        return {
            'loss': avg_loss,
            'reward_mean': 0.0,  # Will be computed in eval
            'reward_std': 0.0,
            'accuracy': 0.0,  # Will be computed in eval
            'lr': self.scheduler.get_last_lr()[0]
        }

    @torch.no_grad()
    def evaluate(self) -> Dict[str, float]:
        """Evaluate on validation set."""
        self.model.eval()

        all_predictions = []
        all_labels = []
        total_reward = 0.0

        for batch in self.val_loader:
            questions = batch['questions']
            answers = batch['answers']
            labels = batch['labels'].to(self.device)

            # Generate predictions for each example
            for q, a in zip(questions, answers):
                prompt = self.create_prompt(q, a)

                inputs = self.tokenizer(
                    prompt,
                    return_tensors="pt",
                    truncation=True,
                    max_length=512
                ).to(self.device)

                gen_outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=5,
                    do_sample=False,
                    pad_token_id=self.tokenizer.pad_token_id,
                    eos_token_id=self.tokenizer.eos_token_id
                )

                # Decode
                generated_text = self.tokenizer.decode(
                    gen_outputs[0][inputs['input_ids'].shape[1]:],
                    skip_special_tokens=True
                )

                # Parse prediction
                text_upper = generated_text.strip().upper()
                if "YES" in text_upper[:10]:
                    pred = 1
                elif "NO" in text_upper[:10]:
                    pred = 0
                else:
                    pred = 0  # Default

                all_predictions.append(pred)

            all_labels.extend(labels.cpu().tolist())

        # Convert to tensors
        predictions = torch.tensor(all_predictions)
        labels_tensor = torch.tensor(all_labels)

        # Compute metrics
        from .reward_model import compute_metrics
        metrics = compute_metrics(predictions, labels_tensor)

        # Compute rewards
        rewards = self.reward_model(predictions, labels_tensor)
        metrics['reward_mean'] = rewards.mean().item()

        return metrics

    def train(self):
        """Main training loop."""
        print("\n" + "=" * 50)
        print("Starting Training")
        print("=" * 50 + "\n")

        best_accuracy = 0.0

        for epoch in range(self.num_epochs):
            print(f"\nEpoch {epoch + 1}/{self.num_epochs}")
            print("-" * 50)

            epoch_metrics = {
                'loss': []
            }

            pbar = tqdm(self.train_loader, desc=f"Epoch {epoch + 1}")
            for batch in pbar:
                # Train step
                metrics = self.train_step(batch)

                # Track metrics
                epoch_metrics['loss'].append(metrics['loss'])

                # Log
                if self.global_step % self.logging_steps == 0:
                    log_entry = {
                        'step': self.global_step,
                        'epoch': epoch,
                        **metrics
                    }
                    self.training_logs.append(log_entry)

                    # Log to TensorBoard
                    self.writer.add_scalar('train/loss', metrics['loss'], self.global_step)
                    self.writer.add_scalar('train/learning_rate', metrics['lr'], self.global_step)

                    pbar.set_postfix({
                        'loss': f"{metrics['loss']:.4f}",
                        'lr': f"{metrics['lr']:.2e}"
                    })

                # Evaluate
                if self.global_step % self.eval_steps == 0 and self.global_step > 0:
                    print(f"\n[Step {self.global_step}] Validation:")
                    eval_metrics = self.evaluate()
                    print(f"  Accuracy: {eval_metrics['accuracy']:.4f}")
                    print(f"  F1: {eval_metrics['f1']:.4f}")
                    print(f"  Reward: {eval_metrics['reward_mean']:.4f}")

                    # Log to TensorBoard
                    self.writer.add_scalar('eval/accuracy', eval_metrics['accuracy'], self.global_step)
                    self.writer.add_scalar('eval/f1', eval_metrics['f1'], self.global_step)
                    self.writer.add_scalar('eval/precision', eval_metrics['precision'], self.global_step)
                    self.writer.add_scalar('eval/recall', eval_metrics['recall'], self.global_step)
                    self.writer.add_scalar('eval/reward', eval_metrics['reward_mean'], self.global_step)

                    # Save best model
                    if eval_metrics['accuracy'] > best_accuracy:
                        best_accuracy = eval_metrics['accuracy']
                        self.save_checkpoint("best_model")
                        print(f"  → New best model saved! (acc={best_accuracy:.4f})")

                # Save checkpoint
                if self.global_step % self.save_steps == 0 and self.global_step > 0:
                    self.save_checkpoint(f"checkpoint_step_{self.global_step}")

                self.global_step += 1

            # Epoch summary
            print(f"\nEpoch {epoch + 1} Summary:")
            print(f"  Loss: {np.mean(epoch_metrics['loss']):.4f}")

            # Log epoch metrics to TensorBoard
            self.writer.add_scalar('epoch/loss', np.mean(epoch_metrics['loss']), epoch)

            # End of epoch eval
            print(f"\nEnd of Epoch Validation:")
            eval_metrics = self.evaluate()
            print(f"  Accuracy: {eval_metrics['accuracy']:.4f}")
            print(f"  F1: {eval_metrics['f1']:.4f}")

            # Log to TensorBoard
            self.writer.add_scalar('epoch/accuracy', eval_metrics['accuracy'], epoch)
            self.writer.add_scalar('epoch/f1', eval_metrics['f1'], epoch)

        # Save final model
        self.save_checkpoint("final_model")
        self.save_logs()

        # Close TensorBoard writer
        self.writer.close()
        print(f"\nTensorBoard logs saved to: {self.output_dir / 'tensorboard'}")
        print(f"View with: tensorboard --logdir {self.output_dir / 'tensorboard'}")

        print("\n" + "=" * 50)
        print("Training Complete!")
        print(f"Best Validation Accuracy: {best_accuracy:.4f}")
        print("=" * 50)

        return best_accuracy

    def save_checkpoint(self, name: str):
        """Save model checkpoint."""
        checkpoint_path = self.output_dir / "checkpoints" / f"{name}.pt"
        torch.save(self.model.state_dict(), checkpoint_path)

    def save_logs(self):
        """Save training logs."""
        log_path = self.output_dir / "logs" / "training_log.json"
        with open(log_path, 'w') as f:
            json.dump(self.training_logs, f, indent=2)
        print(f"Logs saved: {log_path}")
