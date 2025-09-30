import requests
from pypdf import PdfReader
import io
import xml.etree.ElementTree as ET
from datetime import datetime
import json
import os
import uuid
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def get_latest_pdf_from_page(page_url, keywords=None):
    """
    Fetches the HTML page and finds the latest PDF link.
    Optionally filters by a list of keywords in href.
    """
    response = requests.get(page_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    pdf_links = []

    for a in soup.find_all("a", href=True):
        href = a['href']
        if href.lower().endswith(".pdf"):
            if keywords is None or any(kw.lower() in href.lower() for kw in keywords):
                pdf_links.append(urljoin(page_url, href))

    if not pdf_links:
        print(f"No PDF links found on page: {page_url}")
        return None

    latest_pdf = pdf_links[0]  # First link assumed latest
    print(f"Latest PDF found for {page_url}: {latest_pdf}")
    return latest_pdf


def extract_fields_from_pdf(pdf_url: str):
    """
    Extract fields from a single PDF and return them as a list of dicts.
    """
    print(f"Fetching PDF: {pdf_url}")
    response = requests.get(pdf_url, stream=True)
    response.raise_for_status()

    pdf_bytes = io.BytesIO(response.content)
    reader = PdfReader(pdf_bytes)
    xfa = reader.xfa
    if not xfa:
        print(f"No XFA data found in PDF: {pdf_url}")
        return []

    # Extract form.xml
    form_xml = None
    if isinstance(xfa, list):
        for i in range(0, len(xfa), 2):
            packet_name = xfa[i].decode("utf-8", errors="ignore")
            if packet_name == "form":
                form_xml = xfa[i+1].decode("utf-8", errors="ignore")
                break
    elif isinstance(xfa, dict) and "form" in xfa:
        data = xfa["form"]
        form_xml = data if isinstance(data, str) else data.decode("utf-8", errors="ignore")

    if not form_xml:
        print(f"form.xml not found in PDF: {pdf_url}")
        return []

    root = ET.fromstring(form_xml)
    date_scraped = datetime.today().strftime("%Y-%m-%d")
    entries = []

    ns = {'xfa': root.tag[root.tag.find("{")+1:root.tag.find("}")]} if "{" in root.tag else {}

    def recurse_subform(node, parent_section="MainForm"):
        section_name = node.attrib.get("name", parent_section)

        for field in node.findall(".//xfa:field", ns):
            field_uuid = str(uuid.uuid4())
            original_field_name = field.attrib.get("name", "")

            # Extract dropdown/options
            options = []
            for items in field.findall(".//xfa:items", ns):
                for text_elem in items.findall("xfa:text", ns):
                    if text_elem.text and text_elem.text.strip():
                        options.append(text_elem.text.strip())
            content = ", ".join(options) if options else original_field_name

            entry = {
                "id": field_uuid,
                "title": original_field_name,
                "section": section_name,
                "content": content,
                "source": pdf_url,
                "date_published": None,
                "date_scraped": date_scraped,
                "granularity": "field-level"
            }
            entries.append(entry)

        for sub in node.findall("xfa:subform", ns):
            recurse_subform(sub, section_name)

    for subform in root.findall("xfa:subform", ns):
        recurse_subform(subform)

    print(f"✅ Extracted {len(entries)} fields from {pdf_url}")
    return entries

def extract_fields_from_webpages(page_urls: list, output_file: str = "all_forms.json", pdf_keywords=None):
    """
    Extract fields from multiple web pages containing PDFs and append to a single JSON.
    """
    all_entries = []

    # Load existing JSON if it exists
    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            all_entries = json.load(f)

    for page_url in page_urls:
        pdf_url = get_latest_pdf_from_page(page_url, keywords=pdf_keywords)
        if pdf_url:
            entries = extract_fields_from_pdf(pdf_url)
            all_entries.extend(entries)

    # Save all entries to JSON
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)

    print(f"✅ Total entries saved in {output_file}: {len(all_entries)}")
    return all_entries

# --------------------------
# Example usage
# --------------------------
if __name__ == "__main__":
    webpages = [
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5710.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1295.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5583.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5709.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5686.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5708.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5557.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/cit0001.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/cit0002.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/cit0003.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1344.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5533.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5257.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5645.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5409.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5476.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5475.html"

    ]
    extract_fields_from_webpages(webpages, "all_forms.json", pdf_keywords=["imm", "cit"])
