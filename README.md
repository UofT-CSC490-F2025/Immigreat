### Welcome to Immigreat!

[![Test Coverage](https://github.com/UofT-CSC490-F2025/Immigreat/actions/workflows/test-coverage.yml/badge.svg)](https://github.com/UofT-CSC490-F2025/Immigreat/actions/workflows/test-coverage.yml)
[![codecov](https://codecov.io/gh/UofT-CSC490-F2025/Immigreat/branch/main/graph/badge.svg)](https://codecov.io/gh/UofT-CSC490-F2025/Immigreat)
![Coverage](./coverage.svg)

This application is designed to be your new best immigration\* friend!

Simply upload any existing paperwork you have a get started.

\*Current development only covers immigration assistance for Canada.

## Developing

Currently working using python 3.13

## Testing

This project uses pytest with comprehensive test coverage. To run tests locally:

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests with coverage
pytest --cov=src --cov-report=html --cov-report=term

# View detailed HTML coverage report
# Open htmlcov/index.html in your browser
```

### Test Structure

- `tests/unit/` - Unit tests for individual modules
- `tests/integration/` - Integration tests for component interactions
- `tests/conftest.py` - Shared test fixtures and configuration

### Coverage Goals

We aim for **>90% code coverage** across all modules. Current coverage is automatically reported on PRs and updated in this README.

### Quick Start

```bash
# Run all tests
python run_tests.py

# Run with HTML report (opens in browser)
python run_tests.py --html

# Run only fast unit tests
python run_tests.py --unit --fast

# Windows PowerShell
.\run_tests.ps1 -Html
```

### Documentation

- 📖 [TESTING.md](TESTING.md) - Comprehensive testing guide
- 🚀 [QUICKSTART_TESTING.md](QUICKSTART_TESTING.md) - Quick start guide
- 📊 [TEST_COVERAGE_SUMMARY.md](TEST_COVERAGE_SUMMARY.md) - Implementation summary
