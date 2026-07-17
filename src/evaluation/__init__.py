"""Evaluation utilities for the frozen V8 benchmark suite."""

from .dataset import EXPECTED_CASE_COUNTS, validate_bundle

__all__ = ["EXPECTED_CASE_COUNTS", "validate_bundle"]
