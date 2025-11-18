import torch
import torch.nn.functional as F

def dpo_loss(preferred_scores, rejected_scores, beta=0.1):
    """
    preferred_scores: Tensor of shape (batch_size,)
    rejected_scores: Tensor of shape (batch_size,)
    """
    logits_diff = preferred_scores - rejected_scores
    loss = -F.logsigmoid(beta * logits_diff).mean()
    return loss
