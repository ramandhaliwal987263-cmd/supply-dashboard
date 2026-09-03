"""Runs the full supply chain pipeline end to end: generate -> SQL analysis
-> anomaly detection -> build dashboard."""
import time

from . import anomaly_detection, build_dashboard, generate_data, sql_analysis


def main():
    stages = [
        ("Generate synthetic suppliers & shipments", generate_data.generate),
        ("Analyze performance (SQL)", sql_analysis.run_analysis),
        ("Detect anomalies (statistical + ML)", anomaly_detection.detect),
        ("Build dashboard (Plotly)", build_dashboard.build),
    ]

    print("=" * 70)
    print("SUPPLY CHAIN ANALYSIS & ANOMALY DETECTION SYSTEM")
    print("=" * 70)

    for name, fn in stages:
        print(f"\n--- {name} ---")
        t0 = time.time()
        fn()
        print(f"[{name} done in {time.time() - t0:.1f}s]")

    print("\n" + "=" * 70)
    print("Pipeline complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
