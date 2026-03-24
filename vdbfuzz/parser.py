#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Vector Database (VDB) fuzzing tool - log parsing module.

This module parses user-provided log files to extract HTTP request sequences.
Currently supports Qdrant and Weaviate log formats.
Implements recursive directory traversal to find and analyze all log files.
"""

import os
import sys
import json
import logging
from typing import Dict, List, Tuple, Any, Union, Optional
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('vdbfuzz.parser')


class LogParser:
    """Log parser for vector database HTTP request logs"""
    
    # Supported VDB types
    SUPPORTED_VDB_TYPES = ['qdrant', 'weaviate', 'milvus']
    
    def __init__(self, base_dir: str, vdb_type: str = None):
        """
        Initialize the log parser
        
        Args:
            base_dir: root directory of log files
            vdb_type: explicitly specified VDB type, overrides directory inference
        """
        self.base_dir = Path(base_dir)
        # Prefer explicitly provided vdb_type, otherwise infer from directory name
        if vdb_type:
            vdb_type_lower = vdb_type.lower()
            if vdb_type_lower in self.SUPPORTED_VDB_TYPES:
                self.vdb_type = vdb_type_lower
                logger.info(f"Using explicitly specified VDB type: {self.vdb_type}")
            else:
                logger.warning(f"Unsupported VDB type: {vdb_type}, will infer from directory name")
                self.vdb_type = self._determine_vdb_type()
        else:
            self.vdb_type = self._determine_vdb_type()
    
    def _determine_vdb_type(self) -> str:
        """
        Determine VDB type based on directory name
        
        Returns:
            str: 'qdrant', 'weaviate', or 'milvus'
        """
        dir_name = self.base_dir.name.lower()
        if 'qdrant' in dir_name:
            return 'qdrant'
        elif 'weaviate' in dir_name:
            return 'weaviate'
        elif 'milvus' in dir_name:
            return 'milvus'
        else:
            # Default to qdrant format
            logger.warning(f"Cannot determine VDB type from directory name '{dir_name}', defaulting to 'qdrant'")
            return 'qdrant'
    
    def find_log_files(self) -> List[Path]:
        """
        Recursively traverse the directory to find all JSON log files
        
        Returns:
            list: list of log file paths
        """
        log_files = []
        
        for root, _, files in os.walk(self.base_dir):
            for filename in files:
                if filename.endswith('.json'):
                    log_path = Path(root) / filename
                    log_files.append(log_path)
        
        logger.info(f"Found {len(log_files)} log files")
        return log_files
    
    def parse_log_file(self, log_file: Path) -> Dict:
        """
        Parse a single log file
        
        Args:
            log_file: path to log file
            
        Returns:
            dict: parsed log data
        """
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
            
            # Basic validation
            if 'test_name' not in log_data or 'requests' not in log_data:
                logger.warning(f"Log file {log_file} is invalid: missing required fields")
                return None
            
            logger.debug(f"Parsed log file {log_file}")
            return log_data
        except Exception as e:
            logger.error(f"Failed to parse log file {log_file}: {str(e)}")
            return None
    
    def extract_requests(self, log_data: Dict) -> List[Dict]:
        """
        Extract request sequence from log data
        
        Args:
            log_data: parsed log data
            
        Returns:
            list: list of requests
        """
        if not log_data or 'requests' not in log_data:
            return []
        
        return log_data['requests']
    
    def filter_write_requests(self, requests: List[Dict]) -> List[Dict]:
        """
        Filter write requests (PUT/POST/PATCH)
        
        Args:
            requests: request sequence
            
        Returns:
            list: write requests
        """
        write_methods = ['PUT', 'POST', 'PATCH']
        return [req for req in requests if req.get('method') in write_methods]
    
    def extract_content_from_request(self, request: Dict) -> Optional[Dict]:
        """
        Extract the content part from a request
        
        Args:
            request: single request data
            
        Returns:
            dict: request content, or None if absent
        """
        if not request or 'content' not in request:
            return None
        
        content = request.get('content')
        
        # When vector optimization is enabled, detect and replace float arrays with placeholders
        return self.optimize_float_arrays(content) if content else None
        
    def optimize_float_arrays(self, data: Any, path: List = None) -> Any:
        """
        Recursively traverse and optimize float arrays in data.
        
        Detect float arrays and replace them with placeholders.
        Supports detection and replacement of multi-dimensional arrays (matrices/tensors).
        
        Args:
            data: data to process (dict, list, or primitive)
            path: current path (for recursion tracking)
            
        Returns:
            optimized data
        """
        if path is None:
            path = []
            
        # Dict
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                result[key] = self.optimize_float_arrays(value, path + [key])
            return result
            
        # List
        elif isinstance(data, list):
            # Detect whether it's a multi-dimensional array
            dimensions, is_multidim_array = self.get_array_dimensions(data)
            
            if is_multidim_array:
                # Return multi-dimensional array placeholder
                return f"__FLOAT_MULTI_DIM_{','.join(map(str, dimensions))}__"
            elif self.is_float_array(data):
                # Return single-dimension array placeholder
                return f"__FLOAT_ARRAY_DIM_{len(data)}__"
            else:
                # Recursively process other list elements
                return [self.optimize_float_arrays(item, path + [i]) for i, item in enumerate(data)]
        
        # Other primitive types: return as-is
        return data
    
    def get_array_dimensions(self, data) -> Tuple[List[int], bool]:
        """
        Get dimensions of a multi-dimensional array
        
        Args:
            data: data to inspect
        
        Returns:
            Tuple[List[int], bool]: (dimension list, whether multi-dimensional)
        """
        # Non-list types are not arrays
        if not isinstance(data, list):
            return [], False
            
        # Empty list is not a multi-dimensional array
        if not data:
            return [], False
            
        # One-dimensional numeric array is not treated as multi-dimensional
        if self.is_float_array(data):
            return [len(data)], False
            
        # Ensure all elements are lists
        if not all(isinstance(item, list) for item in data):
            return [], False
        
        # Check child arrays are numeric/multi-d and lengths are consistent
        child_dimensions = []
        is_consistent = True
        first_child_len = len(data[0]) if data else 0
        
        for i, child in enumerate(data):
            # Child array lengths must match
            if len(child) != first_child_len:
                is_consistent = False
                break
                
            # Child must be float array or deeper multi-d
            if not self.is_float_array(child) and not (isinstance(child, list) and len(child) > 0 and isinstance(child[0], list)):
                is_consistent = False
                break
                
            # For deeper multi-d arrays, recurse
            if isinstance(child, list) and len(child) > 0 and isinstance(child[0], list):
                sub_dims, is_sub_multidim = self.get_array_dimensions(child)
                if is_sub_multidim and i == 0:
                    child_dimensions = sub_dims
                elif is_sub_multidim and sub_dims != child_dimensions:
                    is_consistent = False
                    break
                    
        # Valid multi-dimensional array
        if is_consistent and len(data) >= 2 and first_child_len >= 2:
            if child_dimensions:
                # High-dimensional array dimensions
                return [len(data)] + child_dimensions, True
            else:
                # 2D array dimensions
                return [len(data), first_child_len], True
                
        return [], False
    
    def is_float_array(self, data: List) -> bool:
        """
        Check whether a list is a float array.
        
        Criteria:
        1. Non-empty list
        2. ≥80% elements are numbers (float or int, not bool)
        3. Typically length ≥2 (vectors have at least two dimensions)
        
        Args:
            data: list to inspect
            
        Returns:
            bool: whether it is a float array
        """
        # Non-list or empty list is not a float array
        if not isinstance(data, list) or not data:
            return False
        
        # Vectors typically have at least two dimensions
        if len(data) < 2:
            return False
            
        # Ratio of numeric elements (float or int, excluding bool)
        number_count = sum(1 for item in data if isinstance(item, (float, int)) and not isinstance(item, bool))
        number_ratio = number_count / len(data)
        
        # Consider float array if ≥80% are numeric
        return number_ratio >= 0.8
    
    def process_all_logs(self) -> Dict[str, List[Dict]]:
        """
        Process all log files and return requests organized by test
        
        Returns:
            dict: {test_name: [requests]}
        """
        result = {}
        log_files = self.find_log_files()
        
        for log_file in log_files:
            try:
                # Extract test name from directory structure
                test_file = log_file.parent.name
                test_function = log_file.name
                test_key = f"{test_file}.{test_function}"
                
                # Parse log file
                log_data = self.parse_log_file(log_file)
                if not log_data:
                    continue
                
                # Extract request sequence
                requests = self.extract_requests(log_data)
                
                # Create list if test not yet in result
                if test_key not in result:
                    result[test_key] = []
                
                # Append requests
                result[test_key].extend(requests)
                logger.debug(f"Extracted {len(requests)} requests from {test_key}")
            except Exception as e:
                logger.error(f"Error processing log file {log_file}: {str(e)}")
        
        return result
    
    def extract_write_requests_with_content(self) -> Dict[str, List[Dict]]:
        """
        Extract all write requests with content and optimize float arrays
        
        Returns:
            dict: {test_name: [write requests]}
        """
        all_requests = self.process_all_logs()
        result = {}
        
        for test_key, requests in all_requests.items():
            # Filter write requests
            write_requests = self.filter_write_requests(requests)
            
            # Keep requests with content and optimize float arrays
            write_requests_with_content = []
            
            for req in write_requests:
                # Extract and optimize content
                optimized_content = self.extract_content_from_request(req)
                if optimized_content is not None:
                    # Clone request and attach optimized content
                    optimized_req = req.copy()
                    optimized_req['content'] = optimized_content
                    write_requests_with_content.append(optimized_req)
            
            if write_requests_with_content:
                result[test_key] = write_requests_with_content
        
        return result
    
    def get_request_summary(self, request: Dict) -> Dict:
        """
        Get summary info for a request
        
        Args:
            request: single request data
            
        Returns:
            dict: request summary
        """
        return {
            'method': request.get('method', 'UNKNOWN'),
            'url': request.get('url', ''),
            'has_content': 'content' in request,
            'content_size': len(json.dumps(request.get('content', {}))) if 'content' in request else 0,
            'status_code': request.get('response', {}).get('status_code', 0) if 'response' in request else 0
        }
    
    def get_test_summary(self) -> Dict[str, Dict]:
        """
        Get summary info for all tests
        
        Returns:
            dict: {test_name: summary}
        """
        all_requests = self.process_all_logs()
        summary = {}
        
        for test_key, requests in all_requests.items():
            write_requests = self.filter_write_requests(requests)
            write_requests_with_content = [
                req for req in write_requests 
                if self.extract_content_from_request(req) is not None
            ]
            
            summary[test_key] = {
                'total_requests': len(requests),
                'write_requests': len(write_requests),
                'write_requests_with_content': len(write_requests_with_content)
            }
        
        return summary
    
    def save_extracted_requests(self, output_dir: str) -> Dict[str, str]:
        """
        Save extracted requests to JSON files
        
        Args:
            output_dir: output directory
            
        Returns:
            dict: {test_name: output file path}
        """
        output_path = Path(output_dir)
        if not output_path.exists():
            output_path.mkdir(parents=True)
        
        write_requests = self.extract_write_requests_with_content()
        output_files = {}
        
        for test_key, requests in write_requests.items():
            safe_name = test_key.replace('.', '_')
            output_file = output_path / f"{safe_name}.json"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'test_name': test_key,
                    'vdb_type': self.vdb_type,
                    'requests': requests
                }, f, indent=2)
            
            output_files[test_key] = str(output_file)
            logger.info(f"Saved {len(requests)} requests for {test_key} to {output_file}")
        
        return output_files
