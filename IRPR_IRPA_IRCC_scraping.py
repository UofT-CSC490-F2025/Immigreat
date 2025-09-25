import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re
import json
import boto3

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
        section_path = ".//ns:Section"
        subsection_path = ".//ns:Subsection"
        num_path = "ns:Num"
        heading_path = "ns:Heading"
        text_path = ".//ns:Text"
    else:
        ns = {}
        section_path = ".//Section"
        subsection_path = ".//Subsection"
        num_path = "Num"
        heading_path = "Heading"
        text_path = ".//Text"

    # Collect both Section and Subsection elements
    # TODO make this actually work instead of these placeholder entries
    sections = root.findall(section_path, ns) + root.findall(subsection_path, ns)
    print(f"  Found {len(sections)} sections/subsections in {law_name}")

    for i, section in enumerate(sections, start=1):
        number = section.findtext(num_path, default="", namespaces=ns).strip()
        heading = section.findtext(heading_path, default="", namespaces=ns).strip()

        # Fallbacks if missing
        if not number:
            number = f"Sec-{i}"
        if not heading:
            heading = f"{law_name} Section {number}"

        # Prefer <Text> blocks over raw itertext
        texts = []
        for t in section.findall(text_path, ns):
            if t.text:
                texts.append(t.text.strip())
        if not texts:
            texts = [t.strip() for t in section.itertext() if t.strip()]

        content = " ".join(texts)

        docs.append({
            "source": law_name,
            "title": heading,
            "section": number,
            "text": content,
            "url": xml_url
        })

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
MAX_PAGES = 200

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

    # break content by h2 sections instead of one blob
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
                "source": "IRCC",
                "title": title,
                "section": heading,
                "text": "\n".join(texts),
                "url": url
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
    print((row["source"], row["title"], row["section"], row["text"][:100]))

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
