#!/usr/bin/env python3
"""
Test runner script with coverage reporting.

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py --unit             # Run only unit tests
    python run_tests.py --integration      # Run only integration tests
    python run_tests.py --fast             # Skip slow tests
    python run_tests.py --html             # Generate HTML report and open
    python run_tests.py --module MODULE    # Test specific module
"""

import sys
import subprocess
import argparse
import webbrowser
from pathlib import Path


def run_tests(args):
    """Run pytest with specified options."""
    cmd = ['pytest']
    
    # Add coverage options
    cmd.extend([
        '--cov=src',
        '--cov-report=term-missing',
        '--cov-report=html',
        '--cov-report=xml',
        '--cov-report=json'
    ])
    
    # Add verbosity
    if args.verbose:
        cmd.append('-v')
    else:
        cmd.append('-q')
    
    # Filter by test type
    if args.unit:
        cmd.extend(['-m', 'unit'])
    elif args.integration:
        cmd.extend(['-m', 'integration'])
    
    # Skip slow tests
    if args.fast:
        cmd.extend(['-m', 'not slow'])
    
    # Run specific module
    if args.module:
        cmd.append(f'tests/unit/test_{args.module}.py')
    
    # Show print statements
    if args.capture_no:
        cmd.append('-s')
    
    # Fail fast
    if args.fail_fast:
        cmd.append('-x')
    
    # Run tests
    print(f"Running: {' '.join(cmd)}")
    print("-" * 80)
    
    result = subprocess.run(cmd)
    
    # Open HTML report if requested
    if args.html and result.returncode == 0:
        html_report = Path('htmlcov/index.html')
        if html_report.exists():
            print(f"\nOpening coverage report: {html_report}")
            webbrowser.open(html_report.as_uri())
    
    return result.returncode


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Run tests with coverage reporting',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tests.py                    # Run all tests
  python run_tests.py --unit --fast      # Run fast unit tests only
  python run_tests.py --html             # Run tests and open HTML report
  python run_tests.py --module rag_pipeline  # Test specific module
        """
    )
    
    # Test selection
    test_group = parser.add_mutually_exclusive_group()
    test_group.add_argument('--unit', action='store_true',
                           help='Run only unit tests')
    test_group.add_argument('--integration', action='store_true',
                           help='Run only integration tests')
    
    # Test options
    parser.add_argument('--fast', action='store_true',
                       help='Skip slow tests')
    parser.add_argument('--module', type=str,
                       help='Test specific module (e.g., rag_pipeline)')
    
    # Output options
    parser.add_argument('--html', action='store_true',
                       help='Open HTML coverage report after tests')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('-s', '--capture-no', action='store_true',
                       help='Show print statements')
    parser.add_argument('-x', '--fail-fast', action='store_true',
                       help='Stop on first failure')
    
    args = parser.parse_args()
    
    # Check if pytest is available
    try:
        subprocess.run(['pytest', '--version'], 
                      capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: pytest not found. Install it with:")
        print("  pip install -r requirements-dev.txt")
        return 1
    
    # Run tests
    return run_tests(args)


if __name__ == '__main__':
    sys.exit(main())
