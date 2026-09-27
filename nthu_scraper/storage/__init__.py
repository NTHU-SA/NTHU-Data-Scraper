"""Small, strict JSON storage primitives."""

from .json_store import read_json, read_json_optional, write_json_atomic

__all__ = ["read_json", "read_json_optional", "write_json_atomic"]
