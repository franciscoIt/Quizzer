"""
Loaders package for the quiz app.

Expose manager APIs that return normalized questions:
- load_from_files
- load_from_folder

Also keep format-specific modules available if needed.
"""

from .manager import load_from_files, load_from_folder
from . import json_loader, csv_loader

__all__ = [
    "load_from_files",
    "load_from_folder",
    "json_loader",
    "csv_loader",
]
