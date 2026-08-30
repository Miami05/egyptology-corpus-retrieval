# Corpus data licence and attribution

**The code in this repository and the corpus data under `data/` are under different
licences. Read this before publishing, redistributing or deploying publicly.**

| What | Licence |
|---|---|
| Source code (`app/`, `scripts/`, `tests/`) | MIT — see `LICENSE` |
| Corpus data (`data/`, incl. `data/processed/examples.csv`) | **CC BY-SA 4.0** — see below |
| `app/ui/static/GentiumPlus-Translit.woff2` | SIL Open Font License 1.1 — see `app/ui/static/GentiumPlus-OFL.txt` |

## Why the data is not MIT

The corpus is derived from the Thesaurus Linguae Aegyptiae (TLA), released under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). CC BY-SA is a
*share-alike* licence: an adapted version of the data must be released under the same
licence. `data/processed/examples.csv` is an adaptation of TLA data, so it is CC BY-SA
4.0 and **cannot** be relicensed as MIT. Applying MIT to the whole repository would
misstate the terms of someone else's work.

The share-alike obligation attaches to the *data*, not to the code that processes it.
The code stays MIT.

## Required attribution

CC BY-SA 4.0 requires attribution, a licence notice, and an indication of changes.
The dataset's own citation recommendation is:

> Thesaurus Linguae Aegyptiae, Original Earlier Egyptian sentences, corpus v18,
> premium,
> <https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/tla-Earlier_Egyptian_original-v18-premium>,
> v1.1, 2/16/2024, ed. by Tonio Sebastian Richter & Daniel A. Werning on behalf of the
> Berlin-Brandenburgische Akademie der Wissenschaften and Hans-Werner Fischer-Elfert &
> Peter Dils on behalf of the Sächsische Akademie der Wissenschaften zu Leipzig.

Licensed under CC BY-SA 4.0. TLA homepage: <https://thesaurus-linguae-aegyptiae.de>.

The corpus also contains the **Late Egyptian** TLA corpus, whose citation is:

> Thesaurus Linguae Aegyptiae, Original Late Egyptian sentences, corpus v19,
> premium,
> <https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/tla-Late_Egyptian_original-v19-premium>,
> ed. by Tonio Sebastian Richter & Daniel A. Werning on behalf of the
> Berlin-Brandenburgische Akademie der Wissenschaften and Hans-Werner Fischer-Elfert &
> Peter Dils on behalf of the Sächsische Akademie der Wissenschaften zu Leipzig.

Licensed under CC BY-SA 4.0.

```bibtex
@misc{tlaEarlierEgyptianOriginalV18premium,
 editor = {{Berlin-Brandenburgische Akademie der Wissenschaften} and {Sächsische Akademie der Wissenschaften zu Leipzig} and Richter, Tonio Sebastian and Werning, Daniel A. and Hans-Werner Fischer-Elfert and Peter Dils},
 year = {2024},
 title = {Thesaurus Linguae Aegyptiae, Original Earlier Egyptian sentences, corpus v18, premium},
 url = {https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/tla-Earlier_Egyptian_original-v18-premium},
 location = {Berlin},
 organization = {{Berlin-Brandenburgische Akademie der Wissenschaften} and {Sächsische Akademie der Wissenschaften zu Leipzig}},
}
```

## Indication of changes (required by CC BY-SA 4.0 §3(a)(1)(B))

`data/processed/examples.csv` is **not** verbatim TLA data. The TLA sentences were
transformed by `scripts/import_tla_dataset.py` and `scripts/build_examples_from_real.py`
as follows:

- Selected a subset of sentences and reshaped them into one row per sentence with the
  column schema in `app/data/schema.py`.
- Added normalised columns (`*_norm`) produced by `app/data/normalizer.py`: case
  folding, whitespace collapsing, and stripping of editorial markup, used for matching.
- Derived additional fields not present in the source, including `sign_sequence`,
  `formula_type`, `deity`, `recipient`, `offering_items`, `formula_slot` and
  `aesthetic_arrangement_flag`.
- Added project-local identifiers (`source_text_id`, `source_sentence_id`) and a
  `source_ref` pointing back to the originating row in the downloaded parquet.
- `review_status` and any annotations recorded through the app are this project's own
  editorial additions and are not part of the TLA data.

- **Merged two TLA corpora** (2026-08-30): the Earlier Egyptian corpus (12,772 rows)
  and the Late Egyptian corpus (3,601 rows, after dropping 5 sentences already
  present verbatim), giving 16,373 rows. Rows carry their originating corpus in
  `language_stage` and an id prefix (`TLA_EARLIER_*` / `TLA_LATE_*`).
- **Unified the suffix-pronoun marker.** The Earlier corpus writes it `=` (11,671
  occurrences), the Late corpus `⸗` (4,390). They denote the same morpheme. All
  imported rows now use `=`. Without this the same sentence read `n =tn` or `n ⸗tn`
  depending only on which corpus attested that spelling more often — an artefact of
  merging, not of the language.

Translations in the corpus are the German translations from TLA.

## Every copy of the data in this repository

CC BY-SA 4.0 applies to each of these, not only to `examples.csv`:

| File | What it is |
|---|---|
| `data/processed/examples.csv` | the built corpus |
| `data/raw/real_examples_worklist.csv` | an earlier full copy of the same source rows |
| `data/processed/reviewed_annotations_export.csv` | corpus text plus this project's annotations |
| `data/benchmarks/*.csv` | queries and expectations derived from corpus readings |

Exports produced by the app and by `scripts/export_reviewed.py` carry a `licence`
column repeating the attribution, because a file that leaves the repository loses
sight of this one.

## Warranty disclaimer (CC BY-SA 4.0 §5)

Unless otherwise separately undertaken, the licensor offers the licensed material
as-is and makes no representations or warranties of any kind concerning it. Where
disclaimers of warranties are not allowed in full or in part, this disclaimer may not
apply. The full text is at
<https://creativecommons.org/licenses/by-sa/4.0/legalcode>.

## If you deploy this publicly

Attribution must reach the person viewing the data, not only this file. The app
displays the attribution in the sidebar. Do not remove it, and do not present the
corpus as this project's own work.

The Demotic dataset referenced in `scripts/download_all_sources.py`
(`tla-demotic-v18-premium`) is also CC BY-SA 4.0. It is downloaded but is **not** part
of `examples.csv`: it carries no hieroglyphic writings (0 of 13,383 rows), so it
cannot support the sign-based reading this tool provides. If you build it in, add its
citation here too.
