# --- Dependencies ---
import os
import re
import time
import json
import uuid
import hashlib
import random
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse as dateparse
import urllib.robotparser as robotparser
import boto3
from .utils import resolve_output_path

from .constants import (
    IRCC_URLS,
    S3_BUCKET_NAME,
    S3_IRCC_DATA_KEY,
    HTTP_TIMEOUT_LONG as REQUESTS_TIMEOUT,
    MIN_REQUEST_DELAY as MIN_DELAY,
    MAX_REQUEST_DELAY as MAX_DELAY,
    BROWSER_TIMEOUT,
    USER_AGENT,
    MIN_CONTENT_LENGTH,
    DEFAULT_IRCC_OUTPUT
)

# Expose a module-level symbol so tests can patch it directly.
# When not provided, we import lazily within render function.
try:
    from playwright.sync_api import sync_playwright as _sync_playwright
except Exception:
    _sync_playwright = None

# Alias used by tests: they patch scraping.ircc_scraper.sync_playwright
sync_playwright = _sync_playwright

def is_useful_content(text: str) -> bool:
    """Heuristic filter for meaningful IRCC content."""
    if not text or len(text.strip()) < MIN_CONTENT_LENGTH:  # too short
        return False
    junk_markers = [
        "We have archived this page",
        "will not be updating it",
        "Section A – Applicant",
        "Section B –",
        "PDF form",
        "Fill out",
    ]
    for m in junk_markers:
        if m.lower() in text.lower():
            return False
    return True

# Optional Playwright availability based on module-level alias
PLAYWRIGHT_AVAILABLE = sync_playwright is not None

# --- Configuration ---

OUTPUT_FILE = os.getenv("SCRAPE_DEFAULT_OUTPUT", DEFAULT_IRCC_OUTPUT)
CRAWL_SUBPAGES = True   # follow news/article links from listing pages
MAX_SUBPAGE_PER_PAGE = 30

TARGET_S3_BUCKET = os.getenv("TARGET_S3_BUCKET", S3_BUCKET_NAME)
TARGET_S3_KEY = os.getenv("TARGET_S3_KEY", S3_IRCC_DATA_KEY)
S3_CLIENT = boto3.client("s3")

# --- Helpers ---
def read_robots(base_url, user_agent=USER_AGENT):
    """Return RobotFileParser for domain (or None if failed)."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp
    except Exception:
        return None

def allowed_by_robots(url, rp_cache={}):
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    rp = rp_cache.get(base)
    if rp is None:
        rp = read_robots(base)
        rp_cache[base] = rp
    if rp is None:
        # if robots unreadable, be conservative and allow (or choose to block)
        return True
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True

def requests_get(session, url):
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    return session.get(url, headers=headers, timeout=REQUESTS_TIMEOUT)

def render_with_playwright(url):
    """Render page with Playwright and return HTML (requires playwright installed).

    Uses module-level sync_playwright for easier test patching; falls back to lazy import if missing.
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not installed")
    global sync_playwright
    if sync_playwright is None:
        try:
            from playwright.sync_api import sync_playwright as _local_sync
            sync_playwright = _local_sync
        except Exception as e:
            raise RuntimeError("Playwright not installed") from e
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT, timeout=BROWSER_TIMEOUT)
        page.goto(url, wait_until="networkidle")
        html = page.content()
        browser.close()
        return html

def detect_requires_js(html_text):
    """Heuristic: detect if content says JS required or modern widget placeholders."""
    if not html_text:
        return True
    markers = [
        "You need a browser that supports JavaScript",
        "JavaScript must be enabled",
        "This page requires JavaScript",
        "Enable JavaScript",
        "Check our current processing times",  # processing times uses JS widget
    ]
    for m in markers:
        if m.lower() in html_text.lower():
            return True
    return False

def parse_date_published(soup):
    """Try common meta tags and 'Date modified' text on Canada.ca pages."""
    # meta tags to try in order
    meta_props = [
        ('meta', {'property': 'article:published_time'}),
        ('meta', {'name': 'dcterms.date'}),
        ('meta', {'name': 'DC.date.issued'}),
        ('meta', {'name': 'date'}),
        ('meta', {'itemprop': 'datePublished'}),
        ('meta', {'name': 'Date'}),
        ('meta', {'property': 'og:updated_time'}),
    ]
    for tag, attrs in meta_props:
        el = soup.find(tag, attrs=attrs)
        if el:
            content = el.get('content') or el.get('value') or el.text
            if content:
                try:
                    return dateparse(content).date().isoformat()
                except Exception:
                    pass
    # Look for <time datetime="">
    t = soup.find('time')
    if t:
        dt = t.get('datetime') or t.text
        try:
            return dateparse(dt).date().isoformat()
        except Exception:
            pass
    # Look for "Date modified" blocks on Canada.ca pages
    text = soup.get_text(separator=" ", strip=True)
    m = re.search(r'Date (?:modified|updated)[:\s]*([A-Za-z0-9,\- ]{6,60})', text, flags=re.I)
    if m:
        candidate = m.group(1).strip()
        try:
            return dateparse(candidate).date().isoformat()
        except Exception:
            pass
    return None

def extract_sections_from_main(soup):
    """
    Returns a list of {'section': str or None, 'content': str}.
    Tightened to avoid nav/footer cruft.
    """
    main = soup.find('main') or soup.find(attrs={'role': 'main'}) or soup.body
    if main is None:
        return []

    # Remove cruft
    for selector in [
        'nav', 'footer', 'header',
        '.breadcrumb', '.breadcrumbs',
        '.share', '.skip-nav',
        'form', 'aside'
    ]:
        for el in main.select(selector):
            el.decompose()

    headings = main.find_all(['h2', 'h3'])
    sections = []
    if not headings:
        parts = [el.get_text(" ", strip=True) for el in main.find_all(['p', 'li'])]
        content = "\n\n".join([p for p in parts if is_useful_content(p)])
        if content:
            sections.append({'section': None, 'content': content})
        return sections

    for h in headings:
        title = h.get_text(strip=True)
        parts = []
        for sib in h.next_siblings:
            if getattr(sib, 'name', None) in ['h2', 'h3']:
                break
            if getattr(sib, 'name', None) in ['p', 'ul', 'ol', 'div', 'table']:
                txt = sib.get_text(" ", strip=True)
                if is_useful_content(txt):
                    parts.append(txt)
        content = "\n\n".join(parts).strip()
        if content:
            sections.append({'section': title, 'content': content})
    return sections

def make_record(url, title, section_title, content, date_published):
    """Create the JSON record with deterministic id (sha256 of source+section)."""
    base = (url + "||" + (section_title or "")).encode("utf-8")
    uid = hashlib.sha256(base).hexdigest()
    record = {
        "id": uid,
        "title": title or "",
        "section": section_title or "",
        "content": content or "",
        "source": url,
        "date_published": date_published,
        "date_scraped": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "granularity": "section" if section_title else "page",
    }
    return record

# --- Core scraping functions ---
def fetch_html(url, session, use_playwright=True):
    """Fetch page HTML. Try requests first; if heuristics indicate JS required or requests fails,
       try Playwright (if available)."""
    r = None
    try:
        r = requests_get(session, url)
        if r.status_code == 200 and r.text and not detect_requires_js(r.text):
            return r.text
        # if content short or indicates JS requirement, try Playwright
    except Exception as e:
        # fallthrough to playwright if available
        pass
    if use_playwright and PLAYWRIGHT_AVAILABLE:
        try:
            html = render_with_playwright(url)
            return html
        except Exception as e:
            print(f"[WARNING] Playwright render failed for {url}: {e}")
    # last attempt: return requests text if available
    if r is not None:
        return r.text
    raise RuntimeError(f"Failed to fetch {url}")

def is_listing_page(soup):
    """Heuristic: pages with multiple links to news/articles (news or notices)"""
    # If main has many <a> tags with /news/ or '/immigration-refugees-citizenship/news'
    main = soup.find('main') or soup.body
    if not main:
        return False
    anchors = main.find_all('a', href=True)
    if len(anchors) > 25:
        return True
    # check for news list patterns
    for a in anchors[:50]:
        href = a['href']
        if '/news/' in href or '/news/' in urljoin('', href):
            return True
    return False

def find_internal_article_links(soup, base_url, limit=MAX_SUBPAGE_PER_PAGE):
    """Collect internal canada.ca article links efficiently.

    Why it's important: Link extraction runs for many pages; the original version performed
    O(n^2) de-duplication using a list membership check. Switching to a set avoids quadratic
    behavior on large pages and speeds up crawling.
    """
    main = soup.find('main') or soup.body
    anchors = main.find_all('a', href=True)

    # Use a set for O(1) de-dup checks
    seen = set()
    results = []

    for a in anchors:
        href = a['href']
        if not href or href.startswith(('#', 'mailto:', 'tel:')):
            continue
        full = urljoin(base_url, href)
        if full == base_url:
            continue
        parsed = urlparse(full)
        if not parsed.netloc.endswith('canada.ca'):
            continue
        path = parsed.path

        # Heuristics for likely article content
        if ('/news/' in path or
                '/immigration-refugees-citizenship/news' in path or
                '/services/' in path or
                path.endswith('.html')):
            if full not in seen:
                seen.add(full)
                results.append(full)
                if len(results) >= limit:
                    break

    return results

def scrape_page(url, visited, session, crawl_subpages=False):
    """Scrape a single page; returns list of records."""
    print(f"[INFO] Scraping {url}")
    if not allowed_by_robots(url):
        print(f"[WARNING] Blocked by robots.txt: {url}")
        return []

    html = fetch_html(url, session, use_playwright=True)
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find('h1') or soup.find('title')
    title = title_tag.get_text(strip=True) if title_tag else ""
    date_pub = parse_date_published(soup)

    records = []
    sections = extract_sections_from_main(soup)
    if not sections:
        text = soup.get_text("\n\n", strip=True)
        if is_useful_content(text):
            records.append(make_record(url, title, None, text, date_pub))
    else:
        for sec in sections:
            if is_useful_content(sec['content']):
                rec = make_record(url, title, sec['section'], sec['content'], date_pub)
                records.append(rec)

    # Crawl subpages if listing
    if crawl_subpages and is_listing_page(soup):
        article_links = find_internal_article_links(soup, url)
        print(f"[INFO] Found {len(article_links)} article links on {url}")
        for link in article_links:
            if link in visited:
                continue
            visited.add(link)
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            try:
                records += scrape_page(link, visited, session, crawl_subpages=False)
            except Exception as e:
                print(f"[WARNING] Subpage scrape failed {link}: {e}")
    return records

def scrape_all(urls, out_path=OUTPUT_FILE, crawl_subpages=CRAWL_SUBPAGES):
    visited = set()
    out_path = resolve_output_path(out_path)
    session = requests.Session()
    all_records = []
    for url in urls:
        if url in visited:
            print(f"[DEBUG] Already visited {url}")
            continue
        visited.add(url)
        try:
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            recs = scrape_page(url, visited, session, crawl_subpages=crawl_subpages)
            all_records.extend(recs)
        except Exception as e:
            print(f"[ERROR] Failed to scrape {url}: {e}")
    # write JSON Lines
    # write JSON array (not JSON Lines)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(all_records, fh, ensure_ascii=False, indent=2)
    print(f"[INFO] Saved {len(all_records)} records to {out_path}")

    # ---------- UPLOAD TO S3 ----------
    if not TARGET_S3_BUCKET or not TARGET_S3_KEY:
        print(
            "[WARNING] Skipping S3 upload because TARGET_S3_BUCKET or "
            "TARGET_S3_KEY is not configured."
        )
        return all_records

    S3_CLIENT.upload_file(out_path, TARGET_S3_BUCKET, TARGET_S3_KEY)

    print(f"Uploaded {out_path} to s3://{TARGET_S3_BUCKET}/{TARGET_S3_KEY}")

    return all_records
