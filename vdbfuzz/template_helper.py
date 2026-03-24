


template_import = """
import json
import logging
import os
import sys
import time
import argparse
import traceback
import requests
from urllib.parse import urlparse, urlunparse
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from pathlib import Path

# Import mutation module - walk up the directory tree to find the vdbfuzz package
def _setup_vdbfuzz_path():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Walk up at most 10 directory levels
    for _ in range(10):
        vdbfuzz_dir = os.path.join(current_dir, 'vdbfuzz')
        if os.path.isdir(vdbfuzz_dir) and os.path.exists(os.path.join(vdbfuzz_dir, 'mutator.py')):
            if current_dir not in sys.path:
                sys.path.insert(0, current_dir)
            return True
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:  # Reached root directory
            break
        current_dir = parent_dir
    return False

_setup_vdbfuzz_path()

try:
    from vdbfuzz.mutator import Mutator
except ImportError as e:
    raise ImportError(f"Failed to import Mutator. Ensure the vdbfuzz package is on the correct path: {e}")
"""

template_save_failure = """
def save_failure(failure_info):
    \"\"\"
    Save failure details to file

    Args:
        failure_info: failure info dict
    \"\"\"
    if not OUTPUT_DIR:
        logger.warning("OUTPUT_DIR not set; cannot save failure details")
        return

    # Create directory for failure information
    failure_dir = Path(OUTPUT_DIR) / "failures" / TEST_NAME.replace(".", "_")
    failure_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    mutation_type = failure_info.get("mutation", {}).get("type", "unknown")
    mutation_path = "_".join(str(x) for x in failure_info.get("mutation", {}).get("path", []))
    
    filename = f"failure_{mutation_type}_{mutation_path}_{timestamp}.json"
    file_path = failure_dir / filename
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(failure_info, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved failure information to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save failure information: {str(e)}")
"""

template_log_config = """
# Logging configuration
# Create directory for log files
os.makedirs('logs', exist_ok=True)

# Add console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# Add file handler
# Use timestamp as part of the filename
log_file = "logs/mutation_test_" + datetime.now().strftime('%Y%m%d_%H%M%S') + ".log"
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)  # Record detailed logs to file
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)  # DEBUG level to capture all logs
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)
"""



    
def get_content_keys_hash(content) -> str:
    """Generate a hash-like string for content structure, deduplicating by key layout only
    
    Args:
        content: request content
        
    Returns:
        str: comma-separated key structure
    """
    if isinstance(content, dict):
        # For dicts, consider only keys, not values
        sorted_keys = sorted(content.keys())
        
        # Recursively process nested dicts
        result = []
        for key in sorted_keys:
            value = content[key]
            if isinstance(value, dict):
                # If the value is a dict, recurse into its key structure
                nested_keys = get_content_keys_hash(value)
                result.append(f"{key}:{{{nested_keys}}}")
            else:
                # For non-dict values, record only the key name
                result.append(key)
            
        return ",".join(result)
    elif isinstance(content, list) and content and isinstance(content[0], dict):
        # For a list of dicts, inspect the first element's key structure
        return f"list_of_dicts:{get_content_keys_hash(content[0])}"
    else:
        # Non-dict types return empty string since we only care about key structure
        return ""
