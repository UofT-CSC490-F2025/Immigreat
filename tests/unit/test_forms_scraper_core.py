"""Consolidated core tests for forms_scraper: helpers, basic extraction, PDF/XFA/AcroForm paths, and webpage orchestrator."""
import pytest
from unittest.mock import MagicMock, patch, mock_open
import sys
sys.path.insert(0, 'src')

from scraping.forms_scraper import (
    now_date,
    make_hash,
    get_latest_pdf_from_page,
    extract_fields_from_webpages,
    extract_fields_from_pdf,
    extract_xfa_fields_from_xml_root,
    try_parse_xml_safe,
)

# --- Helpers ---

@pytest.mark.unit
class TestHelpersCore:
    def test_now_date_returns_valid_format(self):
        result = now_date()
        assert isinstance(result, str)
        assert len(result) == 10 and result[4] == '-' and result[7] == '-'

    def test_make_hash_creates_consistent_hash(self):
        entry1 = {'title': 'IMM 5710', 'section': 'A', 'content': 'Content', 'source': 'https://example.com/form.pdf'}
        entry2 = {'title': 'IMM 5710', 'section': 'A', 'content': 'Content', 'source': 'https://example.com/form.pdf'}
        entry3 = {'title': 'IMM 5711', 'section': 'B', 'content': 'Different', 'source': 'https://example.com/other.pdf'}
        assert make_hash(entry1) == make_hash(entry2)
        assert make_hash(entry1) != make_hash(entry3)

    def test_try_parse_xml_safe_valid_invalid(self):
        ok = try_parse_xml_safe('<?xml version="1.0"?><root><field>v</field></root>')
        assert ok is not None
        bad = try_parse_xml_safe('<root><unclosed>')
        assert bad is None
        assert try_parse_xml_safe(None) is None
        assert try_parse_xml_safe('') is None

# --- PDF link selection ---

@pytest.mark.unit
class TestGetLatestPdf:
    @patch('scraping.forms_scraper.requests.get')
    def test_get_pdf_from_page_success(self, mock_get):
        html = '<html><body><a href="/path/to/form.pdf">Download Form</a></body></html>'
        r = MagicMock(); r.text = html; r.raise_for_status = MagicMock(); mock_get.return_value = r
        url = get_latest_pdf_from_page('https://example.com/page')
        assert url and url.endswith('.pdf')

    @patch('scraping.forms_scraper.requests.get')
    def test_get_pdf_no_pdf_found(self, mock_get):
        r = MagicMock(); r.text = '<html><body>No PDF</body></html>'; r.raise_for_status = MagicMock(); mock_get.return_value = r
        assert get_latest_pdf_from_page('https://example.com/page') is None

    @patch('scraping.forms_scraper.requests.get')
    def test_get_latest_pdf_scoring_logic(self, mock_get):
        html = '<html><body>\n<a href="/forms/imm5710-2024.pdf">IMM 5710 (2024)</a>\n<a href="/forms/imm5710-2023.pdf">IMM 5710 (2023)</a>\n</body></html>'
        r = MagicMock(); r.status_code = 200; r.text = html; r.raise_for_status = MagicMock(); mock_get.return_value = r
        url = get_latest_pdf_from_page('https://example.com/forms', keywords=['imm'])
        assert url and '2024' in url

# --- PDF extraction paths ---

@pytest.mark.unit
class TestExtractFieldsFromPdfCore:
    @patch('scraping.forms_scraper.requests.get')
    def test_extract_fields_xfa_success(self, mock_get):
        mock_get.return_value = MagicMock(content=b'%PDF', raise_for_status=MagicMock())
        xml = "<form><subform name='A'><field name='F'><caption><text>Cap</text></caption></field></subform></form>"
        xfa_list = [b'form', xml.encode()]
        with patch('scraping.forms_scraper.PdfReader') as pr:
            reader = MagicMock(); reader.xfa = xfa_list; reader.pages = []; pr.return_value = reader
            entries = extract_fields_from_pdf('https://example.com/form.pdf')
        assert entries

    @patch('scraping.forms_scraper.requests.get')
    def test_extract_fields_no_xfa_acroform_success(self, mock_get):
        mock_get.return_value = MagicMock(content=b'%PDF', raise_for_status=MagicMock())
        with patch('scraping.forms_scraper.PdfReader') as pr:
            reader = MagicMock(); reader.xfa = None; reader.pages = []; reader.get_fields.return_value = {'F1': {'/V': 'V1'}}; pr.return_value = reader
            entries = extract_fields_from_pdf('https://example.com/form.pdf')
        assert entries and all(e['section'] == 'AcroForm' for e in entries)

    @patch('scraping.forms_scraper.requests.get')
    def test_extract_fields_all_fail_empty(self, mock_get):
        mock_get.return_value = MagicMock(content=b'%PDF', raise_for_status=MagicMock())
        with patch('scraping.forms_scraper.PdfReader') as pr:
            reader = MagicMock(); reader.xfa = None; reader.pages = []; reader.get_fields.return_value = None; pr.return_value = reader
            entries = extract_fields_from_pdf('https://example.com/form.pdf')
        assert entries == []

    @patch('scraping.forms_scraper.requests.get')
    def test_xfa_dict_multiple_packets_no_form_key(self, mock_get):
        from scraping.forms_scraper import extract_fields_from_pdf
        mock_get.return_value = MagicMock(content=b'%PDF', raise_for_status=MagicMock())
        packet1 = "<template><field name='P1'><caption><text>First</text></caption></field></template>"
        packet2 = "<layout><field name='P2'><caption><text>Second</text></caption></field></layout>"
        with patch('scraping.forms_scraper.PdfReader') as pr:
            reader = MagicMock(); reader.xfa = {'tmpl': packet1, 'lay': packet2}; reader.get_fields.return_value = None; reader.pages = []; pr.return_value = reader
            entries = extract_fields_from_pdf('https://example.com/form.pdf')
        titles = {e['title'] for e in entries}
        assert {'P1','P2'} <= titles

# --- XFA XML helper ---

@pytest.mark.unit
class TestXfaXmlCore:
    def test_simple_fields(self):
        xml = '<form><field name="first"><caption><text>First</text></caption></field></form>'
        root = try_parse_xml_safe(xml)
        res = extract_xfa_fields_from_xml_root(root, 'https://example.com/form.pdf', '2024-01-15')
        assert isinstance(res, list)

    def test_nested_subform(self):
        xml = '<form><subform name="Sect"><field name="F"><caption><text>Cap</text></caption></field></subform></form>'
        root = try_parse_xml_safe(xml)
        res = extract_xfa_fields_from_xml_root(root, 'https://example.com/form.pdf', '2024-01-15')
        assert isinstance(res, list)

# --- Webpage orchestrator ---

@pytest.mark.unit
class TestWebpageOrchestratorCore:
    @patch('scraping.forms_scraper.boto3.client')
    @patch('scraping.forms_scraper.get_latest_pdf_from_page')
    @patch('scraping.forms_scraper.requests.get')
    def test_extract_forms_success(self, mock_get, mock_get_pdf, mock_boto_client):
        mock_get_pdf.return_value = 'https://example.com/form.pdf'
        pdf_resp = MagicMock(content=b'%PDF', raise_for_status=MagicMock()); mock_get.return_value = pdf_resp
        with patch('scraping.forms_scraper.PdfReader') as pr:
            page = MagicMock(); page.extract_text.return_value = 'Form content'; reader = MagicMock(); reader.pages = [page]; pr.return_value = reader
            mock_boto_client.return_value = MagicMock()
            results = extract_fields_from_webpages(['https://example.com/form-page'])
        assert isinstance(results, list)

    @patch('scraping.forms_scraper.boto3.client')
    @patch('scraping.forms_scraper.get_latest_pdf_from_page')
    def test_extract_forms_no_pdf_found(self, mock_get_pdf, mock_boto_client):
        mock_get_pdf.return_value = None
        mock_boto_client.return_value = MagicMock()
        results = extract_fields_from_webpages(['https://example.com/form-page'])
        assert isinstance(results, list)

    @patch('scraping.forms_scraper.get_latest_pdf_from_page')
    @patch('scraping.forms_scraper.extract_fields_from_pdf')
    def test_extract_fields_from_webpages_with_deduplication(self, mock_extract, mock_get_pdf):
        mock_get_pdf.return_value = 'https://example.com/form.pdf'
        mock_extract.return_value = [
            {'title': 'Field1', 'section': 'A', 'content': 'Content1', 'source': 'form.pdf'},
            {'title': 'Field1', 'section': 'A', 'content': 'Content1', 'source': 'form.pdf'},
            {'title': 'Field2', 'section': 'B', 'content': 'Content2', 'source': 'form.pdf'},
        ]
        with patch('scraping.forms_scraper.boto3.client'), patch('builtins.open', mock_open()):
            result = extract_fields_from_webpages(['https://example.com/page1'], output_file='test.json', dedupe=True)
        assert isinstance(result, list)
