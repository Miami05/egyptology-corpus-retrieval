"""Download the three TLA parquet files (Earlier Egyptian, Late Egyptian, Demotic).

Each dataset is pinned to the Hub commit the corpus was built from, because the
Earlier/Late sentence ids are positional (`TLA_EARLIER_n`): an upstream edit that
inserts one sentence would shift every id after it without any error. An output that
already exists is kept unless `--force` is given, and every save prints the row count
and a sha256 so a re-download can be compared with what the corpus was built from.

AES, BBAW, Ramses, Helsinki and St Andrews are not fetched here; the BBAW and
Helsinki importers download (and pin) their own files.
"""

import argparse
import hashlib
from pathlib import Path

import pandas as pd
from datasets import load_dataset


DATASETS = [
    {
        "name": "thesaurus-linguae-aegyptiae/tla-Earlier_Egyptian_original-v18-premium",
        "revision": "a7ba9e9d1a74a9a0f919b024ba84dd6d643b2966",
        "out": "data/raw/tla_earlier/tla_earlier.parquet",
    },
    {
        "name": "thesaurus-linguae-aegyptiae/tla-late_egyptian-v19-premium",
        "revision": "8af85941783ba575d5a8985c80c688f948c50040",
        "out": "data/raw/tla_late/tla_late.parquet",
    },
    {
        "name": "thesaurus-linguae-aegyptiae/tla-demotic-v18-premium",
        "revision": "c02baaaddaf0e2b6b9d128874df23c655eedfe7c",
        "out": "data/raw/tla_demotic/tla_demotic.parquet",
    },
]


def save_dataset(
    dataset_name: str, output_path: str, revision: str, force: bool = False
) -> None:
    out = Path(output_path)
    if out.exists() and not force:
        print(f"Skipping {dataset_name}: {out} exists (use --force to replace it)")
        print()
        return
    print(f"Downloading: {dataset_name} @ {revision}")
    ds = load_dataset(dataset_name, split="train", revision=revision)

    df = ds.to_pandas()

    out.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(out, index=False)

    print(f"Saved {len(df)} rows to {out}")
    print(f"sha256: {hashlib.sha256(out.read_bytes()).hexdigest()}")
    print("Columns:", list(df.columns))
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace parquet files that already exist.",
    )
    args = parser.parse_args()
    for item in DATASETS:
        save_dataset(item["name"], item["out"], item["revision"], args.force)


if __name__ == "__main__":
    main()
