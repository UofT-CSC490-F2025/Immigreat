import json
import uuid
from datetime import date
import requests
import boto3
import os
import time
from .utils import resolve_output_path 
from .constants import (
    REFUGEE_LAW_LAB_DATASETS,
    S3_BUCKET_NAME,
    S3_REFUGEE_LAW_LAB_DATA_KEY,
    DEFAULT_REFUGEE_LAW_LAB_OUTPUT
)

TARGET_S3_BUCKET = os.getenv("TARGET_S3_BUCKET", S3_BUCKET_NAME)
TARGET_S3_KEY = os.getenv("TARGET_S3_KEY", S3_REFUGEE_LAW_LAB_DATA_KEY)

def load_hf_dataset_as_dict(repo_id, subset, split="train"):
    """
    Load a Hugging Face dataset using the Datasets Server API.
    This uses HF's public API - no authentication or complex libraries needed.
    """
    # Use Hugging Face's Datasets Server API to get the data
    # This API provides paginated access to datasets without downloading files
    api_url = f"https://datasets-server.huggingface.co/rows"
    
    all_rows = []
    offset = 0
    limit = 100  # rows per request
    
    while True:
        params = {
            "dataset": repo_id,
            "config": subset,
            "split": split,
            "offset": offset,
            "length": limit
        }
        
        print(f"Fetching rows {offset} to {offset + limit} from {subset}...")
        max_retries = 5
        retry_delay = 2  # Start with 2 seconds
        
        for attempt in range(max_retries):
            try:
                response = requests.get(api_url, params=params, timeout=30)
                response.raise_for_status()
                break  # Success, exit retry loop
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                        print(f"Rate limited. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                        time.sleep(wait_time)
                    else:
                        print(f"Failed after {max_retries} retries due to rate limiting")
                        raise
                else:
                    raise  # Re-raise non-429 errors
        
        data = response.json()
        
        if "rows" not in data or not data["rows"]:
            break
            
        # Extract the row data
        for row_obj in data["rows"]:
            all_rows.append(row_obj["row"])
        
        # Check if we've fetched all rows
        if len(data["rows"]) < limit:
            break

        offset += limit
        
        # Safety limit to avoid infinite loops (adjust as needed)
        if offset > 10000:
            print(f"Warning: Hit safety limit at {offset} rows")
            break
    
    print(f"Loaded {len(all_rows)} total rows from {subset}")
    return all_rows


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
    
    # Resolve output path to /tmp for Lambda
    output_file = resolve_output_path(output_file)
    
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
        s3.upload_file(output_file, TARGET_S3_BUCKET, TARGET_S3_KEY)
        print(f"Uploaded {output_file} to s3://{TARGET_S3_BUCKET}/{TARGET_S3_KEY}")

    return all_records