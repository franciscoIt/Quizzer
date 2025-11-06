"""
Streamlit Quiz Frontend — with CSV download

This file is the same single-file app but adds the ability to download quiz results as a CSV.
It detects nested `pageProps.questions` structures and supports both modes (reveal at end / reveal on demand).

Run with: streamlit run streamlit_quiz_frontend_with_csv.py
"""

import streamlit as st
import json
import re
import pandas as pd
from pathlib import Path
from typing import Any, Dict, List, Optional

st.set_page_config(page_title="Quiz app", layout="wide")

# ---------------- Helpers ----------------

def find_questions_in_obj(obj: Any) -> Optional[List[Dict[str, Any]]]:
    """Recursively search for a list of question dicts in a JSON-like object.
    Returns the first list found, or None."""
    if isinstance(obj, dict):
        # direct keys
        if 'questions' in obj and isinstance(obj['questions'], list):
            return obj['questions']
        if 'pageProps' in obj and isinstance(obj['pageProps'], dict) and 'questions' in obj['pageProps']:
            return obj['pageProps']['questions']
        # search values
        for v in obj.values():
            res = find_questions_in_obj(v)
            if res:
                return res
    elif isinstance(obj, list):
        # heuristics: if list of dicts that look like questions
        if len(obj) > 0 and isinstance(obj[0], dict) and ('question_text' in obj[0] or 'choices' in obj[0]):
            return obj
        for item in obj:
            res = find_questions_in_obj(item)
            if res:
                return res
    return None


def parse_uploaded_jsons(files) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    for uploaded in files:
        try:
            raw = uploaded.read()
            # uploaded can be binary; try decode
            if isinstance(raw, bytes):
                content = raw.decode('utf-8')
            else:
                content = str(raw)
            data = json.loads(content)
        except Exception as e:
            st.error(f"Could not read {getattr(uploaded,'name', 'uploaded file')}: {e}")
            continue

        found = find_questions_in_obj(data)
        if found:
            questions.extend(found)
        elif isinstance(data, list):
            questions.extend(data)
        elif isinstance(data, dict):
            # maybe it's a single question dict
            questions.append(data)
        else:
            st.warning(f"Uploaded file {getattr(uploaded,'name', 'file')} had unexpected structure and was skipped.")
    return questions


def load_from_local_folder(folder_path: str) -> List[Dict[str, Any]]:
    p = Path(folder_path)
    questions: List[Dict[str, Any]] = []
    if not p.exists() or not p.is_dir():
        st.error("Provided folder path does not exist or is not a folder.")
        return questions

    for f in p.glob('**/*.json'):
        try:
            text = f.read_text(encoding='utf-8')
            data = json.loads(text)
        except Exception as e:
            st.warning(f"Could not read {f.name}: {e}")
            continue
        found = find_questions_in_obj(data)
        if found:
            questions.extend(found)
        elif isinstance(data, list):
            questions.extend(data)
        elif isinstance(data, dict):
            questions.append(data)
    return questions


def extract_letters_from_string(s: str) -> List[str]:
    return re.findall(r"\b([A-Z])\b", s)


def get_correct_answers(q: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    ac = q.get('answers_community') or q.get('answers_community', None)
    if ac and isinstance(ac, list) and len(ac) > 0:
        for item in ac:
            if isinstance(item, str):
                candidates.extend(extract_letters_from_string(item))
    if not candidates:
        for key in ('answer_ET', 'answer'):
            val = q.get(key)
            if val:
                if isinstance(val, list):
                    for v in val:
                        candidates.extend(extract_letters_from_string(str(v)))
                else:
                    candidates.extend(extract_letters_from_string(str(val)))
    candidates = [c.upper() for c in candidates]
    seen = set(); out = []
    for c in candidates:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


def get_choices(q: Dict[str, Any]) -> Optional[Dict[str, str]]:
    ch = q.get('choices')
    if isinstance(ch, dict) and ch:
        normalized = {}
        for k, v in ch.items():
            kk = str(k).strip().upper()
            if len(kk) > 1:
                kk = kk[0]
            normalized[kk] = str(v)
        return normalized
    return None


def choice_label(letter: str, text: str) -> str:
    return f"{letter}: {text}"


# ---------------- Session state ----------------
if 'questions' not in st.session_state:
    st.session_state.questions = []
if 'responses' not in st.session_state:
    st.session_state.responses = {}
if 'current_idx' not in st.session_state:
    st.session_state.current_idx = 0
if 'mode' not in st.session_state:
    st.session_state.mode = 'reveal_at_end'
if 'loaded' not in st.session_state:
    st.session_state.loaded = False

# ---------------- UI ----------------
st.title("Quiz app")
st.write("Upload JSON files or load a local folder. This version will detect nested `pageProps.questions` list, and enables CSV download.")

with st.expander("Load quizzes", expanded=True):
    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded = st.file_uploader("Upload JSON quiz files", type=['json'], accept_multiple_files=True)
        if st.button("Load uploaded files"):
            if not uploaded:
                st.warning("No files selected.")
            else:
                st.session_state.questions = parse_uploaded_jsons(uploaded)
                st.session_state.loaded = True
                st.session_state.responses = {}
                st.session_state.current_idx = 0
                st.success(f"Loaded {len(st.session_state.questions)} questions from uploaded files.")
    with col2:
        folder = st.text_input("Local folder path (optional)", value="")
        if st.button("Load from local folder"):
            if not folder:
                st.warning("Provide a folder path where JSON files are located.")
            else:
                qs = load_from_local_folder(folder)
                if qs:
                    st.session_state.questions = qs
                    st.session_state.loaded = True
                    st.session_state.responses = {}
                    st.session_state.current_idx = 0
                    st.success(f"Loaded {len(qs)} questions from {folder}.")

mode = st.radio("Choose mode:", options=["Reveal correct answers at the end", "Show correct answer on demand (per question)"], index=0)
st.session_state.mode = 'reveal_at_end' if mode.startswith('Reveal') else 'show_on_demand'

if not st.session_state.loaded or not st.session_state.questions:
    st.info("No questions loaded yet. Upload JSON files or load from a local folder to begin.")
    st.stop()

questions = st.session_state.questions
n_questions = len(questions)

# navigation
col_prev, col_next = st.columns([1,1])
with col_prev:
    if st.button("Previous") and st.session_state.current_idx > 0:
        st.session_state.current_idx -= 1
with col_next:
    if st.button("Next") and st.session_state.current_idx < n_questions - 1:
        st.session_state.current_idx += 1

st.progress((st.session_state.current_idx + 1) / max(1, n_questions))
st.markdown(f"**Question {st.session_state.current_idx + 1} / {n_questions}**")

q = questions[st.session_state.current_idx]
question_text = q.get('question_text') or q.get('text') or '<no question_text found>'
st.markdown(question_text)

choices = get_choices(q)
correct = get_correct_answers(q)
url = q.get('url', '')

resp_key = f"resp_{st.session_state.current_idx}"

if choices:
    labels = [choice_label(k, choices[k]) for k in sorted(choices.keys())]
    label_to_letter = {choice_label(k, choices[k]): k for k in choices}
    if len(correct) > 1:
        sel = st.multiselect("Select one or more answers:", options=labels, key=resp_key)
        selected_letters = [label_to_letter[s] for s in sel]
        st.session_state.responses[st.session_state.current_idx] = selected_letters
    else:
        sel = st.radio("Select one answer:", options=labels, key=resp_key)
        selected_letter = label_to_letter[sel]
        st.session_state.responses[st.session_state.current_idx] = [selected_letter]
else:
    st.warning("This question does not contain `choices`. Answer input will be recorded but the question is ungradable automatically.")
    free = st.text_input("Your answer (free text)", key=resp_key)
    st.session_state.responses[st.session_state.current_idx] = free

if st.session_state.mode == 'show_on_demand':
    if st.button("Show correct answer", key=f"reveal_{st.session_state.current_idx}"):
        if correct:
            st.info(f"Correct answer(s): {', '.join(correct)}")
            if choices:
                for c in correct:
                    st.markdown(f"- **{c}**: {choices.get(c, '(choice text not available)')}")
        else:
            st.info("No authoritative correct answer available for this question.")

if st.checkbox("Mark this question as 'skip' (will be treated as incorrect)", key=f"skip_{st.session_state.current_idx}"):
    st.session_state.responses[st.session_state.current_idx] = []

st.markdown("---")
if st.button("Finish quiz and show summary"):
    failed = []
    results = []
    for idx, question in enumerate(questions):
        resp = st.session_state.responses.get(idx, None)
        corr = get_correct_answers(question)
        ch = get_choices(question)

        gradeable = bool(corr) and bool(ch)

        if isinstance(resp, list):
            user_letters = [r.upper() for r in resp]
        elif isinstance(resp, str):
            user_letters = extract_letters_from_string(resp)
        else:
            user_letters = []

        if set(user_letters) == set(corr) and len(user_letters) > 0:
            is_correct = True
        else:
            is_correct = False

        if not gradeable or not is_correct:
            failed.append((idx, question, user_letters, corr))

        # prepare row for CSV export
        results.append({
            "index": idx + 1,
            "question_id": question.get('question_id', ''),
            "enunciate": question.get('question_text', ''),
            "user_answer": ",".join(user_letters) if user_letters else "",
            "correct_answer": ",".join(corr) if corr else "",
            "is_correct": is_correct,
            "url": question.get('url', '')
        })

    st.header("Summary — Failed Questions")
    st.write(f"Total questions: {n_questions} — Failed / Ungradable: {len(failed)}")

    if not failed:
        st.success("All graded questions were answered correctly!")
    else:
        for idx, question, user_ans, corr_ans in failed:
            with st.expander(f"Question {idx+1}: {question.get('question_text')[:80]}..."):
                st.write(question.get('question_text'))
                st.write("**URL:**", question.get('url', ''))
                st.write("**Your answer:**", user_ans if user_ans else "(no answer)")
                st.write("**Correct answer(s):**", corr_ans if corr_ans else "(no authoritative correct answer)")
                ch = get_choices(question)
                if ch:
                    st.write("**Choices:**")
                    for k in sorted(ch.keys()):
                        st.markdown(f"- **{k}**: {ch[k]}")

    # prepare CSV for download
    try:
        df = pd.DataFrame(results)
        csv_data = df.to_csv(index=False).encode('utf-8')

        st.download_button(
            label="Descargar resultados como CSV",
            data=csv_data,
            file_name="quiz_results.csv",
            mime="text/csv",
        )
    except Exception as e:
        st.error(f"Error al preparar el CSV: {e}")

    st.balloons()

