"""
Judge model for evaluating factual correctness of immigration Q&A responses.

Uses Qwen2.5-1.5B-Instruct as base model, fine-tuned with RL to predict
whether an answer is factually correct (label=1) or incorrect (label=0).
"""

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from typing import List, Dict, Tuple, Optional
import re


class ImmigrationJudge:
    """
    LLM-based judge for evaluating factual correctness of immigration answers.
    """

    def __init__(
            self,
            model_name: str = "Qwen/Qwen2.5-1.5B-Instruct",
            quantize: bool = True,
            use_lora: bool = True,
            lora_r: int = 16,
            lora_alpha: int = 32,
            lora_dropout: float = 0.05,
            device: str = "cuda" if torch.cuda.is_available() else "cpu"
    ):
        """
        Initialize the judge model.

        Args:
            model_name: HuggingFace model identifier
            quantize: Whether to use 4-bit quantization (saves memory)
            use_lora: Whether to use LoRA adapters for training
            lora_r: LoRA rank (higher = more parameters but better)
            lora_alpha: LoRA scaling factor
            lora_dropout: Dropout for LoRA layers
            device: Device to load model on
        """
        self.model_name = model_name
        self.device = device
        self.use_lora = use_lora

        print(f"Loading model: {model_name}")
        print(f"Quantization: {quantize}")
        print(f"LoRA: {use_lora}")
        print(f"Device: {device}")

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        # Set padding side to left for decoder-only models
        self.tokenizer.padding_side = 'left'

        # Configure quantization if enabled
        if quantize and device == "cuda":
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=True
            )

            # Prepare model for training with quantization
            if use_lora:
                print("Preparing model for k-bit training...")
                self.model = prepare_model_for_kbit_training(self.model)
        else:
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                device_map="auto" if device == "cuda" else None,
                trust_remote_code=True
            )
            if device == "cpu":
                self.model = self.model.to(device)

        # Add LoRA adapters if requested
        if use_lora:
            print(f"Adding LoRA adapters (r={lora_r}, alpha={lora_alpha})...")
            lora_config = LoraConfig(
                r=lora_r,
                lora_alpha=lora_alpha,
                target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
                lora_dropout=lora_dropout,
                bias="none",
                task_type="CAUSAL_LM"
            )
            self.model = get_peft_model(self.model, lora_config)
            self.model.print_trainable_parameters()

        self.model.eval()
        print("Model loaded successfully!")

    def create_prompt(self, question: str, answer: str) -> str:
        """
        Create a prompt for the judge to evaluate factual correctness.

        Args:
            question: The immigration-related question
            answer: The answer to evaluate

        Returns:
            Formatted prompt string
        """
        prompt = f"""You are an expert immigration judge. Evaluate whether the following answer to an immigration question is factually correct.

Question: {question}

Answer: {answer}

Is this answer factually correct? Respond with ONLY "YES" or "NO".

Judgment:"""
        return prompt

    def parse_response(self, response: str) -> int:
        """
        Parse the model's response to extract binary label.

        Args:
            response: Raw model output

        Returns:
            1 if correct (YES), 0 if incorrect (NO)
        """
        response = response.strip().upper()

        # Look for YES/NO in the response
        if "YES" in response[:20]:  # Check first 20 chars
            return 1
        elif "NO" in response[:20]:
            return 0
        else:
            # Default to 0 if unclear
            print(f"Warning: Unclear response: {response}")
            return 0

    @torch.no_grad()
    def judge_single(self, question: str, answer: str):
        """Judge a single Q&A pair."""

        # CRITICAL: Very explicit prompt!
        prompt = f"""You are evaluating whether an answer is factually correct for Canadian immigration questions.

    Question: {question}

    Answer to evaluate: {answer}

    Your task: Determine if the answer is factually correct and helpful.

    Respond with ONLY ONE WORD:
    - Reply "YES" if the answer is factually correct
    - Reply "NO" if the answer is incorrect or unhelpful

    Do not explain. Do not include URLs. Do not copy from the answer.
    Just output: YES or NO

    Your response:"""

        # Format for the model
        messages = [{"role": "user", "content": prompt}]

        # Generate response
        inputs = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model.generate(
                inputs,
                max_new_tokens=10,  # Only need "YES" or "NO"!
                temperature=0.1,  # Very low temperature for consistency
                do_sample=False,  # Greedy decoding
                pad_token_id=self.tokenizer.eos_token_id
            )

        # Decode response
        response = self.tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True)
        response = response.strip().upper()

        # Debug print
        print(f"Judge raw response: '{response}'")

        # Look for YES/NO
        if "YES" in response:
            return 1, response
        elif "NO" in response:
            return 0, response
        else:
            print(f"⚠️ Warning: Judge gave unclear response: {response}")
            print(f"   Question: {question[:50]}...")
            print(f"   Answer: {answer[:50]}...")
            return 0, response

    @torch.no_grad()
    def judge_batch(self, questions: List[str], answers: List[str]) -> List[int]:
        """
        Judge a batch of Q&A pairs.

        Args:
            questions: List of immigration questions
            answers: List of answers to evaluate

        Returns:
            List of predictions (0 or 1 for each pair)
        """
        predictions = []
        for question, answer in zip(questions, answers):
            pred, _ = self.judge_single(question, answer)
            predictions.append(pred)
        return predictions

    def evaluate(self, dataset: List[Dict]) -> Dict[str, float]:
        """
        Evaluate judge performance on a labeled dataset.

        Args:
            dataset: List of dicts with keys: 'question', 'answer', 'label'

        Returns:
            Dictionary with accuracy and other metrics
        """
        from .reward_model import compute_metrics

        predictions = []
        labels = []

        for item in dataset:
            pred, _ = self.judge_single(item['question'], item['answer'])
            predictions.append(pred)
            labels.append(item['label'])

        predictions = torch.tensor(predictions)
        labels = torch.tensor(labels)

        metrics = compute_metrics(predictions, labels)

        return metrics


def load_judge(
        model_name: str = "Qwen/Qwen2.5-1.5B-Instruct",
        quantize: bool = True,
        checkpoint_path: Optional[str] = None
) -> ImmigrationJudge:
    """
    Convenience function to load a judge model.

    Args:
        model_name: Base model to use
        quantize: Whether to quantize
        checkpoint_path: Optional path to fine-tuned weights

    Returns:
        ImmigrationJudge instance
    """
    judge = ImmigrationJudge(model_name=model_name, quantize=quantize)

    if checkpoint_path:
        print(f"Loading checkpoint from {checkpoint_path}")
        # Load fine-tuned weights
        state_dict = torch.load(checkpoint_path, map_location=judge.device)
        judge.model.load_state_dict(state_dict)
        print("Checkpoint loaded!")

    return judge


if __name__ == "__main__":
    # Test the judge
    print("Testing ImmigrationJudge...")

    judge = ImmigrationJudge(quantize=False)  # Use False for CPU testing

    # Test example
    question = "Is IELTS mandatory for Canadian PR?"
    answer_correct = "Yes, a language proficiency test such as IELTS is typically required for Express Entry and other PR streams."
    answer_wrong = "No, you don't need any English test for Canadian immigration."

    print(f"\n--- Test 1: Correct Answer ---")
    print(f"Question: {question}")
    print(f"Answer: {answer_correct}")
    pred, response = judge.judge_single(question, answer_correct)
    print(f"Raw response: {response}")
    print(f"Prediction: {pred} (Expected: 1)")

    print(f"\n--- Test 2: Wrong Answer ---")
    print(f"Question: {question}")
    print(f"Answer: {answer_wrong}")
    pred, response = judge.judge_single(question, answer_wrong)
    print(f"Raw response: {response}")
    print(f"Prediction: {pred} (Expected: 0)")
