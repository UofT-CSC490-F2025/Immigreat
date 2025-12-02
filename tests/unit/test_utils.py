"""Unit tests for scraping utilities."""
import pytest
import sys
import os
sys.path.insert(0, 'src')
sys.path.insert(0, 'src/scraping')


@pytest.mark.unit
class TestResolveOutputPath:
    """Tests for resolve_output_path function."""

    def test_resolve_output_path_relative(self):
        """Test resolve_output_path with relative path."""
        from scraping.utils import resolve_output_path
        
        result = resolve_output_path("output.json")
        
        # Should convert to /tmp/output.json (on Windows: /tmp\output.json)
        assert result == os.path.join("/tmp", "output.json")

    def test_resolve_output_path_absolute(self):
        """Test resolve_output_path with absolute path."""
        from scraping.utils import resolve_output_path
        
        result = resolve_output_path("/data/output.json")
        
        # Should keep absolute path
        assert result == "/data/output.json"
