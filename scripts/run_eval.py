from __future__ import annotations

from app.data.loader import load_examples_csv
from app.services.evaluation import evaluate_leave_one_out

DATA_PATH = "data/processed/examples.csv"


def main() -> None:
    df = load_examples_csv(DATA_PATH)
    metrics = evaluate_leave_one_out(df, k=3)
    print("Evaluation metrics:")
    for key, value in metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
