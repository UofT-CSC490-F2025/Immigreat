from scraping.constants import IRCC_URLS, S3_BUCKET_NAME, S3_IRCC_DATA_KEY
from scraping.ircc_scraper import scrape_all


def handler(event, context):
    """Lambda handler that orchestrates the IRCC scraping workflow."""
    event = event or {}
    urls = event.get("urls", IRCC_URLS)
    out_path = event.get("out_path", "ircc_scraped_data.json")
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
        "s3_bucket": S3_BUCKET_NAME,
        "s3_key": S3_IRCC_DATA_KEY,
    }


if __name__ == "__main__":
    handler({}, None)
