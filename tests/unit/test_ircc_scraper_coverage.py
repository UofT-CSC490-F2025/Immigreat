"""
Additional tests to improve coverage for ircc_scraper.py
Focuses on edge cases and error paths that were previously uncovered.
"""

import os
import sys
import json
import tempfile
from unittest.mock import Mock, patch, MagicMock
import pytest


class TestPlaywrightImportHandling:
    """Test handling when playwright is not available"""
    
    def test_playwright_import_exception_handling(self):
        """Test that exception during playwright import is handled gracefully"""
        # This tests lines 36-37
        # The module-level import exception is already covered by the try/except
        # We just need to verify the behavior when playwright is truly unavailable
        from src.scraping import ircc_scraper
        
        # If playwright is not available, sync_playwright should be None or raise error
        if not ircc_scraper.PLAYWRIGHT_AVAILABLE:
            with pytest.raises(RuntimeError, match="Playwright not installed"):
                ircc_scraper.render_with_playwright("http://example.com")
    
    def test_render_with_playwright_lazy_import_failure(self):
        """Test lazy import failure in render_with_playwright (lines 113-117)"""
        from src.scraping import ircc_scraper
        
        # Temporarily set PLAYWRIGHT_AVAILABLE to False and sync_playwright to None
        original_available = ircc_scraper.PLAYWRIGHT_AVAILABLE
        original_sync = ircc_scraper.sync_playwright
        
        try:
            # Mock the module to simulate lazy import failure
            ircc_scraper.sync_playwright = None
            with patch.dict('sys.modules', {'playwright.sync_api': None}):
                with pytest.raises(RuntimeError, match="Playwright not installed"):
                    ircc_scraper.render_with_playwright("http://example.com")
        finally:
            ircc_scraper.PLAYWRIGHT_AVAILABLE = original_available
            ircc_scraper.sync_playwright = original_sync


class TestDetectRequiresJS:
    """Test JavaScript detection edge cases"""
    
    def test_detect_requires_js_with_processing_times_marker(self):
        """Test detection of processing times widget that requires JS (line 178-179)"""
        from src.scraping.ircc_scraper import detect_requires_js
        
        html_with_widget = """
        <html>
            <body>
                <p>Check our current processing times for your application</p>
            </body>
        </html>
        """
        assert detect_requires_js(html_with_widget) is True
    
    def test_detect_requires_js_empty_html(self):
        """Test detection with empty HTML"""
        from src.scraping.ircc_scraper import detect_requires_js
        
        assert detect_requires_js("") is True
        assert detect_requires_js(None) is True


class TestParseDatePublished:
    """Test date parsing edge cases"""
    
    def test_parse_date_published_invalid_date_format(self):
        """Test handling of invalid date format in meta tags (line 189)"""
        from bs4 import BeautifulSoup
        from src.scraping.ircc_scraper import parse_date_published
        
        html = """
        <html>
            <head>
                <meta property="article:published_time" content="not-a-valid-date">
            </head>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = parse_date_published(soup)
        # Should return None when date parsing fails
        assert result is None


class TestFetchHTMLEdgeCases:
    """Test fetch_html edge cases"""
    
    def test_fetch_html_requests_returns_short_content_no_playwright(self):
        """Test when requests returns short content but playwright unavailable (line 270)"""
        from src.scraping import ircc_scraper
        
        original_available = ircc_scraper.PLAYWRIGHT_AVAILABLE
        
        try:
            # Disable playwright
            ircc_scraper.PLAYWRIGHT_AVAILABLE = False
            
            mock_session = Mock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "short"  # Very short content
            mock_session.get.return_value = mock_response
            
            # Should return the short text even though it's not ideal
            result = ircc_scraper.fetch_html("http://example.com", mock_session, use_playwright=True)
            assert result == "short"
        finally:
            ircc_scraper.PLAYWRIGHT_AVAILABLE = original_available


class TestScrapeAllS3Upload:
    """Test S3 upload scenarios in scrape_all"""
    
    def test_scrape_all_with_s3_upload_success(self):
        """Test successful S3 upload path (lines 368-369)"""
        from src.scraping import ircc_scraper
        
        # Save original values
        original_bucket = ircc_scraper.TARGET_S3_BUCKET
        original_key = ircc_scraper.TARGET_S3_KEY
        original_client = ircc_scraper.S3_CLIENT
        
        try:
            # Set S3 config
            ircc_scraper.TARGET_S3_BUCKET = "test-bucket"
            ircc_scraper.TARGET_S3_KEY = "test-key.json"
            
            # Mock S3 client
            mock_s3 = Mock()
            ircc_scraper.S3_CLIENT = mock_s3
            
            # Mock scraping
            with patch('src.scraping.ircc_scraper.scrape_page') as mock_scrape:
                mock_scrape.return_value = [
                    {
                        "id": "test123",
                        "title": "Test",
                        "content": "Test content",
                        "source": "http://example.com"
                    }
                ]
                
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp:
                    tmp_path = tmp.name
                
                try:
                    result = ircc_scraper.scrape_all(
                        ["http://example.com"],
                        out_path=tmp_path,
                        crawl_subpages=False
                    )
                    
                    # Verify S3 upload was called
                    mock_s3.upload_file.assert_called_once_with(
                        tmp_path,
                        "test-bucket",
                        "test-key.json"
                    )
                    
                    assert len(result) == 1
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
        finally:
            # Restore original values
            ircc_scraper.TARGET_S3_BUCKET = original_bucket
            ircc_scraper.TARGET_S3_KEY = original_key
            ircc_scraper.S3_CLIENT = original_client
    
    def test_scrape_all_s3_upload_with_empty_bucket(self):
        """Test S3 upload skipped when bucket is empty string (line 357-358)"""
        from src.scraping import ircc_scraper
        
        original_bucket = ircc_scraper.TARGET_S3_BUCKET
        original_key = ircc_scraper.TARGET_S3_KEY
        original_client = ircc_scraper.S3_CLIENT
        
        try:
            # Set empty bucket
            ircc_scraper.TARGET_S3_BUCKET = ""
            ircc_scraper.TARGET_S3_KEY = "test-key.json"
            
            mock_s3 = Mock()
            ircc_scraper.S3_CLIENT = mock_s3
            
            with patch('src.scraping.ircc_scraper.scrape_page') as mock_scrape:
                mock_scrape.return_value = []
                
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp:
                    tmp_path = tmp.name
                
                try:
                    result = ircc_scraper.scrape_all(
                        ["http://example.com"],
                        out_path=tmp_path,
                        crawl_subpages=False
                    )
                    
                    # Verify S3 upload was NOT called
                    mock_s3.upload_file.assert_not_called()
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
        finally:
            ircc_scraper.TARGET_S3_BUCKET = original_bucket
            ircc_scraper.TARGET_S3_KEY = original_key
            ircc_scraper.S3_CLIENT = original_client
    
    def test_scrape_all_s3_upload_with_empty_key(self):
        """Test S3 upload skipped when key is empty string"""
        from src.scraping import ircc_scraper
        
        original_bucket = ircc_scraper.TARGET_S3_BUCKET
        original_key = ircc_scraper.TARGET_S3_KEY
        original_client = ircc_scraper.S3_CLIENT
        
        try:
            ircc_scraper.TARGET_S3_BUCKET = "test-bucket"
            ircc_scraper.TARGET_S3_KEY = ""
            
            mock_s3 = Mock()
            ircc_scraper.S3_CLIENT = mock_s3
            
            with patch('src.scraping.ircc_scraper.scrape_page') as mock_scrape:
                mock_scrape.return_value = []
                
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp:
                    tmp_path = tmp.name
                
                try:
                    result = ircc_scraper.scrape_all(
                        ["http://example.com"],
                        out_path=tmp_path,
                        crawl_subpages=False
                    )
                    
                    mock_s3.upload_file.assert_not_called()
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
        finally:
            ircc_scraper.TARGET_S3_BUCKET = original_bucket
            ircc_scraper.TARGET_S3_KEY = original_key
            ircc_scraper.S3_CLIENT = original_client


class TestScrapePageErrorHandling:
    """Test error handling in scrape_page"""
    
    def test_scrape_page_subpage_scraping_error(self):
        """Test handling of subpage scraping errors (line 357-358)"""
        from src.scraping import ircc_scraper
        from bs4 import BeautifulSoup
        
        # Create a listing page HTML
        listing_html = """
        <html>
            <body>
                <main>
                    """ + "\n".join([f'<a href="/news/article-{i}">Article {i}</a>' for i in range(30)]) + """
                </main>
            </body>
        </html>
        """
        
        visited = set()
        mock_session = Mock()
        
        with patch('src.scraping.ircc_scraper.fetch_html') as mock_fetch:
            # First call returns listing page
            # Subsequent calls raise exception
            def fetch_side_effect(url, session, use_playwright=True):
                if "example.com" in url:
                    return listing_html
                raise RuntimeError("Simulated fetch error")
            
            mock_fetch.side_effect = fetch_side_effect
            
            with patch('src.scraping.ircc_scraper.allowed_by_robots', return_value=True):
                # This should handle the errors gracefully and return records from main page
                result = ircc_scraper.scrape_page(
                    "http://example.com",
                    visited,
                    mock_session,
                    crawl_subpages=True
                )
                
                # Should still return some result despite subpage errors
                assert isinstance(result, list)
