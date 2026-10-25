"""Database-facing helpers shared by the Streamlit front ends.

The corpus is loaded from CSV but annotations live in SQLite, so every review
surface needs the same three things: a way to map CSV rows back to their database
IDs, a way to read an example's annotation history, and a way to export the
reviewed rows. Keeping them here means the reading-suggestion workspace and the
older annotation app cannot drift apart.

A few small helpers that must survive Streamlit's re-running of the app script live
here too (the reviewer-key attempt counter, the corpus-signature memo): the script
file is executed afresh on every rerun, so anything it defined at module level would
reset each time, whereas an imported module persists for the life of the process.
"""

from __future__ import annotations

import math
import re
import secrets
import threading
import time
import weakref
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from io import StringIO

import pandas as pd

from app.storage.db import DatabaseUnavailable, SessionLocal
from app.storage.repo import AnnotationRepo, ExampleRepo

ANNOTATION_STATUSES = ["accepted", "edited", "rejected", "uncertain"]

CC_BY_SA_URL = "https://creativecommons.org/licenses/by-sa/4.0/"

# CC BY-SA 4.0 §3(a) applies to every distribution of adapted material, not just to
# the repository. The reviewed export carries `transliteration_gold` and `translation`
# — corpus text, not this project's own work — so a copy that leaves the app must
# carry the attribution, the licence, the statement that it is adapted, and a link to
# the original *of the corpus each row actually came from*. Shipped as a column rather
# than a comment header because a `#` line breaks `pd.read_csv` for anyone downstream.
#
# Plain-text twins of CORPUS_CREDITS in whyptology_app.py (that one is HTML for the
# page footer); tests/test_audit_ui.py fails if the two drift apart. The TLA entries
# repeat each dataset card's own citation recommendation.
_TLA_EDITORS = (
    "ed. by Tonio Sebastian Richter & Daniel A. Werning on behalf of the "
    "Berlin-Brandenburgische Akademie der Wissenschaften and Hans-Werner "
    "Fischer-Elfert & Peter Dils on behalf of the Sächsische Akademie der "
    "Wissenschaften zu Leipzig"
)
PUBLIC_CREDITS: dict[tuple[str, str], str] = {
    ("TLA", "Earlier Egyptian"): (
        "Thesaurus Linguae Aegyptiae, Original Earlier Egyptian sentences, corpus "
        "v18, premium, https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/"
        f"tla-Earlier_Egyptian_original-v18-premium, v1.1, 2/16/2024, {_TLA_EDITORS}"
    ),
    ("TLA", "Late Egyptian"): (
        "Thesaurus Linguae Aegyptiae, Late Egyptian sentences, corpus v19, premium, "
        "https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/"
        f"tla-late_egyptian-v19-premium, v1.0, 1/19/2025, {_TLA_EDITORS}"
    ),
    ("TLA", "Demotic"): (
        "Thesaurus Linguae Aegyptiae, Demotic sentences, corpus v18, premium, "
        "https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/"
        f"tla-demotic-v18-premium, v1.1, 2/16/2024, {_TLA_EDITORS}"
    ),
    ("AES", ""): (
        "AES — Ancient Egyptian Sentences, https://github.com/simondschweitzer/aes, "
        "derived from AED-TEI (https://github.com/simondschweitzer/aed-tei; S. "
        "Schweitzer and contributors, BBAW/SAW)"
    ),
    ("BBAW", ""): (
        "the BBAW Egyptian corpus, https://huggingface.co/datasets/phiwi/bbaw_egyptian, "
        "derived from the AED-TEI publication of the project “Strukturen und "
        "Transformationen des Wortschatzes der ägyptischen Sprache” "
        "(Berlin-Brandenburgische Akademie der Wissenschaften), January 2018 snapshot"
    ),
    ("Ramses", ""): (
        "the Ramses transliteration corpus V. 2019-09-01, University of Liège/Projet "
        "Ramses, https://doi.org/10.5281/zenodo.4954597"
    ),
}

_NOTICE_TAIL = (
    "Adapted: normalised, re-segmented and extended with derived fields; see "
    "DATA-LICENSE.md. Annotation columns are this project's own editorial additions. "
    "Redistribution of this file must keep this notice and stay under CC BY-SA 4.0. "
    "No warranties are given; the licence may not give you all the permissions "
    "necessary for your intended use."
)

# The fallback for a row whose source is missing or unknown, and for an export with
# no `source` column at all: names every public corpus, so it is never narrower than
# the truth. Kept a superset of the earlier TLA-only wording.
LICENCE_NOTICE = (
    "Corpus text (transliteration_gold, translation) derived from the Thesaurus "
    "Linguae Aegyptiae (https://thesaurus-linguae-aegyptiae.de): Earlier Egyptian "
    "corpus v18 (https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/"
    "tla-Earlier_Egyptian_original-v18-premium), Late Egyptian corpus v19 "
    "(https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/"
    "tla-late_egyptian-v19-premium) and Demotic corpus v18 "
    "(https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/"
    "tla-demotic-v18-premium), ed. Richter & Werning (BBAW) and Fischer-Elfert & "
    "Dils (SAW Leipzig); and from "
    + "; ".join(credit for key, credit in PUBLIC_CREDITS.items() if key[0] != "TLA")
    + f" — licensed CC BY-SA 4.0 ({CC_BY_SA_URL}). "
    + _NOTICE_TAIL
)


def licence_notice_for(source: object, language_stage: object = "") -> str:
    """The attribution notice for one row, from its `source` (and TLA stage).

    An unknown or blank source gets the generic `LICENCE_NOTICE`, never a guess.
    """
    src = safe_str(source).strip()
    stage = safe_str(language_stage).strip()
    credit = PUBLIC_CREDITS.get((src, stage if src == "TLA" else ""))
    if credit is None:
        return LICENCE_NOTICE
    return (
        f"Corpus text (transliteration_gold, translation) derived from {credit} "
        f"— licensed CC BY-SA 4.0 ({CC_BY_SA_URL}). " + _NOTICE_TAIL
    )


_PLAIN_NUMBER = re.compile(r"^[+-]?\d+(\.\d+)?$")


def neutralise_spreadsheet_formulas(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy in which no text cell can be read as a spreadsheet formula.

    Excel and LibreOffice treat a cell starting with `=`, `+`, `-` or `@` (or a tab or
    carriage return) as a formula, and 406 corpus readings start with one of them
    (the suffix pronoun `=f`). A single quote in front makes the cell plain text.
    Plain numbers (`-5`) are left alone. Anyone reading the CSV programmatically will
    see that leading quote and must strip it.
    """
    out = frame.copy()

    def fix(value: object) -> object:
        if (
            isinstance(value, str)
            and value
            and value[0] in "=+-@\t\r"
            and not _PLAIN_NUMBER.match(value)
        ):
            return "'" + value
        return value

    for column in out.columns:
        series = out[column]
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            out[column] = series.map(fix)
    return out


def with_licence_notice(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach the CC BY-SA notice to every row of an export.

    With a `source` column the notice names that row's own corpus (and, for TLA, its
    `language_stage`); without one every row gets the generic `LICENCE_NOTICE`. Cells
    that would open as spreadsheet formulas are neutralised last, see
    `neutralise_spreadsheet_formulas`, so every export path gets that too.
    """
    out = frame.copy()
    if "source" in out.columns:
        stages = out["language_stage"] if "language_stage" in out.columns else [""] * len(out)
        cache: dict[tuple[str, str], str] = {}
        notices = []
        for source, stage in zip(out["source"], stages):
            key = (safe_str(source), safe_str(stage))
            if key not in cache:
                cache[key] = licence_notice_for(*key)
            notices.append(cache[key])
        out["licence"] = notices
    else:
        out["licence"] = LICENCE_NOTICE
    return neutralise_spreadsheet_formulas(out)


# ---------- readable text names ----------

# AES rows keep a content hash in source_text_id (annotations and benchmarks hold it,
# so it cannot change without scripts/migrate_example_ids.py). The readable handles
# are elsewhere: the importer writes the upstream name into grammar_notes as
# 'AES text: <name>' (audit A32), and every AES row's source_ref carries the
# upstream text id ('AES/<corpus>#text=<id>&sentence=...'), which is the same for
# all sentences of one papyrus. Rows imported before A32 have only the latter.
_AES_TEXT_NAME_RE = re.compile(r"(?:^|;\s*)AES text:\s*([^;]+)")
_AES_UPSTREAM_TEXT_RE = re.compile(r"#text=([^&]+)")


def aes_text_name(row) -> str:
    """The upstream AES text name of a row, or its upstream text id, else ''."""
    if safe_str(row.get("source")).strip() != "AES":
        return ""
    match = _AES_TEXT_NAME_RE.search(safe_str(row.get("grammar_notes")))
    if match and match.group(1).strip():
        return match.group(1).strip()
    match = _AES_UPSTREAM_TEXT_RE.search(safe_str(row.get("source_ref")))
    if match and match.group(1).strip():
        return f"AES text {match.group(1).strip()}"
    return ""


def text_label(row, fallback: str = "—") -> str:
    """What the UI calls a row's text: the AES name when there is one, else the id.

    For AES the hash id stays in brackets so a reviewer can still match it to an
    annotation or a benchmark row. Plain text; callers escape for their sink.
    """
    text_id = safe_str(row.get("source_text_id")).strip()
    name = aes_text_name(row)
    if name:
        return f"{name} ({text_id})" if text_id else name
    return text_id or fallback


# ---------- reviewer key ----------


def check_reviewer_key(entered: str, expected: str) -> bool:
    """Constant-time key comparison that cannot raise on non-ASCII text.

    `secrets.compare_digest` raises TypeError for a non-ASCII `str`, so a reviewer
    typing 'Pässwort' (or an operator choosing such a key) crashed the page. Comparing
    the UTF-8 bytes avoids that. An empty key on either side never matches.
    """
    if not entered or not expected:
        return False
    return secrets.compare_digest(entered.encode("utf-8"), expected.encode("utf-8"))


@dataclass(frozen=True)
class KeyAttemptResult:
    """Outcome of one reviewer-key attempt (see KeyAttemptGuard.attempt)."""

    ok: bool
    # Seconds this session must still wait before the key is compared again; > 0
    # only when the attempt was refused without a comparison.
    wait: int = 0
    # Failures inside the window for this session / for the whole process, after
    # this attempt. Logged as counts; the typed value is never stored or logged.
    session_failures: int = 0
    global_failures: int = 0
    # Seconds this attempt was slowed by the process-wide rate brake.
    delayed: float = 0.0


SESSION_ATTEMPTS_KEY = "_reviewer_key_attempts"


class KeyAttemptGuard:
    """Brake on reviewer-key guessing: per-session backoff plus a global slowdown.

    Two layers, decided by the owner on 2026-10-25 after review of the first
    version (a process-wide lockout, which let one guesser lock every real reviewer
    out for as long as it kept guessing):

    * **Per session, exponential backoff.** After `free_attempts` failures inside
      `window` seconds a session must wait `base_cooldown`, doubling with each
      further failure up to `max_cooldown`. While waiting, that session's key is not
      even compared, so its guesses make no progress. Other sessions are unaffected.
    * **Process-wide, slow-down only.** Streamlit hands an attacker a fresh session
      per connection, so the per-session counter alone can be sidestepped. When
      more than `global_free` failures from all sessions sit inside `window`, every
      attempt (right or wrong, from any session) is delayed by `global_step`
      seconds per excess failure, capped at `global_max_delay`. It never refuses:
      a real reviewer is at most `global_max_delay` seconds slower.

    `attempt` does the cooldown check, the comparison and the counter update as one
    transaction under a lock (only the slow-down sleep happens outside it), so two
    concurrent attempts cannot interleave the way the first version's separate
    calls could. State is in memory, so a restart clears it.

    Neither layer caps how many attempts run at once: the slow-down delays each
    attempt but N parallel connections still get about N / `global_max_delay`
    guesses a second. The real protection is the key's length — use 20 or more
    random characters (review of fix round 1).
    """

    def __init__(
        self,
        free_attempts: int = 5,
        window: float = 15 * 60,
        base_cooldown: float = 30.0,
        max_cooldown: float = 15 * 60,
        global_free: int = 20,
        global_step: float = 0.25,
        global_max_delay: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.free_attempts = free_attempts
        self.window = window
        self.base_cooldown = base_cooldown
        self.max_cooldown = max_cooldown
        self.global_free = global_free
        self.global_step = global_step
        self.global_max_delay = global_max_delay
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._global_failures: list[float] = []

    # -- helpers; callers hold self._lock --

    def _session_record(self, session: MutableMapping) -> dict:
        record = session.get(SESSION_ATTEMPTS_KEY)
        if not isinstance(record, dict):
            record = {"failures": [], "locked_until": 0.0}
            session[SESSION_ATTEMPTS_KEY] = record
        return record

    def _prune(self, stamps: list[float], now: float) -> list[float]:
        return [t for t in stamps if now - t < self.window]

    def _session_wait(self, record: dict, now: float) -> int:
        return max(0, math.ceil(record["locked_until"] - now))

    def _global_delay(self, now: float) -> float:
        self._global_failures = self._prune(self._global_failures, now)
        excess = len(self._global_failures) - self.global_free
        if excess <= 0:
            return 0.0
        return min(self.global_max_delay, self.global_step * excess)

    # -- public API --

    def seconds_locked(self, session: MutableMapping) -> int:
        """Whole seconds until this session may try again; 0 when it may."""
        with self._lock:
            return self._session_wait(self._session_record(session), self._clock())

    def global_delay(self) -> float:
        """Seconds every attempt is currently slowed by; 0 below the global rate."""
        with self._lock:
            return self._global_delay(self._clock())

    def attempt(
        self, session: MutableMapping, entered: str, expected: str
    ) -> KeyAttemptResult:
        """Check one typed key for one session; never raises on any text.

        An empty submission is not a guess: it is neither compared nor counted.
        """
        with self._lock:
            now = self._clock()
            record = self._session_record(session)
            wait = self._session_wait(record, now)
            if wait:
                return KeyAttemptResult(
                    ok=False,
                    wait=wait,
                    session_failures=len(record["failures"]),
                    global_failures=len(self._global_failures),
                )
            delay = self._global_delay(now) if entered else 0.0
        if delay:
            self._sleep(delay)
        with self._lock:
            now = self._clock()
            record = self._session_record(session)
            # Another rerun of this same session may have failed meanwhile.
            wait = self._session_wait(record, now)
            if wait:
                return KeyAttemptResult(
                    ok=False,
                    wait=wait,
                    session_failures=len(record["failures"]),
                    global_failures=len(self._global_failures),
                    delayed=delay,
                )
            if check_reviewer_key(entered, expected):
                # Only this session's counter is cleared: a correct key elsewhere
                # must not wipe the evidence of someone else's guessing.
                record["failures"] = []
                record["locked_until"] = 0.0
                return KeyAttemptResult(
                    ok=True,
                    global_failures=len(self._global_failures),
                    delayed=delay,
                )
            if not entered:
                return KeyAttemptResult(
                    ok=False,
                    session_failures=len(record["failures"]),
                    global_failures=len(self._global_failures),
                )
            record["failures"] = self._prune(record["failures"], now) + [now]
            count = len(record["failures"])
            if count >= self.free_attempts:
                record["locked_until"] = now + min(
                    self.max_cooldown,
                    self.base_cooldown * 2 ** (count - self.free_attempts),
                )
            self._global_failures = self._prune(self._global_failures, now) + [now]
            return KeyAttemptResult(
                ok=False,
                session_failures=count,
                global_failures=len(self._global_failures),
                delayed=delay,
            )


REVIEWER_KEY_GUARD = KeyAttemptGuard()


# ---------- Markdown safety ----------

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!$|~<>:&=])")


def md_escape(text: object) -> str:
    """Make corpus or user text safe to interpolate into Markdown.

    Streamlit renders `st.markdown`, `st.caption`, `st.warning` and expander labels as
    Markdown, so a reading such as `rʾ n [r](m)t` turns into a link and `$ṯms.t$` into
    maths, and a typed query can inject an image or a link. Whitespace runs (including
    newlines) collapse to one space and each Markdown-significant character gets a
    backslash. `:` blocks `:red[...]` colour directives and `=` blocks setext headings.
    """
    if text is None:
        return ""
    flat = " ".join(str(text).split())
    return _MD_SPECIAL.sub(r"\\\1", flat)


def md_code(text: object) -> str:
    """The text as a Markdown code span. Backslash escapes do not work inside one, so
    backticks (the only thing that could close the span) become apostrophes."""
    if text is None:
        return "``"
    flat = " ".join(str(text).split()).replace("`", "'")
    return f"`{flat}`"


# ---------- corpus signature memo ----------

_SIGNATURE_MEMO: dict[int, tuple[weakref.ref, str]] = {}
_SIGNATURE_LOCK = threading.Lock()


def signature_for_frame(df: pd.DataFrame, compute: Callable[[pd.DataFrame], str]) -> str:
    """`compute(df)`, remembered for as long as this very DataFrame object lives.

    Hashing 130k rows costs ~0.2 s and the app asked for it 3-4 times per rerun. The
    cached corpus frames are shared objects, so identity is stable across reruns; the
    weak reference both drops the entry when the frame is freed and guards against
    `id()` being reused by a different frame.
    """
    key = id(df)
    with _SIGNATURE_LOCK:
        hit = _SIGNATURE_MEMO.get(key)
        if hit is not None and hit[0]() is df:
            return hit[1]
    value = compute(df)

    def forget(ref: weakref.ref, key: int = key) -> None:
        with _SIGNATURE_LOCK:
            entry = _SIGNATURE_MEMO.get(key)
            if entry is not None and entry[0] is ref:
                del _SIGNATURE_MEMO[key]

    with _SIGNATURE_LOCK:
        _SIGNATURE_MEMO[key] = (weakref.ref(df, forget), value)
    return value

HISTORY_COLUMNS = [
    "id",
    "status",
    "transliteration",
    "normalized_reading_order",
    "variant_writing_note",
    "morphology_note",
    "syntax_note",
    "aesthetic_arrangement_flag",
    "created_at",
]


def safe_str(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    return "" if text.lower() == "nan" else text


def coerce_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "t"}
    return bool(value)


def attach_db_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Add the database `id` for each CSV row, so annotations can be attached.

    Raises DatabaseUnavailable rather than propagating a driver error, so the caller
    can decide to carry on read-only. A frame without an `id` column is still fully
    usable for reading, searching and browsing — only saving needs the ids.
    """
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover - driver-level failure
        raise DatabaseUnavailable(str(exc)) from exc
    try:
        repo = ExampleRepo(session)
        id_map = {
            (source, source_text_id, source_sentence_id): example_id
            for example_id, source, source_text_id, source_sentence_id in (
                repo.list_example_keys()
            )
        }
    except Exception as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        session.close()

    out = df.copy()
    # Vectorised: the per-row .apply() over 12,772 rows was pure overhead.
    keys = pd.MultiIndex.from_arrays(
        [out["source"], out["source_text_id"], out["source_sentence_id"]]
    )
    out["id"] = [id_map.get(key) for key in keys]
    return out


def build_row_key(row: pd.Series, position: int) -> str:
    """Stable per-row key so Streamlit widget state does not collide."""
    db_id = safe_str(row.get("id")) or "noid"
    source = safe_str(row.get("source"))
    text_id = safe_str(row.get("source_text_id"))
    sentence_id = safe_str(row.get("source_sentence_id"))
    return f"{position}_{db_id}_{source}_{text_id}_{sentence_id}"


def annotation_history_to_df(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=pd.Index(HISTORY_COLUMNS))
    return pd.DataFrame(
        [
            {
                "id": row.id,
                "status": row.status,
                "transliteration": row.transliteration,
                "normalized_reading_order": row.normalized_reading_order,
                "variant_writing_note": row.variant_writing_note,
                "morphology_note": row.morphology_note,
                "syntax_note": row.syntax_note,
                "aesthetic_arrangement_flag": bool(row.aesthetic_arrangement_flag),
                "created_at": row.created_at,
            }
            for row in rows
        ]
    )


def load_annotation_state(example_id: int | None) -> tuple[object | None, pd.DataFrame]:
    """Return (latest annotation, full history) for one example.

    One query, not two: the history is fetched and the newest row taken from it in
    Python. Asking the database for "latest" separately meant running the same
    ordered SELECT twice for every result row on every rerun.
    """
    if example_id is None:
        return None, annotation_history_to_df([])
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover - driver-level failure
        raise DatabaseUnavailable(str(exc)) from exc
    try:
        repo = AnnotationRepo(session)
        rows = repo.list_for_example(example_id)
    except Exception as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        session.close()
    return (rows[0] if rows else None), annotation_history_to_df(rows)


def annotated_example_count() -> int:
    """How many examples carry at least one annotation.

    Home and Projects only need this number. They used to call
    `reviewed_annotation_rows()`, which pulls every annotation ever written *and*
    the full corpus row for each annotated example — on every sidebar click.
    """
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover - driver-level failure
        raise DatabaseUnavailable(str(exc)) from exc
    try:
        return AnnotationRepo(session).count_annotated_examples()
    except Exception as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        session.close()


def annotated_example_ids() -> set[int]:
    """Ids of examples with at least one annotation (for badges in listings)."""
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover - driver-level failure
        raise DatabaseUnavailable(str(exc)) from exc
    try:
        return set(AnnotationRepo(session).annotated_example_ids())
    except Exception as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        session.close()


def load_annotation_states(
    example_ids: list[int],
) -> dict[int, tuple[object | None, pd.DataFrame]]:
    """Latest annotation and history for many examples, in one query.

    The Workspace shows several parallels at once and each needs its own annotation
    state; fetching them one at a time meant a round trip per visible row on every
    rerun — including every keystroke in a note field.
    """
    wanted = [int(i) for i in example_ids if i is not None]
    if not wanted:
        return {}
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover - driver-level failure
        raise DatabaseUnavailable(str(exc)) from exc
    try:
        rows = AnnotationRepo(session).list_for_examples(wanted)
    except Exception as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        session.close()

    grouped: dict[int, list] = {example_id: [] for example_id in wanted}
    for row in rows:
        grouped.setdefault(row.example_id, []).append(row)
    return {
        example_id: (
            (history[0] if history else None),
            annotation_history_to_df(history),
        )
        for example_id, history in grouped.items()
    }


def reviewed_annotation_rows() -> list[dict]:
    """Every example that has at least one saved annotation, base + latest."""
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover - driver-level failure
        raise DatabaseUnavailable(str(exc)) from exc
    try:
        example_repo = ExampleRepo(session)
        annotation_repo = AnnotationRepo(session)

        latest_annotations = {
            row.example_id: row
            for row in annotation_repo.list_latest_annotations_only()
        }
        examples = example_repo.list_examples_by_ids(list(latest_annotations))

        export_rows: list[dict] = []
        for example in examples:
            latest = latest_annotations.get(example.id)
            if latest is None:
                continue
            export_rows.append(
                {
                    "example_id": example.id,
                    "source": example.source,
                    "source_text_id": example.source_text_id,
                    "source_sentence_id": example.source_sentence_id,
                    "language_stage": example.language_stage,
                    "script_type": example.script_type,
                    "genre": example.genre,
                    "period": example.period,
                    "hieroglyphs": example.hieroglyphs,
                    "mdc": example.mdc,
                    "sign_sequence": example.sign_sequence,
                    "transliteration_gold": example.transliteration_gold,
                    "translation": example.translation,
                    "lemma_sequence": example.lemma_sequence,
                    "upos": example.upos,
                    "glossing": example.glossing,
                    "formula_type": example.formula_type,
                    "deity": example.deity,
                    "recipient": example.recipient,
                    "offering_items": example.offering_items,
                    "formula_slot": example.formula_slot,
                    "base_display_sequence": example.display_sequence,
                    "base_normalized_reading_order": example.normalized_reading_order,
                    "base_alt_transliterations": example.alt_transliterations,
                    "base_variant_writing_note": example.variant_writing_note,
                    "base_morphology_note": example.morphology_note,
                    "base_syntax_note": example.syntax_note,
                    "base_aesthetic_arrangement_flag": bool(
                        example.aesthetic_arrangement_flag
                    ),
                    "latest_transliteration": latest.transliteration,
                    "latest_status": latest.status,
                    "latest_uncertainty_note": latest.uncertainty_note or "",
                    "latest_grammar_note": latest.grammar_note or "",
                    "latest_display_sequence": latest.display_sequence or "",
                    "latest_normalized_reading_order": (
                        latest.normalized_reading_order or ""
                    ),
                    "latest_alt_transliterations": latest.alt_transliterations or "",
                    "latest_variant_writing_note": latest.variant_writing_note or "",
                    "latest_morphology_note": latest.morphology_note or "",
                    "latest_syntax_note": latest.syntax_note or "",
                    "latest_aesthetic_arrangement_flag": bool(
                        latest.aesthetic_arrangement_flag
                    ),
                    "source_ref": example.source_ref,
                    # Carries the 'AES text: <name>' note, so the Reviews page can
                    # show the readable text name (audit A32), not only the hash.
                    "grammar_notes": example.grammar_notes or "",
                    "latest_annotation_created_at": latest.created_at,
                }
            )
        return export_rows
    except DatabaseUnavailable:
        raise
    except Exception as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        session.close()


def build_reviewed_export_csv() -> str:
    buffer = StringIO()
    with_licence_notice(pd.DataFrame(reviewed_annotation_rows())).to_csv(
        buffer, index=False
    )
    return buffer.getvalue()


def score_breakdown_lines(row: pd.Series) -> list[str]:
    keys = [
        "fuzzy_score",
        "tfidf_score",
        "overlap_score",
        "idf_overlap_score",
        "exact_bonus",
        "glyph_overlap_score",
        "glyph_idf_overlap_score",
        "glyph_order_score",
        "glyph_exact_bonus",
        "reading_order_overlap",
        "final_score",
    ]
    return [f"{key}: {float(row[key]):.4f}" for key in keys if key in row]
