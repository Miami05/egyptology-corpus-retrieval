"""Experiment 3 step 1: the builder's --exclude-same-text rule (same source_text_id for
TLA/AES/Ramses, a +-window of sentence numbers for BBAW)."""

import pytest

from scripts.build_competitive_ambiguity_benchmark import same_text_exclusions

SOURCES = ["BBAW", "BBAW", "BBAW", "BBAW", "AES", "AES", "Ramses", "TLA"]
TEXTS = ["bbaw", "bbaw", "bbaw", "bbaw", "AES_1", "AES_1", "RAMSES_X", "TLA_1"]
SENTENCES = ["B000100", "B000120", "B000121", "B000079", "s1", "s2", "S_train_1", "S1"]


def test_bbaw_window_is_inclusive_and_symmetric():
    same_text, window = same_text_exclusions(SOURCES, TEXTS, SENTENCES, [0], 20)
    assert same_text == set()
    assert window == {0, 1}  # 100 and 120; 121 and 79 are outside +-20


def test_non_bbaw_rows_share_their_text_id():
    same_text, window = same_text_exclusions(SOURCES, TEXTS, SENTENCES, [4, 7], 20)
    assert same_text == {4, 5, 7}
    assert window == set()


def test_bbaw_must_be_one_text():
    with pytest.raises(SystemExit):
        same_text_exclusions(["BBAW", "BBAW"], ["a", "b"], ["B1", "B2"], [0], 20)


def test_bbaw_sentence_id_must_be_numbered():
    with pytest.raises(SystemExit):
        same_text_exclusions(["BBAW"], ["a"], ["X1"], [0], 20)
