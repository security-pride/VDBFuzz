#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gRPC data-capture injection tool - V2.
It does not modify the original files. Instead, it creates copies with gRPC interception enabled.

Features:
1. Correctly identifies multiline import statements and bracket scopes to avoid injecting into incomplete imports.
2. Prevents duplicate injection.
3. Uses regular expressions and a more robust parsing strategy for Python source structure.
"""

import os
import sys
import re
import ast
import json
import shutil
import argparse
import logging
import traceback
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('GrpcCaptureInjector')

# gRPC interceptor code template
GRPC_CAPTURE_HEADER = """
# ---------- gRPC request capture code (auto-generated) ----------
import os
import sys
import json
import time
import logging
from datetime import datetime

# Configure the logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GrpcCapture")

# Add the project root to the Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# Create the log directory
log_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
script_name = os.path.basename(__file__).split('.')[0]
grpc_logs_dir = f"network_logs/grpc/{script_name}_{log_timestamp}"
os.makedirs(grpc_logs_dir, exist_ok=True)
log_file = f"{grpc_logs_dir}/{script_name}_{int(time.time())}.json"
print(f"gRPC requests will be logged to: {log_file}")

# Store captured requests
captured_requests = []

# Basic dependency check
GRPC_AVAILABLE = False
try:
    import grpc
    from google.protobuf import text_format
    GRPC_AVAILABLE = True
except ImportError as e:
    print(f"Note: failed to import gRPC dependencies: {e}, gRPC requests cannot be captured")

# Define custom interceptors implementing all four required interfaces
if GRPC_AVAILABLE:
    # Unary-unary interceptor
    class UnaryUnaryInterceptor(grpc.UnaryUnaryClientInterceptor):
        def intercept_unary_unary(self, continuation, client_call_details, request):
            # Record the request
            try:
                method = client_call_details.method
                request_str = text_format.MessageToString(request)
                
                request_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time())}"
                request_info = {
                    "request_id": request_id,
                    "method": method.decode('utf-8') if isinstance(method, bytes) else method,
                    "timestamp": time.time(),
                    "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "request_type": "unary_unary",
                    "request": {"request_str": request_str}
                }
                
                # Get the response
                response = continuation(client_call_details, request)
                
                # Record the response
                request_info["response"] = str(response)
                
                # Add the record to the captured-request list
                captured_requests.append(request_info)
                logger.info(f"Captured gRPC request: {method}")
                
                return response
            except Exception as e:
                logger.error(f"Error while intercepting request: {e}")
                return continuation(client_call_details, request)

    # Unary-stream interceptor
    class UnaryStreamInterceptor(grpc.UnaryStreamClientInterceptor):
        def intercept_unary_stream(self, continuation, client_call_details, request):
            # Record the request
            try:
                method = client_call_details.method
                request_str = text_format.MessageToString(request)
                
                request_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time())}"
                request_info = {
                    "request_id": request_id,
                    "method": method.decode('utf-8') if isinstance(method, bytes) else method,
                    "timestamp": time.time(),
                    "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "request_type": "unary_stream",
                    "request": {"request_str": request_str}
                }
                
                # Get the response
                response_iterator = continuation(client_call_details, request)
                
                # Record the response
                request_info["response"] = "Stream response (not captured)"
                
                # Add the record to the captured-request list
                captured_requests.append(request_info)
                logger.info(f"Captured gRPC streaming request: {method}")
                
                return response_iterator
            except Exception as e:
                logger.error(f"Error while intercepting streaming request: {e}")
                return continuation(client_call_details, request)

    # Stream-unary interceptor
    class StreamUnaryInterceptor(grpc.StreamUnaryClientInterceptor):
        def intercept_stream_unary(self, continuation, client_call_details, request_iterator):
            # Record the request(simplified)
            try:
                method = client_call_details.method
                
                request_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time())}"
                request_info = {
                    "request_id": request_id,
                    "method": method.decode('utf-8') if isinstance(method, bytes) else method,
                    "timestamp": time.time(),
                    "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "request_type": "stream_unary",
                    "request": {"request_str": "Stream request (not captured)"}
                }
                
                # Get the response
                response = continuation(client_call_details, request_iterator)
                
                # Record the response
                request_info["response"] = str(response)
                
                # Add the record to the captured-request list
                captured_requests.append(request_info)
                logger.info(f"Captured client-streaming gRPC request: {method}")
                
                return response
            except Exception as e:
                logger.error(f"Error while intercepting client-streaming request: {e}")
                return continuation(client_call_details, request_iterator)

    # Stream-stream interceptor
    class StreamStreamInterceptor(grpc.StreamStreamClientInterceptor):
        def intercept_stream_stream(self, continuation, client_call_details, request_iterator):
            # Record the request(simplified)
            try:
                method = client_call_details.method
                
                request_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time())}"
                request_info = {
                    "request_id": request_id,
                    "method": method.decode('utf-8') if isinstance(method, bytes) else method,
                    "timestamp": time.time(),
                    "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "request_type": "stream_stream",
                    "request": {"request_str": "Bidirectional stream (not captured)"}
                }
                
                # Get the response
                response_iterator = continuation(client_call_details, request_iterator)
                
                # Record the response
                request_info["response"] = "Bidirectional stream response (not captured)"
                
                # Add the record to the captured-request list
                captured_requests.append(request_info)
                logger.info(f"Captured bidirectional gRPC request: {method}")
                
                return response_iterator
            except Exception as e:
                logger.error(f"Error while intercepting bidirectional streaming request: {e}")
                return continuation(client_call_details, request_iterator)

    # Override the original channel-construction function
    original_insecure_channel = grpc.insecure_channel

    def intercepted_insecure_channel(*args, **kwargs):
        # Create the original channel
        channel = original_insecure_channel(*args, **kwargs)
        
        # Attach all interceptors
        from grpc import intercept_channel
        intercepted = intercept_channel(
            channel,
            UnaryUnaryInterceptor(),
            UnaryStreamInterceptor(),
            StreamUnaryInterceptor(),
            StreamStreamInterceptor()
        )
        target = args[0] if args else kwargs.get('target', 'unknown')
        print(f"Intercepted gRPC channel: {target}")
        return intercepted

    # Apply the monkey patch
    grpc.insecure_channel = intercepted_insecure_channel
# ---------- end of gRPC request capture code ----------
"""

# Code template inserted after pymilvus connections are established
GRPC_CAPTURE_CONNECT_CODE = """
# ---------- enable gRPC request capture ----------
if 'grpc_capture' in globals() and grpc_capture is not None:
    connections.set_install_channel_callback(grpc_capture.interceptor.install_channel_interceptor)
    grpc_capture.interceptor.set_log_file(grpc_capture.log_file)
    print("gRPC interceptor enabled (connections module)")
# ---------- end of gRPC request capture enablement ----------
"""

# Code template inserted after MilvusClient initialization
GRPC_CAPTURE_MILVUSCLIENT_CODE = """
# ---------- enable MilvusClient gRPC request capture ----------
if 'grpc_capture' in globals() and grpc_capture is not None:
    # Preserve the original MilvusClient class
    if 'original_milvus_client' not in globals():
        original_milvus_client = MilvusClient
        
        # Create a wrapper class to intercept requests
        class InterceptedMilvusClient(original_milvus_client):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # Get the internal gRPC channel and apply the interceptor
                if hasattr(self, '_MilvusClient__grpc_client') and hasattr(self._MilvusClient__grpc_client, '_channel'):
                    self._MilvusClient__grpc_client._channel = grpc_capture.interceptor.install_channel_interceptor(self._MilvusClient__grpc_client._channel)
                    print("gRPC interceptor installed on MilvusClient")
        
        # Replace the global MilvusClient
        globals()['MilvusClient'] = InterceptedMilvusClient
        print("MilvusClient replaced to enable gRPC interception")
# ---------- end of MilvusClient gRPC request capture enablement ----------
"""

# Code template appended before program exit
GRPC_CAPTURE_END_CODE = """
# ---------- save gRPC request logs ----------
print(f"Saving gRPC requests to file: {log_file}")
try:
    # Ensure the log directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # Save captured requests to the log file
    if 'captured_requests' in globals() and captured_requests:
        log_data = {
            "timestamp": time.time(),
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "requests": captured_requests
        }
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
        
        print(f"\u2705 Successfully saved {len(captured_requests)} gRPC requests to: {log_file}")
    else:
        print("\u274c No requests were captured; nothing to save")
except Exception as e:
    print(f"\u274c Error while saving gRPC requests: {e}")
# ---------- end of gRPC request log save ----------
"""

# Marker used to detect already-injected code
CAPTURE_CODE_MARKER = "# ---------- gRPC request capture code (auto-generated) ----------"

def has_pymilvus_import(source_code):
    """Check whether the code imports the pymilvus package."""
    # Check direct imports or from-import statements
    direct_import = re.compile(r'(?:^|\s)(?:import\s+pymilvus|from\s+pymilvus\s+import)', re.MULTILINE)
    
    # Check imports of MilvusClient (newer API)
    milvus_client_import = re.compile(r'(?:^|\s)(?:from\s+pymilvus\s+import\s+(?:[^\n]*,\s*)?MilvusClient|import\s+pymilvus.*MilvusClient)', re.MULTILINE)
    
    return bool(direct_import.search(source_code)) or bool(milvus_client_import.search(source_code))

def has_capture_code(source_code):
    """Check whether gRPC capture code has already been injected."""
    return CAPTURE_CODE_MARKER in source_code

def find_balanced_imports(source_code):
    """
    Find all import statements, including multiline imports, and return their start and end line numbers.
    This also handles nested brackets.
    """
    lines = source_code.splitlines()
    imports = []
    in_import = False
    start_line = 0
    
    # Track parentheses, braces, and brackets
    brackets = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Skip empty lines and comments
        if not stripped or stripped.startswith('#'):
            continue
        
        # Detect the start of an import statement
        if (stripped.startswith('import ') or stripped.startswith('from ')) and not in_import:
            start_line = i
            in_import = True
            
            # Count bracket balance
            brackets += stripped.count('(') - stripped.count(')')
            brackets += stripped.count('{') - stripped.count('}')
            brackets += stripped.count('[') - stripped.count(']')
            
            # If this is a single-line import with no unmatched brackets, record it immediately
            if brackets == 0 and not stripped.endswith('\\'):
                imports.append((start_line, i))
                in_import = False
        
        # If currently inside an import, keep tracking bracket balance
        elif in_import:
            brackets += stripped.count('(') - stripped.count(')')
            brackets += stripped.count('{') - stripped.count('}')
            brackets += stripped.count('[') - stripped.count(']')
            
            # Check whether the multiline import ends on this line
            if brackets == 0 and not stripped.endswith('\\'):
                imports.append((start_line, i))
                in_import = False
    
    # Handle an import still open at end of file
    if in_import:
        imports.append((start_line, len(lines) - 1))
    
    return imports

def find_insertion_point(source_code):
    """
    Find a suitable code-insertion point while avoiding multiline imports.
    Returns the line number, where 0 means the beginning of the file.
    """
    if not source_code.strip():
        return 0
    
    imports = find_balanced_imports(source_code)
    
    if imports:
        # Insert after all imports have completed
        return imports[-1][1] + 1
    
    # If there are no imports, insert near the top of the file after header comments
    lines = source_code.splitlines()
    for i, line in enumerate(lines):
        if line.strip() and not line.strip().startswith('#'):
            return i
    
    # The file only contains comments or is empty
    return len(lines)

def find_main_block(source_code):
    """
    Find the `if __name__ == "__main__":` block.
    Returns the start line number and indentation level, or None if not found.
    """
    pattern = re.compile(r'^\s*if\s+__name__\s*==\s*[\'"]__main__[\'"]\s*:', re.MULTILINE)
    match = pattern.search(source_code)
    
    if match:
        lines = source_code.splitlines()
        line_number = source_code[:match.start()].count('\n')
        # Get the indentation level
        indent = len(lines[line_number]) - len(lines[line_number].lstrip())
        return (line_number, indent)
    
    return None

def find_connections_import(source_code):
    """Find the line number of the pymilvus connections import."""
    pattern = re.compile(r'(?:^|\s)from\s+pymilvus\s+import\s+(?:[^,\n]*,\s*)*connections', re.MULTILINE)
    match = pattern.search(source_code)
    
    if match:
        return source_code[:match.start()].count('\n')
    
    return None

def find_milvus_connect(source_code):
    """Find all pymilvus connections module connect statements."""
    # Find all connections.connect calls
    pattern = re.compile(r'(?:^|\s)connections\.connect\s*\(', re.MULTILINE)
    matches = list(pattern.finditer(source_code))
    
    if matches:
        # Compute the line number for each match
        connect_lines = []
        for match in matches:
            line_number = source_code[:match.start()].count('\n')
            connect_lines.append(line_number)
        return connect_lines
    
    return []

def find_milvus_client(source_code):
    """Find all MilvusClient initialization statements."""
    # Find all MilvusClient initializations
    pattern = re.compile(r'(?:^|\s)(?:\w+\s*=\s*)?MilvusClient\s*\(', re.MULTILINE)
    matches = list(pattern.finditer(source_code))
    
    if matches:
        # Compute the line number for each match
        client_lines = []
        for match in matches:
            line_number = source_code[:match.start()].count('\n')
            client_lines.append(line_number)
        return client_lines
    
    return []

def inject_grpc_capture(source_file, target_file):
    """Inject gRPC data-capture code into a Python file."""
    try:
        with open(source_file, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        # 1. Check whether pymilvus is used
        if not has_pymilvus_import(source_code):
            logger.info(f"[skip] {source_file} - pymilvus is not used")
            return False
        
        # 2. Check whether gRPC capture code has already been injected
        if has_capture_code(source_code):
            logger.info(f"[skip] {source_file} - gRPC capture code is already present")
            return False
        
        # 3. Find a suitable insertion point
        lines = source_code.splitlines()
        insert_line = find_insertion_point(source_code)
        
        # 3.1 Insert the gRPC capture code at the chosen insertion point
        new_lines = lines[:insert_line]
        # Ensure there is a blank line before the insertion point
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(GRPC_CAPTURE_HEADER.strip())
        # Ensure there is a blank line after the insertion point
        if insert_line < len(lines) and lines[insert_line].strip():
            new_lines.append("")
        new_lines.extend(lines[insert_line:])
        
        # Update the source code
        new_code = '\n'.join(new_lines)
        
        # 4. Detect and inject support for two API patterns: connections and MilvusClient
        # 4.1 First, check whether the connections module is used
        connect_lines = find_milvus_connect(new_code)
        if connect_lines:
            # Split the source code into lines again
            lines = new_code.splitlines()
            offset = 0  # Track line-number shifts caused by insertion
            
            for line_num in connect_lines:
                # Adjust the line number to account for prior insertions
                adjusted_line = line_num + offset
                
                # Find the full end position of the connect statement, including multiline calls
                bracket_count = lines[adjusted_line].count('(') - lines[adjusted_line].count(')')
                end_line = adjusted_line
                
                while bracket_count > 0 and end_line < len(lines) - 1:
                    end_line += 1
                    bracket_count += lines[end_line].count('(') - lines[end_line].count(')')
                
                # Insert interceptor code after the connect statement
                insert_pos = end_line + 1
                connection_code = GRPC_CAPTURE_CONNECT_CODE.strip().split('\n')
                
                # Ensure surrounding blank lines
                if insert_pos < len(lines) and lines[insert_pos].strip():
                    connection_code.append("")
                if insert_pos > 0 and lines[insert_pos-1].strip():
                    connection_code.insert(0, "")
                
                lines[insert_pos:insert_pos] = connection_code
                offset += len(connection_code)
            
            # Update the source code
            new_code = '\n'.join(lines)
            logger.info(f"[ok] Added interceptor code for the connections module")
        
        # 4.2 Check whether MilvusClient is used
        client_lines = find_milvus_client(new_code)
        if client_lines:
            # Split the source code into lines again
            lines = new_code.splitlines()
            
            # Insert interceptor code before the first MilvusClient initialization
            # Find the first MilvusClient initialization position
            first_client_line = min(client_lines)
            
            # Ensure there is a blank line before the insertion point
            client_code = GRPC_CAPTURE_MILVUSCLIENT_CODE.strip().split('\n')
            if first_client_line > 0 and lines[first_client_line-1].strip():
                client_code.insert(0, "")
            
            # Insert the MilvusClient interceptor code
            lines[first_client_line:first_client_line] = client_code
            
            # Update the source code
            new_code = '\n'.join(lines)
            logger.info(f"[ok] Added interceptor code for MilvusClient")
        
        # 5. Add log-saving code, preferably before the end of the main block, or at EOF if no main block exists
        main_info = find_main_block(new_code)
        lines = new_code.splitlines()
        
        if main_info:
            # If a main block exists, insert the save code before it ends
            main_line, main_indent = main_info
            
            # Find the end of the main block
            end_line = len(lines)
            for i in range(main_line + 1, len(lines)):
                # If a line has the same or lower indentation, the main block has ended
                if lines[i].strip() and len(lines[i]) - len(lines[i].lstrip()) <= main_indent:
                    end_line = i
                    break
            
            # Insert the log-save code at the end of the main block
            save_code = GRPC_CAPTURE_END_CODE.strip().split('\n')
            
            # Ensure surrounding blank lines
            if end_line < len(lines) and lines[end_line].strip():
                save_code.append("")
            if end_line > 0 and lines[end_line-1].strip():
                save_code.insert(0, "")
            
            # Indent the save code
            indented_save_code = []
            indent_str = ' ' * (main_indent + 4)  # Indent one extra level (4 spaces)
            for line in save_code:
                indented_save_code.append(indent_str + line if line.strip() else line)
            
            lines[end_line:end_line] = indented_save_code
        else:
            # If there is no main block, append the save code at the end of the file
            end_line = len(lines)
            save_code = GRPC_CAPTURE_END_CODE.strip().split('\n')
            
            # Ensure surrounding blank lines
            if end_line > 0 and lines[end_line-1].strip():
                save_code.insert(0, "")
            
            # Append the code without indentation
            lines.extend(save_code)
        
        # Update the source code
        new_code = '\n'.join(lines)
        
        # 6. Create the target directory
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        
        # 7. Write the new file
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(new_code)
        
        logger.info(f"[ok] Created a copy with gRPC capture enabled: {target_file}")
        return True
    
    except Exception as e:
        logger.error(f"[error] Failed to process file {source_file}: {e}")
        logger.debug(traceback.format_exc())
        return False

def process_directory(source_dir, target_dir):
    """Process an entire directory and create copies of Python files with gRPC capture enabled."""
    # Collect all Python files
    py_files = list(Path(source_dir).glob("**/*.py"))
    
    # Counters
    total = len(py_files)
    success = 0
    
    for source_file in py_files:
        # Compute the target file path
        rel_path = source_file.relative_to(source_dir)
        target_file = Path(target_dir) / rel_path
        
        # Inject gRPC capture code
        if inject_grpc_capture(str(source_file), str(target_file)):
            success += 1
    
    logger.info(f"Processing complete. Created {success} copies with gRPC capture enabled")
    return success

def main():
    """Run the CLI entry point."""
    parser = argparse.ArgumentParser(description='gRPC request capture code injection tool')
    parser.add_argument('--src', required=True, help='Source code directory')
    parser.add_argument('--dest', required=True, help='Output directory')
    
    args = parser.parse_args()
    
    # Process the entire directory
    process_directory(args.src, args.dest)

if __name__ == "__main__":
    main()
