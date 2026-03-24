#!/usr/bin/env python3
"""
Requests Interceptor - For capturing and logging requests HTTP request/response data
"""
import json
import os
import time
from typing import Any, Callable, Dict, List, Optional, Union

# requests must be imported
import requests
from requests import Request, Response, Session


class RequestsInterceptor:
    """Utility class for intercepting requests HTTP requests and responses"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls, output_dir: str = None) -> 'RequestsInterceptor':
        """Get singleton instance of interceptor"""
        if cls._instance is None:
            cls._instance = RequestsInterceptor(output_dir)
        return cls._instance
    
    def __init__(self, output_dir: str = None):
        """
        Initialize requests interceptor
        
        Args:
            output_dir: Output directory, if None, uses http_logs in the current directory
        """
        self.output_dir = output_dir or os.path.join(os.getcwd(), "http_logs")
        self.requests: List[Dict[str, Any]] = []
        self.original_methods = {}
        self.debug_mode = True  # Enable debug mode
        self.initialized = False
        self.test_name = None
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
    
    def set_test_name(self, test_name: str) -> None:
        """Set current test name"""
        # If there are previous request records, try to save them first
        if self.requests and len(self.requests) > 0:
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
        """Save request logs to file"""
        if not self.requests:
            print("No request records to save")
            return ""
            
        # Print actual request count verification
        if self.debug_mode and len(self.requests) > 0:
            print(f"[Interceptor-Save] Actually saved {len(self.requests)} request records")
        
        timestamp = int(time.time())
        test_id = self.test_name or "unknown_test"
        filename = f"{test_id}_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        # Save request data as JSON file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                "test_name": self.test_name,
                "timestamp": timestamp,
                "requests": self.requests,
            }, f, indent=2, default=str)
        
        print(f"HTTP logs saved to: {filepath}")
        # Keep the requests in memory to allow capture across parameterized tests
        # self.requests = []
        return filepath
    
    def _log_request(self, method: str, url: str, headers: Dict = None, data: Any = None, params: Dict = None) -> Dict:
        """Log HTTP request"""
        print(f"[DEBUG] Intercepting request: {method} {url}")
        request_data = {
            "method": method,
            "url": str(url),
            "headers": dict(headers) if headers else {},
            "timestamp": time.time(),
        }
        
        # Try to log request parameters
        if params:
            request_data["params"] = self._prepare_data_for_json(params)
            
        # Try to log request body
        if data:
            try:
                # Try to parse JSON string
                if isinstance(data, str) and data.strip().startswith('{'):
                    try:
                        request_data["content"] = json.loads(data)
                    except json.JSONDecodeError:
                        request_data["content"] = data
                else:
                    request_data["content"] = self._prepare_data_for_json(data)
            except Exception as e:
                request_data["content"] = f"<failed to parse content: {str(e)}>"

        self.requests.append(request_data)
        return request_data
    
    def _log_response(self, response: Response, request_entry: Dict) -> None:
        """Log HTTP response"""
        response_data = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "elapsed_ms": response.elapsed.total_seconds() * 1000 if hasattr(response, "elapsed") else None,
            "timestamp": time.time(),
        }
        
        # Try to log response content
        try:
            # Try to parse as JSON
            content = response.content
            if content and b'{' in content and b'}' in content:
                try:
                    content_str = content.decode('utf-8')
                    response_data["content"] = json.loads(content_str)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    response_data["content"] = self._prepare_data_for_json(content)
            else:
                response_data["content"] = self._prepare_data_for_json(content)
        except Exception as e:
            response_data["content"] = f"<failed to parse response content: {str(e)}>"

        request_entry["response"] = response_data
        print(f"[DEBUG] Intercepted response: {response.status_code} for {response.request.method} {response.url}")
    
    def install(self) -> None:
        """Install the interceptor"""
        if self.initialized:
            return
        
        print("[DEBUG] Installing Requests interceptor")
        print(f"[DEBUG] Original requests module id: {id(requests)}")
        print(f"[DEBUG] Original requests.get id: {id(requests.get)}")
        print(f"[DEBUG] Original requests.post id: {id(requests.post)}")
        
        # Store original methods before patching
        self.original_methods = {
            "get": requests.get,
            "post": requests.post,
            "put": requests.put,
            "delete": requests.delete,
            "patch": requests.patch,
            "head": requests.head,
            "options": requests.options,
        }
        
        # Reference to interceptor for use in patched methods
        interceptor = self
        
        # Patch the get method
        def patched_get(url, **kwargs):
            print(f"[DEBUG] patched_get called for URL: {url}")
            # Log the request
            request_entry = interceptor._log_request(
                method="GET", 
                url=url, 
                headers=kwargs.get('headers'),
                data=kwargs.get('data'),
                params=kwargs.get('params')
            )
            
            # Call original method
            print(f"[DEBUG] Calling original get method, id: {id(interceptor.original_methods['get'])}")
            response = interceptor.original_methods["get"](url, **kwargs)
            
            # Log the response
            interceptor._log_response(response, request_entry)
            
            return response
        
        # Patch the post method
        def patched_post(url, **kwargs):
            print(f"[DEBUG] patched_post called for URL: {url}")
            # Log the request
            request_entry = interceptor._log_request(
                method="POST",
                url=url,
                headers=kwargs.get('headers'),
                data=kwargs.get('data') or kwargs.get('json')
            )
            
            # Call original method
            print(f"[DEBUG] Calling original post method, id: {id(interceptor.original_methods['post'])}")
            response = interceptor.original_methods["post"](url, **kwargs)
            
            # Log the response
            interceptor._log_response(response, request_entry)
            
            return response
        
        # Patch the put method
        def patched_put(url, **kwargs):
            # Log the request
            request_entry = interceptor._log_request(
                method="PUT",
                url=url,
                headers=kwargs.get('headers'),
                data=kwargs.get('data') or kwargs.get('json')
            )
            
            # Call original method
            response = interceptor.original_methods["put"](url, **kwargs)
            
            # Log the response
            interceptor._log_response(response, request_entry)
            
            return response
        
        # Patch the delete method
        def patched_delete(url, **kwargs):
            # Log the request
            request_entry = interceptor._log_request(
                method="DELETE",
                url=url,
                headers=kwargs.get('headers'),
                data=kwargs.get('data') or kwargs.get('json')
            )
            
            # Call original method
            response = interceptor.original_methods["delete"](url, **kwargs)
            
            # Log the response
            interceptor._log_response(response, request_entry)
            
            return response
        
        # Replace the methods
        print(f"[DEBUG] Replacing requests.get with patched_get, id before: {id(requests.get)}")
        requests.get = patched_get
        print(f"[DEBUG] ID after patching: {id(requests.get)}")
        
        print(f"[DEBUG] Replacing requests.post with patched_post, id before: {id(requests.post)}")
        requests.post = patched_post
        print(f"[DEBUG] ID after patching: {id(requests.post)}")
        
        requests.put = patched_put
        requests.delete = patched_delete
        
        self.initialized = True
        print("Requests interceptor installed, now capturing all requests HTTP traffic")
    
    def uninstall(self) -> None:
        """Uninstall the interceptor"""
        if not self.initialized:
            return
        
        # Restore original methods
        if hasattr(self, 'original_methods'):
            for method_name, original_method in self.original_methods.items():
                setattr(requests, method_name, original_method)
        
        self.initialized = False
        self.original_methods = {}
        print("Requests interceptor uninstalled")


def get_interceptor(output_dir: str = None) -> RequestsInterceptor:
    """
    Get Requests interceptor
    
    Args:
        output_dir: Log output directory
        
    Returns:
        Interceptor instance
    """
    return RequestsInterceptor.get_instance(output_dir)


# Provide simple context manager for use in tests
class RequestsCapture:
    def __init__(self, test_name: str = None, output_dir: str = None):
        self.test_name = test_name
        self.interceptor = get_interceptor(output_dir)
    
    def __enter__(self):
        self.interceptor.set_test_name(self.test_name)
        self.interceptor.install()
        return self.interceptor
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Print debug info to help identify issues
        if self.interceptor.debug_mode:
            print(f"[Interceptor-Exit] There are {len(self.interceptor.requests)} request records before exit")
            
        # Capture request copy first, to prevent being cleared during saving
        if self.interceptor.requests and len(self.interceptor.requests) > 0:
            self.interceptor.save_logs()
        else:
            print("No request records to save when interceptor exits")
            
        self.interceptor.uninstall()


if __name__ == "__main__":
    # Simple example
    def test_example():
        with RequestsCapture(test_name="example_requests_test") as capture:
            try:
                # Test various HTTP methods
                print("\nTest 1: Using requests.get")
                response = requests.get("https://httpbin.org/get?param1=value1")
                print(f"requests.get status code: {response.status_code}")
                
                print("\nTest 2: Using requests.post")
                response = requests.post(
                    "https://httpbin.org/post",
                    json={"collection_name": "test_collection"}
                )
                print(f"requests.post status code: {response.status_code}")
                
                print("\nTest 3: Using requests.put")
                response = requests.put(
                    "https://httpbin.org/put",
                    json={"collection_name": "test_collection", "data": {"id": 1}}
                )
                print(f"requests.put status code: {response.status_code}")
                
                print(f"\nTotal captured requests: {len(capture.interceptor.requests)}")
            except Exception as e:
                print(f"Failed to send request: {e}")
    
    test_example()
