# Test Coverage Implementation

This document describes the test coverage implementation for the Immigreat project.

## Overview

We use `pytest` with `pytest-cov` for comprehensive code coverage testing. The test suite includes:

- **Unit tests**: Testing individual functions and classes in isolation
- **Integration tests**: Testing interactions between components
- **Mocking**: Using `moto`, `pytest-mock`, and `unittest.mock` for AWS services and external dependencies

## Running Tests

### Quick Start

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run all tests with coverage
pytest

# Run with detailed coverage report
pytest --cov=src --cov-report=html --cov-report=term-missing

# Run specific test categories
pytest -m unit          # Only unit tests
pytest -m integration   # Only integration tests
pytest -m "not slow"    # Skip slow tests
```

### Coverage Reports

After running tests, coverage reports are generated in multiple formats:

1. **Terminal output**: Shows coverage summary and missing lines
2. **HTML report**: Open `htmlcov/index.html` in your browser for detailed interactive report
3. **XML report**: `coverage.xml` for CI/CD integration
4. **JSON report**: `coverage.json` for programmatic access

## Test Structure

```
tests/
├── conftest.py                 # Shared fixtures and configuration
├── unit/                       # Unit tests
│   ├── test_data_ingestion.py
│   ├── test_rag_pipeline.py
│   ├── test_forms_scraper.py
│   ├── test_ircc_scraper.py
│   ├── test_scraping_utils.py
│   └── test_db_admin_lambda.py
└── integration/                # Integration tests
    └── test_rag_integration.py
```

## Coverage Configuration

### pytest.ini

Configures pytest behavior:

- Test discovery patterns
- Coverage options
- Test markers

### .coveragerc

Configures coverage.py:

- Source code paths
- Files to omit
- Report formatting
- Exclusion patterns (e.g., `pragma: no cover`)

## CI/CD Integration

### GitHub Actions Workflows

1. **test-coverage.yml**: Main test workflow

   - Runs on push and PR
   - Tests across Python 3.11, 3.12, 3.13
   - Uploads coverage to Codecov
   - Comments coverage on PRs
   - Archives HTML reports

2. **coverage-badge.yml**: Badge generation
   - Updates coverage badge on main branch
   - Commits badge SVG to repository

## Test Fixtures

Common fixtures available in all tests (from `conftest.py`):

- `mock_env_vars`: Mock environment variables
- `mock_db_connection`: Mock PostgreSQL connection
- `mock_secrets_manager`: Mock AWS Secrets Manager
- `mock_s3`: Mock S3 client
- `mock_bedrock_runtime`: Mock AWS Bedrock client
- `sample_document`: Sample document data
- `sample_documents`: Multiple sample documents
- `sample_s3_event`: S3 trigger event
- `sample_query_event`: RAG query event

## Writing Tests

### Unit Test Example

```python
import pytest
from unittest.mock import patch

@pytest.mark.unit
class TestMyModule:
    def test_my_function(self, mock_env_vars):
        """Test description."""
        # Arrange
        input_data = "test"

        # Act
        result = my_function(input_data)

        # Assert
        assert result == expected_output
```

### Integration Test Example

```python
@pytest.mark.integration
@pytest.mark.slow
class TestIntegration:
    @patch('module.external_service')
    def test_complete_flow(self, mock_service, mock_env_vars):
        """Test end-to-end flow."""
        # Setup all mocks
        # Execute flow
        # Verify results
```

## Coverage Goals

- **Overall target**: >90% code coverage
- **Minimum per module**: >80% code coverage
- **Critical paths**: 100% coverage for error handling and data validation

## Coverage Badges

Coverage badges are displayed in the README:

- GitHub Actions workflow badge
- Codecov badge
- Local coverage percentage badge

All badges update automatically on push to main branch.

## Troubleshooting

### Common Issues

1. **Import errors**: Ensure `PYTHONPATH` includes `src/` directory
2. **Missing dependencies**: Run `pip install -r requirements-dev.txt`
3. **AWS mock failures**: Check `moto` version compatibility
4. **Slow tests**: Use `-m "not slow"` to skip slow integration tests

### Debugging Tests

```bash
# Run with verbose output
pytest -v

# Run specific test
pytest tests/unit/test_data_ingestion.py::TestCleanText::test_clean_whitespace

# Run with print statements visible
pytest -s

# Drop into debugger on failure
pytest --pdb
```

## Continuous Improvement

To improve coverage:

1. Review HTML coverage report to identify untested code
2. Add tests for uncovered lines
3. Add edge cases and error conditions
4. Ensure all Lambda handlers have integration tests
5. Test error handling paths

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [coverage.py documentation](https://coverage.readthedocs.io/)
- [moto documentation](http://docs.getmoto.org/)
