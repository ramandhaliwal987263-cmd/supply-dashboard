"""
Generates synthetic suppliers + shipment/inventory data with realistic
supplier-tier-driven lead times and a small, deliberate set of injected
anomalies (extreme delays, quantities, unit costs) for the anomaly-detection
stage to actually find.
"""
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_SUPPLIERS = 40
N_SHIPMENTS = 20_000
START_DATE = date(2023, 1, 1)
END_DATE = date(2024, 12, 31)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

rng = np.random.default_rng(SEED)

REGIONS = ["North America", "Europe", "East Asia", "South Asia", "Latin America"]
CATEGORIES = ["Electronics Components", "Raw Materials", "Packaging",
              "Machinery Parts", "Office Supplies", "Textiles"]
WAREHOUSES = ["Chicago DC", "Dallas DC", "Atlanta DC", "Newark DC", "Reno DC"]

# reliability tier -> (promised_lead_time_days, actual_mean_days, actual_std_days)
# Promised dates carry a small built-in buffer, as real supplier SLAs do, so
# a "reliable" tier actually clears its own promise most of the time (~90%
# on-time) while tier C's promise is optimistic relative to what it actually
# delivers (~33% on-time) -- that gap is what the dashboard is meant to surface.
TIER_PROFILE = {
    "A": {"promised": 7, "actual_mean": 5.5, "actual_std": 1.2, "weight": 0.30},
    "B": {"promised": 9, "actual_mean": 8.0, "actual_std": 2.2, "weight": 0.45},
    "C": {"promised": 11, "actual_mean": 13.0, "actual_std": 4.5, "weight": 0.25},
}

CATEGORY_PROFILE = {
    "Electronics Components": {"qty_mean": 500, "unit_cost_mean": 12.0},
    "Raw Materials": {"qty_mean": 5000, "unit_cost_mean": 2.5},
    "Packaging": {"qty_mean": 8000, "unit_cost_mean": 0.8},
    "Machinery Parts": {"qty_mean": 150, "unit_cost_mean": 85.0},
    "Office Supplies": {"qty_mean": 1000, "unit_cost_mean": 4.0},
    "Textiles": {"qty_mean": 2000, "unit_cost_mean": 6.5},
}


def build_suppliers() -> pd.DataFrame:
    tiers = rng.choice(list(TIER_PROFILE.keys()), size=N_SUPPLIERS,
                        p=[t["weight"] for t in TIER_PROFILE.values()])
    suppliers = pd.DataFrame({
        "supplier_id": [f"SUP{i:03d}" for i in range(1, N_SUPPLIERS + 1)],
        "supplier_name": [f"Supplier {i}" for i in range(1, N_SUPPLIERS + 1)],
        "region": rng.choice(REGIONS, size=N_SUPPLIERS),
        "primary_category": rng.choice(CATEGORIES, size=N_SUPPLIERS),
        "reliability_tier": tiers,
    })
    return suppliers


def random_order_date() -> date:
    delta = (END_DATE - START_DATE).days
    return START_DATE + timedelta(days=int(rng.integers(0, delta)))


def generate_shipments(suppliers: pd.DataFrame) -> pd.DataFrame:
    rows = []
    supplier_records = suppliers.to_dict("records")

    for i in range(1, N_SHIPMENTS + 1):
        supplier = supplier_records[rng.integers(0, len(supplier_records))]
        tier = TIER_PROFILE[supplier["reliability_tier"]]
        category = supplier["primary_category"]
        cat_profile = CATEGORY_PROFILE[category]

        order_date = random_order_date()
        expected_delivery = order_date + timedelta(days=tier["promised"])

        actual_lead_time = max(1, round(rng.normal(tier["actual_mean"], tier["actual_std"])))
        actual_delivery = order_date + timedelta(days=int(actual_lead_time))

        quantity = max(1, round(rng.lognormal(np.log(cat_profile["qty_mean"]), 0.4)))
        unit_cost = round(max(0.1, rng.lognormal(np.log(cat_profile["unit_cost_mean"]), 0.25)), 2)

        # --- Deliberate anomalies (~1.5% of shipments, independent draws) ---
        is_delay_anomaly = rng.random() < 0.007
        if is_delay_anomaly:
            actual_delivery = actual_delivery + timedelta(days=int(rng.integers(20, 60)))

        is_qty_anomaly = rng.random() < 0.005
        if is_qty_anomaly:
            quantity = int(quantity * rng.integers(10, 30))

        is_cost_anomaly = rng.random() < 0.005
        if is_cost_anomaly:
            unit_cost = round(unit_cost * rng.integers(5, 15), 2)

        warehouse = rng.choice(WAREHOUSES)
        status = rng.choice(["Delivered", "Delivered", "Delivered", "Delivered", "Cancelled"])

        rows.append({
            "shipment_id": f"SHP{i:06d}",
            "supplier_id": supplier["supplier_id"],
            "product_category": category,
            "warehouse": warehouse,
            "order_date": order_date.isoformat(),
            "expected_delivery_date": expected_delivery.isoformat(),
            "actual_delivery_date": actual_delivery.isoformat() if status == "Delivered" else "",
            "quantity": quantity,
            "unit_cost": unit_cost,
            "total_cost": round(quantity * unit_cost, 2),
            "status": status,
            "injected_anomaly": is_delay_anomaly or is_qty_anomaly or is_cost_anomaly,
        })

    return pd.DataFrame(rows)


def generate():
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    suppliers = build_suppliers()
    shipments = generate_shipments(suppliers)

    suppliers_path = RAW_DIR / "suppliers.csv"
    shipments_path = RAW_DIR / "shipments.csv"
    suppliers.to_csv(suppliers_path, index=False)
    shipments.to_csv(shipments_path, index=False)

    print(f"Wrote {len(suppliers):,} suppliers to {suppliers_path}")
    print(f"Wrote {len(shipments):,} shipments to {shipments_path}")
    print(f"Injected anomalies: {shipments['injected_anomaly'].sum():,} "
          f"({shipments['injected_anomaly'].mean():.2%})")


if __name__ == "__main__":
    generate()
