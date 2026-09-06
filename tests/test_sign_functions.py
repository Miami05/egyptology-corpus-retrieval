"""Item C step 1: the sign-function inventory — the fold and the supplement.

Three things are pinned.

1. **The fold is total and correct.** Every `function` value that occurs in either
   shipped table has an entry in `CLASS_FOLD`; the two "or" labels fold to two
   classes, the rest to one; nothing folds to the empty set.
2. **The supplement is exactly the pre-registered thirteen rows** (ROADMAP.md, "Item C
   … Supplement table, written by the lead now (not tuned)"), every row carries
   `source_note = "project supplement"`, and none of its signs is one Nederhof's table
   already covers — the supplement adds, it never overrides.
3. **An absent table degrades to `{unk}`, not to an error.** A deployment that does not
   ship the file must behave as it did before item C.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.services.sign_functions import (
    CLASS_FOLD,
    CLASSES,
    SIGN_FUNCTIONS_PATH,
    SUPPLEMENT_NOTE,
    SUPPLEMENT_PATH,
    UNKNOWN_CLASSES,
    load_sign_functions,
)

# The lead's table, retyped here from the pre-registration so the CSV is checked
# against the decision and not against itself: sign -> {(function, value)}.
PRE_REGISTERED = {
    "\U000133F2": {("phonogram", "w")},                      # Z7
    "\U000133E5": {("typographic", "")},                     # Z2
    "\U000133EA": {("typographic", "")},                     # Z3
    "\U000133EB": {("typographic", "")},                     # Z3A
    "\U000133A2": {("phonogram", "k")},                      # V31A
    "\U00013217": {("phonogram", "mw"), ("determinative", "")},   # N35A
    "\U000131FF": {("logogram", "tꜣ"), ("determinative", "")},  # N17, tꜣ
    "\U000133F1": {("determinative", "")},                   # Z6
    "\U0001333B": {("phonogram", "mr")},                     # U7
    "\U0001341D": {("phonogram", "m")},                      # Aa15
    "\U0001307B": {("determinative", "")},                   # D6
}


# --------------------------------------------------------------------------- #
# 1. the five-class fold
# --------------------------------------------------------------------------- #


def test_fold_covers_every_shipped_function_label():
    labels: set[str] = set()
    for path in (SIGN_FUNCTIONS_PATH, SUPPLEMENT_PATH):
        if path.exists():
            labels |= set(pd.read_csv(path, keep_default_na=False)["function"])
    assert labels, "neither sign-function table is present"
    assert labels <= set(CLASS_FOLD), sorted(labels - set(CLASS_FOLD))


def test_fold_shape():
    assert CLASS_FOLD["logogram or determinative"] == frozenset({"log", "det"})
    assert CLASS_FOLD["phonogram or phonetic determinative"] == frozenset(
        {"phon", "phondet"}
    )
    for label, classes in CLASS_FOLD.items():
        assert classes, label
        assert classes <= set(CLASSES), label
        expected = 2 if " or " in label else 1
        assert len(classes) == expected, (label, classes)
    assert "unk" not in {c for classes in CLASS_FOLD.values() for c in classes}


def test_class_distribution_is_uniform_and_sums_to_one():
    functions = load_sign_functions()
    for sign in list(functions.classes)[:200] + ["�", ""]:
        distribution = functions.class_distribution(sign)
        assert abs(sum(distribution.values()) - 1.0) < 1e-12, sign
        assert len(set(distribution.values())) == 1, sign


def test_uncovered_sign_is_unk():
    functions = load_sign_functions()
    # A TLA `<g>` placeholder is not a sign; a private-use character is not either.
    for sign in ("<g>D77</g>", "", "", "x"):
        assert functions.classes_for(sign) == UNKNOWN_CLASSES
        assert sign not in functions


def test_absent_tables_degrade_to_unk(tmp_path: Path):
    functions = load_sign_functions(
        path=tmp_path / "nope.csv", supplement_path=tmp_path / "nope2.csv"
    )
    assert len(functions) == 0
    assert functions.classes_for("\U00013000") == UNKNOWN_CLASSES
    assert functions.entries_for("\U00013000") == ()


# --------------------------------------------------------------------------- #
# 2. the supplement
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not SUPPLEMENT_PATH.exists(), reason="supplement not built")
def test_supplement_is_the_pre_registered_table():
    frame = pd.read_csv(SUPPLEMENT_PATH, keep_default_na=False)
    assert len(frame) == 13
    assert set(frame["source_note"]) == {SUPPLEMENT_NOTE}
    got: dict[str, set[tuple[str, str]]] = {}
    for _, row in frame.iterrows():
        got.setdefault(str(row["sign"]), set()).add(
            (str(row["function"]), str(row["value"]))
        )
    assert got == PRE_REGISTERED


@pytest.mark.skipif(not SUPPLEMENT_PATH.exists(), reason="supplement not built")
def test_supplement_codepoint_column_matches_the_character():
    frame = pd.read_csv(SUPPLEMENT_PATH, keep_default_na=False)
    for _, row in frame.iterrows():
        assert f"U+{ord(str(row['sign'])):04X}" == str(row["codepoint"])


@pytest.mark.skipif(
    not (SUPPLEMENT_PATH.exists() and SIGN_FUNCTIONS_PATH.exists()),
    reason="both tables required",
)
def test_supplement_only_adds_signs_nederhof_does_not_cover():
    nederhof = set(pd.read_csv(SIGN_FUNCTIONS_PATH, keep_default_na=False)["sign"])
    supplement = set(pd.read_csv(SUPPLEMENT_PATH, keep_default_na=False)["sign"])
    assert not (nederhof & supplement)


@pytest.mark.skipif(not SUPPLEMENT_PATH.exists(), reason="supplement not built")
def test_supplement_rows_are_marked_and_loaded_alongside():
    functions = load_sign_functions()
    z7 = "\U000133F2"
    assert functions.classes_for(z7) == frozenset({"phon"})
    entries = functions.entries_for(z7)
    assert len(entries) == 1 and entries[0].is_supplement and entries[0].value == "w"
    # N35A carries two functions, so its class set carries both.
    assert functions.classes_for("\U00013217") == frozenset({"phon", "det"})
    # A Nederhof sign is unaffected and not marked as supplement.
    a1 = functions.entries_for("\U00013000")
    assert a1 and not any(entry.is_supplement for entry in a1)


@pytest.mark.skipif(not SIGN_FUNCTIONS_PATH.exists(), reason="table not built")
def test_nederhof_rows_keep_their_attribution():
    functions = load_sign_functions()
    a1 = functions.entries_for("\U00013000")
    assert a1
    assert all("Nederhof" in entry.source_note for entry in a1)
