"""Additional unit tests for Lambda handlers."""
import pytest
import json
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, 'src')
sys.path.insert(0, 'src/scraping')


@pytest.mark.unit
class TestIRCCScrapingLambda:
    """Tests for IRCC scraping Lambda handler."""

    @patch('scraping.ircc_scraping_lambda.scrape_all')
    def test_handler_success(self, mock_scrape):
        """Test successful handler execution."""
        from scraping.ircc_scraping_lambda import handler
        
        mock_scrape.return_value = [
            {'id': '1', 'content': 'Test content', 'source': 'IRCC'}
        ]
        
        result = handler({}, None)
        
        assert result['status'] == 'completed'
        assert result['records_scraped'] == 1

    @patch('scraping.ircc_scraping_lambda.scrape_all')
    def test_handler_scraping_error(self, mock_scrape):
        """Test handler with scraping error."""
        from scraping.ircc_scraping_lambda import handler
        
        mock_scrape.side_effect = Exception("Scraping failed")
        
        # Handler doesn't catch exceptions, so test should expect exception
        with pytest.raises(Exception, match="Scraping failed"):
            handler({}, None)


@pytest.mark.unit
class TestFormsScrapingLambda:
    """Tests for forms scraping Lambda handler."""

    @patch('scraping.forms_scraping_lambda.extract_fields_from_webpages')
    def test_handler_success(self, mock_scrape):
        """Test successful handler execution."""
        from scraping.forms_scraping_lambda import handler
        
        mock_scrape.return_value = [
            {'id': '1', 'content': 'Form content', 'source': 'Forms'}
        ]
        
        result = handler({}, None)
        
        assert result['status'] == 'completed'
        assert result['records_scraped'] == 1


@pytest.mark.unit
class TestIRPRIRPAScrapingLambda:
    """Tests for IRPR/IRPA scraping Lambda handler."""

    @patch('scraping.irpr_irpa_scraping_lambda.scrape_irpr_irpa_laws')
    def test_handler_success(self, mock_scrape):
        """Test successful handler execution."""
        from scraping.irpr_irpa_scraping_lambda import handler
        
        mock_scrape.return_value = [
            {'id': '1', 'content': 'Regulation content', 'source': 'IRPR'}
        ]
        
        result = handler({}, None)
        
        assert result['status'] == 'completed'
        assert result['records_scraped'] == 1


@pytest.mark.unit
class TestRefugeeLawScrapingLambda:
    """Tests for Refugee Law scraping Lambda handler."""

    @patch('scraping.refugee_law_scraping_lambda.scrape_refugee_law_lab')
    def test_handler_success(self, mock_scrape):
        """Test successful handler execution."""
        from scraping.refugee_law_scraping_lambda import handler
        
        mock_scrape.return_value = [
            {'id': '1', 'content': 'Decision content', 'source': 'Refugee Law Lab'}
        ]
        
        result = handler({}, None)
        
        assert result['status'] == 'completed'
        assert result['records_scraped'] == 1
