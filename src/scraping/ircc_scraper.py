IRCC_URLS = [
    "https://www.canada.ca/en/immigration-refugees-citizenship.html",
    "https://www.canada.ca/en/services/immigration-citizenship.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/visit-canada.html",
    "https://ircc.canada.ca/english/information/applications/visa.asp",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/visit-canada/apply-visitor-visa.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/visit-canada/visitor-visa.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/apply-permanent-residence.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/family-sponsorship/spouse-partner-children.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/refugees.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/permanent-residents.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/permanent-residents/card/apply.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/permanent-residents/card.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/citizenship.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/account.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/check-status.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/account/link-paper-online.html",
    "https://ircc.canada.ca/english/helpcentre/index-featured-can.asp",
    "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/contact-ircc.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/contact-ircc/client-support-centre.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/check-processing-times.html",
    "https://ircc.canada.ca/english/information/fees/fees.asp",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/biometrics.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/partners-service-providers/authorized-paid-representatives-portal.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/news.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/news/notices.html",
]

# --- Dependencies ---
import re
import time
import json
import uuid
import hashlib
import random
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse as dateparse
import urllib.robotparser as robotparser
import boto3

def is_useful_content(text: str) -> bool:
    """Heuristic filter for meaningful IRCC content."""
    if not text or len(text.strip()) < 40:  # too short
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

# Optional Playwright renderer
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

# --- Configuration ---
USER_AGENT = "IRCCScraperBot/1.0 (+https://your-org.example)"
REQUESTS_TIMEOUT = 30
MIN_DELAY = 0.5
MAX_DELAY = 1.5
OUTPUT_FILE = "ircc_scrape.json"
CRAWL_SUBPAGES = True   # follow news/article links from listing pages
MAX_SUBPAGE_PER_PAGE = 30
LOG_LEVEL = logging.INFO

# Setup logging
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s: %(message)s")
VISITED = set()

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
    """Render page with Playwright and return HTML (requires playwright installed)."""
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not installed")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT, timeout=60000)
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
            logging.warning("Playwright render failed for %s: %s", url, e)
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
    main = soup.find('main') or soup.body
    anchors = main.find_all('a', href=True)
    links = []
    base_parsed = urlparse(base_url)
    for a in anchors:
        href = a['href']
        if href.startswith('#') or href.startswith('mailto:') or href.startswith('tel:'):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if not parsed.netloc.endswith('canada.ca'):
            continue
        # simple heuristics to avoid CV-intensive links:
        if '/news/' in parsed.path or '/immigration-refugees-citizenship/news' in parsed.path or '/services/' in parsed.path:
            links.append(full)
        # otherwise include if .html and not too deep
        elif parsed.path.endswith('.html'):
            links.append(full)
    # dedupe & limit
    uniq = []
    for u in links:
        if u not in uniq and u != base_url:
            uniq.append(u)
            if len(uniq) >= limit:
                break
    return uniq

def scrape_page(url, session, crawl_subpages=False):
    """Scrape a single page; returns list of records."""
    logging.info("Scraping %s", url)
    if not allowed_by_robots(url):
        logging.warning("Blocked by robots.txt: %s", url)
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
        logging.info("Found %d article links on %s", len(article_links), url)
        for link in article_links:
            if link in VISITED:
                continue
            VISITED.add(link)
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            try:
                records += scrape_page(link, session, crawl_subpages=False)
            except Exception as e:
                logging.warning("Subpage scrape failed %s: %s", link, e)
    return records

def scrape_all(urls, out_path=OUTPUT_FILE, crawl_subpages=CRAWL_SUBPAGES):
    session = requests.Session()
    all_records = []
    for url in urls:
        if url in VISITED:
            logging.debug("Already visited %s", url)
            continue
        VISITED.add(url)
        try:
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            recs = scrape_page(url, session, crawl_subpages=crawl_subpages)
            all_records.extend(recs)
        except Exception as e:
            logging.error("Failed to scrape %s: %s", url, e)
    # write JSON Lines
    with open(out_path, "w", encoding="utf-8") as fh:
        for r in all_records:
            fh.write(json.dumps(r, ensure_ascii=False, indent=2) + "\n")
    logging.info("Saved %d records to %s", len(all_records), out_path)

    # ---------- UPLOAD TO S3 ----------
    s3 = boto3.client("s3")

    bucket_name = "raw-immigreation-documents"
    s3_key = "ircc_scraped_data.json"  # path inside S3 bucket

    s3.upload_file(out_path, bucket_name, s3_key)

    print(f"Uploaded {out_path} to s3://{bucket_name}/{s3_key}")

    return all_records

results = scrape_all(IRCC_URLS, out_path="ircc_scraped_data.json", crawl_subpages=True)
print(f"Scraped {len(results)} records. Saved to ircc_scraped_data.json")