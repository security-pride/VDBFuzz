#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Vector Database (VDB) fuzzing tool - test runner.

This module automates execution of test templates.
Workflow:
1. Scan all test template files in the target directory.
2. Execute tests according to the chosen strategy (parallel or serial).
3. Collect results and generate a report.
"""

import os
import sys
import json
import time
import logging
import argparse
import importlib.util
import concurrent.futures
import traceback
import signal
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional, Set, Union

# Configure logging without basicConfig to avoid duplicate setup
# Directly obtain logger instance; relies on root logger configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('vdbfuzz.runner')

# Track executed tests to avoid duplication
executed_tests = set()

# Capture SIGINT for graceful shutdown
def signal_handler(sig, frame):
    logger.warning("Interrupt received; stopping test execution...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


HARNESS_FAILURE_MARKERS = (
    "error: unrecognized arguments:",
    "Unable to connect to the target server; aborting test execution",
)


class TestRunner:
    """
    Test runner that executes test templates and records results
    """
    
    # Supported VDB types
    SUPPORTED_VDB_TYPES = ['qdrant', 'weaviate', 'milvus']
    
    def __init__(
        self, 
        templates_dir: str, 
        target_url: str, 
        output_dir: str = None,
        parallel: bool = False,
        max_workers: int = 4,
        time_limit: int = 0,
        fuzzing_iterations: int = 0,
        vdb_type: str = None
    ):
        """
        Initialize the test runner
        
        Args:
            templates_dir: directory containing test templates
            target_url: target VDB server URL
            output_dir: output directory for results (default: templates_dir/results)
            parallel: whether to run tests in parallel
            max_workers: max worker threads for parallel mode
            time_limit: time limit in minutes (0 for unlimited)
            fuzzing_iterations: mutation iterations per test (0 for template default)
            vdb_type: target VDB type for filtering and directed mutation
        """
        self.templates_dir = Path(templates_dir)
        self.target_url = target_url
        self.vdb_type = vdb_type.lower() if vdb_type else None
        
        # Validate VDB type
        if self.vdb_type and self.vdb_type not in self.SUPPORTED_VDB_TYPES:
            logger.warning(f"Unsupported VDB type: {vdb_type}, loading all templates")
            self.vdb_type = None
        
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = self.templates_dir / "results"
        
        self.parallel = parallel
        self.max_workers = max_workers
        self.time_limit = time_limit
        self.fuzzing_iterations = fuzzing_iterations
        self.start_time = time.time()
        
        # Ensure output directory exists
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        # Create log directory
        self.logs_dir = self.output_dir / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        # History file path
        self.history_file = self.output_dir / "executed_tests_history.json"
        
        # Load executed test list
        global executed_tests
        executed_tests = self.load_executed_tests()
        logger.info(f"Loaded {len(executed_tests)} executed test templates from history")
        
        # Configure file logger
        self.setup_file_logger()

    def setup_file_logger(self):
        """Set up file logger"""
        log_file = self.logs_dir / f"test_run_{time.strftime('%Y%m%d_%H%M%S')}.log"
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)
        
        logger.info(f"Logs will be saved to: {log_file}")
        
    def load_executed_tests(self) -> Set[str]:
        """
        Load executed test paths from history file
        
        Returns:
            set: set of executed test paths
        """
        if not self.history_file.exists():
            logger.info(f"History file not found: {self.history_file}")
            return set()
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                executed = set(json.load(f))
                logger.info(f"Loaded {len(executed)} executed test templates from history file")
                return executed
        except Exception as e:
            logger.error(f"Failed to read history file: {str(e)}")
            return set()
    
    def save_executed_tests(self):
        """Persist executed test list to history file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(list(executed_tests), f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(executed_tests)} executed test templates to history")
        except Exception as e:
            logger.error(f"Failed to save history file: {str(e)}")

    def find_template_files(self) -> List[Path]:
        """
        Find all test template files, optionally filtered by VDB type
        
        Returns:
            list: list of template file paths
        """
        template_files = []
        
        # If VDB type specified, prefer scanning the subdirectory
        if self.vdb_type:
            vdb_subdir = self.templates_dir / self.vdb_type
            if vdb_subdir.exists() and vdb_subdir.is_dir():
                logger.info(f"Using VDB-type subdirectory: {vdb_subdir}")
                for file_path in vdb_subdir.glob("**/*.py"):
                    if file_path.is_file() and "_test.py" in file_path.name:
                        template_files.append(file_path)
            else:
                # Subdirectory absent, fall back to content-based filtering
                logger.info(f"VDB subdirectory {vdb_subdir} not found; falling back to content filter")
                template_files = self._filter_templates_by_content()
        else:
            # No VDB type specified; load all templates
            for file_path in self.templates_dir.glob("**/*.py"):
                if file_path.is_file() and "_test.py" in file_path.name:
                    template_files.append(file_path)
        
        logger.info(f"Found {len(template_files)} test templates in {self.templates_dir}"
                   + (f" (type: {self.vdb_type})" if self.vdb_type else ""))
        return sorted(template_files)
    
    def _filter_templates_by_content(self) -> List[Path]:
        """
        Filter templates by parsing VDB_TYPE in file content
        
        Returns:
            list: matching template file paths
        """
        import re
        template_files = []
        vdb_type_pattern = re.compile(r'^VDB_TYPE\s*=\s*["\']([\w]+)["\']', re.MULTILINE)
        
        for file_path in self.templates_dir.glob("**/*.py"):
            if file_path.is_file() and "_test.py" in file_path.name:
                try:
                    # Read the beginning only (globals usually in first 200 lines)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = ''.join(f.readlines()[:200])
                    
                    match = vdb_type_pattern.search(content)
                    if match:
                        file_vdb_type = match.group(1).lower()
                        if file_vdb_type == self.vdb_type:
                            template_files.append(file_path)
                    else:
                        # Unknown type; include by default
                        logger.debug(f"Could not determine VDB type for {file_path.name}; including by default")
                        template_files.append(file_path)
                except Exception as e:
                    logger.warning(f"Failed to read template {file_path}: {str(e)}")
        
        return template_files

    def execute_template(self, template_path: Path) -> Dict[str, Any]:
        """
        Execute a single test template
        
        Args:
            template_path: template file path
            
        Returns:
            dict: test result
        """
        if str(template_path) in executed_tests:
            logger.warning(f"Template {template_path.name} already executed, skipping")
            return {"status": "skipped", "file": str(template_path), "reason": "already_executed"}

        start_time = time.time()
        template_name = template_path.stem
        logger.info(f"Start executing test template: {template_name}")
        
        # Prepare command arguments
        cmd = [
            sys.executable, 
            str(template_path),
            "-t", self.target_url,
            "-o", str(self.output_dir)
        ]
        
        # Pass iteration parameter
        if self.fuzzing_iterations > -1:
            cmd.extend(["-n", str(self.fuzzing_iterations)])
            
        # Pass time limit
        if self.time_limit > -1:
            cmd.extend(["-l", str(self.time_limit)])
                    
        logger.info(f"Test config: target={self.target_url}, VDB type={self.vdb_type or 'auto'}, iterations={self.fuzzing_iterations if self.fuzzing_iterations > 0 else 'default'}, time limit={self.time_limit if self.time_limit > 0 else 'default'} minutes")

        logger.debug(f"Test command: {' '.join(cmd)}")
            
        test_log_file = self.logs_dir / f"{template_name}_{time.strftime('%Y%m%d_%H%M%S')}.log"
        
        try:
            # Run test process
            harness_failure = False
            with open(test_log_file, 'w', encoding='utf-8') as log_file:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    universal_newlines=True,
                    bufsize=1  # line buffering
                )
                
                # Stream output to log
                for line in process.stdout:
                    log_file.write(line)
                    logger.debug(line.strip())
                    if any(marker in line for marker in HARNESS_FAILURE_MARKERS):
                        harness_failure = True
                    
                process.wait()
            
            status = "success" if process.returncode == 0 and not harness_failure else "failure"
            if status == "success":
                executed_tests.add(str(template_path))
            
            elapsed_time = time.time() - start_time
            logger.info(f"Test {template_name} finished, status: {status}, elapsed: {elapsed_time:.2f}s")
            
            return {
                "status": status,
                "file": str(template_path),
                "execution_time": elapsed_time,
                "log_file": str(test_log_file),
                "return_code": process.returncode
            }
            
        except Exception as e:
            logger.error(f"Error executing test {template_name}: {str(e)}")
            traceback.print_exc()
            
            return {
                "status": "error",
                "file": str(template_path),
                "error": str(e),
                "log_file": str(test_log_file)
            }

    def run_sequential(self, templates: List[Path]) -> List[Dict[str, Any]]:
        """
        Execute tests sequentially
        
        Args:
            templates: list of test templates
            
        Returns:
            list: test results
        """
        results = []
        
        for template in templates:
            result = self.execute_template(template)
            results.append(result)
            
        return results

    def run_parallel(self, templates: List[Path]) -> List[Dict[str, Any]]:
        """
        Execute tests in parallel
        
        Args:
            templates: list of test templates
            
        Returns:
            list: test results
        """
        results = []
        completed = 0
        total = len(templates)
        
        logger.info(f"Starting parallel mode with max workers: {self.max_workers}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_template = {
                executor.submit(self.execute_template, template): template 
                for template in templates
            }
            
            for future in concurrent.futures.as_completed(future_to_template):
                template = future_to_template[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    completed += 1
                    logger.info(f"Progress: {completed}/{total} ({completed/total*100:.1f}%)")
                    
                    # Check time limit
                    if self.time_limit > 0 and (time.time() - self.start_time) / 60 >= self.time_limit:
                        logger.warning(f"Time limit reached ({self.time_limit} minutes); canceling remaining tasks")
                        for f in future_to_template:
                            f.cancel()
                        break
                        
                except Exception as e:
                    logger.error(f"Error processing result for template {template.name}: {str(e)}")
                    traceback.print_exc()
        
        return results

    def generate_report(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate a test report
        
        Args:
            results: list of test results
            
        Returns:
            dict: test report
        """
        total_time = time.time() - self.start_time
        success_count = sum(1 for r in results if r.get("status") == "success")
        failure_count = sum(1 for r in results if r.get("status") == "failure")
        error_count = sum(1 for r in results if r.get("status") == "error")
        skipped_count = sum(1 for r in results if r.get("status") == "skipped")
        
        report = {
            "summary": {
                "total_tests": len(results),
                "success": success_count,
                "failure": failure_count,
                "error": error_count,
                "skipped": skipped_count,
                "total_time": total_time,
                "success_rate": success_count / len(results) * 100 if results else 0
            },
            "execution_mode": "parallel" if self.parallel else "sequential",
            "target_url": self.target_url,
            "vdb_type": self.vdb_type,
            "time_limit_minutes": self.time_limit,
            "fuzzing_iterations": self.fuzzing_iterations,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "detailed_results": results
        }
        
        # Save report
        report_file = self.output_dir / f"test_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
            
        logger.info(f"Test report saved to: {report_file}")
        
        # Print summary
        logger.info("==== Test Execution Summary ====")
        logger.info(f"Total tests: {len(results)}")
        logger.info(f"Success: {success_count}")
        logger.info(f"Failure: {failure_count}")
        logger.info(f"Error: {error_count}")
        logger.info(f"Skipped: {skipped_count}")
        logger.info(f"Success rate: {report['summary']['success_rate']:.2f}%")
        logger.info(f"Total time: {total_time:.2f}s")
        
        return report

    def run_tests(self) -> Dict[str, Any]:
        """
        Execute all test templates
        
        Returns:
            dict: test report
        """
        templates = self.find_template_files()
        
        if not templates:
            logger.error(f"No test templates found in {self.templates_dir}")
            return {"error": "no_templates_found"}
        
        try:
            # Choose execution mode
            if self.parallel:
                results = self.run_parallel(templates)
            else:
                results = self.run_sequential(templates)
                
            # Generate report
            report = self.generate_report(results)
            # Save executed tests
            self.save_executed_tests()
            return report
            
        except KeyboardInterrupt:
            logger.warning("User interrupted test execution")
            # Save executed tests
            self.save_executed_tests()
            return {"error": "user_interrupt"}
        except Exception as e:
            logger.error(f"Error during test execution: {str(e)}")
            traceback.print_exc()
            return {"error": str(e)}
        finally:
            # Always persist executed tests
            self.save_executed_tests()


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description='VDB fuzzing - test runner')
    parser.add_argument('-i', '--input-dir', type=str, required=True,
                      help='Directory containing test templates')
    parser.add_argument('-t', '--target', type=str, required=True,
                      help='Target server URL (e.g., http://localhost:6333)')
    parser.add_argument('-o', '--output-dir', type=str, default=None,
                      help='Output directory for results (default: input-dir/results)')
    parser.add_argument('-p', '--parallel', action='store_true',
                      help='Run tests in parallel')
    parser.add_argument('-w', '--workers', type=int, default=4,
                      help='Max worker threads when running in parallel (default: 4)')
    parser.add_argument('-l', '--time-limit', type=int, default=0,
                      help='Time limit in minutes (0 for unlimited)')
    parser.add_argument('-n', '--iterations', type=int, default=10,
                      help='Mutation iterations per test (0 to use template default)')
    parser.add_argument('-v', '--verbose', action='store_true',
                      help='Enable verbose logging')
    parser.add_argument('--reset-history', action='store_true',
                      help='Reset executed-test history and rerun all tests')
    parser.add_argument('-vdb', '--vdb-type', type=str, choices=['qdrant', 'weaviate', 'milvus'],
                      help='Target VDB type for filtering templates and directed mutation')
    
    args = parser.parse_args()
    
    # Set log level
    if args.verbose:
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
    
    # Create test runner and start tests
    runner = TestRunner(
        templates_dir=args.input_dir,
        target_url=args.target,
        output_dir=args.output_dir,
        parallel=args.parallel,
        max_workers=args.workers,
        time_limit=args.time_limit,
        fuzzing_iterations=args.iterations,
        vdb_type=args.vdb_type
    )
    
    # Reset executed test history if requested
    if args.reset_history:
        global executed_tests
        executed_tests.clear()  # clear set instead of reassigning
        logger.info("Reset test execution history; all templates will run")
    
    try:
        runner.run_tests()
    except KeyboardInterrupt:
        logger.warning("User interrupted execution")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error occurred while running tests: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
