"""Unit tests for IRPR/IRPA scraper with extensive mocking."""
import unittest
from unittest.mock import Mock, MagicMock, patch, mock_open
import xml.etree.ElementTree as ET
import uuid


class TestIRPRIRPAScraper(unittest.TestCase):
    """Test IRPR/IRPA XML parsing scraper functions."""

    def test_extract_text_with_text_tags(self):
        """Test extracting text from XML elements with Text tags."""
        from scraping.irpr_irpa_scraper import extract_text
        
        xml_str = '''<?xml version="1.0"?>
        <root xmlns="http://example.com">
            <Text>First paragraph.</Text>
            <Text>Second paragraph.</Text>
        </root>'''
        
        root = ET.fromstring(xml_str)
        ns = {"ns": "http://example.com"}
        
        result = extract_text(root, ".//ns:Text", ns)
        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_extract_text_with_itertext_fallback(self):
        """Test extracting text using itertext when no Text tags exist."""
        from scraping.irpr_irpa_scraper import extract_text
        
        xml_str = '''<?xml version="1.0"?>
        <root>
            <p>Some content</p>
            <span>More content</span>
        </root>'''
        
        root = ET.fromstring(xml_str)
        result = extract_text(root, ".//Text", {})
        assert "Some content" in result
        assert "More content" in result

    def test_extract_text_empty_element(self):
        """Test extracting text from empty element."""
        from scraping.irpr_irpa_scraper import extract_text
        
        xml_str = '<root></root>'
        root = ET.fromstring(xml_str)
        result = extract_text(root, ".//Text", {})
        assert result == ""

    def test_process_element_with_number_and_heading(self):
        """Test processing element with both number and heading."""
        from scraping.irpr_irpa_scraper import process_element
        
        xml_str = '''<?xml version="1.0"?>
        <Section>
            <Num>5</Num>
            <Heading>Important Section</Heading>
            <Text>Section content here.</Text>
        </Section>'''
        
        root = ET.fromstring(xml_str)
        docs = []
        
        process_element(
            root, docs, "Test Law", {}, 
            "Section", "Subsection", "Num", "Heading", ".//Text"
        )
        
        assert len(docs) == 1
        assert docs[0]["section"] == "5"
        assert docs[0]["title"] == "Important Section"
        assert "Section content" in docs[0]["content"]
        assert docs[0]["source"] == "Test Law"
        assert docs[0]["granularity"] == "section"

    def test_process_element_without_number(self):
        """Test processing element without number generates synthetic number."""
        from scraping.irpr_irpa_scraper import process_element
        
        xml_str = '''<?xml version="1.0"?>
        <Section>
            <Heading>No Number Section</Heading>
            <Text>Content without number.</Text>
        </Section>'''
        
        root = ET.fromstring(xml_str)
        docs = []
        
        process_element(
            root, docs, "Test Law", {}, 
            "Section", "Subsection", "Num", "Heading", ".//Text"
        )
        
        assert len(docs) == 1
        assert "unlabeled" in docs[0]["section"]
        assert docs[0]["title"] == "No Number Section"

    def test_process_element_without_heading(self):
        """Test processing element without heading generates synthetic heading."""
        from scraping.irpr_irpa_scraper import process_element
        
        xml_str = '''<?xml version="1.0"?>
        <Section>
            <Num>10</Num>
            <Text>Content without heading.</Text>
        </Section>'''
        
        root = ET.fromstring(xml_str)
        docs = []
        
        process_element(
            root, docs, "Test Law", {}, 
            "Section", "Subsection", "Num", "Heading", ".//Text"
        )
        
        assert len(docs) == 1
        assert docs[0]["section"] == "10"
        assert "Test Law Section 10" in docs[0]["title"]

    def test_process_element_with_margnote(self):
        """Test processing element with Margnote as heading fallback."""
        from scraping.irpr_irpa_scraper import process_element
        
        xml_str = '''<?xml version="1.0"?>
        <Section>
            <Num>3</Num>
            <Margnote>Marginal Note Heading</Margnote>
            <Text>Content with margnote.</Text>
        </Section>'''
        
        root = ET.fromstring(xml_str)
        docs = []
        
        process_element(
            root, docs, "Test Law", {}, 
            "Section", "Subsection", "Num", "Heading", ".//Text"
        )
        
        assert len(docs) == 1
        assert docs[0]["title"] == "Marginal Note Heading"

    def test_process_element_with_nested_subsections(self):
        """Test recursive processing of nested subsections."""
        from scraping.irpr_irpa_scraper import process_element
        
        xml_str = '''<?xml version="1.0"?>
        <Section>
            <Num>1</Num>
            <Heading>Main Section</Heading>
            <Text>Main content.</Text>
            <Subsection>
                <Num>1</Num>
                <Text>Subsection content.</Text>
            </Subsection>
        </Section>'''
        
        root = ET.fromstring(xml_str)
        docs = []
        
        process_element(
            root, docs, "Test Law", {}, 
            "Section", "Subsection", "Num", "Heading", ".//Text"
        )
        
        assert len(docs) == 2
        assert docs[0]["section"] == "1"
        assert docs[1]["section"] == "1.1"
        assert docs[1]["title"] == "Main Section (continuation)"

    def test_process_element_with_minimal_content(self):
        """Test that elements with minimal content still get extracted via itertext."""
        from scraping.irpr_irpa_scraper import process_element
        
        xml_str = '''<?xml version="1.0"?>
        <Section>
            <Num>1</Num>
            <Heading>Minimal Section</Heading>
        </Section>'''
        
        root = ET.fromstring(xml_str)
        docs = []
        
        process_element(
            root, docs, "Test Law", {}, 
            "Section", "Subsection", "Num", "Heading", ".//Text"
        )
        
        # Should extract text via itertext fallback
        assert len(docs) >= 1

    @patch('scraping.irpr_irpa_scraper.requests.get')
    def test_parse_and_store_with_namespace(self, mock_get):
        """Test parsing XML with namespace."""
        from scraping.irpr_irpa_scraper import parse_and_store
        
        xml_str = '''<?xml version="1.0"?>
        <root xmlns="http://laws.justice.gc.ca">
            <Section>
                <Num>1</Num>
                <Heading>Test Section</Heading>
                <Text>Test content.</Text>
            </Section>
        </root>'''
        
        mock_response = Mock()
        mock_response.content = xml_str.encode('utf-8')
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        docs = []
        parse_and_store("Test Law", "http://example.com/law.xml", docs)
        
        assert len(docs) >= 1
        assert docs[0]["source"] == "Test Law"

    @patch('scraping.irpr_irpa_scraper.requests.get')
    def test_parse_and_store_without_namespace(self, mock_get):
        """Test parsing XML without namespace."""
        from scraping.irpr_irpa_scraper import parse_and_store
        
        xml_str = '''<?xml version="1.0"?>
        <root>
            <Section>
                <Num>2</Num>
                <Heading>No Namespace Section</Heading>
                <Text>No namespace content.</Text>
            </Section>
        </root>'''
        
        mock_response = Mock()
        mock_response.content = xml_str.encode('utf-8')
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        docs = []
        parse_and_store("Test Law", "http://example.com/law.xml", docs)
        
        assert len(docs) >= 1

    @patch('scraping.irpr_irpa_scraper.requests.get')
    def test_parse_and_store_multiple_sections(self, mock_get):
        """Test parsing XML with multiple top-level sections."""
        from scraping.irpr_irpa_scraper import parse_and_store
        
        xml_str = '''<?xml version="1.0"?>
        <root>
            <Section>
                <Num>1</Num>
                <Text>First section.</Text>
            </Section>
            <Section>
                <Num>2</Num>
                <Text>Second section.</Text>
            </Section>
        </root>'''
        
        mock_response = Mock()
        mock_response.content = xml_str.encode('utf-8')
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        docs = []
        parse_and_store("Multi Section Law", "http://example.com/law.xml", docs)
        
        assert len(docs) >= 2

    @patch('scraping.irpr_irpa_scraper.boto3.client')
    @patch('scraping.irpr_irpa_scraper.parse_and_store')
    @patch('builtins.open', new_callable=mock_open)
    def test_scrape_irpr_irpa_laws_basic(self, mock_file, mock_parse, mock_boto):
        """Test basic scraping workflow."""
        from scraping.irpr_irpa_scraper import scrape_irpr_irpa_laws
        
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        
        # Mock parse_and_store to add some docs
        def add_docs(law_name, xml_url, docs):
            docs.append({
                "id": str(uuid.uuid4()),
                "title": f"{law_name} Test",
                "section": "1",
                "content": "Test content",
                "source": law_name,
                "date_published": None,
                "date_scraped": "2024-01-01",
                "granularity": "section"
            })
        
        mock_parse.side_effect = add_docs
        
        result = scrape_irpr_irpa_laws(upload_to_s3=True)
        
        assert isinstance(result, list)
        assert len(result) > 0
        assert mock_s3.upload_file.called

    @patch('scraping.irpr_irpa_scraper.boto3.client')
    @patch('scraping.irpr_irpa_scraper.parse_and_store')
    @patch('builtins.open', new_callable=mock_open)
    def test_scrape_irpr_irpa_laws_no_s3_upload(self, mock_file, mock_parse, mock_boto):
        """Test scraping without S3 upload."""
        from scraping.irpr_irpa_scraper import scrape_irpr_irpa_laws
        
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        
        def add_docs(law_name, xml_url, docs):
            docs.append({
                "id": str(uuid.uuid4()),
                "title": "Test",
                "section": "1",
                "content": "Test",
                "source": law_name,
                "date_published": None,
                "date_scraped": "2024-01-01",
                "granularity": "section"
            })
        
        mock_parse.side_effect = add_docs
        
        result = scrape_irpr_irpa_laws(upload_to_s3=False)
        
        assert isinstance(result, list)
        assert not mock_s3.upload_file.called

    @patch('scraping.irpr_irpa_scraper.boto3.client')
    @patch('scraping.irpr_irpa_scraper.parse_and_store')
    @patch('builtins.open', new_callable=mock_open)
    def test_scrape_irpr_irpa_laws_custom_output(self, mock_file, mock_parse, mock_boto):
        """Test scraping with custom output file."""
        from scraping.irpr_irpa_scraper import scrape_irpr_irpa_laws
        
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        
        def add_docs(law_name, xml_url, docs):
            docs.append({
                "id": str(uuid.uuid4()),
                "title": "Test",
                "section": "1",
                "content": "Test",
                "source": law_name,
                "date_published": None,
                "date_scraped": "2024-01-01",
                "granularity": "section"
            })
        
        mock_parse.side_effect = add_docs
        
        result = scrape_irpr_irpa_laws(output_file="custom.json", upload_to_s3=False)
        
        assert isinstance(result, list)
        # Verify file operations occurred
        assert mock_file.called


if __name__ == "__main__":
    unittest.main()
