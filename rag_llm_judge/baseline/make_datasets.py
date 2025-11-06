# make_datasets.py
import json
import random
import os

def split_dataset(in_file, out_dir="baseline", seed=42):
    with open(in_file, encoding="utf-8") as f:
        data = [json.loads(line) for line in f]

    random.seed(seed)
    random.shuffle(data)

    n = len(data)
    train, val, test = data[:int(0.7*n)], data[int(0.7*n):int(0.85*n)], data[int(0.85*n):]

    os.makedirs(out_dir, exist_ok=True)
    for name, split in zip(["train", "val", "test"], [train, val, test]):
        with open(f"{out_dir}/{name}.jsonl", "w") as f:
            for ex in split:
                f.write(json.dumps(ex) + "\n")

    print(f"Saved: train={len(train)}, val={len(val)}, test={len(test)}")
