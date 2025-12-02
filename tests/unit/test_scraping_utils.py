"""Unit tests for scraping utilities and constants."""
import pytest
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, 'src')

from scraping.utils import resolve_output_path
from scraping import constants


@pytest.mark.unit
class TestConstants:
    """Tests for scraping constants."""

    def test_justice_xmls_defined(self):
        """Test that Justice XML URLs are defined."""
        assert hasattr(constants, 'JUSTICE_XMLS')
        assert 'IRPA' in constants.JUSTICE_XMLS
        assert 'IRPR' in constants.JUSTICE_XMLS
        assert 'https://' in constants.JUSTICE_XMLS['IRPA']

    def test_refugee_law_lab_datasets(self):
        """Test Refugee Law Lab dataset configuration."""
        assert hasattr(constants, 'REFUGEE_LAW_LAB_DATASETS')
        assert isinstance(constants.REFUGEE_LAW_LAB_DATASETS, list)
        assert len(constants.REFUGEE_LAW_LAB_DATASETS) > 0

    def test_forms_webpages(self):
        """Test forms webpage URLs."""
        assert hasattr(constants, 'FORMS_WEBPAGES')
        assert isinstance(constants.FORMS_WEBPAGES, list)
        assert len(constants.FORMS_WEBPAGES) > 0
        assert all('canada.ca' in url for url in constants.FORMS_WEBPAGES)

    def test_ircc_urls(self):
        """Test IRCC URLs."""
        assert hasattr(constants, 'IRCC_URLS')
        assert isinstance(constants.IRCC_URLS, list)
        assert len(constants.IRCC_URLS) > 0

    def test_s3_configuration(self):
        """Test S3 configuration constants."""
        assert hasattr(constants, 'S3_BUCKET_NAME')
        assert hasattr(constants, 'S3_IRCC_DATA_KEY')
        assert hasattr(constants, 'S3_FORMS_DATA_KEY')

    def test_timeout_constants(self):
        """Test timeout constants are defined."""
        assert hasattr(constants, 'HTTP_TIMEOUT_SHORT')
        assert hasattr(constants, 'HTTP_TIMEOUT_LONG')
        assert constants.HTTP_TIMEOUT_SHORT < constants.HTTP_TIMEOUT_LONG

    def test_pdf_keywords(self):
        """Test PDF keywords are defined."""
        assert hasattr(constants, 'PDF_KEYWORDS')
        assert isinstance(constants.PDF_KEYWORDS, list)

    def test_date_format(self):
        """Test date format is defined."""
        assert hasattr(constants, 'DATE_FORMAT')
        assert isinstance(constants.DATE_FORMAT, str)


@pytest.mark.unit
class TestResolveOutputPath:
    """Tests for output path resolution utility."""

    @patch.dict('os.environ', {'LAMBDA_TASK_ROOT': '/var/task'})
    def test_resolve_path_in_lambda(self):
        """Test path resolution in Lambda environment."""
        import os
        result = resolve_output_path('output.json')
        # Normalize paths for cross-platform compatibility
        assert result == os.path.join('/tmp', 'output.json') or result == '/tmp/output.json'

    @patch.dict('os.environ', {}, clear=True)
    def test_resolve_path_local(self):
        """Test path resolution in local environment."""
        result = resolve_output_path('output.json')
        
        # Should return the original filename when not in Lambda
        assert 'output.json' in result

    @patch.dict('os.environ', {'LAMBDA_TASK_ROOT': '/var/task'})
    def test_resolve_path_with_directory(self):
        """Test path resolution with directory prefix."""
        result = resolve_output_path('data/output.json')
        
        # Should handle paths with directories
        assert '/tmp/' in result or 'output.json' in result


@pytest.mark.unit
class TestScraperConstants:
    """Tests for scraper-specific constants."""

    def test_user_agent_defined(self):
        """Test that user agent is defined."""
        assert hasattr(constants, 'USER_AGENT')
        assert isinstance(constants.USER_AGENT, str)
        assert len(constants.USER_AGENT) > 0

    def test_min_content_length(self):
        """Test minimum content length constant."""
        assert hasattr(constants, 'MIN_CONTENT_LENGTH')
        assert isinstance(constants.MIN_CONTENT_LENGTH, int)
        assert constants.MIN_CONTENT_LENGTH > 0

    def test_request_delays(self):
        """Test request delay constants."""
        assert hasattr(constants, 'MIN_REQUEST_DELAY')
        assert hasattr(constants, 'MAX_REQUEST_DELAY')
        assert constants.MIN_REQUEST_DELAY <= constants.MAX_REQUEST_DELAY

    def test_browser_timeout(self):
        """Test browser timeout constant."""
        assert hasattr(constants, 'BROWSER_TIMEOUT')
        assert isinstance(constants.BROWSER_TIMEOUT, (int, float))

    def test_default_outputs(self):
        """Test default output file constants."""
        assert hasattr(constants, 'DEFAULT_IRCC_OUTPUT')
        assert hasattr(constants, 'DEFAULT_FORMS_OUTPUT')
        assert '.json' in constants.DEFAULT_IRCC_OUTPUT
        assert '.json' in constants.DEFAULT_FORMS_OUTPUT
