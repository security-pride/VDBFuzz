#!/usr/bin/env python3

from pathlib import Path

from setuptools import find_packages, setup


ROOT_DIR = Path(__file__).resolve().parent
README = ROOT_DIR / "README.md"


setup(
    name="vdbfuzz",
    version="0.1.0",
    description="Fuzzing toolkit for vector databases",
    long_description=README.read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="VDB Fuzzer Team",
    packages=find_packages(include=["vdbfuzz", "vdbfuzz.*"]),
    include_package_data=True,
    package_data={
        "vdbfuzz": ["weaviate_keywords.json", "getcov/*.sh"],
        "vdbfuzz.keywords": ["*.json"],
    },
    install_requires=[
        "requests>=2.31,<3",
    ],
    extras_require={
        "capture": [
            "httpx>=0.27,<1",
            "pytest>=7,<9",
            "PyYAML>=6,<7",
        ],
        "milvus-grpc": [
            "grpcio>=1.50,<2",
            "protobuf>=4.21,<6",
            "tqdm>=4.65,<5",
            "pymilvus>=2.5,<3",
            "numpy>=1.24,<3",
            "colorama>=0.4.6,<1",
            "pytz>=2023.3,<2026",
        ],
        "weaviate": [
            "weaviate-client>=4,<5",
        ],
        "dev": [
            "httpx>=0.27,<1",
            "pytest>=7,<9",
            "PyYAML>=6,<7",
            "weaviate-client>=4,<5",
            "grpcio>=1.50,<2",
            "protobuf>=4.21,<6",
            "tqdm>=4.65,<5",
            "pymilvus>=2.5,<3",
            "numpy>=1.24,<3",
            "colorama>=0.4.6,<1",
            "pytz>=2023.3,<2026",
        ],
    },
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "vdbfuzz-generator=vdbfuzz.generator:main",
            "vdbfuzz-run=vdbfuzz.run:main",
            "vdbfuzz-grpc-run=vdbfuzz.grpcfuzz.run_fuzzing:main",
            "vdbfuzz-grpc-replay=vdbfuzz.grpcfuzz.replay:main",
            "vdbfuzz-grpc-convert=vdbfuzz.grpcfuzz.convert_requests:main",
            "vdbfuzz-grpc-merge=vdbfuzz.grpcfuzz.merge_requests:main",
            "vdbfuzz-grpc-inject=vdbfuzz.grpcfuzz.inject_grpc_capture_v2:main",
        ],
    },
)
