"""Unit tests for IRCC scraper module."""
import pytest
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, 'src')

from scraping.ircc_scraper import (
    is_useful_content,
    read_robots,
    allowed_by_robots,
    requests_get
)


@pytest.mark.unit
class TestIsUsefulContent:
    """Tests for content usefulness detection."""

    def test_useful_content(self):
        """Test detection of useful content."""
        content = "This is a substantial piece of content about Canadian immigration " * 5
        
        assert is_useful_content(content) is True

    def test_too_short_content(self):
        """Test rejection of too short content."""
        content = "Short"
        
        assert is_useful_content(content) is False

    def test_archived_page_marker(self):
        """Test detection of archived page markers."""
        content = "We have archived this page and will not be updating it." * 3
        
        assert is_useful_content(content) is False

    def test_form_section_marker(self):
        """Test detection of form section markers."""
        content = "Section A – Applicant information goes here" * 5
        
        assert is_useful_content(content) is False

    def test_pdf_form_marker(self):
        """Test detection of PDF form markers."""
        content = "Please fill out this PDF form for your application" * 5
        
        assert is_useful_content(content) is False

    def test_empty_or_whitespace(self):
        """Test rejection of empty or whitespace content."""
        assert is_useful_content("") is False
        assert is_useful_content("   ") is False
        assert is_useful_content(None) is False

    def test_case_insensitive_markers(self):
        """Test that marker detection is case-insensitive."""
        content = "WE HAVE ARCHIVED THIS PAGE and will not be updating it" * 5
        
        assert is_useful_content(content) is False


@pytest.mark.unit
class TestReadRobots:
    """Tests for robots.txt reading."""

    @patch('scraping.ircc_scraper.robotparser.RobotFileParser')
    def test_read_robots_success(self, mock_parser_class):
        """Test successful robots.txt reading."""
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        
        result = read_robots('https://example.com')
        
        assert result is not None
        mock_parser.set_url.assert_called_once()
        mock_parser.read.assert_called_once()

    @patch('scraping.ircc_scraper.robotparser.RobotFileParser')
    def test_read_robots_error(self, mock_parser_class):
        """Test robots.txt reading with error."""
        mock_parser = MagicMock()
        mock_parser.read.side_effect = Exception("Connection error")
        mock_parser_class.return_value = mock_parser
        
        result = read_robots('https://example.com')
        
        assert result is None


@pytest.mark.unit
class TestAllowedByRobots:
    """Tests for robots.txt permission checking."""

    def test_allowed_by_robots_no_robots(self):
        """Test behavior when robots.txt unavailable."""
        with patch('scraping.ircc_scraper.read_robots', return_value=None):
            result = allowed_by_robots('https://example.com/page')
            
            # Should default to allowing when robots.txt unavailable
            assert result is True

    def test_allowed_by_robots_cached(self):
        """Test robots.txt caching behavior."""
        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = True
        
        with patch('scraping.ircc_scraper.read_robots', return_value=mock_rp):
            # First call
            result1 = allowed_by_robots('https://example.com/page1', {})
            # Second call with cache
            cache = {'https://example.com': mock_rp}
            result2 = allowed_by_robots('https://example.com/page2', cache)
            
            assert result1 is True
            assert result2 is True

    def test_allowed_by_robots_disallowed(self):
        """Test when URL is disallowed by robots.txt."""
        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = False
        
        with patch('scraping.ircc_scraper.read_robots', return_value=mock_rp):
            result = allowed_by_robots('https://example.com/private', {})
            
            assert result is False

    def test_allowed_by_robots_error_handling(self):
        """Test error handling in permission checking."""
        mock_rp = MagicMock()
        mock_rp.can_fetch.side_effect = Exception("Parse error")
        
        with patch('scraping.ircc_scraper.read_robots', return_value=mock_rp):
            result = allowed_by_robots('https://example.com/page', {})
            
            # Should default to allowing on error
            assert result is True


@pytest.mark.unit
class TestRequestsGet:
    """Tests for HTTP GET requests."""

    @patch('scraping.ircc_scraper.requests.Session.get')
    def test_requests_get_success(self, mock_get):
        """Test successful HTTP GET request."""
        from requests import Session
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'<html>Test content</html>'
        mock_get.return_value = mock_response
        
        session = Session()
        response = requests_get(session, 'https://example.com')
        
        assert response.status_code == 200
        mock_get.assert_called_once()
        
        # Check that proper headers were set
        call_args = mock_get.call_args
        assert 'headers' in call_args[1]
        assert 'User-Agent' in call_args[1]['headers']

    @patch('scraping.ircc_scraper.requests.Session.get')
    def test_requests_get_with_timeout(self, mock_get):
        """Test that timeout is properly set."""
        from requests import Session
        
        mock_response = MagicMock()
        mock_get.return_value = mock_response
        
        session = Session()
        requests_get(session, 'https://example.com')
        
        call_args = mock_get.call_args
        assert 'timeout' in call_args[1]


@pytest.mark.unit
class TestScraperConfiguration:
    """Tests for scraper configuration."""

    def test_crawl_subpages_setting(self):
        """Test CRAWL_SUBPAGES configuration."""
        from scraping import ircc_scraper
        
        assert hasattr(ircc_scraper, 'CRAWL_SUBPAGES')
        assert isinstance(ircc_scraper.CRAWL_SUBPAGES, bool)

    def test_max_subpage_setting(self):
        """Test MAX_SUBPAGE_PER_PAGE configuration."""
        from scraping import ircc_scraper
        
        assert hasattr(ircc_scraper, 'MAX_SUBPAGE_PER_PAGE')
        assert isinstance(ircc_scraper.MAX_SUBPAGE_PER_PAGE, int)
        assert ircc_scraper.MAX_SUBPAGE_PER_PAGE > 0

    def test_s3_configuration(self):
        """Test S3 configuration."""
        from scraping import ircc_scraper
        
        assert hasattr(ircc_scraper, 'TARGET_S3_BUCKET')
        assert hasattr(ircc_scraper, 'TARGET_S3_KEY')
