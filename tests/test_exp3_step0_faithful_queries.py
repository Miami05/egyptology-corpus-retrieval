"""Experiment 3 step 0 helpers, on synthetic inputs only (no corpus, no benchmark)."""

from __future__ import annotations

from app.data.normalizer import search_fold
from scripts.exp3_step0_faithful_queries import (
    aligned_query,
    apply_respelling,
    faithful_pairs,
    merging_keys,
    mover_tokens,
    recipe_query,
)


def test_faithful_pairs_drop_what_the_search_key_drops():
    # The editor-supplied yod and a lone `ʾ` fold to nothing, so they are not tokens.
    pairs = faithful_pairs("n(.ꞽ).t rʾ ʾ ꜥḥꜥ.n")
    assert [faithful for faithful, _ in pairs] == ["n", "t", "rʾ", "ꜥḥꜥ", "n"]
    assert [folded for _, folded in pairs] == ["n", "t", "r", "aha", "n"]


def test_recipe_decides_on_the_folded_token():
    # `ḥr` folds to the stop token `hr`; `ꜥnḫw` folds to `ankhw` (five letters), so
    # its ending is stripped although the faithful token has only four.
    query = recipe_query("ḥr ꜥnḫw nb", "simplified_transliteration")
    assert query == "ꜥnḫ nb"
    assert search_fold(query) == "ankh nb"


def test_recipe_partial_keeps_sixty_percent():
    query = recipe_query("ꜣḫ sḏm ḥtp nṯr wꜥb", "partial_transliteration")
    assert query == "ꜣḫ sḏm ḥtp"


def test_aligned_query_restores_letters_and_keeps_residue():
    query, residue = aligned_query("ankh pl djd", "ꜥnḫ ḏd")
    assert query == "ꜥnḫ pl ḏd"
    assert residue == ["pl"]
    assert search_fold(query) == search_fold("ꜥnḫ") + " pl " + search_fold("ḏd")


def test_aligned_query_keeps_repeated_words_in_order():
    query, residue = aligned_query("pa pa", "pꜣ pꜥ")
    assert query == "pꜣ pꜥ"
    assert residue == []


def test_apply_respelling_from_notes():
    notes = "Target row excluded; name lemma d1 respelled tꜣ-rpy.t -> tꜣ-rp.t."
    assert apply_respelling("m-bꜣḥ tꜣ-rpy.t tꜣ", notes) == "m-bꜣḥ tꜣ-rp.t tꜣ"
    assert apply_respelling("m-bꜣḥ", "no respelling") == "m-bꜣḥ"


def test_merging_keys_and_movers():
    tokens = {"pꜣ", "pꜥ", "ḥr", "hr", "ḫr", "ẖr", "nb", "ꜥꜣ"}
    merging, key_count = merging_keys(tokens)
    assert "pa" in merging["aleph/ayin"]
    assert "khr" in merging["kh/khh"]
    assert "hr" in merging["h-dot/h"]
    assert "nb" not in set().union(*merging.values())
    # `ꜥꜣ` alone (no ꜣꜣ / ꜥꜥ spelling) is a single spelling: no merge.
    assert "aa" not in merging["aleph/ayin"]
    assert key_count == len({search_fold(token) for token in tokens})

    loose, strict = mover_tokens("pꜣ nb", merging)
    assert loose == ["pꜣ[aleph/ayin]"] and strict == loose
    # Typed in ASCII, the token hits a merging key but cannot name its letter.
    loose, strict = mover_tokens("pa nb", merging)
    assert loose == ["pa[aleph/ayin]"] and strict == []


def test_conservative_variant_needs_both_letters():
    tokens = {"ḥr", "hr"}
    merging, _ = merging_keys(tokens)
    conservative, _ = merging_keys(tokens, conservative=True)
    assert "hr" in merging["h-dot/h"] and "hr" in conservative["h-dot/h"]
    # The recorded rule counts `khr` as an ḥ/h merge when an ASCII `khr` meets `ḫr`
    # (the h of the digraph); the conservative variant needs a real ḥ-spelling.
    tokens = {"ḫr", "khr"}
    merging, _ = merging_keys(tokens)
    conservative, _ = merging_keys(tokens, conservative=True)
    assert "khr" not in conservative["h-dot/h"]
