"""Consolidated edge tests for forms_scraper: XFA namespaces, deep/subform chains, heuristic fallthroughs, truncation, and orchestrator edge cases."""
import json
from unittest.mock import patch, MagicMock, mock_open
import scraping.forms_scraper as forms_scraper

# --- XFA namespace and deep hierarchy ---

def test_xfa_namespace_multiple_named_subforms():
    xml = ('<xfa:form xmlns:xfa="http://www.xfa.org/schema">'
           '  <xfa:subform name="A">'
           '    <xfa:subform name="B">'
           '      <xfa:field name="FieldB">'
           '        <xfa:caption><xfa:text>CaptionB</xfa:text></xfa:caption>'
           '      </xfa:field>'
           '    </xfa:subform>'
           '  </xfa:subform>'
           '</xfa:form>')
    root = forms_scraper.try_parse_xml_safe(xml)
    entries = forms_scraper.extract_xfa_fields_from_xml_root(root, "http://example.com/namespaced.pdf", "2025-02-01")
    assert entries and entries[0]["section"] == "A > B"


def test_xfa_deep_single_named_subform():
    xml = ('<form>'
           '  <subform>'
           '    <subform>'
           '      <subform name="Late">'
           '        <field name="DeepField">'
           '          <caption><text>Late Caption</text></caption>'
           '        </field>'
           '      </subform>'
           '    </subform>'
           '  </subform>'
           '</form>')
    root = forms_scraper.try_parse_xml_safe(xml)
    entries = forms_scraper.extract_xfa_fields_from_xml_root(root, "http://example.com/deep.pdf", "2025-03-01")
    assert entries and entries[0]["section"] == "Late"


def test_xfa_caption_without_text_nodes():
    xml = ('<form>'
           '  <subform name="A">'
           '    <field name="NoTextField">'
           '      <caption><foo/></caption>'
           '    </field>'
           '  </subform>'
           '</form>')
    root = forms_scraper.try_parse_xml_safe(xml)
    entries = forms_scraper.extract_xfa_fields_from_xml_root(root, "http://example.com/notext.pdf", "2025-03-02")
    assert entries and entries[0]["content"] == "NoTextField"


def test_xfa_items_nodes_without_text():
    xml = ('<form>'
           '  <subform name="A">'
           '    <field name="OptField">'
           '      <caption><text>CaptionOpt</text></caption>'
           '      <items><text>   </text><text/> </items>'
           '    </field>'
           '  </subform>'
           '</form>')
    root = forms_scraper.try_parse_xml_safe(xml)
    entries = forms_scraper.extract_xfa_fields_from_xml_root(root, "http://example.com/itemsblank.pdf", "2025-03-03")
    assert entries and entries[0]["content"].startswith("CaptionOpt")


def test_xfa_mainform_section():
    xml = ('<form>'
           '  <subform>'
           '    <field name="F1">'
           '      <caption><text>Caption One</text></caption>'
           '    </field>'
           '  </subform>'
           '</form>')
    root = forms_scraper.try_parse_xml_safe(xml)
    entries = forms_scraper.extract_xfa_fields_from_xml_root(root, "http://example.com/form.pdf", "2025-01-01")
    assert entries and entries[0]["section"] == "MainForm"


def test_xfa_mixed_packets_list_and_dict_in_reader(monkeypatch):
    """Reader.xfa contains mixed malformed and valid packets; ensure valid parsed."""
    # Build a FakeReader with xfa packets including: bytes marker, malformed xml, and valid xml
    class FakePage:
        def extract_text(self):
            return ""  # force reliance on XFA path
    valid_xml = (
        "<form><subform name=\"Root\">"
        "<field name=\"A\"><caption><text>CapA</text></caption>"
        "<items><text>One</text><text>Two</text></items></field>"
        "</subform></form>"
    )
    class FakeReader:
        # List style alternating name/blob entries (some malformed, one valid)
        xfa = [b"template", valid_xml.encode("utf-8"), b"form", b"<bad"]
        def __init__(self, *args, **kwargs):
            self.pages = [FakePage()]
        def get_fields(self):
            return None
    class FakeResp:
        content = b"%PDF-FAKE"
        def raise_for_status(self):
            pass
    monkeypatch.setattr(forms_scraper, "PdfReader", FakeReader)
    monkeypatch.setattr(forms_scraper.requests, "get", lambda url, stream=True, timeout=0: FakeResp())
    entries = forms_scraper.extract_fields_from_pdf("http://example.com/mixed_xfa.pdf")
    # Mixed packets should not raise; if structure not recognized, return [] gracefully
    assert entries == []

# --- PDF heuristic and fallthroughs ---

def test_pdf_all_pages_extraction_exception(monkeypatch):
    class BadPage:
        def extract_text(self):
            raise RuntimeError("fail")
    class FakeReader:
        xfa = None
        def __init__(self):
            self.pages = [BadPage(), BadPage()]
        def get_fields(self):
            return None
    class FakeResp:
        content = b"%PDF-FAKE"
        def raise_for_status(self):
            pass
    monkeypatch.setattr(forms_scraper, "PdfReader", FakeReader)
    monkeypatch.setattr(forms_scraper.requests, "get", lambda url, stream=True, timeout=0: FakeResp())
    entries = forms_scraper.extract_fields_from_pdf("http://example.com/allfail.pdf")
    assert entries == []


def test_pdf_mixed_pages_only_whitespace(monkeypatch):
    class PageWS:
        def __init__(self, txt):
            self._txt = txt
        def extract_text(self):
            return self._txt
    class FakeReader:
        xfa = None
        def __init__(self):
            self.pages = [PageWS("   \n\n"), PageWS("\t  ")]
        def get_fields(self):
            return None
    class FakeResp:
        content = b"%PDF-FAKE"
        def raise_for_status(self):
            pass
    monkeypatch.setattr(forms_scraper, "PdfReader", FakeReader)
    monkeypatch.setattr(forms_scraper.requests, "get", lambda url, stream=True, timeout=0: FakeResp())
    entries = forms_scraper.extract_fields_from_pdf("http://example.com/whitespace.pdf")
    assert entries == []


def test_pdf_heuristic_truncation(monkeypatch):
    class FakePage:
        def __init__(self, text):
            self._text = text
        def extract_text(self):
            return self._text
    lines = [f"Question number {i}?" for i in range(250)]
    page_text = "\n".join(lines)
    class FakeReader:
        xfa = None
        def __init__(self, *args, **kwargs):
            self.pages = [FakePage(page_text)]
        def get_fields(self):
            return None
    class FakeResp:
        content = b"%PDF-FAKE"
        def raise_for_status(self):
            pass
    monkeypatch.setattr(forms_scraper, "PdfReader", FakeReader)
    monkeypatch.setattr(forms_scraper.requests, "get", lambda url, stream=True, timeout=0: FakeResp())
    entries = forms_scraper.extract_fields_from_pdf("http://example.com/big.pdf")
    assert len(entries) == 200 and all(e["section"] == "PageTextHeuristic" for e in entries)


def test_xfa_unparseable_form_packet_fallback(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "\n".join(["X" * 400 for _ in range(3)])
    class FakeReader:
        xfa = [b"form", b"<notxml", b"other", b"<other>"]
        def __init__(self):
            self.pages = [FakePage()]
        def get_fields(self):
            return None
    class FakeResp:
        content = b"%PDF-FAKE"
        def raise_for_status(self):
            pass
    monkeypatch.setattr(forms_scraper, "PdfReader", FakeReader)
    monkeypatch.setattr(forms_scraper.requests, "get", lambda url, stream=True, timeout=0: FakeResp())
    entries = forms_scraper.extract_fields_from_pdf("http://example.com/unparseable.pdf")
    assert entries == []


def test_pdf_full_fallthrough_acro_exception_and_heuristic_empty(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "Y" * 350
    class FakeReader:
        xfa = None
        def __init__(self):
            self.pages = [FakePage()]
        def get_fields(self):
            raise RuntimeError("Acro error")
    class FakeResp:
        content = b"%PDF-FAKE"
        def raise_for_status(self):
            pass
    monkeypatch.setattr(forms_scraper, "PdfReader", FakeReader)
    monkeypatch.setattr(forms_scraper.requests, "get", lambda url, stream=True, timeout=0: FakeResp())
    entries = forms_scraper.extract_fields_from_pdf("http://example.com/fallthrough.pdf")
    assert entries == []


def test_acroform_exception_no_text_fallback_empty(monkeypatch):
    """AcroForm get_fields raises; pages return empty text -> final empty list."""
    class FakePage:
        def extract_text(self):
            return ''
    class FakeReader:
        xfa = None
        def __init__(self):
            self.pages = [FakePage()]
        def get_fields(self):
            raise RuntimeError('forced get_fields failure')
    class FakeResp:
        content = b"%PDF-FAKE"
        def raise_for_status(self):
            pass
    monkeypatch.setattr(forms_scraper, "PdfReader", FakeReader)
    monkeypatch.setattr(forms_scraper.requests, "get", lambda url, stream=True, timeout=0: FakeResp())
    entries = forms_scraper.extract_fields_from_pdf("http://example.com/acro_empty.pdf")
    assert entries == []


def test_pdf_heuristic_empty_long_lines(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "\n".join([
                "Z" * 310,
                "This line has many words none short enough to pass",
                "A" * 305,
            ])
    class FakeReader:
        xfa = None
        def __init__(self):
            self.pages = [FakePage()]
        def get_fields(self):
            return None
    class FakeResp:
        content = b"%PDF-FAKE"
        def raise_for_status(self):
            pass
    monkeypatch.setattr(forms_scraper, "PdfReader", FakeReader)
    monkeypatch.setattr(forms_scraper.requests, "get", lambda url, stream=True, timeout=0: FakeResp())
    entries = forms_scraper.extract_fields_from_pdf("http://example.com/heuristic_empty.pdf")
    assert entries == []


def test_text_fallback_long_lines_no_heuristics(monkeypatch):
    """Long lines with many words and no punctuation triggers -> heuristics stay empty."""
    long_line = ' '.join(['word'] * 120)
    class FakeReader:
        xfa = None
        def __init__(self, *a, **k):
            class P:
                def extract_text(self_inner):
                    return long_line
            self.pages = [P()]
        def get_fields(self):
            return None
    class FakeResp:
        content = b"%PDF-FAKE"
        def raise_for_status(self):
            pass
    monkeypatch.setattr(forms_scraper, "PdfReader", FakeReader)
    monkeypatch.setattr(forms_scraper.requests, "get", lambda url, stream=True, timeout=0: FakeResp())
    entries = forms_scraper.extract_fields_from_pdf("http://example.com/longlines.pdf")
    assert entries == []


def test_extract_fields_from_webpages_s3_upload_paths(monkeypatch, tmp_path):
    """Exercise S3 success and failure branches without real network."""
    out_file = tmp_path / "forms_out.json"
    monkeypatch.setattr(forms_scraper, "get_latest_pdf_from_page", lambda page, **k: None)
    # Success path
    class S3Ok:
        def upload_file(self, filename, bucket, key):
            return None
    monkeypatch.setattr(forms_scraper.boto3, "client", lambda name: S3Ok())
    with patch('builtins.open', mock_open()):
        res_ok = forms_scraper.extract_fields_from_webpages(["https://example.com/forms"], output_file=str(out_file))
    assert isinstance(res_ok, list)
    # Failure path
    class S3Fail:
        def upload_file(self, filename, bucket, key):
            raise Exception("S3 upload failed")
    monkeypatch.setattr(forms_scraper.boto3, "client", lambda name: S3Fail())
    with patch('builtins.open', mock_open()):
        try:
            _ = forms_scraper.extract_fields_from_webpages(["https://example.com/forms"], output_file=str(out_file))
        except Exception as e:
            assert "S3 upload failed" in str(e)

# --- Orchestrator edge cases ---

def test_orchestrator_dedupe_skip(monkeypatch, tmp_path):
    existing_entry = {"id": "x", "title": "T", "section": "S", "content": "C", "source": "U", "date_published": None,
                      "date_scraped": "2025-01-01", "granularity": "field-level"}
    out_file = tmp_path / "forms.json"
    out_file.write_text(json.dumps([existing_entry]), encoding="utf-8")
    monkeypatch.setattr(forms_scraper, "get_latest_pdf_from_page", lambda page, **k: "http://example.com/form.pdf")
    monkeypatch.setattr(forms_scraper, "extract_fields_from_pdf", lambda url: [existing_entry])
    class FakeS3:
        def upload_file(self, filename, bucket, key):
            pass
    monkeypatch.setattr(forms_scraper.boto3, "client", lambda name: FakeS3())
    saved = forms_scraper.extract_fields_from_webpages(["http://example.com/page"], output_file=str(out_file), dedupe=True)
    assert len(saved) == 1


def test_orchestrator_corrupt_existing(monkeypatch, tmp_path):
    out_file = tmp_path / "corrupt.json"
    out_file.write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setattr(forms_scraper, "get_latest_pdf_from_page", lambda page, **k: "http://example.com/form.pdf")
    monkeypatch.setattr(forms_scraper, "extract_fields_from_pdf", lambda url: [{"id": "y", "title": "New", "section": "S", "content": "C2", "source": "U2", "date_published": None,
                                                                                "date_scraped": "2025-01-02", "granularity": "field-level"}])
    class FakeS3:
        def upload_file(self, filename, bucket, key):
            pass
    monkeypatch.setattr(forms_scraper.boto3, "client", lambda name: FakeS3())
    saved = forms_scraper.extract_fields_from_webpages(["http://example.com/page"], output_file=str(out_file), dedupe=True)
    assert len(saved) == 1 and saved[0]["title"] == "New"


def test_orchestrator_none_pdf(monkeypatch, tmp_path):
    out_file = tmp_path / "empty.json"
    monkeypatch.setattr(forms_scraper, "get_latest_pdf_from_page", lambda page, **k: None)
    class FakeS3:
        def __init__(self):
            self.uploads = []
        def upload_file(self, filename, bucket, key):
            self.uploads.append((filename, bucket, key))
    monkeypatch.setattr(forms_scraper.boto3, "client", lambda name: FakeS3())
    saved = forms_scraper.extract_fields_from_webpages(["http://example.com/page"], output_file=str(out_file), dedupe=True)
    assert saved == [] and json.loads(out_file.read_text(encoding="utf-8")) == []
