import os

from .constants import (
    IRCC_URLS,
    S3_BUCKET_NAME,
    S3_IRCC_DATA_KEY,
    DEFAULT_IRCC_OUTPUT,
)
from .ircc_scraper import scrape_all


DEFAULT_OUTPUT = os.getenv("SCRAPE_DEFAULT_OUTPUT", DEFAULT_IRCC_OUTPUT)
TARGET_BUCKET = os.getenv("TARGET_S3_BUCKET", S3_BUCKET_NAME)
TARGET_KEY = os.getenv("TARGET_S3_KEY", S3_IRCC_DATA_KEY)


def handler(event, context):
    """Lambda handler that orchestrates the IRCC scraping workflow."""
    event = event or {}
    urls = event.get("urls", IRCC_URLS)
    out_path = event.get("out_path", DEFAULT_OUTPUT)
    crawl_subpages = event.get("crawl_subpages", True)

    print(
        f"Starting IRCC scrape for {len(urls)} urls; "
        f"crawl_subpages={crawl_subpages}; output={out_path}"
    )
    results = scrape_all(urls, out_path=out_path, crawl_subpages=crawl_subpages)
    print(f"Scraped {len(results)} records. Saved to {out_path}")

    return {
        "status": "completed",
        "records_scraped": len(results),
        "output_file": out_path,
        "s3_bucket": TARGET_BUCKET,
        "s3_key": TARGET_KEY,
    }
