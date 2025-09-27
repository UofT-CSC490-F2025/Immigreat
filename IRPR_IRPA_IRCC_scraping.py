import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re
import json
import boto3
from datetime import date
import uuid

# ---------- PART 1: JUSTICE LAWS (IRPA + IRPR) ----------
JUSTICE_XMLS = {
    "IRPA": "https://laws-lois.justice.gc.ca/eng/XML/I-2.5.xml",
    "IRPR": "https://laws-lois.justice.gc.ca/eng/XML/SOR-2002-227.xml"
}

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

    def process_element(elem, parent_number="", parent_heading=""):
        """Recursively process sections, subsections, paragraphs."""
        number = elem.findtext(num_tag, default=None, namespaces=ns)
        heading = elem.findtext(heading_tag, default=None, namespaces=ns)

        if not number:
            number = f"{parent_number}" if parent_number else "Sec-1"
        else:
            number = f"{parent_number}.{number}" if parent_number else number

        if not heading:
            heading = f"{parent_heading} Section {number}" if parent_heading else f"{law_name} Section {number}"

        content = extract_text(elem)

        docs.append({
            "id": str(uuid.uuid4()),
            "title": heading,
            "section": number,
            "content": content,
            "source": law_name,
            "date_published": None,  # XML does not provide publication date
            "date_scraped": str(date.today()),
            "granularity": "section"  # section-level entry for laws
        })

        # TODO Note: Here's the logic that processes subsections. We are only using title and section.
        # If there are subsections, title = title + subsection, and section = subsection is stored. And so on.

        # Recursively process subsections
        for sub_elem in elem.findall(subsection_tag, ns):
            process_element(sub_elem, parent_number=number, parent_heading=heading)

    # Find all top-level sections and process recursively
    sections = root.findall(section_tag, ns)
    print(f"  Found {len(sections)} top-level sections in {law_name}")
    for sec in sections:
        process_element(sec)

# Run for each law
for law_name, xml_url in JUSTICE_XMLS.items():
    parse_and_store(law_name, xml_url)

# ---------- PART 2: IRCC WEB PAGES ---------- 
# TODO: filter out junk data from database
IRCC_PAGES = {
    "Application Overview": "https://www.canada.ca/en/immigration-refugees-citizenship/services/application.html",
    "Program Delivery Instructions": "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/publications-manuals/operational-bulletins-manuals.html"
}

# only crawl pages we care about
ALLOWED_PREFIXES = [
    "/en/immigration-refugees-citizenship/services/application",
    "/en/immigration-refugees-citizenship/corporate/publications-manuals/operational-bulletins-manuals"
]

#TODO adjust max pages to scrape and depth of scraping appropriately
MAX_PAGES = 1000

def scrape_ircc_page(title, url, depth=1, visited=None, count=[0]):
    if visited is None:
        visited = set()
    if url in visited or count[0] >= MAX_PAGES:
        return
    if not url.endswith(".html"):
        return
    visited.add(url)
    count[0] += 1
    print(f"[{count[0]}/{MAX_PAGES}] Scraping {title} -> {url}")

    try:
        resp = requests.get(url)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"Skipping {url} (HTTP error {e})")
        return
    except requests.exceptions.RequestException as e:
        print(f"Skipping {url} (Request failed: {e})")
        return

    print(f"Scraping {title} -> {url}")
    soup = BeautifulSoup(resp.text, "html.parser")

    # main content only
    main = soup.find("main", id="wb-cont") or soup

    # skip archived pages
    if "ARCHIVED" in main.get_text():
        print(f"Skipping archived page: {url}")
        return

    # attempt to extract publication date from meta tags
    date_published = None
    for meta_name in ["datePublished", "DC.date", "article:published_time"]:
        tag = soup.find("meta", {"name": meta_name}) or soup.find("meta", {"property": meta_name})
        if tag and tag.get("content"):
            date_published = tag["content"]
            break

    # ---------- HYBRID: PAGE-LEVEL ENTRY ----------
    # create a single document representing the entire page (useful for archival / full-page retrieval)
    page_content = main.get_text("\n", strip=True)
    if page_content:
        docs.append({
            "id": str(uuid.uuid4()),
            "title": title,
            "section": "",  # empty for full page
            "content": page_content,
            "source": "IRCC",
            "date_published": date_published,
            "date_scraped": str(date.today()),
            "granularity": "page"  # page-level entry
        })

    # break content by h2 sections instead of one blob (section-level entries for RAG / fine-grained retrieval)
    for section in main.find_all("h2"):
        heading = section.get_text(strip=True)
        texts = []
        for sib in section.find_next_siblings():
            if sib.name == "h2":
                break
            if sib.name in ["p", "li"]:
                txt = sib.get_text(strip=True)
                if txt:
                    texts.append(txt)

        if texts:
            docs.append({
                "id": str(uuid.uuid4()),
                "title": title,
                "section": heading,
                "content": "\n".join(texts),
                "source": "IRCC",
                "date_published": date_published,
                "date_scraped": str(date.today()),
                "granularity": "section"  # section-level entry
            })

    # crawl sub-links only if they match allowed patterns
    if depth > 0:
        base = "https://www.canada.ca"
        for a in main.select("a[href]"):
            href = a["href"]
            if any(href.startswith(p) for p in ALLOWED_PREFIXES):
                sub_url = base + href if href.startswith("/") else href
                sub_title = a.get_text(strip=True) or "Untitled"
                scrape_ircc_page(sub_title, sub_url, depth=depth-1, visited=visited)

# run
for title, url in IRCC_PAGES.items():
    scrape_ircc_page(title, url, depth=2)

# ---------- CHECK DATA ----------
print("Database filled. Example rows:")
for row in docs[:5]:
    print((row["id"], row["source"], row["title"], row["section"], row["content"][:100], row.get("granularity"), row["date_published"], row["date_scraped"]))

# ---------- EXPORT TO JSON ----------
output_file = "immigration_data.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(docs, f, ensure_ascii=False, indent=2)

print(f"Exported {len(docs)} records to {output_file}")

# ---------- UPLOAD TO S3 ----------
s3 = boto3.client("s3")

bucket_name = "raw-immigreation-documents"
s3_key = "immigration_data.json"  # path inside S3 bucket

s3.upload_file(output_file, bucket_name, s3_key)

print(f"Uploaded {output_file} to s3://{bucket_name}/{s3_key}")