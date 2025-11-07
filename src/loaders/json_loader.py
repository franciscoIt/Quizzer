"""
JSON loader for quiz app

Provides functions to load question lists from uploaded file objects or from local
folders containing JSON files. It implements robust detection of nested structures
such as `pageProps.questions` and returns a flat list of question dicts.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _find_questions_in_obj(obj: Any) -> Optional[List[Dict[str, Any]]]:
    """Recursively search for a list of question dicts in a JSON-like object.
    Returns the first list found, or None.
    """
    if isinstance(obj, dict):
        if 'questions' in obj and isinstance(obj['questions'], list):
            return obj['questions']
        if 'pageProps' in obj and isinstance(obj['pageProps'], dict) and 'questions' in obj['pageProps']:
            return obj['pageProps']['questions']
        for v in obj.values():
            res = _find_questions_in_obj(v)
            if res:
                return res
    elif isinstance(obj, list):
        if len(obj) > 0 and isinstance(obj[0], dict) and ('question_text' in obj[0] or 'choices' in obj[0]):
            return obj
        for item in obj:
            res = _find_questions_in_obj(item)
            if res:
                return res
    return None


def load_from_files(files) -> List[Dict[str, Any]]:
    """Parse uploaded file-like objects (as returned by Streamlit file_uploader).

    Returns a flat list of question dicts.
    """
    questions: List[Dict[str, Any]] = []
    for uploaded in files:
        try:
            raw = uploaded.read()
            content = raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)
            data = json.loads(content)
        except Exception:
            # Let the caller handle logging / user notification in the UI layer.
            continue

        found = _find_questions_in_obj(data)
        if found:
            questions.extend(found)
        elif isinstance(data, list):
            questions.extend(data)
        elif isinstance(data, dict):
            questions.append(data)
    return questions


def load_from_folder(folder_path: str) -> List[Dict[str, Any]]:
    """Load all JSON files from a local folder recursively and return a flat list of questions."""
    p = Path(folder_path)
    questions: List[Dict[str, Any]] = []
    if not p.exists() or not p.is_dir():
        return questions

    for f in p.glob('**/*.json'):
        try:
            text = f.read_text(encoding='utf-8')
            data = json.loads(text)
        except Exception:
            continue
        found = _find_questions_in_obj(data)
        if found:
            questions.extend(found)
        elif isinstance(data, list):
            questions.extend(data)
        elif isinstance(data, dict):
            questions.append(data)
    return questions
