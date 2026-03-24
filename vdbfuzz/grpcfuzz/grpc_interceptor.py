#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gRPC interceptor implementation used to capture Milvus gRPC requests
"""

import os
import json
import time
import logging
from google.protobuf import text_format
from pymilvus.grpc_gen import milvus_pb2

# Configure the logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class GrpcInterceptor:
    """gRPC request interceptor used to capture and record pymilvus gRPC traffic."""
    
    def __init__(self):
        """Initialize the interceptor."""
        self.requests = []
        self.log_file = None
        self.logger = logging.getLogger("GrpcInterceptor")
    
    def intercept_unary_unary(self, continuation, client_call_details, request):
        """Intercept unary gRPC calls."""
        try:
            # Record request metadata
            method = client_call_details.method
            # Try to serialize the request in text format
            request_str = text_format.MessageToString(request)
            
            # Create the request record
            request_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time())}"
            request_info = {
                "request_id": request_id,
                "method": method.decode('utf-8') if isinstance(method, bytes) else method,
                "timestamp": time.time(),
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S.%f"),
                "request": {"request_str": request_str}
            }
            
            # Forward the request and get the response
            response = continuation(client_call_details, request)
            
            # Record response metadata
            request_info["response"] = str(response)
            
            # Append the record to the request list
            self.requests.append(request_info)
            
            return response
        except Exception as e:
            self.logger.error(f"Error while intercepting request: {e}")
            # Still execute the original request when interception fails
            return continuation(client_call_details, request)
    
    def intercept_unary_stream(self, continuation, client_call_details, request):
        """Intercept unary-stream gRPC calls."""
        try:
            # Record request metadata
            method = client_call_details.method
            # Try to serialize the request in text format
            request_str = text_format.MessageToString(request)
            
            # Create the request record
            request_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time())}"
            request_info = {
                "request_id": request_id,
                "method": method.decode('utf-8') if isinstance(method, bytes) else method,
                "timestamp": time.time(),
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S.%f"),
                "request": {"request_str": request_str}
            }
            
            # Forward the request and get the response
            response_iterator = continuation(client_call_details, request)
            
            # Record response metadata(stream reference only)
            request_info["response"] = str(response_iterator)
            
            # Append the record to the request list
            self.requests.append(request_info)
            
            return response_iterator
        except Exception as e:
            self.logger.error(f"Error while intercepting streaming request: {e}")
            # Still execute the original request when interception fails
            return continuation(client_call_details, request)

    def intercept_stream_unary(self, continuation, client_call_details, request_iterator):
        """Intercept client-streaming gRPC calls."""
        # Because streaming request payloads are difficult to capture, only call metadata is recorded here
        try:
            method = client_call_details.method
            request_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time())}"
            request_info = {
                "request_id": request_id,
                "method": method.decode('utf-8') if isinstance(method, bytes) else method,
                "timestamp": time.time(),
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S.%f"),
                "request": {"request_str": "Stream request - content not captured"}
            }
            
            # Forward the request and get the response
            response = continuation(client_call_details, request_iterator)
            
            # Record response metadata
            request_info["response"] = str(response)
            
            # Append the record to the request list
            self.requests.append(request_info)
            
            return response
        except Exception as e:
            self.logger.error(f"Error while intercepting client-streaming request: {e}")
            return continuation(client_call_details, request_iterator)

    def intercept_stream_stream(self, continuation, client_call_details, request_iterator):
        """Intercept bidirectional streaming gRPC calls."""
        # Because streaming request and response payloads are difficult to capture, only call metadata is recorded here
        try:
            method = client_call_details.method
            request_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time())}"
            request_info = {
                "request_id": request_id,
                "method": method.decode('utf-8') if isinstance(method, bytes) else method,
                "timestamp": time.time(),
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S.%f"),
                "request": {"request_str": "Bidirectional stream - content not captured"}
            }
            
            # Forward the request and get the responseiterator
            response_iterator = continuation(client_call_details, request_iterator)
            
            # Record response metadata
            request_info["response"] = str(response_iterator)
            
            # Append the record to the request list
            self.requests.append(request_info)
            
            return response_iterator
        except Exception as e:
            self.logger.error(f"Error while intercepting bidirectional streaming request: {e}")
            return continuation(client_call_details, request_iterator)
    
    def set_log_file(self, log_file_path):
        """Set the log file path."""
        self.log_file = log_file_path
        self.logger.info(f"Set log file path: {log_file_path}")
        
        # Create the directory containing the log file
        log_dir = os.path.dirname(log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            self.logger.info(f"Created log directory: {log_dir}")
    
    def save_captured_requests(self):
        """Save captured requests to the log file."""
        if not self.log_file:
            self.logger.warning("The log file path is not set; captured requests cannot be saved")
            return False
        
        if not self.requests:
            self.logger.warning("No requests were captured; nothing to save")
            return False
        
        try:
            # Ensure the log directory exists
            log_dir = os.path.dirname(self.log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            
            # Assemble the log payload
            log_data = {
                "timestamp": time.time(),
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "requests": self.requests
            }
            
            # Write the log file
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"Successfully saved {len(self.requests)} captured gRPC requests to: {self.log_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error while saving captured requests: {e}")
            return False
    
    def install_channel_interceptor(self, channel):
        """Install the interceptor on a gRPC channel."""
        try:
            from grpc import intercept_channel
            
            # Install the interceptor on the channel
            intercepted_channel = intercept_channel(channel, self)
            self.logger.info("Successfully installed the gRPC interceptor on the channel")
            
            return intercepted_channel
        except ImportError as e:
            self.logger.error(f"grpc.intercept_channel is unavailable: {e}")
            return channel
        except Exception as e:
            self.logger.error(f"Failed to install interceptor: {e}")
            return channel
