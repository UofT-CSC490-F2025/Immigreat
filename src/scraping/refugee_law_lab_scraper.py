import json
import uuid
from datetime import date
from huggingface_hub import hf_hub_download
import pyarrow.parquet as pq
import pandas as pd
import boto3

from .constants import (
    REFUGEE_LAW_LAB_DATASETS,
    S3_BUCKET_NAME,
    S3_REFUGEE_LAW_LAB_DATA_KEY,
    DEFAULT_REFUGEE_LAW_LAB_OUTPUT
)

def load_hf_dataset_as_dict(repo_id, subset, split="train"):
    """Download and load a Hugging Face dataset using huggingface_hub."""
    # Download the parquet file for the specific subset
    file_path = hf_hub_download(
        repo_id=repo_id,
        filename=f"{subset}/{split}-00000-of-00001.parquet",  # Common HF pattern
        repo_type="dataset"
    )
    
    # Read with pyarrow and convert to list of dicts
    table = pq.read_table(file_path)
    df = table.to_pandas()
    return df.to_dict('records')

def transform_record(record):
    """Convert one record to your schema with language filtering."""
    raw_text = record.get("unofficial_text", "")
    lang = record.get("language", "")

    # Drop clearly French-labeled records
    if lang == "fr":
        return None

    return {
        "id": str(uuid.uuid4()),
        "title": record.get("name", ""),
        "section": record.get("dataset", ""),  # RAD or RPD
        "content": raw_text,
        "source": record.get("source_url", ""),
        "date_published": record.get("document_date", ""),
        "date_scraped": record.get("scraped_timestamp", str(date.today())),
        "granularity": "decision",
    }


def scrape_refugee_law_lab(output_file=None, upload_to_s3=True):
    """
    Scrape Refugee Law Lab datasets (RAD and RPD) from Hugging Face.
    
    Args:
        output_file (str, optional): Path to save JSON output. Defaults to DEFAULT_REFUGEE_LAW_LAB_OUTPUT.
        upload_to_s3 (bool): Whether to upload results to S3. Defaults to True.
    
    Returns:
        list: List of document dictionaries containing refugee law decisions.
    """
    if output_file is None:
        output_file = DEFAULT_REFUGEE_LAW_LAB_OUTPUT
    
    # Load both RAD and RPD datasets
    all_records = []

    for subset in REFUGEE_LAW_LAB_DATASETS:
        print(f"Fetching {subset} dataset...")
        ds = load_hf_dataset_as_dict("refugee-law-lab/canadian-legal-data", subset, split="train")
        transformed = [transform_record(r) for r in ds]
        # Drop None (skipped French/empty)
        transformed = [r for r in transformed if r is not None]
        print(f" → {len(transformed)} English records kept from {subset}")
        all_records.extend(transformed)

    # Save combined output
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(all_records)} ENGLISH records from RAD + RPD to {output_file}")

    # Upload to S3
    if upload_to_s3:
        s3 = boto3.client("s3")
        s3.upload_file(output_file, S3_BUCKET_NAME, S3_REFUGEE_LAW_LAB_DATA_KEY)
        print(f"Uploaded {output_file} to s3://{S3_BUCKET_NAME}/{S3_REFUGEE_LAW_LAB_DATA_KEY}")

    return all_records
