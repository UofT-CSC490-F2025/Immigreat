"""Unit tests for Refugee Law Lab scraper with extensive mocking."""
import unittest
from unittest.mock import Mock, MagicMock, patch, mock_open
import json
import uuid


class TestRefugeeLawLabScraper(unittest.TestCase):
    """Test Refugee Law Lab Hugging Face dataset scraper functions."""

    @patch('scraping.refugee_law_lab_scraper.requests.get')
    def test_load_hf_dataset_basic(self, mock_get):
        """Test loading dataset from Hugging Face API."""
        from scraping.refugee_law_lab_scraper import load_hf_dataset_as_dict
        
        # Mock API response with rows
        mock_response = Mock()
        mock_response.json.return_value = {
            "rows": [
                {"row": {"name": "Case 1", "unofficial_text": "Decision text 1"}},
                {"row": {"name": "Case 2", "unofficial_text": "Decision text 2"}}
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = load_hf_dataset_as_dict("test/repo", "subset", "train")
        
        assert len(result) == 2
        assert result[0]["name"] == "Case 1"
        assert result[1]["name"] == "Case 2"

    @patch('scraping.refugee_law_lab_scraper.requests.get')
    def test_load_hf_dataset_pagination(self, mock_get):
        """Test dataset pagination with multiple API calls."""
        from scraping.refugee_law_lab_scraper import load_hf_dataset_as_dict
        
        # First page with 100 rows
        response1 = Mock()
        response1.json.return_value = {
            "rows": [{"row": {"id": f"case{i}"}} for i in range(100)]
        }
        response1.raise_for_status = Mock()
        
        # Second call returns less than limit (50 rows), indicating end
        response2 = Mock()
        response2.json.return_value = {
            "rows": [{"row": {"id": f"case{i}"}} for i in range(100, 150)]
        }
        response2.raise_for_status = Mock()
        
        mock_get.side_effect = [response1, response2]
        
        result = load_hf_dataset_as_dict("test/repo", "subset", "train")
        
        # Should stop after second call since it returned less than 100 rows
        assert len(result) == 150
        assert mock_get.call_count == 2

    @patch('scraping.refugee_law_lab_scraper.requests.get')
    def test_load_hf_dataset_empty_response(self, mock_get):
        """Test handling empty dataset response."""
        from scraping.refugee_law_lab_scraper import load_hf_dataset_as_dict
        
        mock_response = Mock()
        mock_response.json.return_value = {"rows": []}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = load_hf_dataset_as_dict("test/repo", "subset", "train")
        
        assert len(result) == 0

    @patch('scraping.refugee_law_lab_scraper.requests.get')
    @patch('scraping.refugee_law_lab_scraper.time.sleep')
    def test_load_hf_dataset_rate_limit_retry(self, mock_sleep, mock_get):
        """Test retry logic on rate limit (429 error)."""
        from scraping.refugee_law_lab_scraper import load_hf_dataset_as_dict
        
        # First call rate limited, second succeeds
        error_response = Mock()
        error_response.status_code = 429
        error_response.raise_for_status.side_effect = Exception("Rate limited")
        
        from requests.exceptions import HTTPError
        error = HTTPError()
        error.response = error_response
        
        success_response = Mock()
        success_response.json.return_value = {
            "rows": [{"row": {"name": "Case 1"}}]
        }
        success_response.raise_for_status = Mock()
        
        # First call fails with 429, second succeeds
        def side_effect(*args, **kwargs):
            if mock_get.call_count == 1:
                raise error
            return success_response
        
        mock_get.side_effect = side_effect
        
        result = load_hf_dataset_as_dict("test/repo", "subset", "train")
        
        assert len(result) == 1
        assert mock_sleep.called  # Should have waited before retry

    @patch('scraping.refugee_law_lab_scraper.requests.get')
    def test_load_hf_dataset_no_rows_key(self, mock_get):
        """Test handling response without 'rows' key."""
        from scraping.refugee_law_lab_scraper import load_hf_dataset_as_dict
        
        mock_response = Mock()
        mock_response.json.return_value = {"error": "Invalid request"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = load_hf_dataset_as_dict("test/repo", "subset", "train")
        
        assert len(result) == 0

    def test_transform_record_full_data(self):
        """Test transforming complete record."""
        from scraping.refugee_law_lab_scraper import transform_record
        
        record = {
            "name": "Test Case Name",
            "unofficial_text": "Full decision text here.",
            "dataset": "RAD",
            "source_url": "https://example.com/case",
            "document_date": "2024-01-15",
            "scraped_timestamp": "2024-01-20",
            "language": "en"
        }
        
        result = transform_record(record)
        
        assert result is not None
        assert result["title"] == "Test Case Name"
        assert result["content"] == "Full decision text here."
        assert result["section"] == "RAD"
        assert result["source"] == "https://example.com/case"
        assert result["date_published"] == "2024-01-15"
        assert result["date_scraped"] == "2024-01-20"
        assert result["granularity"] == "decision"
        assert "id" in result  # UUID should be generated

    def test_transform_record_french_filtered(self):
        """Test that French records are filtered out."""
        from scraping.refugee_law_lab_scraper import transform_record
        
        record = {
            "name": "Cas de Test",
            "unofficial_text": "Texte en français.",
            "language": "fr"
        }
        
        result = transform_record(record)
        
        assert result is None  # French records should return None

    def test_transform_record_missing_fields(self):
        """Test transforming record with missing fields."""
        from scraping.refugee_law_lab_scraper import transform_record
        
        record = {
            "unofficial_text": "Minimal data."
        }
        
        result = transform_record(record)
        
        assert result is not None
        assert result["title"] == ""
        assert result["content"] == "Minimal data."
        assert result["section"] == ""
        assert result["source"] == ""

    def test_transform_record_english_language(self):
        """Test English records are accepted."""
        from scraping.refugee_law_lab_scraper import transform_record
        
        record = {
            "name": "English Case",
            "unofficial_text": "English text.",
            "language": "en"
        }
        
        result = transform_record(record)
        
        assert result is not None
        assert result["title"] == "English Case"

    def test_transform_record_no_language_field(self):
        """Test records without language field are accepted."""
        from scraping.refugee_law_lab_scraper import transform_record
        
        record = {
            "name": "No Language Field",
            "unofficial_text": "Text without language."
        }
        
        result = transform_record(record)
        
        assert result is not None

    @patch('scraping.refugee_law_lab_scraper.boto3.client')
    @patch('scraping.refugee_law_lab_scraper.load_hf_dataset_as_dict')
    @patch('builtins.open', new_callable=mock_open)
    def test_scrape_refugee_law_lab_basic(self, mock_file, mock_load, mock_boto):
        """Test basic scraping workflow."""
        from scraping.refugee_law_lab_scraper import scrape_refugee_law_lab
        
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        
        # Mock dataset loading
        mock_load.return_value = [
            {
                "name": "Case 1",
                "unofficial_text": "Decision 1",
                "dataset": "RAD",
                "language": "en"
            },
            {
                "name": "Case 2",
                "unofficial_text": "Decision 2",
                "dataset": "RPD",
                "language": "en"
            }
        ]
        
        result = scrape_refugee_law_lab(upload_to_s3=True)
        
        assert isinstance(result, list)
        assert len(result) > 0  # Should have records from both datasets
        assert mock_s3.upload_file.called

    @patch('scraping.refugee_law_lab_scraper.boto3.client')
    @patch('scraping.refugee_law_lab_scraper.load_hf_dataset_as_dict')
    @patch('builtins.open', new_callable=mock_open)
    def test_scrape_refugee_law_lab_filters_french(self, mock_file, mock_load, mock_boto):
        """Test that French records are filtered out."""
        from scraping.refugee_law_lab_scraper import scrape_refugee_law_lab
        
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        
        # Mix of English and French records
        mock_load.return_value = [
            {"name": "English", "unofficial_text": "English text", "language": "en"},
            {"name": "Français", "unofficial_text": "Texte français", "language": "fr"},
            {"name": "English2", "unofficial_text": "More English", "language": "en"}
        ]
        
        result = scrape_refugee_law_lab(upload_to_s3=False)
        
        # Should only have 2 English records per dataset
        # Since we have 2 datasets (RAD, RPD) in REFUGEE_LAW_LAB_DATASETS
        assert len(result) > 0
        # Verify no French titles in result
        for record in result:
            assert record["title"] != "Français"

    @patch('scraping.refugee_law_lab_scraper.boto3.client')
    @patch('scraping.refugee_law_lab_scraper.load_hf_dataset_as_dict')
    @patch('builtins.open', new_callable=mock_open)
    def test_scrape_refugee_law_lab_no_s3_upload(self, mock_file, mock_load, mock_boto):
        """Test scraping without S3 upload."""
        from scraping.refugee_law_lab_scraper import scrape_refugee_law_lab
        
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        
        mock_load.return_value = [
            {"name": "Case", "unofficial_text": "Text", "language": "en"}
        ]
        
        result = scrape_refugee_law_lab(upload_to_s3=False)
        
        assert isinstance(result, list)
        assert not mock_s3.upload_file.called

    @patch('scraping.refugee_law_lab_scraper.boto3.client')
    @patch('scraping.refugee_law_lab_scraper.load_hf_dataset_as_dict')
    @patch('builtins.open', new_callable=mock_open)
    def test_scrape_refugee_law_lab_custom_output(self, mock_file, mock_load, mock_boto):
        """Test scraping with custom output file."""
        from scraping.refugee_law_lab_scraper import scrape_refugee_law_lab
        
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        
        mock_load.return_value = [
            {"name": "Case", "unofficial_text": "Text", "language": "en"}
        ]
        
        result = scrape_refugee_law_lab(output_file="custom.json", upload_to_s3=False)
        
        assert isinstance(result, list)
        assert mock_file.called

    @patch('scraping.refugee_law_lab_scraper.boto3.client')
    @patch('scraping.refugee_law_lab_scraper.load_hf_dataset_as_dict')
    @patch('builtins.open', new_callable=mock_open)
    def test_scrape_refugee_law_lab_multiple_datasets(self, mock_file, mock_load, mock_boto):
        """Test scraping multiple datasets (RAD and RPD)."""
        from scraping.refugee_law_lab_scraper import scrape_refugee_law_lab
        
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        
        # Different responses for different datasets
        call_count = [0]
        def load_side_effect(repo_id, subset, split):
            call_count[0] += 1
            return [
                {
                    "name": f"{subset} Case {call_count[0]}",
                    "unofficial_text": f"Text from {subset}",
                    "dataset": subset,
                    "language": "en"
                }
            ]
        
        mock_load.side_effect = load_side_effect
        
        result = scrape_refugee_law_lab(upload_to_s3=False)
        
        assert isinstance(result, list)
        # Should be called once per dataset
        assert mock_load.call_count == 2  # RAD + RPD

    @patch('scraping.refugee_law_lab_scraper.boto3.client')
    @patch('scraping.refugee_law_lab_scraper.load_hf_dataset_as_dict')
    @patch('builtins.open', new_callable=mock_open)
    def test_scrape_refugee_law_lab_empty_dataset(self, mock_file, mock_load, mock_boto):
        """Test handling empty dataset."""
        from scraping.refugee_law_lab_scraper import scrape_refugee_law_lab
        
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        
        mock_load.return_value = []
        
        result = scrape_refugee_law_lab(upload_to_s3=False)
        
        assert isinstance(result, list)
        assert len(result) == 0

    @patch('scraping.refugee_law_lab_scraper.requests.get')
    @patch('scraping.refugee_law_lab_scraper.time.sleep')
    def test_load_hf_dataset_max_retries_exhausted(self, mock_sleep, mock_get):
        """Test that max retries are exhausted and exception is raised."""
        from scraping.refugee_law_lab_scraper import load_hf_dataset_as_dict
        from requests.exceptions import HTTPError
        
        # All retries fail with 429
        error_response = Mock()
        error_response.status_code = 429
        
        error = HTTPError()
        error.response = error_response
        
        mock_get.side_effect = error
        
        # Should raise after max_retries (5) attempts
        with self.assertRaises(HTTPError):
            load_hf_dataset_as_dict("test/repo", "subset", "train")
        
        # Should have called sleep for exponential backoff (4 times, not on last attempt)
        assert mock_sleep.call_count == 4

    @patch('scraping.refugee_law_lab_scraper.requests.get')
    def test_load_hf_dataset_non_429_error(self, mock_get):
        """Test that non-429 HTTP errors are immediately raised."""
        from scraping.refugee_law_lab_scraper import load_hf_dataset_as_dict
        from requests.exceptions import HTTPError
        
        # Non-429 error (e.g., 500)
        error_response = Mock()
        error_response.status_code = 500
        
        error = HTTPError()
        error.response = error_response
        
        mock_get.side_effect = error
        
        # Should raise immediately without retry
        import pytest
        with pytest.raises(HTTPError):
            load_hf_dataset_as_dict("test/repo", "subset", "train")
        
        # Should only try once
        assert mock_get.call_count == 1

    @patch('scraping.refugee_law_lab_scraper.requests.get')
    def test_load_hf_dataset_safety_limit(self, mock_get):
        """Test safety limit at 10,000 rows prevents infinite loops."""
        from scraping.refugee_law_lab_scraper import load_hf_dataset_as_dict
        
        # Mock that always returns 100 rows (full page)
        def get_side_effect(*args, **kwargs):
            mock_response = Mock()
            # Always return 100 rows to simulate infinite dataset
            offset = kwargs.get('params', {}).get('offset', 0)
            mock_response.json.return_value = {
                "rows": [{"row": {"id": f"case{i}"}} for i in range(offset, offset + 100)]
            }
            mock_response.raise_for_status = Mock()
            return mock_response
        
        mock_get.side_effect = get_side_effect
        
        result = load_hf_dataset_as_dict("test/repo", "subset", "train")
        
        # Should stop after offset > 10000 (breaks after offset=10000 fetch)
        # Last page fetched is at offset=10000, giving 10100 total rows
        assert len(result) == 10100
        # Should have made 101 requests (offsets 0, 100, 200, ..., 10000)
        assert mock_get.call_count == 101


if __name__ == "__main__":
    unittest.main()
