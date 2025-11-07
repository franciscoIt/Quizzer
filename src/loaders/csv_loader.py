"""
CSV loader for quiz app

Provides functions to load question lists from uploaded CSV files or from local
folders containing CSV files. It expects files that follow (approximately) the
same structure as the exported quiz CSVs (flexible column sets are allowed).

Behavior:
- Accepts flexible column sets.
- Parses comma-separated 'correct_answer' fields into lists.
- Returns a flat list of question dicts, one per row.
"""

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import io


def _parse_correct_answers(value: Optional[str]) -> List[str]:
    """Split a comma-separated correct_answer field into a clean list."""
    if not value:
        return []
    return [v.strip().upper() for v in str(value).split(",") if v.strip()]


def load_from_files(files) -> List[Dict[str, Any]]:
    """
    Load questions from uploaded file-like objects (as from Streamlit's file_uploader).
    Returns a list of dictionaries (one per row).
    """
    questions: List[Dict[str, Any]] = []

    for uploaded in files:
        try:
            raw = uploaded.read()
            content = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            reader = csv.DictReader(io.StringIO(content))
        except Exception:
            continue  # skip unreadable files

        for row in reader:
            # normalize keys and strip values
            row = { (k.strip() if k else k): (v.strip() if isinstance(v, str) else v) for k, v in row.items() }
            # parse correct_answer into list
            row["correct_answer"] = _parse_correct_answers(row.get("correct_answer"))
            questions.append(row)

    return questions


def load_from_folder(folder_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """
    Load all CSV files from a local folder recursively and return a flat list of question dicts.
    """
    p = Path(folder_path)
    questions: List[Dict[str, Any]] = []
    if not p.exists() or not p.is_dir():
        return questions

    for f in p.glob("**/*.csv"):
        try:
            text = f.read_text(encoding="utf-8")
            reader = csv.DictReader(io.StringIO(text))
        except Exception:
            continue

        for row in reader:
            row = { (k.strip() if k else k): (v.strip() if isinstance(v, str) else v) for k, v in row.items() }
            row["correct_answer"] = _parse_correct_answers(row.get("correct_answer"))
            questions.append(row)

    return questions
