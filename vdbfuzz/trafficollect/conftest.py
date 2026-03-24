import pytest
import yaml
import os
import json

try:
    from .requests_interceptor import RequestsCapture, get_interceptor
except ImportError:
    from requests_interceptor import RequestsCapture, get_interceptor


def pytest_addoption(parser):
    parser.addoption("--endpoint", action="store", default="http://172.17.0.11:23210", help="endpoint")
    parser.addoption("--token", action="store", default="root:Milvus", help="token")
    parser.addoption("--http-capture", action="store_true", default=False, help="Capture HTTP traffic during tests")
    parser.addoption("--http-logs-dir", action="store", default="./http_logs", help="Directory to save HTTP logs")


@pytest.fixture
def endpoint(request):
    return request.config.getoption("--endpoint")


@pytest.fixture
def token(request):
    return request.config.getoption("--token")


# Global interceptor instance
_interceptor = None


def pytest_configure(config):
    """Configure pytest - set up HTTP traffic capture if enabled"""
    global _interceptor
    
    if config.getoption("--http-capture"):
        output_dir = config.getoption("--http-logs-dir")
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"\n[HTTP Capture] Initializing HTTP traffic capture. Logs will be saved to {output_dir}")
        _interceptor = get_interceptor(output_dir)


def pytest_runtest_setup(item):
    """Set up test - activate HTTP traffic capture"""
    global _interceptor
    
    if item.config.getoption("--http-capture") and _interceptor:
        # Extract test name for the log file
        test_name = f"{item.cls.__name__}_{item.name}" if hasattr(item, "cls") else item.name
        _interceptor.set_test_name(test_name)
        _interceptor.install()
        print(f"[HTTP Capture] Starting capture for test: {test_name}")


def pytest_runtest_teardown(item):
    """Tear down test - save HTTP traffic logs"""
    global _interceptor
    
    if item.config.getoption("--http-capture") and _interceptor and _interceptor.initialized:
        print(f"[HTTP Capture] Requests captured: {len(_interceptor.requests)}")
        if _interceptor.requests:
            log_file = _interceptor.save_logs()
            print(f"[HTTP Capture] Saved HTTP traffic to: {log_file}")
