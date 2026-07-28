from pathlib import Path

import pandas as pd
from datasets import load_dataset


DATASETS = [
    {
        "name": "thesaurus-linguae-aegyptiae/tla-Earlier_Egyptian_original-v18-premium",
        "out": "data/raw/tla_earlier/tla_earlier.parquet",
    },
    {
        "name": "thesaurus-linguae-aegyptiae/tla-late_egyptian-v19-premium",
        "out": "data/raw/tla_late/tla_late.parquet",
    },
    {
        "name": "thesaurus-linguae-aegyptiae/tla-demotic-v18-premium",
        "out": "data/raw/tla_demotic/tla_demotic.parquet",
    },
]


def save_dataset(dataset_name: str, output_path: str) -> None:
    print(f"Downloading: {dataset_name}")
    ds = load_dataset(dataset_name, split="train")

    df = ds.to_pandas()

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(out, index=False)

    print(f"Saved {len(df)} rows to {out}")
    print("Columns:", list(df.columns))
    print()


def main() -> None:
    for item in DATASETS:
        save_dataset(item["name"], item["out"])


if __name__ == "__main__":
    main()
