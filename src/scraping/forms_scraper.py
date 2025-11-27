import requests
from pypdf import PdfReader
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import json
import os
import uuid
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import hashlib
import traceback
import boto3
from scraping.utils import resolve_output_path

from .constants import (
    FORMS_WEBPAGES,
    S3_BUCKET_NAME,
    S3_FORMS_DATA_KEY,
    HTTP_TIMEOUT_SHORT,
    HTTP_TIMEOUT_LONG,
    PDF_KEYWORDS,
    DEFAULT_FORMS_OUTPUT,
    DATE_FORMAT
)

# Read from environment variables (set by Lambda) or fall back to constants
TARGET_S3_BUCKET = os.getenv("TARGET_S3_BUCKET", S3_BUCKET_NAME)
TARGET_S3_KEY = os.getenv("TARGET_S3_KEY", S3_FORMS_DATA_KEY)

# ----------------------
# Utilities
# ----------------------
def now_date() -> str:
    return datetime.now(timezone.utc).strftime(DATE_FORMAT)

def make_hash(entry: dict) -> str:
    """Create a stable hash for deduplication from title, section, content, source."""
    s = f"{entry.get('title','')}||{entry.get('section','')}||{entry.get('content','')}||{entry.get('source','')}"
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

# ----------------------
# PDF discovery
# ----------------------
def get_latest_pdf_from_page(page_url: str, keywords: list | None = None, prefer_text_keyword: bool = False) -> str | None:
    """
    Fetch HTML and find pdf links. keywords: list of substrings to filter href/text.
    prefer_text_keyword: if True, also checks anchor text for keyword matches (useful when href obfuscated).
    Returns absolute PDF URL or None.
    """
    try:
        resp = requests.get(page_url, timeout=HTTP_TIMEOUT_SHORT)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Failed to fetch page {page_url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    candidates = []

    for a in soup.find_all("a", href=True):
        href = a['href'].strip()
        href_lower = href.lower()
        if not href_lower.endswith(".pdf"):
            continue
        full = urljoin(page_url, href)

        if keywords is None:
            candidates.append((full, a.get_text(strip=True)))
        else:
            # accept if any keyword in href OR (optionally) anchor text
            match = any(kw.lower() in href_lower for kw in keywords)
            if not match and prefer_text_keyword:
                txt = a.get_text(" ", strip=True).lower()
                match = any(kw.lower() in txt for kw in keywords)
            if match:
                candidates.append((full, a.get_text(strip=True)))

    if not candidates:
        print(f"No PDF links found on page: {page_url}")
        return None

    # Heuristics to pick the "latest":
    # - If multiple, try to pick one with a date-like substring (YYYY or YYYY-MM).
    # - Otherwise pick first encountered (often newest on IRCC pages).
    def score_candidate(item):
        url, text = item
        u = url.lower()
        score = 0
        # prefer year strings
        for y in range(1990, 2031):
            ys = str(y)
            if ys in u:
                score += 10
        # prefer keyword presence (already filtered)
        # prefer shorter path (likely canonical)
        score -= len(u.split('/'))
        return score

    candidates.sort(key=score_candidate, reverse=True)
    chosen = candidates[0][0]
    print(f"Latest PDF found for {page_url}: {chosen}")
    return chosen

# ----------------------
# XFA parsing helpers
# ----------------------
def try_parse_xml_safe(xml_text: str):
    """Return ElementTree root or None on failure (wrap in try since many packets may not be XML)."""
    try:
        return ET.fromstring(xml_text)
    except Exception:
        return None

def extract_xfa_fields_from_xml_root(root: ET.Element, pdf_url: str, date_scraped: str):
    """
    Given an ElementTree root of an XFA form packet (likely 'form' or similar),
    extract field entries robustly using namespace handling.
    """
    entries = []
    # derive namespace map if present
    ns = {}
    if root.tag.startswith("{"):
        uri = root.tag[root.tag.find("{")+1:root.tag.find("}")]
        ns = {'xfa': uri}
    else:
        ns = {}

    # Collect all <field> elements and determine their nearest ancestor subform name by walking up.
    # Build mapping of element -> parent using manual tree walk to enable ancestor lookup.
    parent_map = {c: p for p in root.iter() for c in p}
    # collect all field elements
    field_elems = []
    if ns:
        field_elems = root.findall(".//xfa:field", ns)
    else:
        field_elems = root.findall(".//field")

    for field in field_elems:
        # find nearest ancestor subform node that has a name attribute
        ancestor = field
        section_parts = []
        while ancestor is not None and ancestor is not root:
            ancestor = parent_map.get(ancestor)
            if ancestor is None:
                break
            # tag match for subform (namespace-aware)
            tag_clean = ancestor.tag
            if isinstance(tag_clean, str) and tag_clean.lower().endswith("subform"):
                nm = ancestor.attrib.get("name")
                if nm:
                    section_parts.insert(0, nm)
        section = " > ".join(section_parts) if section_parts else "MainForm"

        # original field name
        original_field_name = field.attrib.get("name", "") or ""

        # caption handling: prefer caption/value/text but be resilient
        caption_text = ""
        if ns:
            caption_node = field.find(".//xfa:caption", ns)
        else:
            caption_node = field.find(".//caption")
        if caption_node is not None:
            # try to grab text children
            # check multiple possible nested paths
            texts = []
            for txt in caption_node.findall(".//", ns) if ns else caption_node.findall(".//"):
                # pick elements whose tag ends with 'text' or contains textual value
                taglow = txt.tag.lower()
                if isinstance(taglow, str) and taglow.endswith("text"):
                    if txt.text and txt.text.strip():
                        texts.append(txt.text.strip())
            if texts:
                caption_text = " ".join(texts)

        # options: find any items/text child nodes
        options = []
        if ns:
            items_nodes = field.findall(".//xfa:items", ns)
        else:
            items_nodes = field.findall(".//items")
        for items in items_nodes:
            if ns:
                text_nodes = items.findall("xfa:text", ns)
            else:
                text_nodes = items.findall("text")
            for t in text_nodes:
                if t.text and t.text.strip():
                    options.append(t.text.strip())

        content = ", ".join(options) if options else (caption_text or original_field_name or "")

        entry = {
            "id": str(uuid.uuid4()),
            "title": original_field_name,
            "section": section,
            "content": content,
            "source": pdf_url,
            "date_published": None,
            "date_scraped": date_scraped,
            "granularity": "field-level"
        }
        entries.append(entry)

    return entries

# ----------------------
# Main PDF extraction
# ----------------------
def extract_fields_from_pdf(pdf_url: str) -> list:
    """
    Extract XFA or AcroForm fields from a pdf URL. Return list of entries.
    """
    print(f"Fetching PDF: {pdf_url}")
    try:
        resp = requests.get(pdf_url, stream=True, timeout=HTTP_TIMEOUT_LONG)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Failed to fetch PDF {pdf_url}: {e}")
        return []

    try:
        pdf_bytes = io.BytesIO(resp.content)
        reader = PdfReader(pdf_bytes)
    except Exception as e:
        print(f"❌ pypdf failed to read PDF {pdf_url}: {e}")
        return []

    date_scraped = now_date()
    all_entries = []

    # 1) XFA extraction (robust: try all packets that might contain XML)
    xfa = reader.xfa

    if xfa:
        # xfa can be list or dict or other. Try to find candidate XML blobs.
        xml_candidates = []

        # list style (alternating name, bytes)
        if isinstance(xfa, list):
            for i in range(0, len(xfa), 2):
                # Decode XFA entries (errors='ignore' ensures decode won't raise)
                name = xfa[i].decode("utf-8", errors="ignore") if isinstance(xfa[i], (bytes, bytearray)) else str(xfa[i])
                blob = xfa[i+1]
                blob_text = blob.decode("utf-8", errors="ignore") if isinstance(blob, (bytes, bytearray)) else str(blob)
                xml_candidates.append((name, blob_text))

        # dict style
        elif isinstance(xfa, dict):
            for k, v in xfa.items():
                txt = v if isinstance(v, str) else v.decode("utf-8", errors="ignore")
                xml_candidates.append((k, txt))

        # prioritize 'form' packet if present
        form_candidate = next((t for t in xml_candidates if t[0].lower() == "form"), None)
        parsed_entries = []
        if form_candidate:
            root = try_parse_xml_safe(form_candidate[1])
            if root is not None:
                parsed_entries = extract_xfa_fields_from_xml_root(root, pdf_url, date_scraped)
        else:
            # try parse each candidate, collecting fields if parse succeeds
            for name, txt in xml_candidates:
                root = try_parse_xml_safe(txt)
                if root is None:
                    continue
                parsed_entries.extend(extract_xfa_fields_from_xml_root(root, pdf_url, date_scraped))

        if parsed_entries:
            print(f"✅ Extracted {len(parsed_entries)} XFA fields from {pdf_url}")
            return parsed_entries
        else:
            # fall through to AcroForm if no XFA fields found
            print(f"ℹ️ XFA present but no fields parsed for {pdf_url}. Trying AcroForm fallback.")
    else:
        print(f"ℹ️ No XFA in PDF: {pdf_url}. Trying AcroForm extraction.")

    # 2) AcroForm extraction
    acro_entries = []
    try:
        # pypdf's get_fields may return dict or None
        fields = reader.get_fields() if hasattr(reader, 'get_fields') else None

        if fields:
            # fields is a dict mapping fieldname -> field dict or value
            for name, meta in fields.items():
                field_uuid = str(uuid.uuid4())
                # meta might be a dict: look for '/V' or 'V' or direct string
                value = ""
                if isinstance(meta, dict):
                    # common keys: '/V', 'V'
                    value = meta.get('/V') or meta.get('V') or meta.get('value') or ""
                    if isinstance(value, bytes):
                        value = value.decode('utf-8', errors='ignore')
                else:
                    # sometimes meta is the string value
                    value = str(meta)
                content = value if value else str(name)
                acro_entries.append({
                    "id": str(uuid.uuid4()),
                    "title": name,
                    "section": "AcroForm",
                    "content": content,
                    "source": pdf_url,
                    "date_published": None,
                    "date_scraped": date_scraped,
                    "granularity": "field-level"
                })

            if acro_entries:
                print(f"✅ Extracted {len(acro_entries)} AcroForm fields from {pdf_url}")
                return acro_entries
    except Exception as e:
        print(f"⚠️ Error while extracting AcroForm fields: {e}\n{traceback.format_exc()}")

    # 3) Last-resort: text extraction heuristic (best-effort)
    try:
        text_chunks = []
        for p in reader.pages:
            try:
                txt = p.extract_text() or ""
                if txt.strip():
                    text_chunks.append(txt)
            except Exception:
                continue
        full_text = "\n".join(text_chunks)
        if full_text.strip():
            # crude heuristic: split on lines that look like questions (lines ending with '?', or lines with ":" and short length)
            lines = [l.strip() for l in full_text.splitlines() if l.strip()]
            # keep 200 most relevant lines
            heuristics = []
            for line in lines:
                if len(line) < 300 and (line.endswith('?') or ':' in line or len(line.split()) < 8):
                    heuristics.append(line)
            heuristics = heuristics[:200]
            if heuristics:
                fallback_entries = []
                for ln in heuristics:
                    fallback_entries.append({
                        "id": str(uuid.uuid4()),
                        "title": ln[:80],
                        "section": "PageTextHeuristic",
                        "content": ln,
                        "source": pdf_url,
                        "date_published": None,
                        "date_scraped": date_scraped,
                        "granularity": "page-level"
                    })
                print(f"ℹ️ Fallback: created {len(fallback_entries)} heuristic text entries for {pdf_url}")
                return fallback_entries
    except Exception:
        pass

    print(f"No usable fields found for {pdf_url}")
    return []

# ----------------------
# Multi-page orchestrator
# ----------------------
def extract_fields_from_webpages(page_urls: list, output_file: str = "all_forms.json", pdf_keywords: list | None = None,
                                 prefer_text_keyword: bool = False, dedupe: bool = True):
    """
    Top-level function to process many pages, find latest pdfs, extract fields, and append to JSON.
    - pdf_keywords: list of keyword substrings to filter pdf links (e.g., ["imm", "cit"])
    - prefer_text_keyword: if True, anchor text also used for keyword matching
    - dedupe: deduplicate using hash(title,section,content,source)
    """
    saved = []
    existing_hashes = set()

    output_file = resolve_output_path(output_file)

    # load existing file
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if dedupe:
                existing_hashes = {make_hash(e) for e in saved}
        except Exception:
            saved = []
            existing_hashes = set()

    for page in page_urls:
        try:
            pdf_url = get_latest_pdf_from_page(page, keywords=pdf_keywords, prefer_text_keyword=prefer_text_keyword)
            if not pdf_url:
                continue
            entries = extract_fields_from_pdf(pdf_url)
            for e in entries:
                h = make_hash(e)
                if dedupe and h in existing_hashes:
                    continue
                existing_hashes.add(h)
                saved.append(e)
        except Exception as e:
            print(f"❌ Error processing page {page}: {e}")
            continue

    # write out
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(saved, f, ensure_ascii=False, indent=2)

    print(f"✅ Done. Total entries saved in {output_file}: {len(saved)}")
    # ---------- UPLOAD TO S3 ----------
    s3 = boto3.client("s3")
    s3.upload_file(output_file, TARGET_S3_BUCKET, TARGET_S3_KEY)
    print(f"Uploaded {output_file} to s3://{TARGET_S3_BUCKET}/{TARGET_S3_KEY}")
    return saved

