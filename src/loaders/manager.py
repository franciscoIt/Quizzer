"""
Loader manager for quiz app (routing + normalization)

This manager:
- Routes uploaded files (Streamlit-like file objects) to json_loader / csv_loader.
- Strictly classifies files by extension or JSON sniffing (unknown files are ignored).
- Normalizes the loaded question dicts into the app's canonical shape so callers
  don't need to know the file format.

Canonical shape (best-effort):
{
  "question_text": "...",       # display text
  "choices": {"A": "text", ...},# optional dict of single-letter keys
  "answer": ["A","C"],          # list of uppercase letters (may be empty)
  "question_id": "...",         # preserved if present
  "url": "...",                 # preserved if present
  ...                          # other fields preserved
}
"""

from pathlib import Path
import io
import json
from typing import Any, Dict, List, Union, Optional

from . import json_loader, csv_loader


def _make_buffer(name: str, data: bytes) -> io.BytesIO:
    b = io.BytesIO(data)
    # attach name attribute for compatibility with loaders / consumers
    try:
        b.name = name
    except Exception:
        pass
    b.seek(0)
    return b


def _is_json_bytes(data: bytes) -> bool:
    try:
        text = data.decode("utf-8")
        json.loads(text)
        return True
    except Exception:
        return False


def _parse_correct_answer_field(val: Any) -> List[str]:
    """
    Accepts string like "A,B" or list like ["A","B"] or None, returns uppercase letter list.
    """
    if not val:
        return []
    if isinstance(val, list):
        out = []
        for item in val:
            if isinstance(item, str):
                for part in item.split(','):
                    p = part.strip().upper()
                    if p:
                        out.append(p)
        return list(dict.fromkeys(out))  # preserve order, unique
    if isinstance(val, str):
        out = [p.strip().upper() for p in val.split(',') if p.strip()]
        return list(dict.fromkeys(out))
    # fallback
    return []


def _build_choices_from_row(row: Dict[str, Any], max_choices: int = 4) -> Dict[str, str]:
    """
    If `choices` already present and is a dict, return normalized form.
    Otherwise look for columns like 'choice_A', 'choice_B', ... up to max_choices.
    """
    ch = row.get('choices')
    if isinstance(ch, dict) and ch:
        normalized = {}
        for k, v in ch.items():
            kk = str(k).strip().upper()
            if len(kk) > 1:
                kk = kk[0]
            if isinstance(v, str):
                normalized[kk] = v
            else:
                normalized[kk] = str(v)
        return normalized

    choices = {}
    letters = [chr(ord('A') + i) for i in range(max_choices)]
    for letter in letters:
        k = f"choice_{letter}"
        if k in row and row.get(k) is not None:
            v = row.get(k)
            if isinstance(v, str) and v.strip():
                choices[letter] = v.strip()
            elif not isinstance(v, str) and v != "":
                choices[letter] = str(v)
    return choices


def _normalize_question(raw: Dict[str, Any], max_choices: int = 4) -> Dict[str, Any]:
    """
    Convert a raw question dict (from JSON or CSV loader) into canonical shape.
    This function does a best-effort mapping and preserves any extra keys.
    """
    q = dict(raw)  # shallow copy

    # 1) question text: prefer explicit keys
    if not q.get('question_text') and q.get('enunciate'):
        q['question_text'] = q.get('enunciate')
    elif not q.get('question_text') and q.get('text'):
        q['question_text'] = q.get('text')

    # 2) correct answer(s): map 'correct_answer' or existing 'answer' fields to 'answer' list
    if 'answer' not in q or not isinstance(q.get('answer'), list):
        if 'correct_answer' in q:
            q['answer'] = _parse_correct_answer_field(q.get('correct_answer'))
        elif 'answer_ET' in q:
            q['answer'] = _parse_correct_answer_field(q.get('answer_ET'))
        else:
            # if there is an 'answers_community' and it's a list of strings, try that
            if 'answers_community' in q and isinstance(q.get('answers_community'), list):
                # flatten strings into letters
                extracted = []
                for item in q.get('answers_community', []):
                    if isinstance(item, str):
                        for part in item.split(','):
                            p = part.strip().upper()
                            if p:
                                extracted.append(p)
                q['answer'] = list(dict.fromkeys(extracted))
            else:
                # leave as-is or set empty list
                if not isinstance(q.get('answer'), list):
                    q['answer'] = []

    # 3) choices: build dict(A..D) if not present
    if not isinstance(q.get('choices'), dict) or not q.get('choices'):
        choices = _build_choices_from_row(q, max_choices=max_choices)
        if choices:
            q['choices'] = choices

    # 4) Normalize 'answer' contents to uppercase single letters (keep only first char)
    if isinstance(q.get('answer'), list):
        norm_ans = []
        for a in q.get('answer', []):
            if isinstance(a, str) and a.strip():
                letter = a.strip().upper()
                # if value is like "A)" or "A. Option", take first A-Z char
                # find first letter A-Z
                found = None
                for ch in letter:
                    if 'A' <= ch <= 'Z':
                        found = ch
                        break
                if found:
                    if found not in norm_ans:
                        norm_ans.append(found)
        q['answer'] = norm_ans
    else:
        q['answer'] = []

    # 5) ensure choices keys are uppercase single letters
    if isinstance(q.get('choices'), dict):
        normalized_choices = {}
        for k, v in q['choices'].items():
            kk = str(k).strip().upper()
            if len(kk) > 1:
                kk = kk[0]
            normalized_choices[kk] = v
        q['choices'] = normalized_choices

    return q


def load_from_files(files, max_choices: int = 4) -> List[Dict[str, Any]]:
    """
    Read uploaded file-like objects, route them to appropriate loader and
    return a list of normalized question dicts ready for the app.
    """
    json_objs: List[io.BytesIO] = []
    csv_objs: List[io.BytesIO] = []

    for uploaded in files:
        try:
            raw = uploaded.read()
        except Exception:
            continue

        raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw or b""
        name = getattr(uploaded, "name", "") or ""
        ext = Path(name).suffix.lower()

        if ext == ".json":
            json_objs.append(_make_buffer(name, raw_bytes))
        elif ext == ".csv":
            csv_objs.append(_make_buffer(name, raw_bytes))
        elif _is_json_bytes(raw_bytes):
            json_objs.append(_make_buffer(name or "unknown.json", raw_bytes))
        else:
            # ignore unknown/unrecognized file types
            continue

    results: List[Dict[str, Any]] = []

    if json_objs:
        raw_qs = json_loader.load_from_files(json_objs)
        for raw_q in raw_qs:
            results.append(_normalize_question(raw_q, max_choices=max_choices))

    if csv_objs:
        raw_qs = csv_loader.load_from_files(csv_objs)
        for raw_q in raw_qs:
            results.append(_normalize_question(raw_q, max_choices=max_choices))

    return results


def load_from_folder(folder_path: Union[str, Path], max_choices: int = 4) -> List[Dict[str, Any]]:
    """
    Recursively load .json and .csv files from a folder and return normalized question dicts.
    """
    p = Path(folder_path)
    results: List[Dict[str, Any]] = []
    if not p.exists() or not p.is_dir():
        return results

    # get raw lists from sub-loaders
    raw_json = json_loader.load_from_folder(folder_path)
    raw_csv = csv_loader.load_from_folder(folder_path)

    for raw_q in raw_json:
        results.append(_normalize_question(raw_q, max_choices=max_choices))
    for raw_q in raw_csv:
        results.append(_normalize_question(raw_q, max_choices=max_choices))

    return results
