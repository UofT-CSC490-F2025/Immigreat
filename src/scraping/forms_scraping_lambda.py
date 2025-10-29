import os

from scraping.constants import (
    FORMS_WEBPAGES,
    S3_BUCKET_NAME,
    S3_FORMS_DATA_KEY,
    DEFAULT_FORMS_OUTPUT,
    PDF_KEYWORDS,
)
from scraping.forms_scraper import extract_fields_from_webpages


DEFAULT_OUTPUT = os.getenv("SCRAPE_DEFAULT_OUTPUT", DEFAULT_FORMS_OUTPUT)
TARGET_BUCKET = os.getenv("TARGET_S3_BUCKET", S3_BUCKET_NAME)
TARGET_KEY = os.getenv("TARGET_S3_KEY", S3_FORMS_DATA_KEY)


def handler(event, context):
    """Lambda handler that orchestrates the forms scraping workflow."""
    event = event or {}
    page_urls = event.get("page_urls", FORMS_WEBPAGES)
    out_path = event.get("out_path", DEFAULT_OUTPUT)
    pdf_keywords = event.get("pdf_keywords", PDF_KEYWORDS)
    prefer_text_keyword = event.get("prefer_text_keyword", False)
    dedupe = event.get("dedupe", True)

    print(
        f"Starting forms scrape for {len(page_urls)} pages; "
        f"pdf_keywords={pdf_keywords}; prefer_text_keyword={prefer_text_keyword}; "
        f"dedupe={dedupe}; output={out_path}"
    )
    
    results = extract_fields_from_webpages(
        page_urls=page_urls,
        output_file=out_path,
        pdf_keywords=pdf_keywords,
        prefer_text_keyword=prefer_text_keyword,
        dedupe=dedupe
    )
    
    print(f"Scraped {len(results)} form field records. Saved to {out_path}")

    return {
        "status": "completed",
        "records_scraped": len(results),
        "output_file": out_path,
        "s3_bucket": TARGET_BUCKET,
        "s3_key": TARGET_KEY,
    }