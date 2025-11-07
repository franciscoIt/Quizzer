import streamlit as st
import re
import pandas as pd
from typing import Any, Dict, List, Optional

# Use loader manager (routes by extension / content sniffing) and returns normalized questions
from src.loaders import load_from_files, load_from_folder

st.set_page_config(page_title="Quiz app", layout="wide")

# ---------------- Helpers ----------------


def extract_letters_from_string(s: str) -> List[str]:
    return re.findall(r"\b([A-Z])\b", s)


def get_correct_answers(q: Dict[str, Any]) -> List[str]:
    """
    Return list of unique uppercase answer letters for question q.
    The manager already normalizes many shapes, but keep fallbacks here.
    """
    candidates: List[str] = []
    ac = q.get('answers_community') or q.get('answers_community', None)
    if ac and isinstance(ac, list) and len(ac) > 0:
        for item in ac:
            if isinstance(item, str):
                candidates.extend(extract_letters_from_string(item))

    if not candidates:
        for key in ('answer_ET', 'answer', 'correct_answer'):
            val = q.get(key)
            if val:
                if isinstance(val, list):
                    for v in val:
                        candidates.extend(extract_letters_from_string(str(v)))
                else:
                    candidates.extend(extract_letters_from_string(str(val)))

    # Normalize and deduplicate preserving order
    candidates = [c.upper() for c in candidates]
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def get_choices(q: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Expect q['choices'] to be a dict like {"A": "text", "B": "text", ...}.
    Return a normalized version with single-letter uppercase keys, or None.
    """
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
st.write(
    "Upload JSON or CSV quiz files or load a local folder. "
    "The loader manager will route and normalize files automatically."
)

with st.expander("Load quizzes", expanded=True):
    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded = st.file_uploader(
            "Upload quiz files (JSON or CSV)",
            type=['json', 'csv'],
            accept_multiple_files=True
        )

        if st.button("Load uploaded files"):
            if not uploaded:
                st.warning("No files selected.")
            else:
                try:
                    # manager returns normalized question dicts
                    questions = load_from_files(uploaded)
                except Exception as e:
                    st.error(f"Error while loading files: {e}")
                    questions = []

                if not questions:
                    st.error("No valid questions found in the uploaded files.")
                else:
                    st.session_state.questions = questions
                    st.session_state.loaded = True
                    st.session_state.responses = {}
                    st.session_state.current_idx = 0
                    st.success(f"Loaded {len(questions)} questions from uploaded files.")

    with col2:
        folder = st.text_input("Local folder path (optional)", value="")
        if st.button("Load from local folder"):
            if not folder:
                st.warning("Provide a folder path where JSON/CSV files are located.")
            else:
                try:
                    questions = load_from_folder(folder)
                except Exception as e:
                    st.error(f"Error while loading folder: {e}")
                    questions = []

                if not questions:
                    st.error("No valid questions found in that folder.")
                else:
                    st.session_state.questions = questions
                    st.session_state.loaded = True
                    st.session_state.responses = {}
                    st.session_state.current_idx = 0
                    st.success(f"Loaded {len(questions)} questions from {folder}.")

mode = st.radio(
    "Choose mode:",
    options=["Reveal correct answers at the end", "Show correct answer on demand (per question)"],
    index=0
)
st.session_state.mode = 'reveal_at_end' if mode.startswith('Reveal') else 'show_on_demand'

if not st.session_state.loaded or not st.session_state.questions:
    st.info("No questions loaded yet. Upload JSON/CSV files or load from a local folder to begin.")
    st.stop()

questions = st.session_state.questions
n_questions = len(questions)

# navigation
col_prev, col_next = st.columns([1, 1])
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
    sorted_keys = sorted(choices.keys())
    labels = [choice_label(k, choices[k]) for k in sorted_keys]
    # mapping from displayed label to letter
    label_to_letter = {labels[i]: sorted_keys[i] for i in range(len(labels))}

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
        ch = get_choices(question) or {}

        row = {
            "index": idx + 1,
            "question_id": question.get('question_id', ''),
            "enunciate": question.get('question_text', ''),
            "user_answer": ",".join(user_letters) if user_letters else "",
            "correct_answer": ",".join(corr) if corr else "",
            "is_correct": is_correct,
            "url": question.get('url', '')
        }

        # Add up to 4 choices (A–D)
        for letter in ["A", "B", "C", "D"]:
            row[f"choice_{letter}"] = ch.get(letter, "")

        results.append(row)

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
