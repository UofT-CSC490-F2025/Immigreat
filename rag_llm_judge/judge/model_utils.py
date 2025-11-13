import torch
import logging
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import get_peft_model, LoraConfig, TaskType

logger = logging.getLogger(__name__)

def load_tokenizer(model_name):
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.padding_side = "right"
    tokenizer.truncation_side = "right"
    return tokenizer

def load_reward_model(model_name, use_lora=False, lora_config=None, quantize=False):
    if quantize:
        bnb_config = BitsAndBytesConfig(load_in_4bit=True)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            num_labels=1,
            quantization_config=bnb_config,
            device_map="auto"
        )
    else:
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            num_labels=1,
            local_files_only=True
        )

    if use_lora:
        if lora_config is None:
            lora_config = LoraConfig(
                r=8,
                lora_alpha=16,
                target_modules=["q_proj", "v_proj"],
                lora_dropout=0.1,
                bias="none",
                task_type=TaskType.SEQ_CLS
            )
        model = get_peft_model(model, lora_config)
        logger.info("Loaded model with LoRA adapters")

    return model

def freeze_transformer_layers(model, num_unfrozen=2):
    """Freezes all layers except the last `num_unfrozen`."""
    # Assumes Hugging Face-style model with encoder layers
    encoder_layers = model.base_model.encoder.layer
    total_layers = len(encoder_layers)

    for i, layer in enumerate(encoder_layers):
        if i < total_layers - num_unfrozen:
            for param in layer.parameters():
                param.requires_grad = False

    logger.info(f"Froze all but the last {num_unfrozen} transformer layers.")

def print_trainable_parameters(model):
    """Log total and trainable parameter counts efficiently.

    Why it's important: Called during training setup; using generator expressions lets PyTorch
    provide sizes while Python does minimal work, reducing overhead for large models.
    """
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    pct = (100 * trainable / total) if total else 0.0
    logger.info(f"Trainable params: {trainable} / {total} ({pct:.2f}%)")
