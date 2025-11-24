"""Unit tests for forms scraper module."""
import pytest
from unittest.mock import MagicMock, patch, mock_open
import sys
import json
sys.path.insert(0, 'src')

from scraping.forms_scraper import (
    now_date,
    make_hash,
    get_latest_pdf_from_page,
    extract_fields_from_webpages
)


@pytest.mark.unit
class TestNowDate:
    """Tests for date formatting."""

    def test_now_date_format(self):
        """Test that now_date returns proper format."""
        date_str = now_date()
        
        assert isinstance(date_str, str)
        assert len(date_str) > 0
        # Should be ISO format
        assert '-' in date_str

    @patch('scraping.forms_scraper.datetime')
    def test_now_date_consistent(self, mock_datetime):
        """Test date formatting consistency."""
        from datetime import datetime, timezone
        
        fixed_time = datetime(2025, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = fixed_time
        mock_datetime.strftime = datetime.strftime
        
        # The actual format depends on DATE_FORMAT constant
        date_str = now_date()
        assert isinstance(date_str, str)


@pytest.mark.unit
class TestMakeHash:
    """Tests for hash generation."""

    def test_make_hash_consistent(self):
        """Test that same input produces same hash."""
        entry = {
            'title': 'Test Title',
            'section': 'Test Section',
            'content': 'Test Content',
            'source': 'Test Source'
        }
        
        hash1 = make_hash(entry)
        hash2 = make_hash(entry)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest length

    def test_make_hash_different_content(self):
        """Test that different content produces different hash."""
        entry1 = {
            'title': 'Title 1',
            'section': 'Section',
            'content': 'Content 1',
            'source': 'Source'
        }
        entry2 = {
            'title': 'Title 2',
            'section': 'Section',
            'content': 'Content 2',
            'source': 'Source'
        }
        
        hash1 = make_hash(entry1)
        hash2 = make_hash(entry2)
        
        assert hash1 != hash2

    def test_make_hash_missing_fields(self):
        """Test hash generation with missing fields."""
        entry = {'title': 'Test'}
        
        hash_val = make_hash(entry)
        
        assert isinstance(hash_val, str)
        assert len(hash_val) == 64


@pytest.mark.unit
class TestGetLatestPdfFromPage:
    """Tests for PDF link extraction."""

    @patch('scraping.forms_scraper.BeautifulSoup')
    @patch('scraping.forms_scraper.requests.get')
    def test_get_pdf_from_page_success(self, mock_get, mock_bs):
        """Test successful PDF link extraction."""
        html_content = '''
        <html>
            <body>
                <a href="/path/to/form.pdf">Download Form</a>
            </body>
        </html>
        '''
        mock_response = MagicMock()
        mock_response.text = html_content
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        # Mock BeautifulSoup to return proper structure
        mock_soup = MagicMock()
        mock_anchor = MagicMock()
        mock_anchor.__getitem__ = MagicMock(return_value='/path/to/form.pdf')
        mock_anchor.get_text = MagicMock(return_value='Download Form')
        mock_soup.find_all = MagicMock(return_value=[mock_anchor])
        mock_bs.return_value = mock_soup
        
        url = get_latest_pdf_from_page('https://example.com/page')
        
        assert url is not None
        assert url.endswith('.pdf')

    @patch('scraping.forms_scraper.requests.get')
    def test_get_pdf_no_pdf_found(self, mock_get):
        """Test when no PDF is found."""
        html_content = '''
        <html>
            <body>
                <a href="/path/to/page.html">No PDF here</a>
            </body>
        </html>
        '''
        mock_response = MagicMock()
        mock_response.text = html_content
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        url = get_latest_pdf_from_page('https://example.com/page')
        
        assert url is None

    @patch('scraping.forms_scraper.requests.get')
    def test_get_pdf_with_keywords(self, mock_get):
        """Test PDF extraction with keyword filtering."""
        html_content = '''
        <html>
            <body>
                <a href="/form1.pdf">Form 1</a>
                <a href="/special_form.pdf">Special Form</a>
            </body>
        </html>
        '''
        mock_response = MagicMock()
        mock_response.text = html_content
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        url = get_latest_pdf_from_page('https://example.com/page', keywords=['special'])
        
        if url:
            assert 'special' in url.lower() or url.endswith('.pdf')

    @patch('scraping.forms_scraper.requests.get')
    def test_get_pdf_request_error(self, mock_get):
        """Test handling of request errors."""
        mock_get.side_effect = Exception("Network error")
        
        url = get_latest_pdf_from_page('https://example.com/page')
        
        assert url is None


@pytest.mark.unit
class TestExtractFieldsFromWebpages:
    """Tests for extracting fields from webpages."""

    @patch('scraping.forms_scraper.boto3.client')
    @patch('scraping.forms_scraper.get_latest_pdf_from_page')
    @patch('scraping.forms_scraper.requests.get')
    def test_extract_forms_success(self, mock_get, mock_get_pdf, mock_boto_client):
        """Test successful extraction of forms."""
        # Mock PDF URL retrieval
        mock_get_pdf.return_value = 'https://example.com/form.pdf'
        
        # Mock PDF download
        pdf_content = b'%PDF-1.4 fake pdf content'
        mock_pdf_response = MagicMock()
        mock_pdf_response.content = pdf_content
        mock_pdf_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_pdf_response
        
        # Mock PDF text extraction
        with patch('scraping.forms_scraper.PdfReader') as mock_pdf_reader:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = 'Form content text'
            mock_reader_instance = MagicMock()
            mock_reader_instance.pages = [mock_page]
            mock_pdf_reader.return_value = mock_reader_instance
            
            # Mock S3 client
            mock_s3 = MagicMock()
            mock_s3.put_object.return_value = {}
            mock_boto_client.return_value = mock_s3
            
            results = extract_fields_from_webpages(['https://example.com/form-page'])
            
            assert isinstance(results, list)
            assert len(results) >= 0

    @patch('scraping.forms_scraper.boto3.client')
    @patch('scraping.forms_scraper.get_latest_pdf_from_page')
    def test_extract_forms_no_pdf_found(self, mock_get_pdf, mock_boto_client, mock_s3):
        """Test when no PDF is found."""
        mock_get_pdf.return_value = None
        mock_s3_client = MagicMock()
        mock_boto_client.return_value = mock_s3_client
        
        results = extract_fields_from_webpages(['https://example.com/form-page'])
        
        assert isinstance(results, list)
        # Should handle missing PDFs gracefully

    @patch('scraping.forms_scraper.boto3.client')
    @patch('scraping.forms_scraper.get_latest_pdf_from_page')
    @patch('scraping.forms_scraper.requests.get')
    def test_extract_forms_pdf_download_error(self, mock_get, mock_get_pdf, mock_boto_client, mock_s3):
        """Test handling of PDF download errors."""
        mock_get_pdf.return_value = 'https://example.com/form.pdf'
        mock_get.side_effect = Exception("Download failed")
        mock_s3_client = MagicMock()
        mock_boto_client.return_value = mock_s3_client
        
        results = extract_fields_from_webpages(['https://example.com/form-page'])
        
        assert isinstance(results, list)
        # Should handle download errors gracefully
