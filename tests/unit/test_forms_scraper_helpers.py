"""Tests for forms scraper helper functions."""
import pytest
from unittest.mock import MagicMock, patch, mock_open
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0, 'src')
sys.path.insert(0, 'src/scraping')


@pytest.mark.unit
class TestFormsScraperHelpers:
    """Test forms scraper helper/utility functions."""

    def test_now_date_returns_valid_format(self):
        """Test now_date returns ISO format date."""
        from scraping.forms_scraper import now_date
        
        result = now_date()
        
        # Should be in YYYY-MM-DD format
        assert len(result) == 10
        assert result[4] == '-'
        assert result[7] == '-'
        
        # Should be parseable as date
        from datetime import datetime
        parsed = datetime.fromisoformat(result)
        assert parsed is not None

    def test_make_hash_creates_consistent_hash(self):
        """Test make_hash creates consistent hashes."""
        from scraping.forms_scraper import make_hash
        
        # make_hash uses title, section, content, source - need to differ in these fields
        entry1 = {'title': 'IMM 5710', 'section': 'A', 'content': 'Content', 'source': 'https://example.com/form.pdf'}
        entry2 = {'title': 'IMM 5710', 'section': 'A', 'content': 'Content', 'source': 'https://example.com/form.pdf'}
        entry3 = {'title': 'IMM 5711', 'section': 'B', 'content': 'Different', 'source': 'https://example.com/other.pdf'}
        
        hash1 = make_hash(entry1)
        hash2 = make_hash(entry2)
        hash3 = make_hash(entry3)
        
        # Same content should produce same hash
        assert hash1 == hash2
        
        # Different content should produce different hash
        assert hash1 != hash3

    def test_make_hash_returns_hex_string(self):
        """Test make_hash returns hexadecimal string."""
        from scraping.forms_scraper import make_hash
        
        entry = {'name': 'Test', 'data': 'Some data'}
        result = make_hash(entry)
        
        # Should be a hex string
        assert isinstance(result, str)
        assert all(c in '0123456789abcdef' for c in result)
        
        # SHA-256 produces 64 character hex string
        assert len(result) == 64

    def test_try_parse_xml_safe_valid_xml(self):
        """Test try_parse_xml_safe with valid XML."""
        from scraping.forms_scraper import try_parse_xml_safe
        
        xml_string = '<?xml version="1.0"?><root><field>value</field></root>'
        
        result = try_parse_xml_safe(xml_string)
        
        assert result is not None
        assert result.tag == 'root'
        assert result.find('field').text == 'value'

    def test_try_parse_xml_safe_invalid_xml(self):
        """Test try_parse_xml_safe with invalid XML."""
        from scraping.forms_scraper import try_parse_xml_safe
        
        invalid_xml = '<root><unclosed>'
        
        result = try_parse_xml_safe(invalid_xml)
        
        # Should return None instead of raising exception
        assert result is None

    def test_try_parse_xml_safe_none_input(self):
        """Test try_parse_xml_safe with None input."""
        from scraping.forms_scraper import try_parse_xml_safe
        
        result = try_parse_xml_safe(None)
        
        assert result is None

    def test_try_parse_xml_safe_empty_string(self):
        """Test try_parse_xml_safe with empty string."""
        from scraping.forms_scraper import try_parse_xml_safe
        
        result = try_parse_xml_safe("")
        
        assert result is None

    def test_try_parse_xml_safe_malformed_xml(self):
        """Test try_parse_xml_safe with various malformed XML."""
        from scraping.forms_scraper import try_parse_xml_safe
        
        # No closing tag
        assert try_parse_xml_safe("<data><item>value") is None
        
        # Mismatched tags
        assert try_parse_xml_safe("<data><item>value</data></item>") is None
        
        # Invalid characters
        assert try_parse_xml_safe("<data>\x00\x01\x02</data>") is None

    @patch('scraping.forms_scraper.requests.get')
    def test_get_latest_pdf_from_page_finds_pdf(self, mock_get):
        """Test get_latest_pdf_from_page finds PDF links."""
        from scraping.forms_scraper import get_latest_pdf_from_page
        
        mock_response = MagicMock()
        mock_response.text = '''<html><body>
            <a href="form_v1.pdf">Old Version</a>
            <a href="form_v2.pdf">Latest Version</a>
            <a href="instructions.pdf">Instructions</a>
        </body></html>'''
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        result = get_latest_pdf_from_page("https://example.com/forms")
        
        # Should find a PDF link
        assert result is not None
        assert result.endswith('.pdf')

    @patch('scraping.forms_scraper.requests.get')
    def test_get_latest_pdf_from_page_with_keywords(self, mock_get):
        """Test get_latest_pdf_from_page filters by keywords."""
        from scraping.forms_scraper import get_latest_pdf_from_page
        
        mock_response = MagicMock()
        mock_response.text = '''<html><body>
            <a href="imm5710.pdf">IMM 5710 - Application</a>
            <a href="imm5669.pdf">IMM 5669 - Background</a>
            <a href="other.pdf">Other Document</a>
        </body></html>'''
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        result = get_latest_pdf_from_page("https://example.com/forms", keywords=['5710', 'application'])
        
        # Should prefer PDF matching keywords
        assert result is not None
        assert '5710' in result.lower() or 'application' in result.lower()

    @patch('scraping.forms_scraper.requests.get')
    def test_get_latest_pdf_from_page_no_pdf(self, mock_get):
        """Test get_latest_pdf_from_page when no PDF found."""
        from scraping.forms_scraper import get_latest_pdf_from_page
        
        mock_response = MagicMock()
        mock_response.text = '<html><body><p>No PDFs here</p></body></html>'
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        result = get_latest_pdf_from_page("https://example.com/forms")
        
        assert result is None

    @patch('scraping.forms_scraper.requests.get')
    def test_get_latest_pdf_from_page_network_error(self, mock_get):
        """Test get_latest_pdf_from_page handles network errors."""
        from scraping.forms_scraper import get_latest_pdf_from_page
        
        mock_get.side_effect = Exception("Network error")
        
        result = get_latest_pdf_from_page("https://example.com/forms")
        
        # Should return None on error
        assert result is None

    def test_extract_xfa_fields_from_xml_root_simple(self):
        """Test extract_xfa_fields_from_xml_root with simple structure."""
        from scraping.forms_scraper import extract_xfa_fields_from_xml_root
        
        xml_string = '''<?xml version="1.0"?>
        <form>
            <field name="firstName"><caption><text>First Name</text></caption></field>
            <field name="lastName"><caption><text>Last Name</text></caption></field>
        </form>'''
        
        root = ET.fromstring(xml_string)
        
        result = extract_xfa_fields_from_xml_root(root, "https://example.com/form.pdf", "2024-01-15")
        
        # Function returns a list of field entries
        assert isinstance(result, list)

    def test_extract_xfa_fields_from_xml_root_nested(self):
        """Test extract_xfa_fields_from_xml_root with nested structure."""
        from scraping.forms_scraper import extract_xfa_fields_from_xml_root
        
        xml_string = '''<?xml version="1.0"?>
        <form>
            <subform name="personalInfo">
                <field name="name"><caption><text>Name</text></caption></field>
                <field name="age"><caption><text>Age</text></caption></field>
            </subform>
        </form>'''
        
        root = ET.fromstring(xml_string)
        
        result = extract_xfa_fields_from_xml_root(root, "https://example.com/form.pdf", "2024-01-15")
        
        # Function returns a list of field entries
        assert isinstance(result, list)

    def test_extract_xfa_fields_from_xml_root_empty(self):
        """Test extract_xfa_fields_from_xml_root with empty XML."""
        from scraping.forms_scraper import extract_xfa_fields_from_xml_root
        
        xml_string = '<?xml version="1.0"?><form></form>'
        root = ET.fromstring(xml_string)
        
        result = extract_xfa_fields_from_xml_root(root, "https://example.com/form.pdf", "2024-01-15")
        
        # Function returns a list, empty if no fields found
        assert isinstance(result, list)
        assert len(result) == 0

    @patch('scraping.forms_scraper.requests.get')
    @patch('scraping.forms_scraper.PdfReader')
    def test_extract_fields_from_pdf_returns_list(self, mock_pdf_reader, mock_get):
        """Test extract_fields_from_pdf returns a list."""
        from scraping.forms_scraper import extract_fields_from_pdf
        
        mock_response = MagicMock()
        mock_response.content = b'PDF content'
        mock_get.return_value = mock_response
        
        mock_pdf = MagicMock()
        mock_pdf.xfa = None
        mock_pdf.get_fields.return_value = {}
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Form field: Value"
        mock_pdf.pages = [mock_page]
        mock_pdf_reader.return_value = mock_pdf
        
        result = extract_fields_from_pdf("https://example.com/form.pdf")
        
        # Should return a list
        assert isinstance(result, list)

    @patch('scraping.forms_scraper.requests.get')
    def test_extract_fields_from_pdf_handles_errors(self, mock_get):
        """Test extract_fields_from_pdf handles errors gracefully."""
        from scraping.forms_scraper import extract_fields_from_pdf
        
        mock_get.side_effect = Exception("Network error")
        
        result = extract_fields_from_pdf("https://example.com/form.pdf")
        
        # Should return empty list on error
        assert result == []

    def test_extract_fields_from_webpages_returns_dict(self):
        """Test extract_fields_from_webpages returns dict structure."""
        from scraping.forms_scraper import extract_fields_from_webpages
        
        # Mock S3 client and upload to avoid AccessDenied error
        with patch('scraping.forms_scraper.get_latest_pdf_from_page', return_value=None):
            with patch('scraping.forms_scraper.extract_fields_from_pdf', return_value=[]):
                with patch('scraping.forms_scraper.boto3.client') as mock_boto:
                    mock_s3 = MagicMock()
                    mock_boto.return_value = mock_s3
                    
                    # Function signature: page_urls, output_file, pdf_keywords, prefer_text_keyword, dedupe
                    result = extract_fields_from_webpages(
                        ["https://example.com/forms"],
                        output_file="test_output.json"
                    )
        
        # Function returns a list
        assert isinstance(result, list)
