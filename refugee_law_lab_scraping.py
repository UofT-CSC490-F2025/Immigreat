import json
import uuid
from datetime import date
from datasets import load_dataset
import boto3
from langdetect import detect, DetectorFactory

import json
import uuid
from datetime import date
from datasets import load_dataset
import boto3

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


# Load both RAD and RPD datasets
datasets_to_merge = ["RAD", "RPD"]
all_records = []

for subset in datasets_to_merge:
    print(f"Fetching {subset} dataset...")
    ds = load_dataset("refugee-law-lab/canadian-legal-data", subset, split="train")
    transformed = [transform_record(r) for r in ds]
    # Drop None (skipped French/empty)
    transformed = [r for r in transformed if r is not None]
    print(f" → {len(transformed)} English records kept from {subset}")
    all_records.extend(transformed)

# Save combined output
output_file = "refugeelawlab_data_en.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_records, f, ensure_ascii=False, indent=2)

print(f"Saved {len(all_records)} ENGLISH records from RAD + RPD to {output_file}")

# Upload to S3
s3 = boto3.client("s3")
bucket_name = "raw-immigreation-documents"
s3_key = "refugeelawlab_data_en.json"

s3.upload_file(output_file, bucket_name, s3_key)
print(f"Uploaded {output_file} to s3://{bucket_name}/{s3_key}")
