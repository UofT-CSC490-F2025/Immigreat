import requests
import sqlite3
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re

# ---------- DATABASE SETUP ----------
conn = sqlite3.connect("immigration.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT,
    title TEXT,
    section TEXT,
    text TEXT,
    url TEXT
)
""")
conn.commit()

# ---------- PART 1: JUSTICE LAWS (IRPA + IRPR) ----------
JUSTICE_XMLS = {
    "IRPA": "https://laws-lois.justice.gc.ca/eng/XML/I-2.5.xml",
    "IRPR": "https://laws-lois.justice.gc.ca/eng/XML/SOR-2002-227.xml"
}


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
    sections = root.findall(section_path, ns) + root.findall(subsection_path, ns)
    print(f"  Found {len(sections)} sections/subsections in {law_name}")

    for section in sections:
        number = section.findtext(num_path, default="", namespaces=ns)
        heading = section.findtext(heading_path, default="", namespaces=ns)

        # Prefer <Text> blocks over raw itertext
        texts = []
        for t in section.findall(text_path, ns):
            if t.text:
                texts.append(t.text.strip())
        if not texts:
            texts = [t.strip() for t in section.itertext() if t.strip()]

        content = " ".join(texts)

        cur.execute("""
            INSERT INTO documents (source, title, section, text, url)
            VALUES (?, ?, ?, ?, ?)
        """, (law_name, heading, number, content, xml_url))

    conn.commit()
    print(f"Stored {law_name} successfully.")

# Run for each law
for law_name, xml_url in JUSTICE_XMLS.items():
    parse_and_store(law_name, xml_url)

# ---------- PART 2: IRCC WEB PAGES ----------
IRCC_PAGES = {
    "Application Overview": "https://www.canada.ca/en/immigration-refugees-citizenship/services/application.html",
    "Program Delivery Instructions": "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/publications-manuals/operational-bulletins-manuals.html"
}

def scrape_ircc_page(title, url, depth=1):
    """
    Scrape a page and optionally follow links to subpages.
    depth=0 -> only this page
    depth=1 -> this page + one level of subpages
    """
    print(f"Scraping {title} -> {url}")
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Collect text from headings + paragraphs
    content = []
    for tag in soup.find_all(["h1", "h2", "h3", "p", "li"]):
        text = tag.get_text(strip=True)
        if text:
            content.append(text)

    full_text = "\n".join(content)
    cur.execute("""
        INSERT INTO documents (source, title, section, text, url)
        VALUES (?, ?, ?, ?, ?)
    """, ("IRCC", title, "N/A", full_text, url))
    conn.commit()

    # If depth > 0, crawl sub-links
    if depth > 0:
        base = "https://www.canada.ca"
        for a in soup.select("a[href]"):
            href = a["href"]
            if href.startswith("/en/immigration-refugees-citizenship/"):
                sub_url = base + href
                sub_title = a.get_text(strip=True) or "Untitled"
                scrape_ircc_page(sub_title, sub_url, depth=0)  # don’t recurse infinitely

for title, url in IRCC_PAGES.items():
    scrape_ircc_page(title, url, depth=1)

# ---------- CHECK DATA ----------
print("Database filled. Example rows:")
for row in cur.execute("SELECT source, title, section, substr(text, 1, 100) FROM documents LIMIT 5"):
    print(row)

conn.close()