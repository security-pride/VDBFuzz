#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Vector Database (VDB) fuzzing tool - test script generation module.

This module converts parsed HTTP request sequences into executable Python test
scripts. The generated scripts use the mutator module to perform mutation
testing and record results.
"""
import pdb

import os
import sys
import json
import logging
import copy
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, "") and str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if __package__ in (None, ""):
    from vdbfuzz.template_helper import (
        template_import,
        template_save_failure,
        template_log_config,
        get_content_keys_hash,
    )
else:
    from .template_helper import (
        template_import,
        template_save_failure,
        template_log_config,
        get_content_keys_hash,
    )


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('vdbfuzz.template_generator')


class TemplateGenerator:
    """Test script generator that turns parsed requests into executable Python tests"""
    
    def __init__(self, output_dir: str, target_url: str = None, template_type: str = 'python', input_file: str = None):
        """
        Initialize the script generator.

        Args:
            output_dir: directory to write generated scripts
            target_url: target server URL (optional)
            template_type: template type, defaults to 'python'
            input_file: path to parsed request data
        """
        self.output_dir = Path(output_dir)
        self.target_url = target_url
        self.template_type = template_type
        self.input_file = input_file
        self.output_files = {}
        
        # Create output directory
        if not self.output_dir.exists():
            self.output_dir.mkdir(parents=True)
    
    def generate_template(self, test_name: str = None, requests: List[Dict] = None, vdb_type: str = 'qdrant') -> List[str]:
        """
        Generate a test script for a single test.

        If input_file is provided, test name, request sequence, and VDB type will
        be loaded from that file; otherwise the provided arguments are used.

        Args:
            test_name: test name
            requests: request sequence
            vdb_type: vector database type
            
        Returns:
            list: list of generated template file paths
        """
        
        # Load from input_file if provided
        if self.input_file:
            try:
                with open(self.input_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                test_name = data.get('test_name')
                requests = data.get('requests', [])
                vdb_type = data.get('vdb_type', 'qdrant')
                
                if not test_name or not requests:
                    logger.error(f"Input file {self.input_file} is missing required test name or request data")
                    return []
                    
            except Exception as e:
                logger.error(f"Failed to read input file {self.input_file}: {str(e)}")
                return []
        
        # If required parameters are missing, return empty list
        if not test_name or not requests:
            logger.error("Missing required test name or request data")
            return []

        # Generate import statements
        imports = self._generate_imports()
        
        # Generate helper functions
        send_request = self._generate_send_request_func(test_name, requests[0])
        conn_check = self._generate_connectivity_check_func(vdb_type)
        save_failure = self._generate_save_failure_func()
        
        # Generate test class
        test_class = self._generate_test_class(test_name, requests, vdb_type)
        
        # Assemble template
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        test_class_name = self._get_class_name(test_name)
        
        template = f"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
{imports}

{template_log_config}

# Get logger for the test module
logger = logging.getLogger('vdbfuzz.test.{test_name.replace(".", "_")}')
logger.info("Log file will be written to: " + log_file)

# Global variables
TARGET_URL = "{self.target_url or ''}"
OUTPUT_DIR = "{str(self.output_dir)}"
TEST_NAME = "{test_name}"
VDB_TYPE = "{vdb_type}"  # Can be overridden via -vdb argument

# Health check endpoints per VDB type
VDB_HEALTH_ENDPOINTS = {{
    'qdrant': '/',
    'weaviate': '/v1/.well-known/ready',
    'milvus': '/healthz'
}}

{send_request}

{conn_check}

{save_failure}

{test_class}

# Main entrypoint
if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='VDB fuzz testing - {test_name}')
    parser.add_argument('-t', '--target', type=str, default=TARGET_URL,
                        help='Target server URL, e.g., http://localhost:6333')
    parser.add_argument('-o', '--output-dir', type=str, default=OUTPUT_DIR,
                        help='Output directory for test results')
    parser.add_argument('-n', '--iterations', type=int, default=200,
                        help='Maximum iterations for mutation testing')
    parser.add_argument('-l', '--time-limit', type=int, default=10,
                        help='Time limit for mutation testing (minutes)')
    parser.add_argument('-vdb', '--vdb-type', type=str, default=VDB_TYPE,
                        choices=['qdrant', 'weaviate', 'milvus'],
                        help='Target VDB type for directed mutation strategies')
    args = parser.parse_args()
    
    # Update global variables
    if args.target:
        TARGET_URL = args.target
    if args.output_dir:
        OUTPUT_DIR = args.output_dir
    if args.vdb_type:
        VDB_TYPE = args.vdb_type
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Instantiate test class and run tests
    test = {test_class_name}()
    sys.exit(0 if test.run_tests() else 1)
"""
        
        return self._save_template(template, test_name)
    
    def _generate_imports(self) -> str:
        """Generate import statements"""
        return template_import
    
    def _generate_send_request_func(self, test_name: str, request: Dict) -> str:
        """Generate the send-request helper function"""
        method = request.get('method', 'POST')
        url_path = request.get('url', '/collections')
        
        return f"""
def send_request(content, request_type="{method}", url_path="{url_path}", custom_headers=None):
    \"\"\"
    Send a request to the target server

    Args:
        content: request body or params
        request_type: HTTP method, defaults to "{method}"
        url_path: URL path, defaults to "{url_path}"
        custom_headers: custom headers to merge into default headers
        
    Returns:
        requests.Response: response object
    \"\"\"
    if not TARGET_URL:
        raise ValueError("Target URL is not set, please use -t to specify the target server URL")
    
    if url_path.startswith(('http://', 'https://')):
        parsed = urlparse(url_path)
        if TARGET_URL:
            target = urlparse(TARGET_URL)
            url = urlunparse((
                target.scheme or parsed.scheme,
                target.netloc or parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            ))
        else:
            url = url_path
    else:
        url = TARGET_URL.rstrip('/') + url_path
    
    # Base headers
    headers = {{
        'Content-Type': 'application/json',
    }}

    # Merge custom headers if provided
    if custom_headers:
        headers.update(custom_headers)

    try:
        logger.debug(f"Sending {{request_type}} request to {{url}}")
        if request_type in ['POST', 'PUT']:
            response = requests.request(
                method=request_type,
                url=url,
                headers=headers,
                json=content,
                timeout=10
            )
        else:
            response = requests.request(
                method=request_type,
                url=url,
                headers=headers,
                params=content,
                timeout=10
            )
        
        # Log response summary
        logger.info(f"Response status code: {{response.status_code}}")
        
        return response
    except Exception as e:
        logger.error(f"Failed to send request: {{str(e)}}")
        return None
"""
    
    def _generate_connectivity_check_func(self, vdb_type: str) -> str:
        """Generate connectivity check function (select endpoint based on VDB_TYPE)"""
        return """
def check_connectivity():
    \"\"\"
    Check vector database connectivity (dynamically select endpoint by VDB_TYPE)

    Returns:
        bool: whether the database is reachable
    \"\"\"
    if not TARGET_URL:
        return False

    try:
        # Dynamically select health-check endpoint based on VDB_TYPE
        endpoint = VDB_HEALTH_ENDPOINTS.get(VDB_TYPE.lower(), '/')
        url = TARGET_URL.rstrip('/') + endpoint
        response = requests.get(url, timeout=5)
        return response.status_code in [200, 404, 503]
    except Exception as e:
        logger.error(f"Connectivity check failed: {str(e)}")
        return False
"""
    
    def _generate_save_failure_func(self) -> str:
        """Generate failure persistence helper"""
        return template_save_failure
    def _generate_test_class(self, test_name: str, requests: List[Dict], vdb_type: str) -> str:
        """Generate the test class code"""
        class_name = self._get_class_name(test_name)
        
        # Deduplicate requests
        unique_requests = []
        seen_requests = set()  # Track observed request signatures
        # pdb.set_trace()
        for request in requests:
            
            method = request.get('method', 'GET')
            url = request.get('url', '/')
            content = request.get('content', {})
            
            # Build request signature: method + url + content field names
            content_keys = get_content_keys_hash(content)
            request_signature = f"{method}|{url}|{content_keys}"
            
            # Add unseen signatures to unique list
            if request_signature not in seen_requests:
                seen_requests.add(request_signature)
                unique_requests.append(request)
            else:
                logger.info(f"Skip duplicate request: {method} {url}")
        
        logger.info(f"Original requests: {len(requests)}, after dedup: {len(unique_requests)}")

        if vdb_type == 'qdrant' and unique_requests[0]['method'] in ['PUT', 'POST'] and unique_requests[-1]['method'] != 'DELETE':
            clean_requests = copy.deepcopy(unique_requests[0])
            clean_requests['method'] = 'DELETE'
            unique_requests.append(clean_requests)

        # Generate test methods
        test_methods = []
        for i, request in enumerate(unique_requests):
            test_methods.append(self._generate_test_method(request, i))
        
        test_methods_str = "\n\n".join(test_methods)
        
        # Get test method count
        test_count = len(test_methods)
        
        # Assemble test class
        return f"""
class {class_name}:
    \"\"\"Auto-generated VDB fuzz test class - {test_name}\"\"\"
    
    def __init__(self):
        \"\"\"Initialize the test class\"\"\"
        self.test_name = "{test_name}"
        self.test_count = {test_count}  # Number of test methods
        self.mutator = Mutator(vdb_type=VDB_TYPE)  # Initialize mutator with directed mutations for VDB type
    
    def run_tests(self):
        \"\"\"Run all tests\"\"\"
        logger.info(f"Start testing: {{self.test_name}}")
        logger.info(f"Target URL: {{TARGET_URL}}")
        
        # Check connectivity
        if not check_connectivity():
            logger.error("Unable to connect to target server, aborting tests")
            return False
        
        # Run all test cases
        try:
            for i in range(self.test_count):
                logger.info(f"Running test {{i+1}}/{{self.test_count}}")
                method_name = f"test_request_{{i}}"
                if hasattr(self, method_name):
                    test_method = getattr(self, method_name)
                    test_method()
                else:
                    logger.warning(f"Test method not found: {{method_name}}")
            
            logger.info("All tests completed")
            return True
        except Exception as e:
            logger.error(f"Exception during tests: {{str(e)}}")
            traceback.print_exc()
            return False

{test_methods_str}
"""
    
    def _generate_test_method(self, request: Dict, index: int) -> str:
        """Generate a test method"""
        method = request.get('method', 'GET')
        url = request.get('url', '/')
        content = request.get('content', {})
        headers = request.get('headers', {})

                
        # Directly use request data instead of referencing raw log data
        formatted_headers = self._format_dict_as_code(headers) if headers else '{}'
        formatted_content = self._format_request_as_code(content)
        
        # Only generate mutation tests for PUT/POST requests
        if index == 0 or (method not in ['PUT', 'POST']) or not content:
            # Non-write request or empty body
            return f"""
    def test_request_{index}(self):
        \"\"\"Test request {index} - {method} {url}\"\"\"
        logger.info(f"Skip non-write or empty-content request: {method} {url}")
        method = '{method}'
        url_path = '{url}'
        headers = {formatted_headers}
        
        # Original request content
        original_content = {formatted_content}


        send_request(original_content, method, url_path, headers)
        return True
"""

        
        return f"""
    def test_request_{index}(self):
        \"\"\"Test request {index} - {method} {url}\"\"\"
        logger.info(f"Testing request: {method} {url}")
        
        method = '{method}'
        url_path = '{url}'
        headers = {formatted_headers}
        
        # Original request content
        original_content = {formatted_content}
        
        if not original_content:
            logger.info("Request has no content, skip mutation testing")
            return True
        
        # Define request sender
        def send_mutated_request(mutated_content):
            return send_request(mutated_content, method, url_path, headers)
        
        logger.info("Start mutation testing...")
        
        # Get CLI arguments
        iterations = getattr(args, 'iterations', 200)  # default 200
        time_limit = getattr(args, 'time_limit', 10)   # default 10 minutes
                    
        mutator = Mutator(vdb_type=VDB_TYPE)  # Create mutator with directed mutations for VDB type
        failures = mutator.normal_mutate(
            original_content=original_content,
            send_request=send_mutated_request,
            connectivity_check_func=check_connectivity,
            save_failure_func=save_failure,
            max_time_minutes=time_limit,  # use configured time_limit
            max_iterations=iterations     # use configured iterations
        )
        
        if failures:
            logger.warning(f"Found {{len(failures)}} mutations causing exceptions")
        else:
            logger.info("No anomalies found in mutation testing")
        
        return len(failures) == 0
"""
    
    def _format_request_as_code(self, request_data) -> str:
        """Convert request data into a Python code string"""
        # Handle complex structures that may contain placeholders
        if isinstance(request_data, dict):
            result = self._format_dict_as_code(request_data)
            return result
        elif isinstance(request_data, list):
            result = self._format_list_as_code(request_data)
            return result
        elif isinstance(request_data, str) and request_data.startswith('__FLOAT_ARRAY_DIM_'):
            # Handle float array placeholder
            return self._handle_float_array_placeholder(request_data)
        else:
            # Other basic types: use json.dumps for conversion
            json_str = json.dumps(request_data, indent=4, ensure_ascii=False)
            # Replace double quotes with single quotes for easier embedding
            return json_str.replace("'", "\\'").replace('"', "'")
    
    def _format_dict_as_code(self, dict_data) -> str:
        """Convert a dict into a Python code string"""
        parts = []
        parts.append('{')  # dict start
        
        for key, value in dict_data.items():
            # Handle key
            key_str = f"'{key}'" if isinstance(key, str) else str(key)
            
            # Handle value by type
            if isinstance(value, dict):
                value_str = self._format_dict_as_code(value)
            elif isinstance(value, list):
                value_str = self._format_list_as_code(value)
            elif isinstance(value, str) and value.startswith('__FLOAT_ARRAY_DIM_'):
                # Handle float array placeholder
                value_str = self._handle_float_array_placeholder(value)
            else:
                # Basic types, use json
                if value is None:
                    value_str = 'None'
                elif isinstance(value, bool):
                    # Use Python's True/False
                    value_str = str(value)
                else:
                    value_str = json.dumps(value, ensure_ascii=False).replace('"', "'")
            
            # Append to result
            parts.append(f"    {key_str}: {value_str},")
        
        parts.append('}')  # dict end
        return '\n'.join(parts)
    
    def _format_list_as_code(self, list_data) -> str:
        """Convert a list into a Python code string"""
        # Check float array placeholder
        if len(list_data) == 1 and isinstance(list_data[0], str) and list_data[0].startswith('__FLOAT_ARRAY_DIM_'):
            return self._handle_float_array_placeholder(list_data[0])
            
        parts = []
        parts.append('[')  # list start
        
        for item in list_data:
            # Handle item by type
            if isinstance(item, dict):
                item_str = self._format_dict_as_code(item)
            elif isinstance(item, list):
                item_str = self._format_list_as_code(item)
            elif isinstance(item, str) and item.startswith('__FLOAT_ARRAY_DIM_'):
                # Handle float array placeholder
                item_str = self._handle_float_array_placeholder(item)
            else:
                # Basic types, use json
                if item is None:
                    item_str = 'None'
                elif isinstance(item, bool):
                    # Use Python's True/False
                    item_str = str(item)
                else:
                    item_str = json.dumps(item, ensure_ascii=False).replace('"', "'")
            
            # Append to result
            parts.append(f"    {item_str},")
        
        parts.append(']')  # list end
        return '\n'.join(parts)
    
    def _handle_float_array_placeholder(self, placeholder) -> str:
        """Handle float array placeholders, converting to code calls"""
        # Handle multi-dimensional placeholders
        if placeholder.startswith('__FLOAT_MULTI_DIM_'):
            try:
                # Extract dimensions from placeholder
                dims_str = placeholder.replace('__FLOAT_MULTI_DIM_', '').replace('__', '')
                dimensions = [int(dim) for dim in dims_str.split(',')]
                
                # Use specialized generators for different multi-d arrays
                if len(dimensions) == 2:
                    # 2D matrix: use embedding matrix generator
                    return f"self.mutator.generate_embedding_matrix(rows={dimensions[0]}, embedding_dim={dimensions[1]}, normalized=True)"
                else:
                    # Other multi-d arrays: use generic generator
                    dims_list = "[" + ", ".join(map(str, dimensions)) + "]"
                    return f"self.mutator.generate_multi_dim_array(dimensions={dims_list}, normalized=True)"
            except (ValueError, IndexError):
                # On parse error, return default 2D matrix
                return "self.mutator.generate_embedding_matrix(rows=5, embedding_dim=100, normalized=True)"
        
        # Handle single-dimension placeholders
        elif placeholder.startswith('__FLOAT_ARRAY_DIM_'):
            try:
                dimension = int(placeholder.replace('__FLOAT_ARRAY_DIM_', '').replace('__', ''))
                # Call mutator.generate_float_array
                return f"self.mutator.generate_float_array(dimension={dimension}, normalized=True)"
            except ValueError:
                # If parse fails, fall back to default dimension
                return "self.mutator.generate_float_array(dimension=100, normalized=True)"
        
        # Other placeholders: return default vector
        else:
            return "self.mutator.generate_float_array(dimension=100, normalized=True)"
    
    def _escape_string_for_code(self, string_value: str) -> str:
        """Escape strings so they can be embedded in generated code"""
        return string_value.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
    
    def _get_class_name(self, test_name: str) -> str:
        """Generate a class name from test name"""
        # Remove illegal chars, convert dot/underscore to camel-case
        parts = ''.join(c if c.isalnum() or c == '_' or c == '.' else '_' for c in test_name).split('.')
        return ''.join(part.title() for part in ''.join(parts).split('_'))
    
    def _indent_code(self, code: str, spaces: int) -> str:
        """Indent code lines"""
        return " " * spaces + code
    
    def _save_template(self, template_content: str, test_name: str) -> List[str]:
        """Save generated template to file"""
        safe_name = test_name.replace('.', '_')
        file_path = self.output_dir / f"{safe_name}_test.py"
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(template_content)
            
            # Set execute permission
            os.chmod(file_path, 0o755)
            
            logger.info(f"Generated test template: {file_path}")
            self.output_files[test_name] = str(file_path)
            return [str(file_path)]
        except Exception as e:
            logger.error(f"Failed to save template {test_name}: {str(e)}")
            return []


def generate_all_templates(parsed_requests_file: str, output_dir: str, target_url: str = None) -> List[str]:
    """
    Generate all test templates for a parsed requests file
    
    Args:
        parsed_requests_file: path to parsed requests file
        output_dir: output directory
        target_url: target server URL (optional)
        
    Returns:
        list: list of generated template file paths
    """
    try:
        with open(parsed_requests_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        test_name = data.get('test_name', 'unknown_test')
        vdb_type = data.get('vdb_type', 'qdrant')
        requests = data.get('requests', [])
        
        if not requests:
            logger.warning(f"No requests found in file {parsed_requests_file}")
            return []
        
        generator = TemplateGenerator(output_dir, target_url)
        template_path = generator.generate_template(test_name, requests, vdb_type)
        
        return [template_path] if template_path else []
    except Exception as e:
        logger.error(f"Failed to generate template: {str(e)}")
        return []


def generate_all_templates_from_parser(log_dir: str, output_dir: str, target_url: str = None) -> List[str]:
    """
    Process a log directory with the parser and generate all test templates
    
    Args:
        log_dir: log directory
        output_dir: output directory
        target_url: target server URL (optional)
        
    Returns:
        list: list of generated template file paths
    """
    try:
        # Import parser
        if __package__ in (None, ""):
            from vdbfuzz.parser import LogParser
        else:
            from .parser import LogParser
        
        # Parse logs
        parser = LogParser(log_dir)
        write_requests = parser.extract_write_requests_with_content()
        
        if not write_requests:
            logger.warning(f"No write requests extracted from {log_dir}")
            return []
        
        # Generate templates for each test
        generator = TemplateGenerator(output_dir, target_url)
        template_paths = []
        
        for test_name, requests in write_requests.items():
            template_path = generator.generate_template(test_name, requests, parser.vdb_type)
            if template_path:
                template_paths.append(template_path)
        
        return template_paths
    except Exception as e:
        logger.error(f"Failed to generate templates from parser: {str(e)}")
        return []


def main():
    """Command-line entrypoint"""
    parser = argparse.ArgumentParser(description='VDB fuzz testing - test script generation')
    parser.add_argument('-i', '--input-dir', type=str, required=True,
                        help='Directory containing log files or a parsed request file')
    parser.add_argument('-o', '--output-dir', type=str, default='./templates',
                        help='Directory to output generated test templates')
    parser.add_argument('-t', '--target', type=str, default='',
                        help='Target server URL (e.g., http://localhost:6333)')
    parser.add_argument('-f', '--file-mode', action='store_true',
                        help='If set, treat input as a parsed request file instead of a log directory')
    
    args = parser.parse_args()
    
    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)
    
    if args.file_mode:
        # Generate templates from a parsed file
        templates = generate_all_templates(args.input_dir, args.output_dir, args.target)
    else:
        # Generate templates from log directory
        templates = generate_all_templates_from_parser(args.input_dir, args.output_dir, args.target)
    
    if templates:
        logger.info(f"Successfully generated {len(templates)} test templates:")
        for template in templates:
            logger.info(f"  - {template}")
    else:
        logger.warning("No test templates were generated")


if __name__ == "__main__":
    main()
