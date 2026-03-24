#!/usr/bin/env python3
import os
import sys
import importlib
import inspect
import pytest
import json
import time
from datetime import datetime
from typing import Dict, List, Callable, Any, Optional, Tuple

# Import interceptor module if available
try:
    from .http_interceptor import HttpCapture
    HTTP_INTERCEPTOR_AVAILABLE = True
except ImportError:
    try:
        from http_interceptor import HttpCapture
        HTTP_INTERCEPTOR_AVAILABLE = True
    except ImportError:
        HTTP_INTERCEPTOR_AVAILABLE = False

def collect_test_functions(base_dir: str) -> Dict[str, List[Callable]]:
    """
    Collect all test functions under the given directory
    
    Args:
        base_dir: base directory to search
        
    Returns:
        dict mapping file path to list of discovered test functions
    """
    test_functions = {}
    import_errors = []
    
    for root, dirs, files in os.walk(base_dir):
        # Skip __pycache__ and other non-test directories
        if "__pycache__" in root:
            continue
            
        for file in files:
            # Only handle test_*.py files
            if file.startswith("test_") and file.endswith(".py"):
                file_path = os.path.join(root, file)
                
                try:
                    # Parse the file without importing to avoid dependency issues
                    functions = []
                    with open(file_path, 'r', encoding='utf-8') as f:
                        try:
                            # Identify test function definitions via regex
                            file_content = f.read()
                            import re
                            test_funcs = re.findall(r'def\s+(test_[\w_]+)\s*\(', file_content)
                            
                            if test_funcs:
                                # Create lightweight wrappers to store test info
                                for func_name in test_funcs:
                                    # Build pytest-compatible wrapper function
                                    def create_test_wrapper(name=func_name, path=file_path):
                                        def wrapper():
                                            print(f"Running test: {name} (from {path})")
                                            # Actual execution is handled by pytest
                                            pass
                                        wrapper.__name__ = name
                                        return wrapper
                                    
                                    functions.append(create_test_wrapper())
                                
                                test_functions[file_path] = functions
                        except Exception as inner_e:
                            import_errors.append(f"Failed to open {file_path}: {inner_e}")
                except Exception as e:
                    import_errors.append(f"Failed to parse {file_path}: {e}")
    
    # Print first 5 import errors only to avoid excessive output
    if import_errors:
        print(f"\nEncountered {len(import_errors)} import errors. Showing the first 5:")
        for i, err in enumerate(import_errors[:5]):
            print(f"{i+1}. {err}")
    
    return test_functions

def save_test_results(test_results: List[dict], output_path: Optional[str] = None) -> str:
    """
    Save test results to a file
    
    Args:
        test_results: list of test result dicts
        output_path: output path; use default if None
        
    Returns:
        path to the saved file
    """
    if not test_results:
        print("No test results to save")
        return ""
        
    if not output_path:
        timestamp = int(time.time())
        output_dir = os.path.join(os.getcwd(), "test_results")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"test_results_{timestamp}.json")
    
    # Aggregate statistics
    total_tests = len(test_results)
    successful_tests = sum(1 for r in test_results if r.get("success", False))
    failed_tests = total_tests - successful_tests
    total_duration = sum(r.get("duration", 0) for r in test_results)
    
    summary = {
        "total_tests": total_tests,
        "successful_tests": successful_tests,
        "failed_tests": failed_tests,
        "total_duration": total_duration,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tests": test_results
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\nTest results saved to: {output_path}")
    print(f"Total: {total_tests}, Success: {successful_tests}, Failed: {failed_tests}, Duration: {total_duration:.2f}s")
    
    return output_path


def run_selected_test(test_func: Callable, file_path: str, capture_http: bool = True, output_dir: Optional[str] = None) -> Tuple[bool, dict]:
    """
    Run the selected test function
    
    Args:
        test_func: test function to run
        file_path: test file path
        capture_http: whether to capture HTTP traffic
        output_dir: directory for HTTP traffic logs
        
    Returns:
        tuple (success, test_info), success indicates whether the test passed, test_info contains metadata
    """
    # Record start time and basic info
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    test_info = {
        "test_name": test_func.__name__,
        "file_path": file_path,
        "timestamp": timestamp,
        "start_time": start_time,
        "command": f"python -m pytest {file_path}::{test_func.__name__} -xvs",
        "success": False,
        "http_logs_path": None
    }
    print(f"Running test: {test_func.__name__} (from {file_path})")
    
    # Configure default output directory
    if output_dir is None:
        output_dir = os.path.join(os.getcwd(), "http_logs")
        os.makedirs(output_dir, exist_ok=True)
    
    # Build test ID
    test_id = f"{os.path.basename(file_path).replace('.py', '')}_{test_func.__name__}"
    
    # Initialize HTTP capture
    http_capture = None
    
    # Check HTTP interceptor availability
    if capture_http and HTTP_INTERCEPTOR_AVAILABLE:
        http_capture = HttpCapture(test_name=test_id, output_dir=output_dir)
        print(f"HTTP capture enabled; logs will be saved to: {output_dir}")
    elif capture_http:
        print("Warning: HTTP capture enabled but interceptor module not found. Ensure http_interceptor.py is alongside this script.")
    
    try:
        if "pytest" in sys.modules:
            # Prepare test command
            test_cmd = ['-xvs', file_path + '::' + test_func.__name__]
            test_info["pytest_cmd"] = ' '.join(test_cmd)
            
            # Choose execution path based on interceptor availability
            if http_capture:  # With HTTP interceptor
                print(f"Executing: pytest {' '.join(test_cmd)} (HTTP capture enabled)")
                with http_capture as _:
                    result = pytest.main(test_cmd)
                    test_info["success"] = result == 0
                    if hasattr(http_capture, "interceptor") and hasattr(http_capture.interceptor, "requests"):
                        test_info["http_requests_count"] = len(http_capture.interceptor.requests)
            else:  # Run directly without interceptor
                print(f"Executing: pytest {' '.join(test_cmd)}")
                result = pytest.main(test_cmd)
                test_info["success"] = result == 0
            
            # If the above fails, try shell invocation
            if '--' in file_path:
                print("Trying shell execution ...")
                cmd = [sys.executable, '-m', 'pytest', '-xvs', file_path + '::' + test_func.__name__]
                import subprocess
                result = subprocess.run(cmd, capture_output=True, text=True)
                test_info["shell_cmd_result"] = (result.returncode == 0)
                print(result.stdout)
                if result.stderr:
                    print("\nError output:")
                    print(result.stderr)
        else:
            # Notify user that pytest is required
            print("\npytest is required to run tests. Direct execution may need framework context and dependencies.")
            print(f"If you want to run manually: cd {os.getcwd()} && python -m pytest {file_path}::{test_func.__name__} -v")
            
            # Provide hints for manual capture integration when enabled
            if http_capture:
                print("\nNote: to manually integrate capture in your test code, add:")
                
                if HTTP_INTERCEPTOR_AVAILABLE:
                    print("""    from http_interceptor import HttpCapture
    with HttpCapture(test_name="test_name") as _:
        # your test code
        pass""")
    except Exception as e:
        print(f"Test execution failed: {e}")
        print("\nTrying alternative execution paths...")
        print(f"You can run manually: cd {os.getcwd()} && python -m pytest {file_path}::{test_func.__name__} -v")
        test_info["error"] = str(e)
    
    test_info["end_time"] = time.time()
    test_info["duration"] = test_info["end_time"] - test_info["start_time"]
    
    return test_info["success"], test_info

def save_test_results(test_results: List[dict], output_path: Optional[str] = None) -> str:
    """
    Save test results to a file
    
    Args:
        test_results: list of test result dicts
        output_path: output path; use default if None
        
    Returns:
        path to the saved file
    """
    if not output_path:
        timestamp = int(time.time())
        output_dir = os.path.join(os.getcwd(), "test_results")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"test_results_{timestamp}.json")
    
    # Aggregate statistics
    total_tests = len(test_results)
    successful_tests = sum(1 for r in test_results if r.get("success", False))
    failed_tests = total_tests - successful_tests
    total_duration = sum(r.get("duration", 0) for r in test_results)
    
    summary = {
        "total_tests": total_tests,
        "successful_tests": successful_tests,
        "failed_tests": failed_tests,
        "total_duration": total_duration,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tests": test_results
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\nTest results saved to: {output_path}")
    print(f"Total tests: {total_tests}, Success: {successful_tests}, Failed: {failed_tests}, Total duration: {total_duration:.2f}s")
    
    return output_path


def run_all_tests(test_functions: Dict[str, List[Callable]], capture_http: bool = True, http_logs_dir: Optional[str] = None) -> List[dict]:
    """
    Run all collected tests
    
    Args:
        test_functions: dict of test functions
        capture_http: whether to capture HTTP traffic
        http_logs_dir: HTTP log output directory
        
    Returns:
        list of test results
    """
    test_results = []
    total_tests = sum(len(funcs) for funcs in test_functions.values())
    current_test = 0
    
    print(f"\nStarting execution of {total_tests} tests")
    
    for file_path, functions in test_functions.items():
        rel_path = os.path.relpath(file_path, os.getcwd())
        print(f"\nRunning {len(functions)} tests in {rel_path} ...")
        
        for func in functions:
            current_test += 1
            print(f"\n[{current_test}/{total_tests}] ", end="")
            success, test_info = run_selected_test(func, file_path, capture_http=capture_http, output_dir=http_logs_dir)
            test_results.append(test_info)
    
    return test_results


def interactive_menu(test_functions: Dict[str, List[Callable]], capture_http: bool = True, http_logs_dir: Optional[str] = None) -> List[dict]:
    """
    Display an interactive menu to choose tests to run
    
    Args:
        test_functions: dict of test functions
        capture_http: whether to capture HTTP traffic
        http_logs_dir: HTTP log output directory
        
    Returns:
        list of test results
    """
    if not test_functions:
        print("No test functions found")
        return []
    
    # Show HTTP capture status
    if capture_http:
        if HTTP_INTERCEPTOR_AVAILABLE:
            print(f"HTTP capture enabled, logs at: {http_logs_dir or os.path.join(os.getcwd(), 'http_logs')}")
            print("(Use --no-http-capture to disable)")
        else:
            print("Warning: HTTP capture is enabled, but http_interceptor module is missing.")
    
    # Build file list
    files = list(test_functions.keys())
    files.sort()
    
    while True:
        print("\nSelect a test file:")
        for i, file_path in enumerate(files):
            rel_path = os.path.relpath(file_path, os.getcwd())
            print(f"{i+1}. {rel_path} ({len(test_functions[file_path])} tests)")
        
        try:
            choice = input("\nEnter file number (q to quit): ")
            if choice.lower() == 'q':
                break
            
            file_idx = int(choice) - 1
            if 0 <= file_idx < len(files):
                file_path = files[file_idx]
                functions = test_functions[file_path]
                
                print(f"\nTest functions in {os.path.relpath(file_path, os.getcwd())}:")
                for j, func in enumerate(functions):
                    print(f"{j+1}. {func.__name__}")
                
                func_choice = input("\nEnter function number (b to go back): ")
                if func_choice.lower() == 'b':
                    continue
                
                func_idx = int(func_choice) - 1
                if 0 <= func_idx < len(functions):
                    # Pass file path into run_selected_test
                    _, test_info = run_selected_test(functions[func_idx], file_path, capture_http=capture_http, output_dir=http_logs_dir)
                    return [test_info]
                else:
                    print("Invalid function number")
            else:
                print("Invalid file number")
        except ValueError:
            print("Please enter a valid number")
        except KeyboardInterrupt:
            break

def main() -> None:
    import argparse
    
    # Build CLI parser
    parser = argparse.ArgumentParser(description='Select and run Qdrant test functions')
    parser.add_argument('--dir', '-d', action='append', help='Test directory to search; can be specified multiple times')
    parser.add_argument('--file', '-f', help='Path to a specific test file to run')
    parser.add_argument('--test', '-t', help='Name of the test function to run (use with --file)')
    parser.add_argument('--no-http-capture', action='store_true', help='Disable HTTP traffic capture')
    parser.add_argument('--http-logs', help='Directory to store HTTP logs')
    parser.add_argument('--interactive', '-i', action='store_true', help='Interactive mode to choose tests')
    parser.add_argument('--results-file', '-o', help='Output file path for test results')
    args = parser.parse_args()
    
    # If a specific test file and function are given, run directly
    if args.file:
        file_path = args.file
        if not os.path.isabs(file_path):
            file_path = os.path.join(os.getcwd(), file_path)
        
        if not os.path.exists(file_path):
            print(f"Error: test file {file_path} does not exist")
            return
        
        if args.test:
            # Create a wrapper for the specified test function name
            def wrapper():
                pass
            wrapper.__name__ = args.test
            
            # Run the specified test directly
            capture_http = not args.no_http_capture
            _, test_info = run_selected_test(wrapper, file_path, capture_http=capture_http, output_dir=args.http_logs)
            save_test_results([test_info], args.results_file)
            return
        else:
            # If only file is provided, collect all tests in that file
            print(f"Collecting tests in {file_path} ...")
            tests = collect_test_functions(os.path.dirname(file_path))
            if file_path in tests:
                print(f"Found {len(tests[file_path])} test functions in {file_path}")
                # Build a dict containing only this file
                file_tests = {file_path: tests[file_path]}
                capture_http = not args.no_http_capture
                
                if args.interactive:
                    # Interactive mode
                    test_results = interactive_menu(file_tests, capture_http=capture_http, http_logs_dir=args.http_logs)
                else:
                    # Automatically run all tests
                    test_results = run_all_tests(file_tests, capture_http=capture_http, http_logs_dir=args.http_logs)
                
                if test_results:
                    save_test_results(test_results, args.results_file)
                return
            else:
                print(f"No test functions found in {file_path}")
                return
    
    # If no directory specified, use default directories
    if not args.dir:
        test_dirs = [
            os.path.join(os.getcwd(), "tests"),
            os.path.join(os.getcwd(), "qdrant_client", "local", "tests")
        ]
    else:
        test_dirs = []
        for path in args.dir:
            # Handle relative and absolute paths
            if os.path.isabs(path):
                test_dirs.append(path)
            else:
                test_dirs.append(os.path.join(os.getcwd(), path))
    
    all_tests = {}
    for test_dir in test_dirs:
        if os.path.exists(test_dir):
            print(f"Collecting tests in {test_dir} ...")
            tests = collect_test_functions(test_dir)
            all_tests.update(tests)
        else:
            print(f"Warning: directory {test_dir} does not exist")
    
    if not all_tests:
        print("Error: no test files found. Ensure correct directories or project root.")
        print(f"Checked directories: {test_dirs}")
        return
    
    print(f"Found {len(all_tests)} test files with {sum(len(funcs) for funcs in all_tests.values())} test functions")
    capture_http = not args.no_http_capture
    
    if args.interactive:
        # Interactive mode
        test_results = interactive_menu(all_tests, capture_http=capture_http, http_logs_dir=args.http_logs)
    else:
        # Automatically run all tests
        test_results = run_all_tests(all_tests, capture_http=capture_http, http_logs_dir=args.http_logs)
    
    if test_results:
        save_test_results(test_results, args.results_file)

if __name__ == "__main__":
    main()
