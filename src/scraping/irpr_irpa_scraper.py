import requests
import xml.etree.ElementTree as ET
import re
import json
import boto3
from datetime import date
import uuid
from constants import JUSTICE_XMLS

# store all documents in memory instead of database
docs = []

def parse_and_store(law_name, xml_url):
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

    def extract_text(elem):
        """Extract all meaningful text from element and its children."""
        texts = [t.text.strip() for t in elem.findall(text_tag, ns) if t.text]
        if not texts:
            texts = [t.strip() for t in elem.itertext() if t.strip()]
        return " ".join(texts)

    def process_element(elem, parent_number="", parent_heading="", unlabeled_count=[0]):
        """Recursively process sections, subsections, paragraphs."""
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

        content = extract_text(elem).strip()

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
            process_element(sub_elem, parent_number=number or "", parent_heading=heading, unlabeled_count=unlabeled_count)

        # Find all top-level sections and process recursively
    sections = root.findall(".//" + section_tag, ns)  # recursive search
    print(f"  Found {len(sections)} sections in {law_name}")
    for sec in sections:
        process_element(sec)

# Run for each law
for law_name, xml_url in JUSTICE_XMLS.items():
    parse_and_store(law_name, xml_url)

# ---------- CHECK DATA ----------
print("Database filled. Example rows:")
for row in docs[:5]:
    print((row["id"], row["source"], row["title"], row["section"], row["content"][:100], row.get("granularity"), row["date_published"], row["date_scraped"]))

# ---------- EXPORT TO JSON ----------
output_file = "irpr_irpa_data.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(docs, f, ensure_ascii=False, indent=2)

print(f"Exported {len(docs)} records to {output_file}")

# ---------- UPLOAD TO S3 ----------
s3 = boto3.client("s3")

bucket_name = "raw-immigreation-documents"
s3_key = "irpr_irpa_data.json"  # path inside S3 bucket

s3.upload_file(output_file, bucket_name, s3_key)

print(f"Uploaded {output_file} to s3://{bucket_name}/{s3_key}")
