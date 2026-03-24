#!/usr/bin/env python3
import os
import sys
import argparse

try:
    from .http_interceptor import get_interceptor, HttpCapture
except ImportError:
    from http_interceptor import get_interceptor, HttpCapture

# Define paths
TEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testcases")
HTTP_LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "http_logs")


def run_single_test(test_file, http_logs_dir=None):
    """Run a single test file with HTTP traffic capture"""
    test_name = os.path.basename(test_file).replace('.py', '')
    print(f"Running test: {test_name}")
    
    # Get interceptor instance
    interceptor = get_interceptor(http_logs_dir)
    interceptor.set_test_name(test_name)
    interceptor.install()
    
    try:
        # Run the test file
        with open(test_file, 'r') as f:
            exec(f.read())
    except Exception as e:
        print(f"Error running test {test_name}: {e}")
        raise
    finally:
        # Save logs and clean up
        interceptor.save_logs()
        interceptor.uninstall()


def run_all_tests(test_dir=TEST_DIR, http_logs_dir=None):
    """Run all test files in the directory with HTTP traffic capture"""
    # Create HTTP logs directory if it doesn't exist
    if http_logs_dir and not os.path.exists(http_logs_dir):
        os.makedirs(http_logs_dir)
    
    # List all test files in the test directory
    test_files = []
    for file in os.listdir(test_dir):
        if file.startswith('test_') and file.endswith('.py'):
            test_files.append(os.path.join(test_dir, file))
    
    if not test_files:
        print(f"No test files found in {test_dir}")
        return
    
    print(f"Found {len(test_files)} test files: {[os.path.basename(f) for f in test_files]}")
    
    # Run each test file
    for test_file in test_files:
        run_single_test(test_file, http_logs_dir)


def main():
    """Parse arguments and run tests"""
    parser = argparse.ArgumentParser(description='Run tests with HTTP traffic capture')
    parser.add_argument('--file', help='Run a specific test file')
    parser.add_argument('--test-dir', default=TEST_DIR, help='Directory containing test files')
    parser.add_argument('--http-logs-dir', default=HTTP_LOGS_DIR, help='Directory for HTTP logs')
    args = parser.parse_args()
    
    if args.file:
        # Run specific test file
        run_single_test(args.file, args.http_logs_dir)
    else:
        # Run all tests
        run_all_tests(args.test_dir, args.http_logs_dir)


if __name__ == "__main__":
    main()
