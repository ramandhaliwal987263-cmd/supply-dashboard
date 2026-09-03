"""
Loads suppliers + shipments into SQLite and runs sql/analysis_queries.sql to
compute lead times, delays, and supplier/category/warehouse/monthly
performance rollups entirely in SQL.
"""
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
DB_PATH = PROCESSED_DIR / "supply_chain.db"
QUERY_PATH = ROOT / "sql" / "analysis_queries.sql"

RESULT_TABLES = [
    "shipments_enriched", "supplier_performance", "category_performance",
    "warehouse_performance", "monthly_trend",
]


def run_analysis() -> dict:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    suppliers = pd.read_csv(RAW_DIR / "suppliers.csv")
    shipments = pd.read_csv(RAW_DIR / "shipments.csv")

    conn = sqlite3.connect(DB_PATH)
    try:
        suppliers.to_sql("suppliers", conn, index=False)
        shipments.to_sql("shipments", conn, index=False)

        conn.executescript(QUERY_PATH.read_text())
        conn.commit()

        results = {}
        for table in RESULT_TABLES:
            df = pd.read_sql(f"SELECT * FROM {table}", conn)
            df.to_csv(PROCESSED_DIR / f"{table}.csv", index=False)
            results[table] = len(df)
            print(f"{table}: {len(df):,} rows -> {PROCESSED_DIR / f'{table}.csv'}")
    finally:
        conn.close()

    return results


if __name__ == "__main__":
    run_analysis()
