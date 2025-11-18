"""
Reward model for evaluating judge predictions against ground truth labels.

For factual correctness:
- Reward = +1 if judge prediction matches ground truth
- Reward = -1 if judge prediction is incorrect
"""

import torch
from typing import List, Dict


class FactualCorrectnessReward:
    """
    Reward model that scores judge predictions based on accuracy.
    """

    def __init__(self, positive_reward: float = 1.0, negative_reward: float = -1.0):
        """
        Args:
            positive_reward: Reward for correct predictions (default: 1.0)
            negative_reward: Reward for incorrect predictions (default: -1.0)
        """
        self.positive_reward = positive_reward
        self.negative_reward = negative_reward

    def compute_reward(self, predictions: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        """
        Compute rewards for a batch of predictions.

        Args:
            predictions: Binary predictions from judge (0 or 1), shape: (batch_size,)
            labels: Ground truth labels (0 or 1), shape: (batch_size,)

        Returns:
            rewards: Tensor of rewards, shape: (batch_size,)
        """
        # Check if predictions match labels
        correct = (predictions == labels).float()

        # Assign rewards: +1 for correct, -1 for incorrect
        rewards = correct * self.positive_reward + (1 - correct) * self.negative_reward

        return rewards

    def compute_reward_from_logits(self, logits: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        """
        Compute rewards from model logits (before argmax).

        Args:
            logits: Model output logits, shape: (batch_size, num_classes)
            labels: Ground truth labels (0 or 1), shape: (batch_size,)

        Returns:
            rewards: Tensor of rewards, shape: (batch_size,)
        """
        # Get predictions from logits
        predictions = torch.argmax(logits, dim=-1)

        return self.compute_reward(predictions, labels)

    def __call__(self, predictions: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        """
        Convenience method for calling compute_reward.
        """
        return self.compute_reward(predictions, labels)


class WeightedReward(FactualCorrectnessReward):
    """
    Weighted reward model for handling class imbalance.

    Useful if your dataset has more correct (1) than incorrect (0) examples,
    or vice versa.
    """

    def __init__(self,
                 positive_reward: float = 1.0,
                 negative_reward: float = -1.0,
                 class_weights: Dict[int, float] = None):
        """
        Args:
            positive_reward: Base reward for correct predictions
            negative_reward: Base reward for incorrect predictions
            class_weights: Optional dict mapping class labels to importance weights
                          e.g., {0: 1.5, 1: 1.0} to weight class 0 more heavily
        """
        super().__init__(positive_reward, negative_reward)
        self.class_weights = class_weights or {0: 1.0, 1: 1.0}

    def compute_reward(self, predictions: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        """
        Compute weighted rewards based on class importance.
        """
        # Get base rewards
        base_rewards = super().compute_reward(predictions, labels)

        # Apply class weights
        weights = torch.tensor([self.class_weights[int(label.item())]
                                for label in labels],
                               device=labels.device)

        weighted_rewards = base_rewards * weights

        return weighted_rewards


def compute_accuracy(predictions: torch.Tensor, labels: torch.Tensor) -> float:
    """
    Helper function to compute accuracy metric.

    Args:
        predictions: Binary predictions (0 or 1)
        labels: Ground truth labels (0 or 1)

    Returns:
        accuracy: Float between 0 and 1
    """
    correct = (predictions == labels).float().sum()
    total = len(labels)
    return (correct / total).item()


def compute_metrics(predictions: torch.Tensor, labels: torch.Tensor) -> Dict[str, float]:
    """
    Compute comprehensive evaluation metrics.

    Args:
        predictions: Binary predictions (0 or 1)
        labels: Ground truth labels (0 or 1)

    Returns:
        Dictionary with accuracy, precision, recall, f1
    """
    predictions = predictions.cpu()
    labels = labels.cpu()

    # True positives, false positives, etc.
    tp = ((predictions == 1) & (labels == 1)).sum().item()
    fp = ((predictions == 1) & (labels == 0)).sum().item()
    tn = ((predictions == 0) & (labels == 0)).sum().item()
    fn = ((predictions == 0) & (labels == 1)).sum().item()

    accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn
    }


if __name__ == "__main__":
    # Test the reward model
    print("Testing FactualCorrectnessReward...")

    reward_model = FactualCorrectnessReward()

    # Example: 4 predictions, 4 labels
    predictions = torch.tensor([1, 0, 1, 0])
    labels = torch.tensor([1, 0, 0, 0])  # First and second correct, third wrong, fourth correct

    rewards = reward_model(predictions, labels)
    print(f"Predictions: {predictions}")
    print(f"Labels: {labels}")
    print(f"Rewards: {rewards}")
    print(f"Expected: [1.0, 1.0, -1.0, 1.0]")

    # Test metrics
    metrics = compute_metrics(predictions, labels)
    print(f"\nMetrics: {metrics}")
    print(f"Accuracy: {metrics['accuracy']:.2%}")
