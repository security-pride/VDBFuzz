#!/usr/bin/env python3
"""
HTTP interceptor used to capture and record httpx request/response data
"""
import json
import os
import time
from typing import Any, Callable, Dict, List, Optional

# httpx is required
import httpx
from httpx import Request, Response


class HttpInterceptor:
    """Utility class to intercept httpx requests and responses"""
    
    def __init__(self, output_dir: str = None):
        """
        Initialize the httpx interceptor
        
        Args:
            output_dir: output directory; defaults to ./http_logs
        """
        self.output_dir = output_dir or os.path.join(os.getcwd(), "http_logs")
        self.requests: List[Dict[str, Any]] = []
        self.original_transport = None
        self.original_client = None
        self.original_send = None
        self.debug_mode = True  # enable debug mode
        self.initialized = False
        self.test_name = None
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
    
    def set_test_name(self, test_name: str) -> None:
        """Set current test name"""
        # If previous requests exist with content, save them first
        if hasattr(self, 'test_name') and self.test_name and hasattr(self, 'requests') and len(self.requests) > 0:
            self.save_logs()
            
        self.test_name = test_name
        # Initialize empty request list
        self.requests = []
    
    def _prepare_data_for_json(self, data: Any) -> Any:
        """Prepare data for JSON serialization"""
        if isinstance(data, bytes):
            try:
                return data.decode('utf-8')
            except UnicodeDecodeError:
                return f"<binary data of length {len(data)}>"
        elif isinstance(data, dict):
            return {str(k): self._prepare_data_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._prepare_data_for_json(item) for item in data]
        return data
    
    def save_logs(self) -> str:
        """Save captured request logs to file"""
        if not hasattr(self, 'requests') or not self.requests:
            print("No request records to save")
            return ""
            
        # Print actual request count for verification
        if self.debug_mode and len(self.requests) > 0:
            print(f"[Interceptor-Save] Saving {len(self.requests)} request records")
        
        timestamp = int(time.time())
        test_id = self.test_name or "unknown_test"
        filename = f"{test_id}_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        # Save request data to JSON file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                "test_name": self.test_name,
                "timestamp": timestamp,
                "requests": self.requests
            }, f, indent=2, default=str)
        
        print(f"Saved HTTP logs to: {filepath}")
        return filepath
    
    def _log_request(self, request: Request) -> None:
        """Record HTTP request"""
        request_data = {
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "timestamp": time.time(),
        }
        
        # Try to record request body
        if request.content:
            try:
                # Attempt to parse as JSON
                if b'{' in request.content and b'}' in request.content:
                    try:
                        content_str = request.content.decode('utf-8')
                        request_data["content"] = json.loads(content_str)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        request_data["content"] = f"<binary data of length {len(request.content)}>"
                else:
                    request_data["content"] = self._prepare_data_for_json(request.content)
            except Exception as e:
                request_data["content"] = f"<error parsing content: {str(e)}>"
        
        if self.debug_mode:
            print(f"[Interceptor-Log] Request: {request.method} {request.url}")
            
        self.current_request = request_data
    
    def _log_response(self, response: Response) -> None:
        """Record HTTP response"""
        if not hasattr(self, 'current_request'):
            # If no current request, create a placeholder
            self.current_request = {
                "method": "UNKNOWN",
                "url": str(response.url),
                "timestamp": time.time(),
            }
        
        response_data = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "timestamp": time.time(),
        }
        
        # Try to record response body
        try:
            # Use .content instead of .read() to avoid consuming the stream
            if hasattr(response, 'content'):
                response_content = response.content
            else:
                response_content = response.read()
                
            # Attempt to parse as JSON
            if b'{' in response_content and b'}' in response_content:
                try:
                    content_str = response_content.decode('utf-8')
                    response_data["content"] = json.loads(content_str)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    response_data["content"] = f"<binary data of length {len(response_content)}>"
            else:
                response_data["content"] = self._prepare_data_for_json(response_content)
        except Exception as e:
            response_data["content"] = f"<error parsing content: {str(e)}>"
        
        # Attach response to the current request
        request_with_response = dict(self.current_request)
        request_with_response["response"] = response_data
        
        # Append to the request list
        self.requests.append(request_with_response)
        
        if self.debug_mode:
            print(f"[Interceptor-Log] Response: {response.status_code} for {self.current_request.get('method', 'UNKNOWN')} {self.current_request.get('url', 'UNKNOWN')}")
            print(f"[Interceptor-Log] Captured {len(self.requests)} request/response pairs")
        
        # Reset current request
        delattr(self, 'current_request')
    
    def install(self) -> None:
        """Install the interceptor"""
        if self.initialized:
            print("Interceptor already installed")
            return
        
        # Method 1: override HTTPTransport to intercept all requests/responses
        original_transport_for_app = httpx.HTTPTransport
        
        class InterceptingTransport(original_transport_for_app):
            # Class-level attributes
            interceptor = None
            debug_mode = False
            
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
            
            def handle_request(self, request):
                # Record request
                if InterceptingTransport.debug_mode:
                    print(f"[Interceptor-Transport] Captured {request.method} request: {request.url}")
                    
                try:
                    InterceptingTransport.interceptor._log_request(request)
                except Exception as e:
                    print(f"[Interceptor-Warning] Failed to log request: {e}")
                    
                # Process request
                response = super().handle_request(request)
                
                # Record response
                if InterceptingTransport.debug_mode:
                    print(f"[Interceptor-Transport] Captured response: {response.status_code}")
                    
                try:
                    InterceptingTransport.interceptor._log_response(response)
                except Exception as e:
                    print(f"[Interceptor-Warning] Failed to log response: {e}")
                    
                return response
        
        # Set class-level references
        InterceptingTransport.interceptor = self
        InterceptingTransport.debug_mode = self.debug_mode
        
        # Save original transport for later restoration
        self.original_transport = httpx.HTTPTransport
        
        # Replace transport
        httpx.HTTPTransport = InterceptingTransport
        
        # Method 2: patch httpx.Client.send to capture existing clients
        original_client = httpx.Client
        
        class InterceptingClient(original_client):
            # Class-level attributes
            interceptor = None
            debug_mode = False
            
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
            
            def send(self, request, *args, **kwargs):
                # Record request
                if InterceptingClient.debug_mode:
                    print(f"[Interceptor-Client] Captured {request.method} request: {request.url}")
                    
                try:
                    InterceptingClient.interceptor._log_request(request)
                except Exception as e:
                    print(f"[Interceptor-Warning] Failed to log request: {e}")
                    
                # Send request
                response = super().send(request, *args, **kwargs)
                
                # Record response
                if InterceptingClient.debug_mode:
                    print(f"[Interceptor-Client] Captured response: {response.status_code}")
                
                try:
                    InterceptingClient.interceptor._log_response(response)
                except Exception as e:
                    print(f"[Interceptor-Warning] Failed to log response: {e}")
                    
                return response
        
        # Store interceptor reference on the class
        InterceptingClient.interceptor = self
        InterceptingClient.debug_mode = self.debug_mode
        
        # Save original client for restoration
        self.original_client = httpx.Client
        
        # Replace client
        httpx.Client = InterceptingClient
        
        # Method 3: patch httpx.request function
        original_send = httpx.request
        interceptor_ref = self  # capture self via closure
        
        def patched_request(method, url, **kwargs):
            if interceptor_ref.debug_mode:
                print(f"[Interceptor-request] Captured {method} request: {url}")
            
            response = original_send(method, url, **kwargs)
            
            if interceptor_ref.debug_mode:
                print(f"[Interceptor-request] Captured response: {response.status_code}")
            
            try:
                # Build request object (not directly available here)
                request = httpx.Request(method, url)
                for k, v in kwargs.get('headers', {}).items():
                    request.headers[k] = v
                
                # Record request and response
                interceptor_ref._log_request(request)
                interceptor_ref._log_response(response)
            except Exception as e:
                print(f"[Interceptor-Warning] Failed to log request/response: {e}")
            
            return response
        
        # Save original method
        self.original_send = httpx.request
        
        # Replace with patched method
        httpx.request = patched_request
        
        self.initialized = True
        print("HTTP interceptor installed; capturing all httpx requests and responses")
    
    def uninstall(self) -> None:
        """Uninstall the interceptor"""
        if not self.initialized:
            return
        
        # Restore original transport
        if self.original_transport:
            httpx.HTTPTransport = self.original_transport
            self.original_transport = None
        
        # Restore original client
        if self.original_client:
            httpx.Client = self.original_client
            self.original_client = None
        
        # Restore original request method
        if self.original_send:
            httpx.request = self.original_send
            self.original_send = None
        
        self.initialized = False
        print("HTTP interceptor uninstalled")


def get_interceptor(output_dir: str = None) -> HttpInterceptor:
    """
    Get an HTTP interceptor
    
    Args:
        output_dir: log output directory
        
    Returns:
        interceptor instance
    """
    return HttpInterceptor(output_dir)


# Simple context manager for use in tests
class HttpCapture:
    def __init__(self, test_name: str = None, output_dir: str = None):
        self.test_name = test_name
        self.interceptor = get_interceptor(output_dir)
    
    def __enter__(self):
        self.interceptor.set_test_name(self.test_name)
        self.interceptor.install()
        return self.interceptor
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Print debug info to help identify issues
        if self.interceptor.debug_mode and hasattr(self.interceptor, 'requests'):
            print(f"[Interceptor-Exit] {len(self.interceptor.requests)} request records before exit")
            
        # Capture a copy before saving to avoid clearing during save
        if hasattr(self.interceptor, 'requests') and self.interceptor.requests:
            self.interceptor.save_logs()
        else:
            print("Warning: interceptor exited with no request records")
            
        self.interceptor.uninstall()


if __name__ == "__main__":
    # Simple example
    def test_example():
        with HttpCapture(test_name="example_test") as capture:
            try:
                # Method 1: use Client to send requests
                print("\nTest 1: httpx.Client GET")
                client = httpx.Client()
                response = client.get("https://httpbin.org/get")
                print(f"httpx Client status: {response.status_code}")
                
                # Method 2: use request function
                print("\nTest 2: httpx.request GET")
                response = httpx.request("GET", "https://httpbin.org/get")
                print(f"httpx request status: {response.status_code}")
                
                # Method 3: use shortcut method
                print("\nTest 3: httpx.get request")
                response = httpx.get("https://httpbin.org/get")
                print(f"httpx get status: {response.status_code}")
                
                print(f"\nTotal captured requests: {len(capture.interceptor.requests)}")
            except Exception as e:
                print(f"Failed to send request: {e}")
    
    test_example()
