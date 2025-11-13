"""
Profile selected hot functions using cProfile and report top offenders.

Targets (5 functions across different files; <=1 scraping function):
- src/data_ingestion.py: chunk_text, chunk_document
- src/scraping/ircc_scraper.py: find_internal_article_links
- rag_llm_judge/judge/data_loader.py: ImmigrationQADataset._load_data
- rag_llm_judge/judge/model_utils.py: print_trainable_parameters (optional if torch present)

Run:
  python scripts/profile_functions.py
"""

import cProfile
import pstats
import io
import tempfile
import sys
import os
from pathlib import Path

# Ensure repo root and src/ are on sys.path so imports work when running as a script
ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Provide minimal env so modules that read env at import time don't crash
os.environ.setdefault("PGVECTOR_SECRET_ARN", "dummy-secret-arn")

# 1) data_ingestion.chunk_text / chunk_document
from data_ingestion import chunk_text, chunk_document

# 2) scraping.ircc_scraper.find_internal_article_links
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except Exception:
    BS4_AVAILABLE = False
from scraping.ircc_scraper import find_internal_article_links

# 3) rag_llm_judge.judge.data_loader.ImmigrationQADataset._load_data
from rag_llm_judge.judge.data_loader import ImmigrationQADataset

# 4) rag_llm_judge.judge.model_utils.print_trainable_parameters (optional)
try:
    import torch.nn as nn
    from rag_llm_judge.judge.model_utils import print_trainable_parameters
    TORCH_AVAILABLE = True
except Exception:
    TORCH_AVAILABLE = False


def profile_callable(name: str, fn, *args, **kwargs):
    pr = cProfile.Profile()
    pr.enable()
    result = fn(*args, **kwargs)
    pr.disable()
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats(pstats.SortKey.CUMULATIVE)
    ps.print_stats(20)
    print(f"\n=== Profile: {name} ===")
    print(s.getvalue())
    return result


def synthetic_text(n_chars: int = 200_000) -> str:
    sentence = (
        "This is a synthetic sentence meant to approximate realistic text with punctuation. "
    )
    parts = []
    total = 0
    while total < n_chars:
        parts.append(sentence)
        total += len(sentence)
    return "".join(parts)


def make_html_with_links(n_links: int = 1000, domain: str = "https://www.canada.ca") -> str:
    links = [
        f'<a href="{domain}/en/immigration-refugees-citizenship/news/{i}.html">News {i}</a>'
        for i in range(n_links // 2)
    ]
    links += [
        f'<a href="{domain}/en/services/{i}/index.html">Service {i}</a>' for i in range(n_links // 2)
    ]
    return f"<html><body><main>\n{''.join(links)}\n</main></body></html>"


def build_temp_jsonl(n_rows: int = 2000) -> Path:
    tmp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    # keep simple JSON lines
    for i in range(n_rows):
        tmp.write('{"question":"Q?","answer":"A.","label":%d}\n' % (i % 2))
    tmp.close()
    return Path(tmp.name)


if __name__ == "__main__":
    # 1) chunk_text
    text = synthetic_text(300_000)
    profile_callable("chunk_text(300k)", chunk_text, text, 1000, 200)

    # 2) chunk_document
    doc = {
        "id": "doc-123",
        "content": text,
        "title": "Title",
        "section": "Section",
        "source": "https://example.com",
        "date_published": "2024-01-01",
        "date_scraped": "2024-01-02",
        "granularity": "page",
    }
    profile_callable("chunk_document(large)", chunk_document, doc, 1000, 200)

    # 3) find_internal_article_links
    if BS4_AVAILABLE:
        html = make_html_with_links(2000)
        soup = BeautifulSoup(html, "html.parser")
        profile_callable("find_internal_article_links(2000)", find_internal_article_links, soup, "https://www.canada.ca")
    else:
        print("[SKIP] BeautifulSoup not available; skipping find_internal_article_links profiling.")

    # 4) ImmigrationQADataset._load_data via ctor
    tmp_path = build_temp_jsonl(5000)
    try:
        profile_callable("ImmigrationQADataset._load_data(5k)", ImmigrationQADataset, str(tmp_path))
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            # Ignore errors during cleanup (e.g., file may already be deleted)
            pass

    # 5) print_trainable_parameters (optional)
    if TORCH_AVAILABLE:
        model = nn.Sequential(
            nn.Linear(4096, 1024),
            nn.ReLU(),
            nn.Linear(1024, 1024),
            nn.ReLU(),
            nn.Linear(1024, 2),
        )
        profile_callable("print_trainable_parameters", print_trainable_parameters, model)
    else:
        print("[SKIP] Torch not available; skipping print_trainable_parameters profiling.")
