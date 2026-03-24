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

# Import interceptor module
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
    Collect all test functions in the specified directory
    
    Args:
        base_dir: The base directory to search
        
    Returns:
        A dictionary where keys are file paths and values are lists of test functions in that file
    """
    test_functions = {}
    import_errors = []
    
    for root, dirs, files in os.walk(base_dir):
        # Skip __pycache__ and other non-test directories
        if "__pycache__" in root:
            continue
            
        for file in files:
            # Only process test_*.py files
            if file.startswith("test_") and file.endswith(".py"):
                file_path = os.path.join(root, file)
                
                try:
                    # Parse the file directly without importing to avoid dependency issues
                    functions = []
                    with open(file_path, 'r', encoding='utf-8') as f:
                        try:
                            # Try to parse file content to identify test functions
                            file_content = f.read()
                            # Use regular expressions to find test function and class method definitions
                            import re
                            # Find standalone test functions
                            test_funcs = re.findall(r'def\s+(test_[\w_]+)\s*\(', file_content)
                            
                            # Find test classes
                            test_classes = re.findall(r'class\s+([\w_]+)\s*:', file_content)
                            
                            # Find test methods in classes
                            class_methods = {}
                            for class_name in test_classes:
                                methods = re.findall(r'def\s+(test_[\w_]+)\s*\(self', file_content)
                                if methods:
                                    class_methods[class_name] = methods
                            
                            if test_funcs:
                                # Create a simple wrapper to store test function information
                                for func_name in test_funcs:
                                    # Create a pytest-compatible wrapper function
                                    def create_test_wrapper(name=func_name, path=file_path):
                                        def wrapper():
                                            print(f"Executing test: {name} (from {path})")
                                            # Actual execution will be handled by pytest
                                            pass
                                        wrapper.__name__ = name
                                        return wrapper
                                    
                                    functions.append(create_test_wrapper())
                                    
                            # Add test methods from classes
                            for class_name, methods in class_methods.items():
                                for method_name in methods:
                                    full_name = f"{class_name}.{method_name}"
                                    
                                    def create_class_test_wrapper(name=method_name, class_name=class_name, path=file_path):
                                        def wrapper():
                                            print(f"Executing test: {class_name}.{name} (from {path})")
                                            # Actual execution will be handled by pytest
                                            pass
                                        wrapper.__name__ = f"{class_name}.{name}"
                                        return wrapper
                                    
                                    functions.append(create_class_test_wrapper())
                                
                                test_functions[file_path] = functions
                        except Exception as inner_e:
                            import_errors.append(f"Failed to open file {file_path}: {inner_e}")
                except Exception as e:
                    import_errors.append(f"Failed to parse {file_path}: {e}")
    
    # Only print the first 5 import errors to avoid excessive scrolling
    if import_errors:
        print(f"\nEncountered {len(import_errors)} import errors. Showing the first 5:")
        for i, err in enumerate(import_errors[:5]):
            print(f"{i+1}. {err}")
    
    return test_functions

def save_test_results(test_results: List[dict], output_path: Optional[str] = None) -> str:
    """
    Save test results to a file
    
    Args:
        test_results: A list of test results
        output_path: The output path. If None, a default path is used.
        
    Returns:
        The path to the saved file
    """
    if not test_results:
        print("No test results to save")
        return ""
        
    if not output_path:
        timestamp = int(time.time())
        output_dir = os.path.join(os.getcwd(), "test_results")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"test_results_{timestamp}.json")
    
    # Summary statistics
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
    print(f"Total tests: {total_tests}, Successful: {successful_tests}, Failed: {failed_tests}, Total duration: {total_duration:.2f}s")
    
    return output_path


def run_selected_test(test_func: Callable, file_path: str, capture_http: bool = True, output_dir: Optional[str] = None) -> Tuple[bool, dict]:
    """
    Run the selected test function
    
    Args:
        test_func: The test function to run
        file_path: The path to the test file
        capture_http: Whether to capture HTTP traffic
        output_dir: The output directory for HTTP traffic logs
        
    Returns:
        A tuple (success, test_info), where success indicates if the test was successful, and test_info contains test information
    """
    # Record test start time and basic information
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    test_info = {
        "test_name": test_func.__name__,
        "file_path": file_path,
        "timestamp": timestamp,
        "start_time": start_time,
    }
    test_name = test_func.__name__
    if '.' in test_name:
        test_info["command"] = f"python -m pytest {file_path}::{test_name} -xvs"
    else:
        test_info["command"] = f"python -m pytest {file_path}::{test_name} -xvs"
    test_info["success"] = False
    test_info["http_logs_path"] = None
    print(f"Running test: {test_func.__name__} (from {file_path})")
    
    # Set default output directory
    if output_dir is None:
        output_dir = os.path.join(os.getcwd(), "http_logs")
        os.makedirs(output_dir, exist_ok=True)
    
    # Generate test ID
    test_id = f"{os.path.basename(file_path).replace('.py', '')}_{test_func.__name__}"
    
    # Initialize HTTP interceptor
    http_capture = None
    
    # Check HTTP interceptor availability
    if capture_http and HTTP_INTERCEPTOR_AVAILABLE:
        http_capture = HttpCapture(test_name=test_id, output_dir=output_dir)
        print(f"HTTP capture enabled, logs will be saved to: {output_dir}")
    elif capture_http:
        print("Warning: HTTP capture is enabled, but the interceptor module was not found. Please ensure http_interceptor.py is in the same directory as this script.")
    
    try:
        if "pytest" in sys.modules:
            # Prepare test command
            test_name = test_func.__name__
            test_cmd = ['-xvs', file_path + '::' + test_name]
            test_info["pytest_cmd"] = ' '.join(test_cmd)
            
            # Choose different execution methods based on available interceptors
            if http_capture:  # Use HTTP interceptor
                print(f"Executing: pytest {' '.join(test_cmd)} (with HTTP interception)")
                with http_capture as _:
                    result = pytest.main(test_cmd)
                    test_info["success"] = result == 0
                    if hasattr(http_capture, "interceptor") and hasattr(http_capture.interceptor, "requests"):
                        test_info["http_requests_count"] = len(http_capture.interceptor.requests)
            else:  # Run directly when no interceptor is available
                print(f"Executing: pytest {' '.join(test_cmd)}")
                result = pytest.main(test_cmd)
                test_info["success"] = result == 0
            
            # If the above method fails, try calling the command line directly
            if '--' in file_path:
                print("Trying to run external shell command...")
                cmd = [sys.executable, '-m', 'pytest', '-xvs', file_path + '::' + test_name]
                import subprocess
                result = subprocess.run(cmd, capture_output=True, text=True)
                test_info["shell_cmd_result"] = (result.returncode == 0)
                print(result.stdout)
                if result.stderr:
                    print("\nError output:")
                    print(result.stderr)
        else:
            # Notify user that pytest is required
            print("\npytest is required to run tests. Note: Running tests directly may require a test framework context and dependencies.")
            print(f"If you want to run this test manually, please execute: cd {os.getcwd()} && python -m pytest {file_path}::{test_name} -v")
            
            # If capture is enabled, provide a hint for manual integration
            if http_capture:
                print("\nNote: To manually integrate the capture feature into your test code, you can add the following code:")
                
                if HTTP_INTERCEPTOR_AVAILABLE:
                    print("""    from http_interceptor import HttpCapture
    with HttpCapture(test_name="tests") as _:
        # Your test code
        pass""")
    except Exception as e:
        print(f"Test execution failed: {e}")
        print("\nTrying a different execution method...")
        print(f"You can run it manually: cd {os.getcwd()} && python -m pytest {file_path}::{test_name} -v")
        test_info["error"] = str(e)
    
    test_info["end_time"] = time.time()
    test_info["duration"] = test_info["end_time"] - test_info["start_time"]
    
    return test_info["success"], test_info

def save_test_results(test_results: List[dict], output_path: Optional[str] = None) -> str:
    """
    Save test results to a file
    
    Args:
        test_results: A list of test results
        output_path: The output path. If None, a default path is used.
        
    Returns:
        The path to the saved file
    """
    if not output_path:
        timestamp = int(time.time())
        output_dir = os.path.join(os.getcwd(), "test_results")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"test_results_{timestamp}.json")
    
    # Summary statistics
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
    print(f"Total tests: {total_tests}, Successful: {successful_tests}, Failed: {failed_tests}, Total duration: {total_duration:.2f}s")
    
    return output_path


def run_all_tests(test_functions: Dict[str, List[Callable]], capture_http: bool = True, http_logs_dir: Optional[str] = None) -> List[dict]:
    """
    Run all collected tests
    
    Args:
        test_functions: A dictionary of test functions
        capture_http: Whether to capture HTTP traffic
        http_logs_dir: The output directory for HTTP logs
        
    Returns:
        A list of test results
    """
    test_results = []
    total_tests = sum(len(funcs) for funcs in test_functions.values())
    current_test = 0
    
    print(f"\nStarting to run all {total_tests} tests")
    
    for file_path, functions in test_functions.items():
        rel_path = os.path.relpath(file_path, os.getcwd())
        print(f"\nRunning {len(functions)} tests in file {rel_path}...")
        
        for func in functions:
            current_test += 1
            print(f"\n[{current_test}/{total_tests}] ", end="")
            success, test_info = run_selected_test(func, file_path, capture_http=capture_http, output_dir=http_logs_dir)
            test_results.append(test_info)
    
    return test_results


def interactive_menu(test_functions: Dict[str, List[Callable]], capture_http: bool = True, http_logs_dir: Optional[str] = None) -> List[dict]:
    """
    Display an interactive menu for the user to select which tests to run
    
    Args:
        test_functions: A dictionary of test functions
        capture_http: Whether to capture HTTP traffic
        http_logs_dir: The output directory for HTTP logs
        
    Returns:
        A list of test results
    """
    if not test_functions:
        print("No test functions found")
        return []
    
    # Display HTTP capture status
    if capture_http:
        if HTTP_INTERCEPTOR_AVAILABLE:
            print(f"HTTP capture is enabled. Logs will be saved to: {http_logs_dir or os.path.join(os.getcwd(), 'http_logs')}")
            print("(Use the --no-http-capture argument to disable this feature)")
        else:
            print("Warning: HTTP capture is enabled, but the http_interceptor module was not found.")
    
    # Create file list
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
                    # Pass the file path to the run_selected_test function
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
    
    # Create command line argument parser
    parser = argparse.ArgumentParser(description='Select and run Qdrant test functions')
    parser.add_argument('--dir', '-d', action='append', help='Specify the test directory path to search, can be specified multiple times')
    parser.add_argument('--file', '-f', help='Directly specify the test file path to run')
    parser.add_argument('--test', '-t', help='Specify the name of the test function to run, requires --file')
    parser.add_argument('--no-http-capture', action='store_true', help='Disable HTTP traffic capture')
    parser.add_argument('--http-logs', help='Specify the output directory for HTTP logs')
    parser.add_argument('--interactive', '-i', action='store_true', help='Interactive mode, allows selecting tests to run')
    parser.add_argument('--results-file', '-o', help='Specify the output file path for test results')
    args = parser.parse_args()
    
    # If a test file and test function are directly specified, run it directly
    if args.file:
        file_path = args.file
        if not os.path.isabs(file_path):
            file_path = os.path.join(os.getcwd(), file_path)
        
        if not os.path.exists(file_path):
            print(f"Error: Test file {file_path} does not exist")
            return
        
        if args.test:
            # Create a wrapper for the test function
            def wrapper():
                pass
            wrapper.__name__ = args.test
            
            # Run the specified test directly
            capture_http = not args.no_http_capture
            _, test_info = run_selected_test(wrapper, file_path, capture_http=capture_http, output_dir=args.http_logs)
            save_test_results([test_info], args.results_file)
            return
        else:
            # If only a file is provided but no test function name, collect all tests in that file
            print(f"Collecting tests in {file_path}...")
            tests = collect_test_functions(os.path.dirname(file_path))
            if file_path in tests:
                print(f"Found {len(tests[file_path])} test functions in {file_path}")
                # Create a dictionary containing only this file
                file_tests = {file_path: tests[file_path]}
                capture_http = not args.no_http_capture
                
                if args.interactive:
                    # Interactive mode
                    test_results = interactive_menu(file_tests, capture_http=capture_http, http_logs_dir=args.http_logs)
                else:
                    # Run all tests automatically
                    test_results = run_all_tests(file_tests, capture_http=capture_http, http_logs_dir=args.http_logs)
                
                if test_results:
                    save_test_results(test_results, args.results_file)
                return
            else:
                print(f"No test functions found in {file_path}")
                return
    
    # If no directory is specified, use the default directory
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
            print(f"Collecting tests in {test_dir}...")
            tests = collect_test_functions(test_dir)
            all_tests.update(tests)
        else:
            print(f"Warning: Directory {test_dir} does not exist")
    
    if not all_tests:
        print("Error: No test files found. Please ensure the correct directory or project root is specified.")
        print(f"Checked directories: {test_dirs}")
        return
    
    print(f"Found a total of {len(all_tests)} test files, containing {sum(len(funcs) for funcs in all_tests.values())} test functions")
    capture_http = not args.no_http_capture
    
    if args.interactive:
        # Interactive mode
        test_results = interactive_menu(all_tests, capture_http=capture_http, http_logs_dir=args.http_logs)
    else:
        # Run all tests automatically
        test_results = run_all_tests(all_tests, capture_http=capture_http, http_logs_dir=args.http_logs)
    
    if test_results:
        save_test_results(test_results, args.results_file)

if __name__ == "__main__":
    main()
