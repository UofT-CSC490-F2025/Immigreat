"""
Data loading utilities for RLVR judge training.
"""

import json
import torch
from torch.utils.data import Dataset, DataLoader
from typing import List, Dict, Optional
from pathlib import Path


class ImmigrationQADataset(Dataset):
    """
    Dataset for immigration Q&A with factual correctness labels.

    Expected format:
    {"question": "...", "answer": "...", "label": 0 or 1}
    """

    def __init__(self, data_path: str, tokenizer=None, max_length: int = 512):
        """
        Args:
            data_path: Path to JSONL file
            tokenizer: Optional tokenizer for preprocessing
            max_length: Maximum sequence length
        """
        self.data_path = Path(data_path)
        self.tokenizer = tokenizer
        self.max_length = max_length

        # Load data
        self.examples = self._load_data()

        print(f"Loaded {len(self.examples)} examples from {data_path}")
        self._print_stats()

    def _load_data(self) -> List[Dict]:
        """Load JSONL data.

        Why it's important: Dataset loading happens frequently in experiments; Python-level
        loop overhead can be a bottleneck on large files. Using a list comprehension over
        splitlines() reduces per-iteration overhead while preserving readability.
        """
        with open(self.data_path, 'r', encoding='utf-8') as f:
            return [json.loads(line) for line in f if line.strip()]

    def _print_stats(self):
        """Print dataset statistics."""
        labels = [ex['label'] for ex in self.examples]
        num_correct = sum(labels)
        num_incorrect = len(labels) - num_correct

        print(f"  - Correct (label=1): {num_correct} ({num_correct / len(labels) * 100:.1f}%)")
        print(f"  - Incorrect (label=0): {num_incorrect} ({num_incorrect / len(labels) * 100:.1f}%)")

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> Dict:
        """Get a single example."""
        example = self.examples[idx]

        # Return raw data (tokenization happens in collate_fn)
        return {
            'question': example['question'],
            'answer': example['answer'],
            'label': example['label']
        }

    def get_examples(self, indices: Optional[List[int]] = None) -> List[Dict]:
        """
        Get multiple examples by indices.

        Args:
            indices: Optional list of indices. If None, returns all.

        Returns:
            List of examples
        """
        if indices is None:
            return self.examples
        return [self.examples[i] for i in indices]


def create_dataloaders(
        train_path: str,
        val_path: str,
        test_path: str,
        batch_size: int = 8,
        num_workers: int = 0
) -> tuple:
    """
    Create train, val, test dataloaders.

    Args:
        train_path: Path to train.jsonl
        val_path: Path to val.jsonl
        test_path: Path to test.jsonl
        batch_size: Batch size for dataloaders
        num_workers: Number of workers for data loading

    Returns:
        Tuple of (train_loader, val_loader, test_loader)
    """
    train_dataset = ImmigrationQADataset(train_path)
    val_dataset = ImmigrationQADataset(val_path)
    test_dataset = ImmigrationQADataset(test_path)

    # Simple collate function (no tokenization here)
    def collate_fn(batch):
        questions = [item['question'] for item in batch]
        answers = [item['answer'] for item in batch]
        labels = torch.tensor([item['label'] for item in batch])

        return {
            'questions': questions,
            'answers': answers,
            'labels': labels
        }

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        collate_fn=collate_fn
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        collate_fn=collate_fn
    )

    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        collate_fn=collate_fn
    )

    return train_loader, val_loader, test_loader


def load_jsonl(file_path: str) -> List[Dict]:
    """
    Simple utility to load JSONL file.

    Args:
        file_path: Path to JSONL file

    Returns:
        List of dictionaries
    """
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            data.append(json.loads(line.strip()))
    return data


def save_jsonl(data: List[Dict], file_path: str):
    """
    Save data to JSONL file.

    Args:
        data: List of dictionaries
        file_path: Output file path
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item) + '\n')
    print(f"Saved {len(data)} examples to {file_path}")


if __name__ == "__main__":
    # Test data loading
    print("Testing data loader...")

    # You'll need to update these paths to your actual data
    data_dir = "../baseline"

    try:
        dataset = ImmigrationQADataset(f"{data_dir}/train.jsonl")

        print(f"\nFirst example:")
        example = dataset[0]
        print(f"Question: {example['question']}")
        print(f"Answer: {example['answer']}")
        print(f"Label: {example['label']}")

        # Test dataloader
        train_loader, val_loader, test_loader = create_dataloaders(
            train_path=f"{data_dir}/train.jsonl",
            val_path=f"{data_dir}/val.jsonl",
            test_path=f"{data_dir}/test.jsonl",
            batch_size=4
        )

        print(f"\nDataloader sizes:")
        print(f"Train batches: {len(train_loader)}")
        print(f"Val batches: {len(val_loader)}")
        print(f"Test batches: {len(test_loader)}")

        # Test one batch
        batch = next(iter(train_loader))
        print(f"\nBatch contents:")
        print(f"Questions: {len(batch['questions'])}")
        print(f"Answers: {len(batch['answers'])}")
        print(f"Labels: {batch['labels']}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Make sure your data files exist in the correct location!")
