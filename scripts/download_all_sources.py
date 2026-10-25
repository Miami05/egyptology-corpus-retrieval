"""Download the three TLA parquet files (Earlier Egyptian, Late Egyptian, Demotic).

Each dataset is pinned to the Hub commit the corpus was built from, because the
Earlier/Late sentence ids are positional (`TLA_EARLIER_n`): an upstream edit that
inserts one sentence would shift every id after it without any error.

A pin alone does not prove which snapshot a local file holds (an output that already
exists is kept unless `--force` is given, and it may predate the pin). So every file
is also checked against the expected *content* checksum of its snapshot — the row
count plus a sha256 over the rows in order (see `content_fingerprint`) — both a file
that is already there and a fresh download. The checksum covers the table, not the
parquet bytes, which differ between pandas/pyarrow versions for the same rows. A
mismatch stops the script: an existing file is left alone and a download is not
written, so the import cannot silently re-point the positional ids.

The expected values were computed on 2026-10-25 from the local data/raw parquets
and, independently, from the pinned snapshots' `train.jsonl` in the Hugging Face
cache; the two agreed for all three datasets. `upstream_sha256` is the sha256 of that
upstream `train.jsonl`, recorded for reference.

AES, BBAW, Ramses, Helsinki and St Andrews are not fetched here; the BBAW and
Helsinki importers download (and pin) their own files.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
from pathlib import Path

import pandas as pd
from datasets import load_dataset


DATASETS = [
    {
        "name": "thesaurus-linguae-aegyptiae/tla-Earlier_Egyptian_original-v18-premium",
        "revision": "a7ba9e9d1a74a9a0f919b024ba84dd6d643b2966",
        "out": "data/raw/tla_earlier/tla_earlier.parquet",
        "content_sha256": (
            "12773:52d2d90d9e43cbec67a4534eb6d5ae9ddcf4b4d7358dc01e75083170f0c880f9"
        ),
        "upstream_sha256": (
            "13d4f6e17e5348c4a1dcf1c02795c8401367e187eaf903da325a1cf83a998f99"
        ),
    },
    {
        "name": "thesaurus-linguae-aegyptiae/tla-late_egyptian-v19-premium",
        "revision": "8af85941783ba575d5a8985c80c688f948c50040",
        "out": "data/raw/tla_late/tla_late.parquet",
        "content_sha256": (
            "3606:ad984cb61d464b1cb65d2f89b224d7c95480be3c7ce875595a81bc1062dc050f"
        ),
        "upstream_sha256": (
            "dfded75c7d34bc1f2f12e18af6936394dc0c5cadacd1229dc28d46751d6389df"
        ),
    },
    {
        "name": "thesaurus-linguae-aegyptiae/tla-demotic-v18-premium",
        "revision": "c02baaaddaf0e2b6b9d128874df23c655eedfe7c",
        "out": "data/raw/tla_demotic/tla_demotic.parquet",
        "content_sha256": (
            "13383:621f3dcef981075a8f911fe68e5e6f453a8cf2c74f9e87c4a9d0f1c6bb20e7d6"
        ),
        "upstream_sha256": (
            "787e9ce8b5005a056f4579723ccffeaa5db1ed0bd7f42b7e5d5ec34d6867a63f"
        ),
    },
]


class SnapshotMismatch(RuntimeError):
    """A file's content is not the snapshot the corpus ids were built from."""


def content_fingerprint(df: pd.DataFrame) -> str:
    """'<rows>:<sha256>' over the column names (sorted) and every row, in order.

    Row order is part of the checksum on purpose: the TLA ids are positions.
    Missing values hash as NUL, everything else as its str().
    """
    digest = hashlib.sha256()
    columns = sorted(str(c) for c in df.columns)
    digest.update(("\x1f".join(columns) + "\n").encode("utf-8"))
    for row in df[columns].itertuples(index=False, name=None):
        cells = (
            "\x00"
            if v is None or (isinstance(v, float) and math.isnan(v))
            else str(v)
            for v in row
        )
        digest.update(("\x1f".join(cells) + "\n").encode("utf-8"))
    return f"{len(df)}:{digest.hexdigest()}"


def _check(df: pd.DataFrame, expected: str | None, what: str) -> None:
    if expected is None:
        return
    actual = content_fingerprint(df)
    if actual != expected:
        raise SnapshotMismatch(
            f"{what}: content checksum {actual} does not match the pinned snapshot "
            f"{expected}. The TLA ids are positional, so importing this file could "
            "re-point them. Nothing was written."
        )


def save_dataset(
    dataset_name: str,
    output_path: str,
    revision: str,
    force: bool = False,
    expected: str | None = None,
) -> None:
    out = Path(output_path)
    if out.exists() and not force:
        if expected is not None:
            try:
                existing = pd.read_parquet(out)
            except Exception as exc:  # unreadable counts as "not the snapshot"
                raise SnapshotMismatch(
                    f"{out}: cannot be read as parquet ({exc})"
                ) from exc
            _check(existing, expected, str(out))
        state = "checksum verified" if expected else "not verified"
        print(f"Skipping {dataset_name}: {out} exists, {state} (use --force to replace it)")
        print()
        return
    print(f"Downloading: {dataset_name} @ {revision}")
    ds = load_dataset(dataset_name, split="train", revision=revision)

    df = ds.to_pandas()
    _check(df, expected, f"{dataset_name} @ {revision}")

    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".partial")
    df.to_parquet(partial, index=False)
    partial.replace(out)

    print(f"Saved {len(df)} rows to {out}")
    print(f"content: {content_fingerprint(df)}")
    print(f"sha256: {hashlib.sha256(out.read_bytes()).hexdigest()}")
    print("Columns:", list(df.columns))
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace parquet files that already exist (the download is still checked).",
    )
    args = parser.parse_args()
    try:
        for item in DATASETS:
            save_dataset(
                item["name"],
                item["out"],
                item["revision"],
                args.force,
                expected=item.get("content_sha256"),
            )
    except SnapshotMismatch as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
