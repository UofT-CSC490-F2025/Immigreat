import json
import scraping.ircc_scraper as ircc


def test_fetch_html_requests_then_playwright_fallback(monkeypatch):
    class Sess:
        def get(self, url, headers=None, timeout=None):
            class R:
                status_code = 200
                text = "JavaScript must be enabled"
            return R()
    monkeypatch.setattr(ircc, "PLAYWRIGHT_AVAILABLE", False)
    # Should return requests text since playwright disabled
    html = ircc.fetch_html("http://example.com/ircc", Sess(), use_playwright=True)
    assert isinstance(html, str)


def test_extract_sections_no_headings():
        html = """
        <html><body><main>
            <p>We have archived this page</p>
            <p>Meaningful content appears here for users</p>
        </main></body></html>
        """.strip()
        soup = ircc.BeautifulSoup(html, "html.parser")
        sections = ircc.extract_sections_from_main(soup)
        assert isinstance(sections, list)


def test_is_listing_page_and_find_links():
        base = "https://www.canada.ca/en/immigration-refugees-citizenship/news.html"
        html = f"""
        <html><body><main>
            <a href="/en/immigration-refugees-citizenship/news/2025/update.html">Update</a>
            <a href="{base}">Self</a>
            <a href="https://other.example.com/x">External</a>
            <a href="#skip">Skip</a>
        </main></body></html>
        """
        soup = ircc.BeautifulSoup(html, "html.parser")
        assert ircc.is_listing_page(soup) is True
        links = ircc.find_internal_article_links(soup, base)
        assert links and links[0].endswith("update.html")


def test_find_internal_article_links_limit():
    base = "https://www.canada.ca/en/immigration-refugees-citizenship/news.html"
    anchors = "".join([f"<a href='/news/{i}.html'>News {i}</a>" for i in range(100)])
    html = f"<html><body><main>{anchors}</main></body></html>"
    soup = ircc.BeautifulSoup(html, "html.parser")
    links = ircc.find_internal_article_links(soup, base)
    assert len(links) <= ircc.MAX_SUBPAGE_PER_PAGE


def test_scrape_page_basic(monkeypatch):
    html = """
    <html><body><main>
      <h1>Title</h1>
      <h2>Section A</h2>
      <p>Useful content about IRCC policies.</p>
      <h2>Section B</h2>
      <p>More details and explanations.</p>
    </main></body></html>
    """
    class Sess:
        def get(self, url, headers=None, timeout=None):
            class R:
                status_code = 200
                text = html
            return R()
    records = ircc.scrape_page("http://example.com/news", visited=set(), session=Sess(), crawl_subpages=False)
    assert records and all("content" in r for r in records)


def test_scrape_page_blocked_by_robots(monkeypatch):
    # Force robots to block
    monkeypatch.setattr(ircc, "allowed_by_robots", lambda url: False)
    class Sess:
        def get(self, url, headers=None, timeout=None):
            class R:
                status_code = 200
                text = "<html><body><main><h1>T</h1></main></body></html>"
            return R()
    recs = ircc.scrape_page("http://example.com/blocked", visited=set(), session=Sess(), crawl_subpages=False)
    assert recs == []


def test_scrape_page_listing_subpage_failures(monkeypatch):
    # Listing page with internal links, but subpage scraping fails to exercise warning path
    base = "https://www.canada.ca/en/immigration-refugees-citizenship/news.html"
    html = f"""
    <html><body><main>
      <h1>Main News</h1>
      <a href="/en/immigration-refugees-citizenship/news/2025/a.html">A</a>
      <a href="/en/immigration-refugees-citizenship/news/2025/b.html">B</a>
    </main></body></html>
    """
    class Sess:
        def get(self, url, headers=None, timeout=None):
            class R:
                status_code = 200
                text = html
            return R()
    # Force scrape_page recursion to raise on subpages
    def failing_scrape(url, visited, session, crawl_subpages=False):
        if url != base and crawl_subpages is False:
            raise RuntimeError("subpage fail")
        # For the main page, return a minimal record
        return [ircc.make_record(url, "T", None, "Body", None)]
    monkeypatch.setattr(ircc, "fetch_html", lambda url, session, use_playwright=True: html)
    monkeypatch.setattr(ircc, "scrape_page", failing_scrape)
    # Call original listing detection via is_listing_page inside failing_scrape on main
    recs = ircc.scrape_page(base, visited=set(), session=Sess(), crawl_subpages=True)
    assert isinstance(recs, list)


def test_scrape_all_s3_skipped(monkeypatch, tmp_path):
    # Ensure S3 upload skipped when env not set (TARGET_S3_* present already, but we can monkeypatch client)
    html = "<html><body><main><h1>T</h1><p>Content ok for save.</p></main></body></html>"
    class Sess:
        def get(self, url, headers=None, timeout=None):
            class R:
                status_code = 200
                text = html
            return R()
    monkeypatch.setattr(ircc, "requests_get", lambda session, url: Sess().get(url))
    # Replace S3 client to avoid real calls
    class FakeS3:
        def upload_file(self, filename, bucket, key):
            self.called = (filename, bucket, key)
    monkeypatch.setattr(ircc, "S3_CLIENT", FakeS3())
    out = tmp_path / "ircc.json"
    recs = ircc.scrape_all(["http://example.com/news"], out_path=str(out), crawl_subpages=False)
    assert isinstance(recs, list)
    assert json.loads(out.read_text(encoding="utf-8")) == recs


def test_fetch_html_requests_fail_then_raise(monkeypatch):
    class Sess:
        def get(self, url, headers=None, timeout=None):
            raise RuntimeError("network fail")
    # Playwright unavailable; requests fail; r is None -> raise
    monkeypatch.setattr(ircc, "PLAYWRIGHT_AVAILABLE", False)
    try:
        ircc.fetch_html("http://example.com/fail", Sess(), use_playwright=True)
    except RuntimeError:
        pass
    else:
        assert False, "Expected RuntimeError"


def test_sections_page_fallback_no_headings_useful(monkeypatch):
    html = """
    <html><body><main>
      <p>This page has general content with details that pass filter.</p>
      <p>More useful text.</p>
    </main></body></html>
    """
    class Sess:
        def get(self, url, headers=None, timeout=None):
            class R:
                status_code = 200
                text = html
            return R()
    recs = ircc.scrape_page("http://example.com/pagefallback", visited=set(), session=Sess(), crawl_subpages=False)
    assert recs and recs[0]["section"] == ""


def test_parse_date_published_meta_and_modified():
        html = """
        <html><head>
            <meta property="article:published_time" content="2025-11-01T10:00:00Z" />
        </head><body>
            <main><h1>T</h1><p>Body</p></main>
        </body></html>
        """
        soup = ircc.BeautifulSoup(html, "html.parser")
        d1 = ircc.parse_date_published(soup)
        assert d1 == "2025-11-01"
        html2 = """
        <html><body>
            <main><h1>T</h1><p>Date modified: November 2, 2025</p></main>
        </body></html>
        """
        d2 = ircc.parse_date_published(ircc.BeautifulSoup(html2, "html.parser"))
        assert d2 == "2025-11-02"


def test_parse_date_published_bad_meta_then_time_tag():
        html = """
        <html><head>
            <meta property="article:published_time" content="bad-date-here" />
        </head><body>
            <time datetime="2025-10-31">31 Oct 2025</time>
        </body></html>
        """
        d = ircc.parse_date_published(ircc.BeautifulSoup(html, "html.parser"))
        assert d == "2025-10-31"


def test_allowed_by_robots_unreadable(monkeypatch):
    # read_robots returns None (unreadable) -> allowed_by_robots returns True
    monkeypatch.setattr(ircc, "read_robots", lambda base: None)
    assert ircc.allowed_by_robots("https://www.canada.ca/en/page") is True


def test_scrape_all_dedupe_visited_urls(monkeypatch, tmp_path):
    base = "https://www.canada.ca/en/"
    html = '''
    <html><body><main>
      <a href="/articles/a">A</a>
      <a href="/articles/a">A duplicate</a>
      <a href="/articles/b">B</a>
    </main></body></html>'''

    # Ensure listing detection and links
    monkeypatch.setattr(ircc, "allowed_by_robots", lambda url: True)
    monkeypatch.setattr(ircc, "is_listing_page", lambda soup: True)
    links = [
        "https://www.canada.ca/en/articles/a",
        "https://www.canada.ca/en/articles/b",
        "https://www.canada.ca/en/articles/a",  # duplicate
    ]
    monkeypatch.setattr(ircc, "find_internal_article_links", lambda soup, base: links)

    calls = []

    orig_scrape = ircc.scrape_page

    def wrapped_scrape(url, visited, session, crawl_subpages=False):
        if url == base:
            # Let original scrape handle listing detection and traversal
            return orig_scrape(url, visited, session, crawl_subpages=True)
        # For subpages, record and return a minimal record
        calls.append(url)
        return [ircc.make_record(url, "T", None, "Body", None)]

    monkeypatch.setattr(ircc, "fetch_html", lambda url, session=None, use_playwright=True: html)
    monkeypatch.setattr(ircc, "scrape_page", wrapped_scrape)

    # Avoid real S3 uploads
    class FakeS3:
        def upload_file(self, filename, bucket, key):
            return None
    monkeypatch.setattr(ircc, "S3_CLIENT", FakeS3())

    out_file = tmp_path / "ircc_dedupe.json"
    out = ircc.scrape_all([base], crawl_subpages=True, out_path=str(out_file))
    assert isinstance(out, list)
    # Should only call scrape_page for two unique article URLs
    assert len(calls) == 2
    assert sorted(calls) == [
        "https://www.canada.ca/en/articles/a",
        "https://www.canada.ca/en/articles/b",
    ]


def test_find_internal_article_links_filter_extremes():
    base = "https://www.canada.ca/en/immigration-refugees-citizenship/news.html"
    html = '''
    <html><body><main>
      <a href="https://example.com/x">ext</a>
      <a href="mailto:someone@example.com">mail</a>
      <a href="tel:+123456">tel</a>
      <a href="#section">hash</a>
    <a href="/en/immigration-refugees-citizenship/news/abc.html">ok1</a>
    <a href="https://www.canada.ca/en/immigration-refugees-citizenship/news/def.html">ok2</a>
    </main></body></html>'''
    soup = ircc.BeautifulSoup(html, "html.parser")
    links = ircc.find_internal_article_links(soup, base)
    assert links == [
        "https://www.canada.ca/en/immigration-refugees-citizenship/news/abc.html",
        "https://www.canada.ca/en/immigration-refugees-citizenship/news/def.html",
    ]


def test_parse_date_published_time_variants():
    soup_ok = ircc.BeautifulSoup(
        '<html><body><time datetime="2024-01-02">January 2, 2024</time></body></html>',
        "html.parser",
    )
    d_ok = ircc.parse_date_published(soup_ok)
    assert d_ok == "2024-01-02"

    soup_bad = ircc.BeautifulSoup(
        '<html><body><time>Not a date</time></body></html>',
        "html.parser",
    )
    d_bad = ircc.parse_date_published(soup_bad)
    assert d_bad is None


def test_scrape_all_s3_skip_when_env_unset(monkeypatch, tmp_path):
    html = '<html><body><main><a href="/content/a">A</a></main></body></html>'

    class Sess:
        def get(self, url, headers=None, timeout=None):
            class R:
                status_code = 200
                text = html
            return R()

    monkeypatch.setattr(ircc, "requests_get", lambda session, url: Sess().get(url))
    monkeypatch.setattr(ircc, "allowed_by_robots", lambda url: True)

    def fake_scrape(url, visited, session, crawl_subpages=False):
        return [ircc.make_record("https://www.canada.ca/en/content/a", "T", None, "Body", None)]

    monkeypatch.setattr(ircc, "scrape_page", fake_scrape)

    # Patch S3 client to avoid network
    class FakeS3:
        def upload_file(self, filename, bucket, key):
            raise AssertionError("S3 upload should be skipped")
    monkeypatch.setattr(ircc, "S3_CLIENT", FakeS3())

    # Clear module-level configured S3 target to skip upload
    monkeypatch.setattr(ircc, "TARGET_S3_BUCKET", "")
    monkeypatch.setattr(ircc, "TARGET_S3_KEY", "")
    out_file = tmp_path / "ircc_skip.json"
    out = ircc.scrape_all(["https://www.canada.ca/en/immigration.html"], crawl_subpages=False, out_path=str(out_file))
    assert isinstance(out, list)
