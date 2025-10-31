import requests
import xml.etree.ElementTree as ET
import re
import json
import boto3
from datetime import date
import uuid
import os
from .utils import resolve_output_path
from .constants import (
    JUSTICE_XMLS,
    S3_BUCKET_NAME,
    S3_IRPR_IRPA_DATA_KEY,
    DEFAULT_IRPR_IRPA_OUTPUT
)

TARGET_S3_BUCKET = os.getenv("TARGET_S3_BUCKET", S3_BUCKET_NAME)
TARGET_S3_KEY = os.getenv("TARGET_S3_KEY", S3_IRPR_IRPA_DATA_KEY)


def extract_text(elem, text_tag, ns):
    """Extract all meaningful text from element and its children."""
    texts = [t.text.strip() for t in elem.findall(text_tag, ns) if t.text]
    if not texts:
        texts = [t.strip() for t in elem.itertext() if t.strip()]
    return " ".join(texts)


def process_element(elem, docs, law_name, ns, section_tag, subsection_tag, num_tag, 
                    heading_tag, text_tag, parent_number="", parent_heading="", 
                    unlabeled_count=None):
    """Recursively process sections, subsections, paragraphs."""
    if unlabeled_count is None:
        unlabeled_count = [0]
    
    number = elem.findtext(num_tag, default=None, namespaces=ns)
    heading = (
        elem.findtext(heading_tag, default=None, namespaces=ns)
        or elem.findtext("Margnote", default=None, namespaces=ns)
    )

    # Build section number
    if number:
        number = f"{parent_number}.{number}" if parent_number else number
    else:
        # generate synthetic number if missing
        unlabeled_count[0] += 1
        number = f"{parent_number}-unlabeled-{unlabeled_count[0]}" if parent_number else f"unlabeled-{unlabeled_count[0]}"

    # Build heading
    if not heading:
        if parent_heading:
            heading = f"{parent_heading} (continuation)"
        else:
            heading = f"{law_name} Section {number} (unlabeled)"

    content = extract_text(elem, text_tag, ns).strip()

    if content:
        docs.append({
            "id": str(uuid.uuid4()),
            "title": heading,
            "section": number,
            "content": content,
            "source": law_name,
            "date_published": None,
            "date_scraped": str(date.today()),
            "granularity": "section"
        })

    # Recursively process subsections
    for sub_elem in elem.findall(subsection_tag, ns):
        process_element(
            sub_elem, docs, law_name, ns, section_tag, subsection_tag, 
            num_tag, heading_tag, text_tag, parent_number=number or "", 
            parent_heading=heading, unlabeled_count=unlabeled_count
        )


def parse_and_store(law_name, xml_url, docs):
    """Parse XML law document and store sections in docs list."""
    print(f"Fetching {law_name}...")
    r = requests.get(xml_url)
    r.raise_for_status()

    root = ET.fromstring(r.content)

    # Extract namespace dynamically (if present)
    m = re.match(r"\{(.*)\}", root.tag)
    if m:
        ns = {"ns": m.group(1)}
        section_tag = "ns:Section"
        subsection_tag = "ns:Subsection"
        num_tag = "ns:Num"
        heading_tag = "ns:Heading"
        text_tag = ".//ns:Text"
    else:
        ns = {}
        section_tag = "Section"
        subsection_tag = "Subsection"
        num_tag = "Num"
        heading_tag = "Heading"
        text_tag = ".//Text"

    # Find all top-level sections and process recursively
    sections = root.findall(".//" + section_tag, ns)  # recursive search
    print(f"  Found {len(sections)} sections in {law_name}")
    for sec in sections:
        process_element(
            sec, docs, law_name, ns, section_tag, subsection_tag, 
            num_tag, heading_tag, text_tag
        )


def scrape_irpr_irpa_laws(output_file=None, upload_to_s3=True):
    """
    Scrape IRPR and IRPA laws from Justice Canada XML sources.
    
    Args:
        output_file (str, optional): Path to save JSON output. Defaults to DEFAULT_IRPR_IRPA_OUTPUT.
        upload_to_s3 (bool): Whether to upload results to S3. Defaults to True.
    
    Returns:
        list: List of document dictionaries containing scraped law sections.
    """
    if output_file is None:
        output_file = DEFAULT_IRPR_IRPA_OUTPUT

    output_file = resolve_output_path(output_file)
    
    docs = []

    for law_name, xml_url in JUSTICE_XMLS.items():
        parse_and_store(law_name, xml_url, docs)

    print("Database filled. Example rows:")
    for row in docs[:5]:
        print((row["id"], row["source"], row["title"], row["section"], 
               row["content"][:100], row.get("granularity"), 
               row["date_published"], row["date_scraped"]))

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)

    print(f"Exported {len(docs)} records to {output_file}")

    if upload_to_s3:
        s3 = boto3.client("s3")
        s3.upload_file(output_file, TARGET_S3_BUCKET, TARGET_S3_KEY)
        print(f"Uploaded {output_file} to s3://{TARGET_S3_BUCKET}/{TARGET_S3_KEY}")
    return docs
