"""
Milvus gRPC fuzzing helpers for vdbfuzz.
"""

__version__ = "0.1.0"
__author__ = "Vector Database Fuzzing Team"

__all__ = ["MilvusFuzzer"]


def __getattr__(name):
    if name == "MilvusFuzzer":
        from .fuzzer_new import MilvusFuzzer
        return MilvusFuzzer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
