"""
Judge module for RLVR training of LLM-based factual correctness evaluator.
"""

from .reward_model import (
    FactualCorrectnessReward,
    WeightedReward,
    compute_accuracy,
    compute_metrics
)

__all__ = [
    "FactualCorrectnessReward",
    "WeightedReward",
    "compute_accuracy",
    "compute_metrics"
]
