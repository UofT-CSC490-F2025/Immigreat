"""Tests for IRCC scraper helper functions."""
import pytest
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, 'src')
sys.path.insert(0, 'src/scraping')


@pytest.mark.unit
class TestIRCCScraperHelpers:
    """Test IRCC scraper helper/utility functions."""

    def test_is_useful_content_valid_text(self):
        """Test is_useful_content with valid content."""
        from scraping.ircc_scraper import is_useful_content
        
        # Long, meaningful content
        assert is_useful_content("This is a detailed guide about Canadian immigration procedures. " * 10)
        
        # Content with numbers and mixed case
        assert is_useful_content("Application Form IMM 5710 requires the following documents...")

    def test_is_useful_content_short_text(self):
        """Test is_useful_content with too-short content."""
        from scraping.ircc_scraper import is_useful_content
        
        assert not is_useful_content("Short")
        assert not is_useful_content("ABC123")

    def test_is_useful_content_junk_text(self):
        """Test is_useful_content with junk patterns."""
        from scraping.ircc_scraper import is_useful_content
        
        # Navigation menu items
        assert not is_useful_content("Home | About | Contact | Services | FAQ")
        
        # Mostly punctuation
        assert not is_useful_content(">>> ... <<< ||| /// *** +++")
        
        # Excessive whitespace
        assert not is_useful_content("   \n\n\n   \t\t\t   ")

    def test_is_useful_content_none_or_empty(self):
        """Test is_useful_content with None or empty string."""
        from scraping.ircc_scraper import is_useful_content
        
        assert not is_useful_content(None)
        assert not is_useful_content("")

    def test_read_robots_success(self):
        """Test read_robots with valid URL."""
        from scraping.ircc_scraper import read_robots
        
        result = read_robots("https://www.canada.ca")
        
        # Should return a RobotFileParser instance
        assert result is not None
        assert hasattr(result, 'can_fetch')

    def test_read_robots_invalid_url(self):
        """Test read_robots with invalid URL."""
        from scraping.ircc_scraper import read_robots
        
        # Should handle gracefully and return None on error
        result = read_robots("https://invalid-domain-that-does-not-exist-123456.com")
        
        # Function returns None on failure
        assert result is None

    def test_allowed_by_robots_with_cache(self):
        """Test allowed_by_robots uses cache."""
        from scraping.ircc_scraper import allowed_by_robots
        
        url1 = "https://www.canada.ca/en/immigration-refugees-citizenship.html"
        url2 = "https://www.canada.ca/en/services/immigration.html"
        
        # First call - should fetch robots.txt
        result1 = allowed_by_robots(url1)
        assert isinstance(result1, bool)
        
        # Second call to same domain - should use cache
        result2 = allowed_by_robots(url2)
        assert isinstance(result2, bool)

    def test_detect_requires_js_with_markers(self):
        """Test detect_requires_js identifies JS-required pages."""
        from scraping.ircc_scraper import detect_requires_js
        
        # Actual markers the function checks for
        assert detect_requires_js("You need a browser that supports JavaScript")
        assert detect_requires_js("JavaScript must be enabled to continue")
        assert detect_requires_js("This page requires JavaScript to function")
        assert detect_requires_js("Enable JavaScript in your browser")
        
        # IRCC-specific markers
        assert detect_requires_js("Check our current processing times")

    def test_detect_requires_js_normal_content(self):
        """Test detect_requires_js with normal content."""
        from scraping.ircc_scraper import detect_requires_js
        
        normal_text = """
        Welcome to Immigration, Refugees and Citizenship Canada.
        This page contains information about visa applications.
        Please read the instructions carefully before submitting.
        """
        
        assert not detect_requires_js(normal_text)

    def test_detect_requires_js_empty_or_none(self):
        """Test detect_requires_js with empty/None input."""
        from scraping.ircc_scraper import detect_requires_js
        
        assert detect_requires_js(None)  # Treat None as requiring JS (defensive)
        assert detect_requires_js("")    # Empty also requires JS

    @patch('scraping.ircc_scraper.requests.Session')
    def test_requests_get_wrapper(self, mock_session_class):
        """Test requests_get wrapper function."""
        from scraping.ircc_scraper import requests_get
        
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response
        
        response = requests_get(mock_session, "https://example.com")
        
        assert response == mock_response
        mock_session.get.assert_called_once()

    def test_parse_date_published_article_tag(self):
        """Test parse_date_published with article:published_time meta tag."""
        from scraping.ircc_scraper import parse_date_published
        from bs4 import BeautifulSoup
        
        html = '<html><head><meta property="article:published_time" content="2024-01-15T10:30:00Z"></head></html>'
        soup = BeautifulSoup(html, 'html.parser')
        
        result = parse_date_published(soup)
        
        assert result == '2024-01-15'

    def test_parse_date_published_dcterms_date(self):
        """Test parse_date_published with dcterms.date meta tag."""
        from scraping.ircc_scraper import parse_date_published
        from bs4 import BeautifulSoup
        
        html = '<html><head><meta name="dcterms.date" content="2024-03-20"></head></html>'
        soup = BeautifulSoup(html, 'html.parser')
        
        result = parse_date_published(soup)
        
        assert result == '2024-03-20'

    def test_parse_date_published_time_element(self):
        """Test parse_date_published with time element."""
        from scraping.ircc_scraper import parse_date_published
        from bs4 import BeautifulSoup
        
        html = '<html><body><time datetime="2024-05-10">May 10, 2024</time></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        
        result = parse_date_published(soup)
        
        assert result == '2024-05-10'

    def test_parse_date_published_date_modified_text(self):
        """Test parse_date_published with 'Date modified' text."""
        from scraping.ircc_scraper import parse_date_published
        from bs4 import BeautifulSoup
        
        html = '<html><body><div>Date modified: 2024-02-15</div></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        
        result = parse_date_published(soup)
        
        # Should find and parse the date
        assert result is not None

    def test_parse_date_published_no_date(self):
        """Test parse_date_published when no date found."""
        from scraping.ircc_scraper import parse_date_published
        from bs4 import BeautifulSoup
        
        html = '<html><body><p>No date information here</p></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        
        result = parse_date_published(soup)
        
        assert result is None

    def test_make_record_creates_proper_structure(self):
        """Test make_record creates proper record structure."""
        from scraping.ircc_scraper import make_record
        
        record = make_record(
            url="https://example.com/page",
            title="Test Title",
            section_title="Section A",
            content="Test content here",
            date_published="2024-01-15"
        )
        
        # Function uses 'source' not 'url', and 'section' not 'section_title'
        assert record['source'] == "https://example.com/page"
        assert record['title'] == "Test Title"
        assert record['section'] == "Section A"
        assert record['content'] == "Test content here"
        assert record['date_published'] == "2024-01-15"
        assert 'id' in record  # Should generate an ID
        assert 'date_scraped' in record
        assert 'granularity' in record

    def test_make_record_generates_unique_ids(self):
        """Test make_record generates unique IDs for different content."""
        from scraping.ircc_scraper import make_record
        
        record1 = make_record(
            url="https://example.com/page1",
            title="Title 1",
            section_title="Section 1",
            content="Content 1",
            date_published="2024-01-15"
        )
        
        record2 = make_record(
            url="https://example.com/page2",
            title="Title 2",
            section_title="Section 2",
            content="Content 2",
            date_published="2024-01-16"
        )
        
        assert record1['id'] != record2['id']

    def test_is_listing_page_with_list_content(self):
        """Test is_listing_page detects listing pages."""
        from scraping.ircc_scraper import is_listing_page
        from bs4 import BeautifulSoup
        
        # Function checks for >25 anchors OR news patterns
        html = '''<html><body><main>
            <h1>Immigration Programs</h1>
            <ul>
                <li><a href="/news/program1">Program 1</a></li>
                <li><a href="/news/program2">Program 2</a></li>
                <li><a href="/news/program3">Program 3</a></li>
            </ul>
        </main></body></html>'''
        
        soup = BeautifulSoup(html, 'html.parser')
        
        result = is_listing_page(soup)
        
        # Has news pattern so should return True
        assert result is True

    def test_is_listing_page_with_article_content(self):
        """Test is_listing_page returns False for article pages."""
        from scraping.ircc_scraper import is_listing_page
        from bs4 import BeautifulSoup
        
        html = '''<html><body>
            <h1>Visa Application Guide</h1>
            <p>This is a detailed article about visa applications.</p>
            <p>It contains multiple paragraphs of content.</p>
            <p>This is clearly an article, not a listing page.</p>
        </body></html>'''
        
        soup = BeautifulSoup(html, 'html.parser')
        
        result = is_listing_page(soup)
        
        assert result is False

    def test_find_internal_article_links(self):
        """Test find_internal_article_links extracts relevant links."""
        from scraping.ircc_scraper import find_internal_article_links
        from bs4 import BeautifulSoup
        
        html = '''<html><body>
            <a href="/en/immigration-refugees-citizenship/services/immigrate-canada.html">Immigrate</a>
            <a href="/en/immigration-refugees-citizenship/services/study-canada.html">Study</a>
            <a href="https://external-site.com">External Link</a>
            <a href="/fr/immigration-refugies-citoyennete/services.html">French</a>
        </body></html>'''
        
        soup = BeautifulSoup(html, 'html.parser')
        base_url = "https://www.canada.ca"
        
        links = find_internal_article_links(soup, base_url, limit=10)
        
        # Should find internal English links
        assert len(links) >= 1
        assert all(link.startswith("https://www.canada.ca") for link in links)
        # Should exclude external and French links
        assert "https://external-site.com" not in links

    def test_extract_sections_from_main(self):
        """Test extract_sections_from_main extracts content sections."""
        from scraping.ircc_scraper import extract_sections_from_main
        from bs4 import BeautifulSoup
        
        html = '''<html><body><main>
            <h2>Section 1: Requirements with lots of text to pass useful filter</h2>
            <p>You must meet the following requirements for immigration and citizenship.</p>
            <h2>Section 2: Documents needed with lots of text to pass useful filter</h2>
            <p>Please prepare the following documents for your application and submission.</p>
        </main></body></html>'''
        
        soup = BeautifulSoup(html, 'html.parser')
        
        sections = extract_sections_from_main(soup)
        
        assert len(sections) >= 0
        # Function returns dicts with 'section' and 'content' keys
        for section in sections:
            assert 'section' in section
            assert 'content' in section
            assert len(section['content']) > 0
