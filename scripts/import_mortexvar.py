"""Build a donor file from the MORTEXVAR Coffin Texts database (Middle Kingdom).

What it is. MORTEXVAR (database.mortexvar.com, C. Gracia Zamacona and colleagues) is a
witness-by-witness database of the Coffin Texts: one record per *line of one witness*
of a spell, with the de Buck reference (`code_text`, e.g. `I 001 1` or
`I 002 a - 003 a`), the witness siglum (`T1L`, `B3Bo`, `Pap.Gard.II`), the
transliteration, a French translation and an analysis/comments column. The whole
database ships inside the site's Vue bundle (`/js/app.<hash>.js`) as three
`JSON.parse('[...]')` string literals: the lines (27,160 records), the spell
metadata (1,186 records, not used for rows) and the documents table (320 records:
`witness`, `document`, `necropolis`, `dating`).

LICENCE STATUS: NONE. The owner allowed the download ("You can download the csv") but
the site says "(c) 2019 by Mortexvar" and no licence has been granted. Therefore:
  * the raw bundle and everything this script produces stay OUTSIDE the repository
    (write `--output`/`--summary` to ~/egyptology-runs/..., never under data/);
    `refuse_output_under_data` rejects an output below this repo's data/ folder, and
    `refuse_unsafe_output` rejects the corpus file and data/private/;
  * no MORTEXVAR row or excerpt belongs in tests, docs or commit messages (the tests
    use invented strings in the same format);
  * the donor CSV is a *candidate*; it may join the corpus only after a licence.

Reading the bundle. The literals are JavaScript single-quoted strings, not JSON, so
they are decoded as JS string literals first (`\\'`, `\\\\`, `\\"`, `\\n`, `\\xHH`,
`\\uHHHH`, `\\u{...}`, line continuations), and only then parsed as JSON. The file's
sha256 is pinned (`PINNED_SHA256`); a different bundle is refused unless the caller
passes `--expect-sha256` with the new digest after checking what changed.

Transliteration. The database writes Manuel de Codage ASCII, the same family as the
Ramses `tgt` files, so the conversion REUSES `scripts.import_ramses.convert_word`
(A -> ꜣ, a -> ꜥ, i -> ꞽ, H -> ḥ, x -> ḫ, X -> ẖ, S -> š, T -> ṯ, D -> ḏ; `h` stays
`h`, so ꜣ ꜥ ḫ ẖ ḥ h remain six distinct letters; `y z w k g b p f m n r t d s` pass
through exactly as in the corpus). Decisions, each on purpose:

  o -> q       The database has NO `q` at all, yet 1,336 rows contain `o`, always in
               words that are plainly q-words (ꜥq "enter", ḥnq.t "beer", qd "form",
               each written with `o` where the corpus writes q). So `o` is this
               database's ASCII for q (ḳ in the Berlin scheme, `q` in the corpus).
               Mapped by `MORTEXVAR_EXTRA_MAP`. This is an inference from the
               spellings, not from documentation: OPEN QUESTION for the owner.
  `[..]`       Restored text. Kept verbatim, exactly as the BBAW rows keep it (the
               search fold already drops the brackets but keeps the letters).
  `(w)`, `.(w)`  Letters the editor supplies though not written (`Sm.(w)`, `n(n)`).
               Kept verbatim: it is the corpus's own `(...)` notation (TLA `(w)di̯`).
  `<..>`       Signs the editor adds; kept, as in the Ramses rows.
  `{..}`       Superfluous text; kept, `normalize_notation` already deletes it from
               the key.
  `.` and `-`  Kept as written. The database uses `.` for suffix pronouns too (`n.k`,
               `im.f`) where the corpus writes ` =k`; telling a suffix from a
               morpheme ending needs a grammatical decision, so no `=` is inserted.
               Consequence: the search fold glues `n.k` into `nk`; see the summary's
               fragment-level overlap for the vocabulary gain with the dots split.
  `N`          The king/owner-name placeholder; kept as the capital letter.
  `Z1`, digits Kept verbatim (a sign name in two rows; `zp 2` repetition counts).
  `(= x)`      An editor's "read as x" gloss (8 rows). `=` is the suffix marker in
               the corpus, so the gloss would inject a second reading into the key;
               such rows are excluded and counted, not rewritten.

Exclusions, applied in this order, each counted in the summary:
  empty_transliteration   no transliteration (omitted lines carry only an analysis)
  lacuna_only             nothing left once the lacuna/unread markers are removed
  lacuna_a35              the documented transliteration-lacuna rule of audit A35,
                          `TRANSLIT_LACUNA_RE` shared with the BBAW/Ramses importers:
                          `//` in a word, empty brackets `[]` / `[...]`, `_`
  lacuna_paren            this database's own lacuna marker: a bracket holding only
                          dots, `(...)` (a broken reading is not evidence, A35)
  unread_token            a bare `?` word (an unreadable sign); a `?` attached to a
                          word, `w(?)`, is an uncertainty mark and is kept
  editorial_gloss         `(= x)` as above
  unsearchable            the search fold of the reading is empty

Stage / period. Stage "Earlier Egyptian" (Middle Egyptian, Coffin Texts). The period
comes from the documents table `dating`, joined on the witness siglum, and only when
every element of the (French, free-text) dating is unambiguous: a XI/XII-dynasty
king or dynasty, or "Moyen Empire" -> "Middle Kingdom"; "I P.I." -> "First
Intermediate Period"; anything else (`?`, empty, `Inconnue`, `XIII d.`, `... ou plus
tard`, mixed Old Kingdom/FIP) -> "unknown". No witness in the table -> "unknown".
The raw dating and the necropolis go into grammar_notes so nothing is lost.

Other columns. `hieroglyphs` and `mdc` are empty (the database has no sign data) and
`display_sequence` falls back to the transliteration, as for the text-only Ramses
rows. `translation` is the French text with its surrounding quotes stripped (the
corpus has no language column; BBAW keeps German there, so it goes in the same
column and `grammar_notes` says `translation language: fr`). `grammar_notes` also
carries `CT spell`, `de Buck` and `witness`. `source_text_id` is
`MORTEXVAR_<blake2b>` over spell, de Buck reference, witness, the array index and the
transliteration (the Ramses content-hash convention); `source_sentence_id` is the
array index, the database's only stable handle.

    python scripts/import_mortexvar.py BUNDLE.js --output OUT.csv --summary OUT.json
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import REQUIRED_COLUMNS  # noqa: E402
from app.data.normalizer import search_fold  # noqa: E402
from scripts.import_bbaw_egyptian import (  # noqa: E402
    TRANSLIT_LACUNA_RE,
    dedup_key,
    deduplicate,
    refuse_unsafe_output,
)
from scripts.import_ramses import convert_word  # noqa: E402

EXAMPLES = PROJECT_ROOT / "data" / "processed" / "examples.csv"
DATA_DIR = PROJECT_ROOT / "data"

# sha256 of app.42196e34.js as downloaded 2026-10-28.
PINNED_SHA256 = "527dce08d26fdec98c0f6a198d8d3a6412c0175e66e78e85e376f34ab7b2fa64"

SOURCE = "MORTEXVAR"
STAGE = "Earlier Egyptian"
UNKNOWN = "unknown"

# The database's ASCII for q (see the module docstring). Applied before the shared
# MdC conversion; `o` is not in the Ramses map, so there is no clash.
MORTEXVAR_EXTRA_MAP: dict[str, str] = {"o": "q"}
_EXTRA_TABLE = str.maketrans(MORTEXVAR_EXTRA_MAP)

# Every character a converted reading is expected to contain. Anything else is
# counted in the summary (kept, not dropped: it is a reason to look, not to discard).
EXPECTED_CHARS = frozenset(
    "ꜣꜥꞽḥḫẖšṯḏ" "abdfghkmnpqrstwyz" "N Z" "0123456789" ".-=()[]<>{}?/"
)

PAREN_LACUNA_RE = re.compile(r"\(\s*(?:\.\s*){2,}\)|\(\s*…\s*\)")
GLOSS_RE = re.compile(r"\(\s*=")
# Fragments to remove when asking "is there any reading left besides the markers?".
_MARKER_STRIP_RE = re.compile(
    r"/{2,}|\[[\s.…\-–—]*\]|_|\(\s*(?:\.\s*){2,}\)|\(\s*…\s*\)"
)

PERIOD_MK = "Middle Kingdom"
PERIOD_FIP = "First Intermediate Period"


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


def refuse_output_under_data(output: str | Path) -> None:
    """The data has no licence: nothing derived from it may be written below data/."""
    target = Path(output).resolve()
    if target == DATA_DIR.resolve() or DATA_DIR.resolve() in target.parents:
        raise SystemExit(
            f"refusing {output}: MORTEXVAR has no licence, so nothing derived from it may "
            "be written under this repo's data/ folder. Use ~/egyptology-runs/..."
        )


def sha256_of(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_sha256(path: str | Path, expected: str) -> str:
    """Return the file's digest, or stop when it is not the pinned bundle."""
    actual = sha256_of(path)
    if actual.lower() != expected.strip().lower():
        raise SystemExit(
            f"refusing {path}: sha256 {actual} is not the expected {expected}. The site "
            "bundle changed (or this is another file). Inspect it, then pass "
            "--expect-sha256 with the new digest."
        )
    return actual


# ---------------------------------------------------------------------------
# Reading the bundle: JSON.parse('...') literals are JS strings, not JSON
# ---------------------------------------------------------------------------

_JSON_PARSE_RE = re.compile(r"JSON\.parse\(\s*'([^'\\]*(?:\\.[^'\\]*)*)'\s*\)", re.DOTALL)
_JS_SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
_JS_ESCAPE_RE = re.compile(r"\\(u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|\r\n|.)", re.DOTALL)


def _js_escape(match: re.Match) -> str:
    body = match.group(1)
    if body.startswith("u{"):
        return chr(int(body[2:-1], 16))
    if body[0] in "ux" and len(body) > 1:
        return chr(int(body[1:], 16))
    if body in ("\n", "\r\n", "\u2028", "\u2029"):
        return ""  # line continuation
    return _JS_SIMPLE_ESCAPES.get(body, body)  # \\ \' \" and unknown escapes: the char


def decode_js_string_literal(body: str) -> str:
    """Decode the inside of a JS single-quoted string literal (without the quotes)."""
    text = _JS_ESCAPE_RE.sub(_js_escape, body)
    # `\uD83D\uDE00` arrives as two lone surrogates; join them into one character.
    return text.encode("utf-16", "surrogatepass").decode("utf-16")


def extract_json_literals(source: str) -> list[object]:
    """Every `JSON.parse('...')` literal in the bundle, decoded and parsed."""
    return [json.loads(decode_js_string_literal(m.group(1))) for m in _JSON_PARSE_RE.finditer(source)]


@dataclass
class Tables:
    lines: list[dict]
    spells: list[dict]
    documents: list[dict]


def split_tables(arrays: list[object]) -> Tables:
    """Tell the three arrays apart by their keys; require exactly one of each."""
    found: dict[str, list[dict]] = {}
    for array in arrays:
        if not isinstance(array, list) or not array or not isinstance(array[0], dict):
            continue
        keys = set(array[0])
        if {"code_text", "witness", "transliteration"} <= keys:
            kind = "lines"
        elif {"spell_order", "spell"} <= keys:
            kind = "spells"
        elif {"witness", "document", "dating"} <= keys:
            kind = "documents"
        else:
            continue
        if kind in found:
            raise SystemExit(f"more than one {kind} array in the bundle; refusing to guess")
        found[kind] = array
    missing = {"lines", "spells", "documents"} - set(found)
    if missing:
        raise SystemExit(f"bundle has no {', '.join(sorted(missing))} array")
    return Tables(found["lines"], found["spells"], found["documents"])


# ---------------------------------------------------------------------------
# Transliteration
# ---------------------------------------------------------------------------


def convert_transliteration(text: str) -> str:
    """MORTEXVAR MdC ASCII -> the corpus's TLA/Berlin Unicode (see the docstring)."""
    text = unicodedata.normalize("NFC", text).translate(_EXTRA_TABLE)
    return " ".join(convert_word(word) for word in text.split())


def unread_tokens(text: str) -> bool:
    """A bare `?` word. `w(?)` or `Hr?` are uncertainty marks and do not count."""
    return "?" in text.split()


def classify_transliteration(raw: str) -> str:
    """The exclusion reason for one raw transliteration, or '' when it is usable.

    Order matters and is the documented one: empty, lacuna_only, lacuna_a35,
    lacuna_paren, unread_token, editorial_gloss. `unsearchable` needs the converted
    text and is decided by the caller.
    """
    text = " ".join(unicodedata.normalize("NFC", raw).split())
    if not text:
        return "empty_transliteration"
    a35 = bool(TRANSLIT_LACUNA_RE.search(text))
    paren = bool(PAREN_LACUNA_RE.search(text))
    unread = unread_tokens(text)
    if a35 or paren or unread:
        residue = _MARKER_STRIP_RE.sub(" ", text)
        residue = " ".join(w for w in residue.split() if w != "?")
        if not search_fold(residue):
            return "lacuna_only"
        if a35:
            return "lacuna_a35"
        if paren:
            return "lacuna_paren"
        return "unread_token"
    if GLOSS_RE.search(text):
        return "editorial_gloss"
    return ""


# ---------------------------------------------------------------------------
# Documents table: witness -> necropolis / dating -> period
# ---------------------------------------------------------------------------

_KING_RE = re.compile(r"(Amenemhat|Sésostris|Mentuhotep)\s*(III|II|I)(?![IVXivx])")
_DYNASTY_RE = re.compile(r"(?<![A-Za-z])(XIII|XII|XI)(?![IVX])")
_FIP_RE = re.compile(r"(?<![A-Za-z])I\s*P\.?\s*I\.?")
_MOYEN_RE = re.compile(r"Moyen\s+Empire")
# Words that carry no period information; anything else left over makes it ambiguous.
_DATING_FILLER = {"fin", "début", "debut", "ou", "d", "dd", "et", "e", "année", "années", "annee", "annees"}


def period_for_dating(dating: str) -> str:
    """"Middle Kingdom" / "First Intermediate Period" only when the dating is clear."""
    text = unicodedata.normalize("NFC", dating or "")
    middle = bool(_KING_RE.search(text) or _MOYEN_RE.search(text))
    dynasties = _DYNASTY_RE.findall(text)
    if any(d == "XIII" for d in dynasties):
        return UNKNOWN
    middle = middle or bool(dynasties)
    fip = bool(_FIP_RE.search(text))
    rest = _KING_RE.sub(" ", text)
    rest = _DYNASTY_RE.sub(" ", rest)
    rest = _MOYEN_RE.sub(" ", rest)
    rest = _FIP_RE.sub(" ", rest)
    leftovers = [w for w in re.findall(r"[^\W\d_]+", rest.lower()) if w not in _DATING_FILLER]
    if leftovers or (middle and fip) or not (middle or fip):
        return UNKNOWN
    return PERIOD_MK if middle else PERIOD_FIP


@dataclass
class WitnessInfo:
    necropolis: str = ""
    dating: str = ""
    period: str = UNKNOWN


def build_witness_index(documents: list[dict]) -> dict[str, WitnessInfo]:
    """witness siglum -> info. A siglum listed twice with different data is unknown."""
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for doc in documents:
        grouped[str(doc.get("witness", "")).strip()].append(doc)
    index: dict[str, WitnessInfo] = {}
    for witness, docs in grouped.items():
        if not witness:
            continue
        keys = {(str(d.get("necropolis", "")).strip(), str(d.get("dating", "")).strip()) for d in docs}
        if len(keys) != 1:
            index[witness] = WitnessInfo()
            continue
        necropolis, dating = next(iter(keys))
        index[witness] = WitnessInfo(necropolis, dating, period_for_dating(dating))
    return index


def witness_prefix(witness: str) -> str:
    """Leading letters of the siglum (`B3Bo` -> `B`, `Sq3Ca` -> `Sq`, `Pap.Gard.II` -> `Pap`)."""
    match = re.match(r"[A-Za-z]+", witness.strip())
    return match.group(0) if match else "(none)"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def strip_translation(value: object) -> str:
    """The French text without its surrounding quotes, on one line."""
    text = " ".join(str(value or "").split())
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()
    elif text[:1] == '"' and text.count('"') == 1:
        text = text[1:].strip()
    return text


def content_id(index: int, spell: str, code_text: str, witness: str, transliteration: str) -> str:
    parts = [
        f"index={index}",
        f"spell={spell}",
        f"code_text={code_text}",
        f"witness={witness}",
        f"transliteration_gold={transliteration}",
    ]
    digest = hashlib.blake2b("\x1f".join(parts).encode("utf-8"), digest_size=6)
    return f"MORTEXVAR_{digest.hexdigest().upper()}"


def grammar_notes(spell: str, code_text: str, witness: str, info: WitnessInfo | None) -> str:
    parts = [f"CT spell: {spell}", f"de Buck: {code_text}", f"witness: {witness}"]
    if info is not None:
        if info.necropolis:
            parts.append(f"necropolis: {info.necropolis}")
        if info.dating:
            parts.append(f"dating: {info.dating}")
    parts.append("translation language: fr")
    return "; ".join(parts)


def to_schema(index: int, record: dict, transliteration: str, info: WitnessInfo | None, sha: str) -> dict:
    spell = " ".join(str(record.get("spell", "")).split())
    code_text = " ".join(str(record.get("code_text", "")).split())
    witness = " ".join(str(record.get("witness", "")).split())
    out = {column: "" for column in REQUIRED_COLUMNS}
    out.update(
        {
            "source": SOURCE,
            "source_text_id": content_id(index, spell, code_text, witness, transliteration),
            "source_sentence_id": f"M{index:06d}",
            "language_stage": STAGE,
            "script_type": "hieroglyphic/hieratic",
            "genre": "unknown",
            "period": info.period if info else UNKNOWN,
            "hieroglyphs": "",
            "mdc": "",
            "sign_sequence": transliteration,
            "transliteration_gold": transliteration,
            "translation": strip_translation(record.get("translation", "")),
            "grammar_notes": grammar_notes(spell, code_text, witness, info),
            "source_ref": f"database.mortexvar.com bundle sha256:{sha[:12]} row {index}",
            "review_status": "seed",
            "display_sequence": transliteration,
            "aesthetic_arrangement_flag": False,
        }
    )
    return out


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

EXCLUSION_REASONS = [
    "empty_transliteration",
    "lacuna_only",
    "lacuna_a35",
    "lacuna_paren",
    "unread_token",
    "editorial_gloss",
    "unsearchable",
]


@dataclass
class ImportReport:
    total: int = 0
    excluded: collections.Counter = field(default_factory=collections.Counter)
    unexpected_chars: collections.Counter = field(default_factory=collections.Counter)
    rows_with_o_to_q: int = 0
    kept_by_prefix: collections.Counter = field(default_factory=collections.Counter)
    kept_by_necropolis: collections.Counter = field(default_factory=collections.Counter)
    kept_by_period: collections.Counter = field(default_factory=collections.Counter)
    kept_without_document: int = 0

    @property
    def kept(self) -> int:
        return self.total - sum(self.excluded.values())


def convert(
    lines: list[dict], documents: list[dict], sha: str = "", limit: int = 0
) -> tuple[pd.DataFrame, ImportReport]:
    witnesses = build_witness_index(documents)
    report = ImportReport()
    rows: list[dict] = []
    for index, record in enumerate(lines):
        report.total += 1
        raw = str(record.get("transliteration", "") or "")
        reason = classify_transliteration(raw)
        if reason:
            report.excluded[reason] += 1
            continue
        transliteration = convert_transliteration(raw)
        if not search_fold(transliteration):
            report.excluded["unsearchable"] += 1
            continue
        witness = " ".join(str(record.get("witness", "")).split())
        info = witnesses.get(witness)
        report.unexpected_chars.update(
            ch for ch in transliteration if ch not in EXPECTED_CHARS and not ch.isspace()
        )
        if "o" in unicodedata.normalize("NFC", raw):
            report.rows_with_o_to_q += 1
        report.kept_by_prefix[witness_prefix(witness)] += 1
        report.kept_by_necropolis[(info.necropolis or UNKNOWN) if info else "(no document)"] += 1
        report.kept_by_period[info.period if info else UNKNOWN] += 1
        if info is None:
            report.kept_without_document += 1
        rows.append(to_schema(index, record, transliteration, info, sha or ("0" * 12)))
        if limit and len(rows) >= limit:
            break
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS), report


# ---------------------------------------------------------------------------
# Vocabulary overlap against the corpus
# ---------------------------------------------------------------------------

_FRAGMENT_SPLIT_RE = re.compile(r"[.\-=\s]+")


def word_tokens(transliteration: str) -> list[str]:
    """Whole-word tokens under the app's search fold."""
    return search_fold(transliteration).split()


def fragment_tokens(transliteration: str) -> list[str]:
    """Tokens with `.`, `-` and `=` treated as separators before the fold."""
    out = []
    for piece in _FRAGMENT_SPLIT_RE.split(str(transliteration)):
        folded = search_fold(piece)
        if folded:
            out.extend(folded.split())
    return out


def vocabulary_overlap(donor: list[str], corpus: list[str], tokenizer) -> dict:
    corpus_vocab: set[str] = set()
    for text in corpus:
        corpus_vocab.update(tokenizer(text))
    counts: collections.Counter = collections.Counter()
    for text in donor:
        counts.update(tokenizer(text))
    types = len(counts)
    new_types = sum(1 for token in counts if token not in corpus_vocab)
    occurrences = sum(counts.values())
    new_occurrences = sum(n for token, n in counts.items() if token not in corpus_vocab)
    return {
        "corpus_types": len(corpus_vocab),
        "donor_types": types,
        "donor_types_new": new_types,
        "donor_types_already_in_corpus": types - new_types,
        "donor_tokens": occurrences,
        "donor_tokens_new": new_occurrences,
        "donor_token_coverage_by_corpus": round(1 - new_occurrences / occurrences, 4) if occurrences else None,
    }


def overlap_report(frame: pd.DataFrame, existing: pd.DataFrame) -> dict:
    donor = frame["transliteration_gold"].astype(str).tolist()
    result: dict = {}
    scopes = {"whole_corpus": existing}
    if "language_stage" in existing.columns:
        scopes["earlier_egyptian_only"] = existing[existing["language_stage"] == STAGE]
    for scope, subset in scopes.items():
        corpus = subset["transliteration_gold"].astype(str).tolist()
        result[scope] = {
            "corpus_rows": len(corpus),
            "word_level (search_fold tokens)": vocabulary_overlap(donor, corpus, word_tokens),
            "fragment_level (split on . - =)": vocabulary_overlap(donor, corpus, fragment_tokens),
        }
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_summary(report: ImportReport, frame: pd.DataFrame, tables: Tables, sha: str, extra: dict) -> dict:
    keys = frame["transliteration_gold"].map(dedup_key) if len(frame) else pd.Series([], dtype=str)
    spells = frame["grammar_notes"].str.extract(r"CT spell: ([^;]+)")[0] if len(frame) else pd.Series([], dtype=str)
    return {
        "bundle_sha256": sha,
        "array_sizes": {
            "lines": len(tables.lines),
            "spells": len(tables.spells),
            "documents": len(tables.documents),
        },
        "rows_in": report.total,
        "rows_out": len(frame),
        "excluded_total": sum(report.excluded.values()),
        "excluded_by_reason": {reason: report.excluded.get(reason, 0) for reason in EXCLUSION_REASONS},
        "kept_by_witness_prefix": dict(report.kept_by_prefix.most_common()),
        "kept_by_necropolis": dict(report.kept_by_necropolis.most_common()),
        "kept_by_period": dict(report.kept_by_period.most_common()),
        "kept_without_document_row": report.kept_without_document,
        "unique_readings_exact": int(frame["transliteration_gold"].nunique()) if len(frame) else 0,
        "unique_readings_yod_insensitive_fold": int(keys.nunique()),
        "spells_kept": int(spells.nunique()),
        "rows_with_o_mapped_to_q": report.rows_with_o_to_q,
        "unexpected_characters": dict(report.unexpected_chars.most_common()),
        **extra,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("bundle", help="the site bundle (app.<hash>.js), kept outside the repo")
    parser.add_argument("--output", required=True, help="donor CSV (outside data/)")
    parser.add_argument("--summary", required=True, help="summary JSON (outside data/)")
    parser.add_argument(
        "--expect-sha256", default=PINNED_SHA256, help="override the pinned digest (default: the 2026-10-28 bundle)"
    )
    parser.add_argument(
        "--existing",
        default=str(EXAMPLES),
        help="corpus to measure vocabulary overlap and duplicates against (read only); '' to skip.",
    )
    parser.add_argument(
        "--drop-duplicates",
        action="store_true",
        help="drop rows whose reading repeats inside the import or is already in --existing.",
    )
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    for target in (args.output, args.summary):
        refuse_output_under_data(target)
    refuse_unsafe_output(args.output, args.existing or None)

    sha = verify_sha256(args.bundle, args.expect_sha256)
    source = Path(args.bundle).read_text(encoding="utf-8")
    tables = split_tables(extract_json_literals(source))
    frame, report = convert(tables.lines, tables.documents, sha=sha, limit=args.limit)

    existing = None
    if args.existing and Path(args.existing).exists():
        existing = pd.read_csv(
            args.existing, dtype=str, usecols=["source", "language_stage", "transliteration_gold"]
        ).fillna("")

    extra: dict = {}
    keys = frame["transliteration_gold"].map(dedup_key) if len(frame) else pd.Series([], dtype=str)
    if existing is not None and len(frame):
        seen = set(existing["transliteration_gold"].map(dedup_key))
        unique_keys = set(keys)
        extra["unique_readings_already_in_corpus"] = len(unique_keys & seen)
        extra["unique_readings_net_new"] = len(unique_keys - seen)
        extra["vocabulary_overlap"] = overlap_report(frame, existing)
    if args.drop_duplicates and len(frame):
        before = len(frame)
        frame, internal, in_corpus = deduplicate(frame, existing)
        extra["drop_duplicates"] = {"before": before, "internal": internal, "already_in_corpus": in_corpus}

    summary = build_summary(report, frame, tables, sha, extra)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"rows in   {summary['rows_in']:>8,}")
    for reason in EXCLUSION_REASONS:
        print(f"  excluded {reason:<22}{summary['excluded_by_reason'][reason]:>8,}")
    print(f"rows out  {summary['rows_out']:>8,}")
    print(f"unique readings (yod-insensitive fold) {summary['unique_readings_yod_insensitive_fold']:,}")
    print(f"wrote {output} and {args.summary}")


if __name__ == "__main__":
    main()
