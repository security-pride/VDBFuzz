#!/usr/bin/env python3

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"


def load_env_file() -> dict:
    values = {}
    if not ENV_FILE.exists():
        return values

    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def get_port(name: str, default: str, env_values: dict) -> str:
    return os.environ.get(name) or env_values.get(name) or default


def build_targets() -> dict:
    env_values = load_env_file()
    qdrant_http_port = get_port("QDRANT_HTTP_PORT", "6333", env_values)
    weaviate_http_port = get_port("WEAVIATE_HTTP_PORT", "18080", env_values)
    milvus_http_port = get_port("MILVUS_HTTP_PORT", "9091", env_values)

    return {
        "qdrant": f"http://127.0.0.1:{qdrant_http_port}/",
        "weaviate": f"http://127.0.0.1:{weaviate_http_port}/v1/.well-known/ready",
        "milvus": f"http://127.0.0.1:{milvus_http_port}/healthz",
    }


def check_url(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status in (200, 404, 503)
    except urllib.error.HTTPError as exc:
        return exc.code in (200, 404, 503)
    except Exception:
        return False


def wait_for_target(name: str, url: str, timeout: int, interval: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check_url(url):
            print(f"[ok] {name}: {url}")
            return True
        time.sleep(interval)
    print(f"[fail] {name}: {url}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait until local VDB services respond")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout in seconds per service")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds")
    args = parser.parse_args()

    success = True
    for name, url in build_targets().items():
        success = wait_for_target(name, url, args.timeout, args.interval) and success

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
