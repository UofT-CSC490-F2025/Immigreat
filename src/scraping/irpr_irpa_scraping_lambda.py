import os

from .constants import (
    JUSTICE_XMLS,
    S3_BUCKET_NAME,
    S3_IRPR_IRPA_DATA_KEY,
    DEFAULT_IRPR_IRPA_OUTPUT,
)
from .irpr_irpa_scraper import scrape_irpr_irpa_laws


DEFAULT_OUTPUT = os.getenv("SCRAPE_DEFAULT_OUTPUT", DEFAULT_IRPR_IRPA_OUTPUT)
TARGET_BUCKET = os.getenv("TARGET_S3_BUCKET", S3_BUCKET_NAME)
TARGET_KEY = os.getenv("TARGET_S3_KEY", S3_IRPR_IRPA_DATA_KEY)


def handler(event, context):
    """Lambda handler that orchestrates the IRPR/IRPA scraping workflow."""
    event = event or {}
    out_path = event.get("out_path", DEFAULT_OUTPUT)
    upload_to_s3 = event.get("upload_to_s3", True)

    print(
        f"Starting IRPR/IRPA scrape for {len(JUSTICE_XMLS)} laws; "
        f"upload_to_s3={upload_to_s3}; output={out_path}"
    )
    results = scrape_irpr_irpa_laws(output_file=out_path, upload_to_s3=upload_to_s3)
    print(f"Scraped {len(results)} records. Saved to {out_path}")

    return {
        "status": "completed",
        "records_scraped": len(results),
        "output_file": out_path,
        "s3_bucket": TARGET_BUCKET,
        "s3_key": TARGET_KEY,
    }