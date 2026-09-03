"""
Flags anomalous shipments two ways and combines them:

1. Statistical: per-category z-scores on quantity, unit cost and delay
   (category-relative because a "normal" quantity for Packaging is a wild
   outlier for Machinery Parts) — flag |z| > 3 on any metric.
2. ML: IsolationForest over those same category-relative z-scores, which
   catches multivariate combinations (e.g. moderately high cost *and*
   moderately high delay together) that no single-metric z-score would flag.

Both are checked against the `injected_anomaly` ground-truth column that
generate_data.py stamped onto the synthetic data, so the report can state an
actual precision/recall instead of just a flagged count.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"
ENRICHED_PATH = PROCESSED_DIR / "shipments_enriched.csv"

Z_THRESHOLD = 3.0
CONTAMINATION = 0.02
SEED = 42


def category_zscore(df: pd.DataFrame, col: str) -> pd.Series:
    grp = df.groupby("product_category")[col]
    mean = grp.transform("mean")
    std = grp.transform("std").replace(0, np.nan)
    return ((df[col] - mean) / std).fillna(0)


def detect() -> dict:
    df = pd.read_csv(ENRICHED_PATH)
    delivered = df[df["status"] == "Delivered"].copy()

    for col in ["quantity", "unit_cost", "delay_days"]:
        delivered[f"{col}_z"] = category_zscore(delivered, col)
    delivered["lead_time_days_z"] = category_zscore(delivered, "lead_time_days")

    z_cols = ["quantity_z", "unit_cost_z", "delay_days_z", "lead_time_days_z"]
    delivered["is_statistical_outlier"] = (delivered[z_cols].abs() > Z_THRESHOLD).any(axis=1)

    iso = IsolationForest(contamination=CONTAMINATION, random_state=SEED, n_estimators=200)
    X = delivered[z_cols].values
    iso.fit(X)
    delivered["ml_anomaly_score"] = -iso.decision_function(X)  # higher = more anomalous
    delivered["is_ml_anomaly"] = iso.predict(X) == -1

    delivered["is_anomaly"] = delivered["is_statistical_outlier"] | delivered["is_ml_anomaly"]

    out_path = PROCESSED_DIR / "shipments_with_anomalies.csv"
    delivered.to_csv(out_path, index=False)

    # --- Validate against the known ground truth ---------------------------
    tp = int((delivered["is_anomaly"] & delivered["injected_anomaly"]).sum())
    fp = int((delivered["is_anomaly"] & ~delivered["injected_anomaly"]).sum())
    fn = int((~delivered["is_anomaly"] & delivered["injected_anomaly"]).sum())
    tn = int((~delivered["is_anomaly"] & ~delivered["injected_anomaly"]).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    summary = {
        "shipments_analyzed": len(delivered),
        "statistical_outliers": int(delivered["is_statistical_outlier"].sum()),
        "ml_anomalies": int(delivered["is_ml_anomaly"].sum()),
        "combined_anomalies": int(delivered["is_anomaly"].sum()),
        "known_injected_anomalies": int(delivered["injected_anomaly"].sum()),
        "detection_precision_vs_known": round(precision, 4),
        "detection_recall_vs_known": round(recall, 4),
        "confusion": {"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn},
    }

    top_anomalies = (
        delivered[delivered["is_anomaly"]]
        .sort_values("ml_anomaly_score", ascending=False)
        .head(15)[["shipment_id", "supplier_id", "product_category", "warehouse",
                    "quantity", "unit_cost", "delay_days", "ml_anomaly_score", "injected_anomaly"]]
    )

    supplier_anomaly_counts = (
        delivered[delivered["is_anomaly"]]
        .groupby("supplier_id").size().sort_values(ascending=False).head(10)
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "anomaly_report.json").write_text(json.dumps({
        "summary": summary,
        "top_anomalies": top_anomalies.to_dict("records"),
        "top_suppliers_by_anomaly_count": supplier_anomaly_counts.to_dict(),
    }, indent=2, default=str))

    lines = ["# Anomaly Detection Report", "",
              f"Shipments analyzed (delivered only): {summary['shipments_analyzed']:,}",
              f"Statistical (per-category z-score, |z| > {Z_THRESHOLD}) outliers: "
              f"{summary['statistical_outliers']:,}",
              f"ML (Isolation Forest, contamination={CONTAMINATION}) anomalies: "
              f"{summary['ml_anomalies']:,}",
              f"**Combined anomalies flagged: {summary['combined_anomalies']:,}**", "",
              "## Validation against known injected anomalies",
              f"Precision: {precision:.1%} | Recall: {recall:.1%}",
              f"(TP={tp}, FP={fp}, FN={fn}, TN={tn})", "",
              "## Top 15 anomalies (by ML anomaly score)", "",
              "| Shipment | Supplier | Category | Qty | Unit Cost | Delay (days) | Score | Known? |",
              "|---|---|---|---|---|---|---|---|"]
    for row in top_anomalies.itertuples():
        lines.append(f"| {row.shipment_id} | {row.supplier_id} | {row.product_category} | "
                      f"{row.quantity:,} | ${row.unit_cost:,.2f} | {row.delay_days:.0f} | "
                      f"{row.ml_anomaly_score:.3f} | {'yes' if row.injected_anomaly else 'no'} |")
    lines += ["", "## Suppliers with the most flagged anomalies", "",
              "| Supplier | Anomaly count |", "|---|---|"]
    for supplier_id, count in supplier_anomaly_counts.items():
        lines.append(f"| {supplier_id} | {count} |")
    (REPORTS_DIR / "anomaly_report.md").write_text("\n".join(lines) + "\n")

    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    detect()
