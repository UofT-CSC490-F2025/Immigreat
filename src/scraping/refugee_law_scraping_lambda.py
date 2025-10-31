import os

from .constants import (
    REFUGEE_LAW_LAB_DATASETS,
    S3_BUCKET_NAME,
    S3_REFUGEE_LAW_LAB_DATA_KEY,
    DEFAULT_REFUGEE_LAW_LAB_OUTPUT,
)
from .refugee_law_lab_scraper import scrape_refugee_law_lab


DEFAULT_OUTPUT = os.getenv("SCRAPE_DEFAULT_OUTPUT", DEFAULT_REFUGEE_LAW_LAB_OUTPUT)
TARGET_BUCKET = os.getenv("TARGET_S3_BUCKET", S3_BUCKET_NAME)
TARGET_KEY = os.getenv("TARGET_S3_KEY", S3_REFUGEE_LAW_LAB_DATA_KEY)


def handler(event, context):
    """Lambda handler that orchestrates the Refugee Law Lab scraping workflow."""
    event = event or {}
    out_path = event.get("out_path", DEFAULT_OUTPUT)
    upload_to_s3 = event.get("upload_to_s3", True)

    print(
        f"Starting Refugee Law Lab scrape for {len(REFUGEE_LAW_LAB_DATASETS)} datasets; "
        f"upload_to_s3={upload_to_s3}; output={out_path}"
    )
    results = scrape_refugee_law_lab(output_file=out_path, upload_to_s3=upload_to_s3)
    print(f"Scraped {len(results)} records. Saved to {out_path}")

    return {
        "status": "completed",
        "records_scraped": len(results),
        "output_file": out_path,
        "s3_bucket": TARGET_BUCKET,
        "s3_key": TARGET_KEY,
    }