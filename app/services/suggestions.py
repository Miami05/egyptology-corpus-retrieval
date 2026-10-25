from __future__ import annotations

import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from dataclasses import replace as dataclasses_replace
from math import sqrt

import pandas as pd

from app.data.query import parse_query
from app.data.normalizer import (
    drop_superfluous_text,
    fold_letter_variants,
    fold_plural_marker,
    fold_weak_consonant_marker,
    nfc,
    normalize_mdc,
    normalize_notation,
    normalize_sign_sequence,
    normalize_transliteration,
    normalize_whitespace,
    superfluous_kept_words,
)
from app.retrieval.scorer import (
    effective_surplus_penalty,
    reading_order_score,
    token_overlap_score,
    tokenize_query,
)

TOKEN_RE = re.compile(r"[\s|:;\-,=~{}\[\]().]+")
LOOSE_MARKER_RE = re.compile(r"[|:;\-,=~{}\[\]().]+")
# Characters the strict key drops: editorial brackets (round, square, curly, angle,
# half-brackets) and the morpheme dot. Their *contents* are kept — `(w)di̯` keeps its
# w — so only the marks vanish, never a letter.
STRICT_DROP_RE = re.compile(r"[()\[\]{}⟨⟩⸢⸣⸤⸥〈〉.|]+")


@dataclass(frozen=True)
class SuggestionWeights:
    """Weights for ranking grouped reading candidates.

    This layer re-ranks the readings that retrieval already ordered, so its weights
    decide what reaches the top 3. Keep `relative_score` dominant: it carries the
    tuned retrieval signal (including IDF-weighted overlap), and when this layer
    recomputes too much of its own similarity it can push a well-retrieved parallel
    out of the top 3.
    """

    relative_score: float = 0.24
    mean_score: float = 0.12
    translit_overlap: float = 0.20
    char_similarity: float = 0.16
    exact_or_near: float = 0.12
    reading_similarity: float = 0.08
    support: float = 0.05
    lemma_density: float = 0.03
    # Not a weight (never part of the weight mass): Tversky penalty on the
    # candidate reading's surplus tokens inside translit_overlap. At 1.0 the
    # overlap is symmetric Jaccard, which lets a one-token reading outscore the
    # full sentence that contains the whole query — see idf_overlap_score, whose
    # docstring also records how 0.3 was chosen and what the holdout showed.
    surplus_penalty: float = 0.3
    # Not a weight either (Experiment 1, 2026-09-05 — see
    # docs/v4-answerability-and-v5-rule.md). A structural switch, off by default:
    # when True the `translit_overlap` signal is not recomputed here at all, it is
    # read from the `idf_overlap_score` column retrieval already produced for the
    # candidate's rows (the group maximum, as `reading_similarity` does). The
    # weights are untouched; only what the translit_overlap slot *carries* changes.
    # Frames without that column (hand-built test frames) fall back to the
    # recomputed value, so the switch can never turn a suggestion into an error.
    carry_forward_idf: bool = False

    def replace(self, **changes: float | bool) -> SuggestionWeights:
        return dataclasses_replace(self, **changes)


# The three pre-registered Experiment 1 configurations. Named presets rather than a
# swept grid: each is a structural choice, and CFG-B introduces no new number (0.40
# is 0.24 + 0.16, the two existing weights summed). Selection is on the held-out set
# only; see the doc.
SUGGESTION_PRESETS: dict[str, SuggestionWeights] = {
    "default": SuggestionWeights(),
    # CFG-A — carry forward: translit_overlap becomes retrieval's IDF-weighted
    # overlap instead of a freshly recomputed plain overlap. Weights unchanged.
    "cfg_a": SuggestionWeights(carry_forward_idf=True),
    # CFG-B — redistribute: relative_score absorbs char_similarity's mass.
    "cfg_b": SuggestionWeights(relative_score=0.40, char_similarity=0.0),
    # CFG-C — both.
    "cfg_c": SuggestionWeights(
        relative_score=0.40, char_similarity=0.0, carry_forward_idf=True
    ),
}

SUGGESTION_PRESET_ENV = "WHYPTOLOGY_SUGGESTION_PRESET"


def resolve_suggestion_preset(name: str | None) -> SuggestionWeights:
    """The `SuggestionWeights` for a preset name; empty/None → today's default.

    Unknown names raise rather than falling back silently: an evaluation run that
    misspells its configuration must fail, not quietly report the baseline again.
    """
    key = (name or "").strip().lower()
    if not key:
        return SUGGESTION_PRESETS["default"]
    if key not in SUGGESTION_PRESETS:
        raise ValueError(
            f"Unknown {SUGGESTION_PRESET_ENV}={name!r}; "
            f"known presets: {', '.join(sorted(SUGGESTION_PRESETS))}"
        )
    return SUGGESTION_PRESETS[key]


# Read once, at import. With the environment variable unset this is
# `SuggestionWeights()` — byte-identical to the behaviour that produced every
# published number — so the switch is invisible unless a run asks for it.
DEFAULT_SUGGESTION_WEIGHTS = resolve_suggestion_preset(os.environ.get(SUGGESTION_PRESET_ENV))


@dataclass(frozen=True)
class ReadingSuggestion:
    candidate_transliteration: str
    confidence_score: float
    supporting_example_count: int
    supporting_sources: list[str]
    evidence_summary: str


def _safe_str(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _token_set(value: object) -> set[str]:
    text = normalize_transliteration(_safe_str(value))
    return {token for token in TOKEN_RE.split(text) if token}


def lemma_ids(value: object) -> set[str]:
    """The lemma IDs in a `lemma_sequence` cell.

    Cells are whitespace-separated `id|lemma` pairs (TLA) or bare ids (AES). The old
    code ran `_token_set` over the cell, which splits on `|` as well, so the folded
    lemma strings (`ndj`, `aha`) landed in the evidence line's list of common lemma
    IDs beside the numbers. Only the part before the bar is an id.
    """
    ids: set[str] = set()
    for part in _safe_str(value).split():
        head = part.split("|", 1)[0].strip()
        if head:
            ids.add(head)
    return ids


def unfold_shared_tokens(shared: list[str], candidate_transliteration: object) -> list[str]:
    """Show shared *folded* tokens as the candidate's own Unicode words.

    The overlap is computed on the loose ASCII fold (`ꜥḥꜥ.n` → `aha n`), so the raw
    shared tokens read `aha, n, stkh` — to an Egyptologist that looks broken. Map
    each back to the whitespace-separated word of `candidate_transliteration` whose
    loose fold contains it, keep first-occurrence order, and fall back to the folded
    form for anything that does not map (e.g. a token only the query had).
    """
    words = _safe_str(candidate_transliteration).split()
    by_fold: dict[str, str] = {}
    for word in words:
        for folded in tokenize_query(loose_reading_form(word)):
            by_fold.setdefault(folded, word)
    shown: list[str] = []
    for token in shared:
        word = by_fold.get(token, token)
        if word not in shown:
            shown.append(word)
    return shown


def strict_reading_key(value: object) -> str:
    """Identity key for a reading: two readings share it only if they are the same
    string of sounds.

    NFC, lower-case, `⸗` → `=`, editorial brackets and dots removed, everything else
    kept. In particular every Egyptological letter stays distinct (ꜣ ≠ ꜥ, ḥ ≠ h,
    ḫ ≠ ẖ, ṯ ≠ t, ḏ ≠ d), the yod ꞽ is a letter and is kept, and `=` survives so a
    suffix pronoun `=ꞽ` does not collapse to the empty string.

    This replaced the old canonical key, which ran the ASCII search fold first and
    merged 256 sentence-level readings that differ in a consonant (ꜣ/ꜥ 85 pairs, ḥ/h
    986 tokens) — corrupting suggestion grouping and support counts. The ASCII fold
    still exists for *search*; it is simply not an identity.

    The `.PL`/`.pl` plural marker is folded to `.w` before the dots are dropped
    below — once the dots are gone the marker is unrecognisable.

    TLA's weak-consonant marker is folded with it (item D′, 2026-09-06): `i̯` → `ꞽ`
    and `u̯` → `w`. It is a *notation* for a weak radical, not a different sound —
    `rdi̯ =f` and `rdꞽ =f` are one reading in two editions' conventions, and the
    search fold and the loose form already treat them as one, so keeping them apart
    here made the same sentence two suggestion groups. 26,914 of 130,472 corpus rows
    have their key rewritten by this and 25 pairs of distinct readings merge.
    Consonants stay distinct as before: ꜣ ≠ ꜥ, ḥ ≠ h, ḫ ≠ ẖ, ṯ ≠ t, ḏ ≠ d, and a
    genuine spelling variant like `ꞽt` / `ꞽtꞽ` remains two readings.

    Two more notation folds, both lossless (fix round 1, A16/A48): the variant letter
    encodings `ʿ ȝ ỉ` are the letters `ꜥ ꜣ ꞽ` (`fold_letter_variants`; 0 corpus rows use
    them, so only typed queries change), and brackets around either half of the plural
    notation no longer leave a second `w` (`šms(.w).pl`, `šms.w(.pl)` → `šmsw`, like
    `šms.w`; 82 corpus rows).
    """
    text = nfc(_safe_str(value)).lower().replace("⸗", "=")
    text = fold_letter_variants(text)
    text = fold_plural_marker(text)
    text = fold_weak_consonant_marker(text)
    text = STRICT_DROP_RE.sub("", text)
    return normalize_whitespace(text)


def notation_folded_reading_key(value: object) -> str:
    """`strict_reading_key` with TLA's weak-consonant notation folded (`i̯`→`ꞽ`, `u̯`→`w`).

    Item D′'s measurement key (2026-09-06). Applied to the raw reading *before* the
    strict key, which is equivalent to folding inside it: the fold composes to NFC
    itself and touches no character the strict key drops or rewrites.

    Once the fold is part of `strict_reading_key` this returns exactly what
    `strict_reading_key` returns — the fold is idempotent — and the two are pinned
    equal by `tests/test_notation_fold.py`. It stays a separate name so the
    duplicate-slot metric keeps measuring the same thing whether or not the fold
    shipped, and so a later change to the key that undid the fold would fail loudly.
    """
    return strict_reading_key(fold_weak_consonant_marker(_safe_str(value)))


def canonical_reading(value: object) -> str:
    """The key readings are grouped and compared by. Strict — see strict_reading_key."""
    return strict_reading_key(value)


def comparison_key(value: object) -> str:
    """`canonical_reading` with superfluous `{…}` text deleted: the key a query and a
    candidate are *compared* by (exactness, token overlap, character similarity).

    The grouping key keeps the braced words (only the braces go), so two editions
    that differ only in what they mark superfluous stay two suggestions. But the
    search key deletes that text (A17), so comparing on the grouping key let deleted
    text back in: the query `ḥtp {n nswt}` was "the same normalized query reading"
    as the candidate `ḥtp n nswt` at 0.92, and `ḥtp` got 0.30 (Astra review).
    """
    return strict_reading_key(drop_superfluous_text(nfc(_safe_str(value))))


def aligned_annotation(
    transliteration: object, lemma_sequence: object, upos: object
) -> list[tuple[str, str, str]]:
    """(token, lemma id, part-of-speech) triples, or [] when the row is not aligned.

    `lemma_sequence` holds whitespace-separated `id|lemma` pairs (TLA) or bare ids
    (AES); `upos` holds whitespace-separated tags. A row is aligned only when all
    three counts are equal — true of 37,638 of the 38,191 corpus rows that carry
    lemma ids at all (553 AES rows are not). Returning [] rather than zipping the
    shorter of the three is the whole point: a token matched against the wrong tag
    would rename the wrong word.
    """
    tokens = _safe_str(transliteration).split()
    lemmas = _safe_str(lemma_sequence).split()
    tags = _safe_str(upos).split()
    if not tokens or len(tokens) != len(lemmas) or len(tokens) != len(tags):
        return []
    return [
        (token, lemma.split("|", 1)[0].strip(), tag)
        for token, lemma, tag in zip(tokens, lemmas, tags)
    ]


def name_normalised_reading_key(
    transliteration: object, lemma_sequence: object = "", upos: object = ""
) -> str:
    """`strict_reading_key`, with every aligned proper noun replaced by its lemma id.

    Item D (2026-09-06). `strict_reading_key` is an identity on *sounds*, so
    `ḥtp-ḏi̯ wsꞽr` and `ḥtp-ḏi̯ (w)sr(.w)` are two different readings — which is
    right for a verb and wrong for Osiris. Substituting the TLA lemma id for a token
    the corpus tags PROPN makes the two one reading and leaves everything else
    exactly as strict as before: a verb in two inflections has two lemmas-in-context
    but is not PROPN, so it does not collapse.

    A row with no full token/lemma/upos alignment (BBAW, Ramses, the 553 misaligned
    AES rows — 71% of the corpus) has no proper nouns to normalise and falls back to
    the plain strict key, byte for byte.

    Lemma ids are numeric (`107500`) or Demotic (`dm1610`) and cannot be mistaken for
    a transliteration token, so they are substituted bare, with no marker.
    """
    annotation = aligned_annotation(transliteration, lemma_sequence, upos)
    if not annotation:
        return strict_reading_key(transliteration)
    return strict_reading_key(
        " ".join(
            lemma_id if tag == "PROPN" and lemma_id else token
            for token, lemma_id, tag in annotation
        )
    )


def loose_reading_form(value: object) -> str:
    """Display / near-match form: ASCII-folded and stripped of editorial marks.

    Deliberately lossy (ḥ and h both become h), so it can tell that a user's plain
    ASCII `htp` means the corpus's `ḥtp` and that `n.t` and `n(.ꞽ).t` are one word.
    Never use it to decide that two corpus readings are identical.
    """
    text = normalize_transliteration(_safe_str(value))
    text = LOOSE_MARKER_RE.sub(" ", text)
    return normalize_mdc(text)


def has_egyptological_letters(text: object) -> bool:
    """Whether `text` contains a non-ASCII letter or a combining mark (ꜣ ꜥ ꞽ ḥ ḏ u̯ …).

    A query typed in plain ASCII/MdC has none, and may mean any of the diacritic
    letters it folds together. A query that does contain one named its consonants, so
    the lossy ASCII fold must not be used to call a different consonant a match (A54).
    """
    return any(
        not char.isascii() and (char.isalpha() or unicodedata.category(char).startswith("M"))
        for char in nfc(_safe_str(text))
    )


def unfolded_reading_form(value: object) -> str:
    """`loose_reading_form` without the lossy letter fold: markers become spaces, but
    every letter stays as written (ꜣ ≠ ꜥ, ḥ ≠ h). The notation is normalised by
    `normalize_notation`, the same lossless helper the search key starts from, so a
    letter variant the search accepts (`ʿnḫ`) is the same letter here (`ꜥnḫ`), and the
    plural, weak-consonant and superfluous-text rules agree with retrieval. Used for
    the query words typed with Egyptological letters (A54), so `n.t` and `n(.t)` still
    share words while `ꜥḥꜥ` and `ꜣḥꜥ` do not.
    """
    text = normalize_notation(_safe_str(value).replace("⸗", "="))
    text = STRICT_DROP_RE.sub("", LOOSE_MARKER_RE.sub(" ", text))
    return normalize_whitespace(text)


def _ngram_cosine(left_form: str, right_form: str) -> float:
    """Cosine similarity of character 2-4-grams of two already-formed strings."""
    left_text = f" {left_form} "
    right_text = f" {right_form} "
    if not left_text.strip() or not right_text.strip():
        return 0.0
    left_counts: Counter[str] = Counter()
    right_counts: Counter[str] = Counter()
    for ngram_size in (2, 3, 4):
        for index in range(0, max(len(left_text) - ngram_size + 1, 0)):
            left_counts[left_text[index : index + ngram_size]] += 1
        for index in range(0, max(len(right_text) - ngram_size + 1, 0)):
            right_counts[right_text[index : index + ngram_size]] += 1
    if not left_counts or not right_counts:
        return 0.0
    numerator = sum(left_counts[token] * right_counts.get(token, 0) for token in left_counts)
    left_norm = sqrt(sum(value * value for value in left_counts.values()))
    right_norm = sqrt(sum(value * value for value in right_counts.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


@dataclass(frozen=True)
class QueryForms:
    """How the words of one text query may be compared with a candidate reading (A54).

    The lossy ASCII fold may only stand in for letters the user did *not* type. That
    is decided per word, on the query as typed (`query_raw`), never on the reading it
    was resolved to: `htp dji nswt` reaches this layer as `htp ḏi nswt`, and the `ḏ`
    there is the app's own conversion of `dj`, not a letter the user chose.

    - `loose`: every word was typed in plain ASCII/MdC → the old loose comparison,
      byte for byte (`loose_reading_form` on both sides).
    - `strict`: every word carries an Egyptological letter → letters compared as
      written (`unfolded_reading_form` on both sides).
    - `mixed`: e.g. `htp ḏi nswt` typed with one palette letter. Each query token
      keeps its own constraint (`tokens`: the token and whether it may match
      loosely), so an ASCII token is compared through the fold and a Unicode one as
      written, and neither can stand in for the other (see `candidate`).

    Superfluous `{…}` text is deleted over the whole reading before it is split into
    words (`superfluous_kept_words`), so a brace spanning a space (`ḥtp {n nswt}`)
    deletes what it encloses here exactly as it does in the search key.
    """

    mode: str
    query_form: str
    tokens: tuple[tuple[str, bool], ...] = ()

    @property
    def loose_words(self) -> frozenset[str]:
        return frozenset(token for token, loose in self.tokens if loose)

    @property
    def strict_words(self) -> frozenset[str]:
        return frozenset(token for token, loose in self.tokens if not loose)

    @classmethod
    def build(cls, reading: str, query_raw: str) -> QueryForms:
        reading_words = _safe_str(reading).split()
        raw_words = _safe_str(query_raw).split()
        if len(raw_words) == len(reading_words):
            flags = [not has_egyptological_letters(raw) for raw in raw_words]
        else:
            # The resolution changed the word count (it never does today); decide per
            # resolved word, but a raw query with no Egyptological letter stays loose.
            whole = not has_egyptological_letters(query_raw)
            flags = [whole or not has_egyptological_letters(word) for word in reading_words]
        if all(flags):
            return cls("loose", loose_reading_form(reading))
        if not any(flags):
            return cls("strict", unfolded_reading_form(reading))
        tokens: list[tuple[str, bool]] = []
        kept_words = superfluous_kept_words(nfc(_safe_str(reading)))
        for word, loose in zip(kept_words, flags):
            form = loose_reading_form(word) if loose else unfolded_reading_form(word)
            tokens.extend((token, loose) for token in form.split())
        return cls("mixed", " ".join(token for token, _ in tokens), tuple(tokens))

    @property
    def loose(self) -> bool:
        return self.mode == "loose"

    def candidate(self, value: object) -> str:
        """The candidate reading in the form comparable with `query_form`.

        In mixed mode each candidate word is shown as the query token it can stand
        for: as written when it equals a strict (Unicode) query token, folded when its
        fold equals a loose (ASCII) one. Words and query tokens are paired by a
        maximum matching (preferring the token at the word's own position), so a word
        that could serve either is reassigned when that lets another word meet its
        token, and `ꜥḥꜥ ꜥḥꜥ` meets both words of the query `aha ꜥḥꜥ`, while
        `ꜣḥꜥ ꜣḥꜥ` only ever meets `aha` (Astra review: a single global loose set
        made the two candidates identical).
        """
        if self.mode == "loose":
            return loose_reading_form(value)
        if self.mode == "strict":
            return unfolded_reading_form(value)
        words = unfolded_reading_form(value).split()
        folds = [loose_reading_form(word) for word in words]
        tokens = self.tokens

        def fits(index: int, slot: int) -> bool:
            token, loose = tokens[slot]
            return (folds[index] if loose else words[index]) == token

        # Each word's compatible query-token slots, tried in this order: the token at
        # its own position, then strict tokens (they name their letters), then loose.
        options = [
            sorted(
                (slot for slot in range(len(tokens)) if fits(index, slot)),
                key=lambda slot, i=index: (slot != i, tokens[slot][1], slot),
            )
            for index in range(len(words))
        ]
        # Maximum matching (augmenting paths), so a word that could serve either a
        # strict or a loose token never takes the loose one when that leaves the
        # strict one unmet (Astra re-review: `aha ꜥḥꜥ n` against `ꜥḥꜥ n ꜣḥꜥ`, where
        # the first word took `aha` positionally and the strict `ꜥḥꜥ` went unmatched).
        owner: dict[int, int] = {}

        def assign(index: int, seen: set[int]) -> bool:
            for slot in options[index]:
                if slot in seen:
                    continue
                seen.add(slot)
                if slot not in owner or assign(owner[slot], seen):
                    owner[slot] = index
                    return True
            return False

        for index in range(len(words)):
            assign(index, set())
        chosen: list[str | None] = [None] * len(words)
        for slot, index in owner.items():
            chosen[index] = tokens[slot][0]
        # An unmatched word: shown as the token form it duplicates, else as written.
        for index, (word, folded) in enumerate(zip(words, folds)):
            if chosen[index] is not None:
                continue
            if word in self.strict_words:
                chosen[index] = word
            elif folded and folded in self.loose_words:
                chosen[index] = folded
            else:
                chosen[index] = word
        return " ".join(word for word in chosen if word)

    def char_similarity(self, query_key: str, candidate_key: str) -> float:
        if self.mode == "loose":
            return char_ngram_similarity(query_key, candidate_key, fold=True)
        if self.mode == "strict":
            return char_ngram_similarity(query_key, candidate_key, fold=False)
        return _ngram_cosine(self.query_form, self.candidate(candidate_key))

    def shown_shared(self, shared: list[str], candidate_transliteration: str) -> list[str]:
        """Shared words as the candidate writes them: loose words are mapped back to
        the candidate's own Unicode word, strict ones are already as written."""
        if self.mode == "strict":
            return list(shared)
        if self.mode == "loose":
            return unfold_shared_tokens(shared, candidate_transliteration)
        shown: list[str] = []
        strict_words = self.strict_words
        # Ordered as the loose mode orders them (by ASCII fold), not ASCII-first.
        for token in sorted(shared, key=lambda t: (loose_reading_form(t), t)):
            word = (
                token
                if token in strict_words
                else unfold_shared_tokens([token], candidate_transliteration)[0]
            )
            if word not in shown:
                shown.append(word)
        return shown


def char_ngram_similarity(left: object, right: object, fold: bool = True) -> float:
    """Cosine similarity of character 2-4-grams. `fold=False` compares the letters as
    written (`unfolded_reading_form`) instead of the lossy ASCII fold."""
    form = loose_reading_form if fold else unfolded_reading_form
    return _ngram_cosine(form(left), form(right))


def _group_lcs(query_groups: list[str], candidate_groups: list[str]) -> float:
    """Ordered coverage of the query's sign groups: LCS length / query length."""
    if not query_groups or not candidate_groups:
        return 0.0
    previous = [0] * (len(candidate_groups) + 1)
    for q in query_groups:
        current = [0]
        for j, c in enumerate(candidate_groups, start=1):
            if q == c:
                current.append(previous[j - 1] + 1)
            else:
                current.append(max(current[-1], previous[j]))
        previous = current
    return previous[-1] / len(query_groups)


def set_overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _source_label(row: pd.Series) -> str:
    source = _safe_str(row.get("source")) or "unknown"
    text_id = _safe_str(row.get("source_text_id")) or "no_text_id"
    sentence_id = _safe_str(row.get("source_sentence_id")) or "no_sentence_id"
    return f"{source}/{text_id}/{sentence_id}"


def _evidence_summary(
    group: pd.DataFrame,
    query_mdc: str,
    query_reading_order: str,
    candidate_transliteration: str,
    query_hieroglyphs: str = "",
    forms: QueryForms | None = None,
) -> str:
    bits: list[str] = []
    if query_hieroglyphs:
        query_groups = query_hieroglyphs.split()
        best_coverage = 0.0
        exact = False
        for value in group.get("hieroglyphs_norm", []):
            groups = str(value).split()
            best_coverage = max(best_coverage, _group_lcs(query_groups, groups))
            exact = exact or " ".join(groups) == query_hieroglyphs
        if exact:
            bits.append("same sign groups as the query")
        elif best_coverage > 0.0:
            bits.append(f"sign groups cover {best_coverage:.0%} of the query, in order")
    candidate_key = comparison_key(candidate_transliteration)
    query_key = comparison_key(query_mdc)
    # Words the user typed with Egyptological letters keep every letter here (see
    # QueryForms), so a different consonant is never "shared" (A54).
    if forms is None:
        forms = QueryForms.build(query_mdc, query_mdc)
    candidate_loose = forms.candidate(candidate_transliteration)
    query_loose = forms.query_form

    if query_key and candidate_key == query_key:
        bits.append("same normalized query reading")
    elif query_loose and candidate_loose == query_loose:
        bits.append("same simplified query reading")
    elif query_key and forms.char_similarity(query_key, candidate_key) >= 0.72:
        bits.append("near simplified query reading")

    query_reading_norm = normalize_sign_sequence(query_reading_order)
    if query_reading_norm:
        candidate_readings = [
            _safe_str(row.get("normalized_reading_order_norm"))
            or normalize_sign_sequence(_safe_str(row.get("normalized_reading_order")))
            for _, row in group.iterrows()
        ]
        # "Same" means the same sign sequence, in order (audit item 6): this used
        # to be a set overlap >= 0.92, which called `A B` and `B A` the same.
        query_sequence = tokenize_query(query_reading_norm)
        if any(tokenize_query(value) == query_sequence for value in candidate_readings):
            bits.append("same normalized reading order")
        elif any(
            reading_order_score(query_reading_norm, value) > 0.0
            for value in candidate_readings
        ):
            bits.append("similar normalized reading order")

    query_tokens = set(tokenize_query(query_loose or query_key))
    candidate_tokens = set(tokenize_query(candidate_loose or candidate_key))
    if query_tokens and candidate_tokens:
        shared = sorted(query_tokens & candidate_tokens)
        if shared:
            shown = ", ".join(forms.shown_shared(shared, candidate_transliteration)[:8])
            bits.append(f"shared transliteration tokens: {shown}")

    lemma_sets = [
        lemma_ids(row.get("lemma_sequence"))
        for _, row in group.iterrows()
        if lemma_ids(row.get("lemma_sequence"))
    ]
    shared_lemmas = set.intersection(*lemma_sets) if lemma_sets else set()
    if shared_lemmas:
        shown = ", ".join(sorted(shared_lemmas)[:8])
        bits.append(f"lemma IDs common to this reading's rows: {shown}")

    formula_bits = []
    for field, label in [
        ("formula_type", "formula type"),
        ("formula_slot", "formula slot"),
        ("genre", "genre"),
    ]:
        values = {_safe_str(value) for value in group.get(field, []) if _safe_str(value)}
        if len(values) == 1:
            formula_bits.append(label)
    if formula_bits:
        bits.append("shared context: " + ", ".join(formula_bits))

    support_count = len(group)
    bits.append(f"supported by {support_count} similar corpus row{'s' if support_count != 1 else ''}")

    return "; ".join(bits)


def absolute_evidence(evidence: float) -> float:
    """One candidate's own absolute match strength, clamped to [0, 1]."""
    return max(0.0, min(1.0, evidence))


def suggest_top_readings(
    retrieval_results: pd.DataFrame,
    query_mdc: str,
    query_reading_order: str = "",
    top_n: int = 3,
    weights: SuggestionWeights = DEFAULT_SUGGESTION_WEIGHTS,
    query_hieroglyphs: str = "",
    debug_signals: list[dict] | None = None,
    query_raw: str | None = None,
) -> list[ReadingSuggestion]:
    """Group the retrieved rows by reading and rank the readings.

    `query_hieroglyphs` is the resegmented sign-group string for a hieroglyph query
    (see app.services.segmentation) — the same grouping retrieval matched on, so
    both layers reason about one segmentation.

    The confidence is a weighted mean over the signals that are *structurally live*
    for this query. A hieroglyph query has no transliteration, so the three
    transliteration-similarity signals (0.48 of the mass) can never fire; the old
    code still divided by the full mass, which compressed every glyph confidence
    below 0.38 and made the numbers incomparable across query types. Dead signals
    now leave the denominator (mirroring combine_scores), and glyph queries get
    their own similarity and exactness signals in the vacated slots.

    That mean is *relative*: `relative_score` and `mean_score` (0.36 of the mass) are
    divided by the pool's own best score, so they are 1.0 for any one-row pool and
    set a floor of about 0.4 on a candidate with almost no overlap (A21). The
    displayed confidence is therefore the relative value times *that candidate's
    own* absolute evidence, its strongest live absolute match (token overlap,
    character similarity, exactness, glyph coverage, reading-order overlap). It is
    per candidate, so one strong candidate in the pool can no longer lift a weak
    one's confidence (fix round 1). The order is still the relative order — the
    factor is applied after sorting — so the displayed confidences need not fall
    monotonically down the list: a candidate ranked second by retrieval can show a
    higher match strength than the first.

    `query_raw` is the query exactly as the user typed it, when `query_mdc` is the
    reading it was already resolved to (the app passes `parse_query(...).reading`).
    Which words may be matched through the lossy ASCII fold is decided on it, per
    word (see QueryForms). Without it `query_mdc` is taken as the typed text.

    `debug_signals`, when a list is passed, receives one dict per candidate group
    with this layer's *own* per-term breakdown (each live signal's weight, raw
    value and weighted contribution, plus the weight mass and the confidence). It
    is a read-only observation hook for Experiment 2's pre-check: nothing is read
    back from it, no branch depends on it, and with the default `None` not a single
    statement of the ranking path changes.
    """
    # The lossy ASCII fold may only stand in for letters the user did not type: it
    # is decided on the query as typed (`query_raw`, or `query_mdc` itself when the
    # caller passes the typed text), before the ASCII-to-Unicode resolution below,
    # which would otherwise make every ASCII query look Unicode (A54).
    typed = _safe_str(query_mdc if query_raw is None else query_raw)

    # A Manuel de Codage or ASCII-digraph query is not a reading, and this layer
    # compares readings as strings of sounds. Resolve it to the transliteration it
    # was understood as first (`htp dji nswt` → `htp ḏi nswt`), so "same simplified
    # query reading" fires for a query typed in the app's own ASCII convention. A
    # Unicode query comes back unchanged.
    query_mdc = parse_query(query_mdc).reading or query_mdc
    # For a hieroglyph query the text signals are not live, so it keeps the old path.
    forms = (
        QueryForms("loose", loose_reading_form(query_mdc))
        if query_hieroglyphs
        else QueryForms.build(query_mdc, typed)
    )

    if retrieval_results.empty:
        return []

    results = retrieval_results.copy()
    results["candidate_transliteration"] = results["transliteration_gold"].map(_safe_str)
    results = results[results["candidate_transliteration"] != ""].copy()
    if results.empty:
        return []

    results["candidate_key"] = results["candidate_transliteration"].map(canonical_reading)
    rows: list[dict] = []
    debug_start = len(debug_signals) if debug_signals is not None else 0
    max_row_score = max(float(value) for value in results["final_score"].fillna(0.0))
    query_key = comparison_key(query_mdc) if not query_hieroglyphs else ""
    query_loose = forms.query_form if not query_hieroglyphs else ""
    query_reading_norm = normalize_sign_sequence(query_reading_order)
    query_glyph_groups = query_hieroglyphs.split()
    surplus_penalty = effective_surplus_penalty(
        query_loose or query_key, weights.surplus_penalty
    )

    # Which signals can fire at all for this query. A weight only joins the
    # denominator when its signal is live, so confidences stay comparable between
    # transliteration and hieroglyph queries.
    text_live = bool(query_key)
    glyph_live = bool(query_glyph_groups)
    reading_live = bool(query_reading_norm)

    for candidate_key, group in results.groupby("candidate_key", sort=False):
        group = group.sort_values("final_score", ascending=False, kind="mergesort").copy()
        best = group.iloc[0]
        best_score = float(best.get("final_score", 0.0) or 0.0)
        # Identical rows (same signs, reading and translation imported twice) are one
        # attestation, not two: they must not inflate support or lemma density.
        distinct = group.drop_duplicates(
            subset=[
                column
                for column in ("hieroglyphs_norm", "candidate_transliteration", "translation")
                if column in group.columns
            ]
        )
        mean_score = float(distinct["final_score"].fillna(0.0).mean())
        support_count = int(len(distinct))
        support_bonus = min(support_count, 5) / 5.0
        best_candidate = best["candidate_transliteration"]
        lemma_density = min(
            sum(1 for value in distinct.get("lemma_sequence", []) if _safe_str(value)),
            5,
        ) / 5.0
        relative_score = best_score / max_row_score if max_row_score > 0 else 0.0
        # mean_score is normalised by the same pool maximum as relative_score;
        # mixing the raw score into a mean of normalised terms silently
        # down-weighted it for every query whose best raw score was below 1.0.
        mean_relative = mean_score / max_row_score if max_row_score > 0 else 0.0

        signals: dict[str, tuple[float, float]] = {
            "relative_score": (weights.relative_score, relative_score),
            "mean_score": (weights.mean_score, mean_relative),
            "support": (weights.support, support_bonus),
            "lemma_density": (weights.lemma_density, lemma_density),
        }

        if text_live:
            candidate_loose = forms.candidate(best_candidate)
            compare_key = comparison_key(best_candidate)
            translit_overlap = max(
                token_overlap_score(query_key, compare_key, surplus_penalty),
                token_overlap_score(query_loose, candidate_loose, surplus_penalty),
            )
            if (
                weights.carry_forward_idf
                and forms.loose
                and "idf_overlap_score" in group.columns
            ):
                # Read, never recompute: this is the number retrieval already
                # scored this candidate's rows with (retrieval is not touched).
                # Only for a query typed wholly in ASCII/MdC: retrieval's overlap is
                # computed on the lossy ASCII key, so for a word typed with
                # Egyptological letters it would credit a different consonant
                # (`ꜣḥꜥ` for `ꜥḥꜥ`) with full overlap (A54, cfg_a/cfg_c).
                translit_overlap = float(
                    group["idf_overlap_score"].fillna(0.0).astype(float).max()
                )
            char_similarity = forms.char_similarity(query_key, compare_key)
            exact_or_near_bonus = 1.0 if compare_key == query_key else 0.0
            if exact_or_near_bonus == 0.0 and query_loose == candidate_loose:
                exact_or_near_bonus = 0.85
            elif exact_or_near_bonus == 0.0 and char_similarity >= 0.82:
                exact_or_near_bonus = 0.65
            signals["translit_overlap"] = (weights.translit_overlap, translit_overlap)
            signals["char_similarity"] = (weights.char_similarity, char_similarity)
            signals["exact_or_near"] = (weights.exact_or_near, exact_or_near_bonus)

        if glyph_live and "hieroglyphs_norm" in group.columns:
            # The candidate group's closest row to the query, in sign terms: ordered
            # coverage of the query's groups (LCS / query length) plus exactness.
            candidate_glyphs = [str(v).split() for v in distinct["hieroglyphs_norm"]]
            glyph_similarity_score = max(
                (_group_lcs(query_glyph_groups, groups) for groups in candidate_glyphs),
                default=0.0,
            )
            glyph_exact = (
                1.0
                if any(" ".join(g) == query_hieroglyphs for g in candidate_glyphs)
                else 0.0
            )
            signals["glyph_similarity"] = (weights.translit_overlap, glyph_similarity_score)
            signals["glyph_exact"] = (weights.exact_or_near, glyph_exact)

        if reading_live:
            reading_similarity = max(
                reading_order_score(
                    query_reading_norm,
                    _safe_str(row.get("normalized_reading_order_norm"))
                    or normalize_sign_sequence(
                        _safe_str(row.get("normalized_reading_order"))
                    ),
                )
                for _, row in group.iterrows()
            )
            signals["reading_similarity"] = (weights.reading_similarity, reading_similarity)

        weight_mass = sum(weight for weight, _ in signals.values())
        weighted = sum(weight * value for weight, value in signals.values())
        candidate_score = weighted / weight_mass if weight_mass > 0 else 0.0
        confidence = max(0.0, min(0.99, candidate_score))

        # The strongest absolute (not pool-relative) match this candidate has on
        # any signal live for the query; 1.0 when none is live (nothing to measure).
        absolute = [
            value
            for name, (_, value) in signals.items()
            if name
            in (
                "translit_overlap",
                "char_similarity",
                "exact_or_near",
                "glyph_similarity",
                "glyph_exact",
                "reading_similarity",
            )
        ]
        evidence = max(absolute) if absolute else 1.0

        if debug_signals is not None:
            debug_signals.append(
                {
                    "candidate_key": candidate_key,
                    "candidate_transliteration": best["candidate_transliteration"],
                    "confidence_score": round(confidence, 3),
                    "weight_mass": weight_mass,
                    "weighted_sum": weighted,
                    "signals": {
                        name: {
                            "weight": weight,
                            "value": value,
                            "weighted": weight * value,
                        }
                        for name, (weight, value) in signals.items()
                    },
                }
            )

        rows.append(
            {
                "candidate_transliteration": best["candidate_transliteration"],
                "confidence_score": round(confidence, 3),
                "evidence": evidence,
                "supporting_example_count": support_count,
                "supporting_sources": [
                    _source_label(row) for _, row in distinct.head(5).iterrows()
                ],
                "evidence_summary": _evidence_summary(
                    group,
                    query_mdc=query_mdc,
                    query_reading_order=query_reading_order,
                    candidate_transliteration=best["candidate_transliteration"],
                    query_hieroglyphs=query_hieroglyphs,
                    forms=forms,
                ),
            }
        )

    # Descending by the *relative* confidence then support; ties break by
    # transliteration in ordinary alphabetical order (they used to break
    # reverse-alphabetically, an accident of a single reverse=True over the whole
    # key). Each candidate's own absolute-evidence factor is applied after sorting,
    # so it can never reorder anything (A21).
    if debug_signals is not None:
        for entry, row in zip(debug_signals[debug_start:], rows):
            relative = entry["confidence_score"]
            entry["relative_confidence"] = relative
            entry["evidence"] = absolute_evidence(row["evidence"])
            entry["confidence_score"] = round(min(0.99, relative * entry["evidence"]), 3)
    rows.sort(
        key=lambda row: (
            -row["confidence_score"],
            -row["supporting_example_count"],
            row["candidate_transliteration"],
        )
    )
    suggestions = []
    for row in rows[:top_n]:
        evidence = absolute_evidence(row["evidence"])
        row = {key: value for key, value in row.items() if key != "evidence"}
        row["confidence_score"] = round(min(0.99, row["confidence_score"] * evidence), 3)
        suggestions.append(ReadingSuggestion(**row))
    return suggestions
