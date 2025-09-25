import requests
import sqlite3
import xml.etree.ElementTree as ET

# -------------------------------
# Scraping V1 for just IRPA and IRPR
# -------------------------------
laws = {
    "IRPA": "https://laws-lois.justice.gc.ca/eng/XML/I-2.5.xml",
    "IRPR": "https://laws-lois.justice.gc.ca/eng/XML/SOR-2002-227.xml"
}

db_file = "immigration_laws.db"

# -------------------------------
# DB Setup
# -------------------------------
conn = sqlite3.connect(db_file)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS laws (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    law_name TEXT,
    section_number TEXT,
    heading TEXT,
    content TEXT
)
""")

# -------------------------------
# Helper: Parse XML and Save
# -------------------------------
def parse_and_store(law_name, xml_url):
    print(f"Fetching {law_name}...")
    r = requests.get(xml_url)
    r.raise_for_status()

    root = ET.fromstring(r.content)

    # The XML has nested <Section> and <Subsection> tags
    for section in root.findall(".//Section"):
        number = section.findtext("Num", default="")
        heading = section.findtext("Heading", default="")
        content = " ".join(section.itertext()).strip()

        c.execute("""
            INSERT INTO laws (law_name, section_number, heading, content)
            VALUES (?, ?, ?, ?)
        """, (law_name, number, heading, content))

    conn.commit()
    print(f"Stored {law_name} successfully.")

# -------------------------------
# Run for each law
# -------------------------------
for law_name, xml_url in laws.items():
    parse_and_store(law_name, xml_url)

print("All laws saved into SQLite.")
