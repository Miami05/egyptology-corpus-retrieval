# Corpus data licence and attribution

**The code in this repository and the corpus data under `data/` are under different
licences. Read this before publishing, redistributing or deploying publicly.**

| What | Licence |
|---|---|
| Source code (`app/`, `scripts/`, `tests/`) | MIT — see `LICENSE` |
| Corpus data (`data/`, incl. `data/processed/examples.csv`) | **CC BY-SA 4.0** — see below |
| `app/ui/static/GentiumPlus-Regular.subset.woff2` | SIL Open Font License 1.1 — see `app/ui/static/GentiumPlus-OFL.txt` |

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

Translations in the corpus are the German translations from TLA.

## If you deploy this publicly

Attribution must reach the person viewing the data, not only this file. The app
displays the attribution in the sidebar. Do not remove it, and do not present the
corpus as this project's own work.

The other TLA datasets referenced in `scripts/download_all_sources.py`
(`tla-late_egyptian-v19-premium`, `tla-demotic-v18-premium`) are also CC BY-SA 4.0.
They are downloaded but are **not** currently part of `examples.csv`, which contains
Earlier Egyptian only. If you build them into the corpus, add their citations here too.
