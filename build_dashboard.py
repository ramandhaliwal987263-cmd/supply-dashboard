"""
Builds a single self-contained, interactive HTML dashboard (Plotly) covering
delivery performance, supplier trends and inventory/anomaly KPIs — standing
in for a Tableau workbook since Tableau Desktop isn't part of this
environment. Open dashboard/supply_chain_dashboard.html directly in a
browser; no server required.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
OUT_PATH = ROOT / "dashboard" / "supply_chain_dashboard.html"

TEMPLATE = "plotly_white"
ANOMALY_COLOR = "#E4572E"
NORMAL_COLOR = "#17879C"
TIER_COLORS = {"A": "#2E8B57", "B": "#E8A33D", "C": "#E4572E"}


def kpi_card(label: str, value: str, sub: str = "") -> str:
    return f"""
    <div class="kpi-card">
      <div class="kpi-value">{value}</div>
      <div class="kpi-label">{label}</div>
      <div class="kpi-sub">{sub}</div>
    </div>"""


def fig_to_div(fig: go.Figure, include_js: bool = False) -> str:
    return fig.to_html(full_html=False, include_plotlyjs="cdn" if include_js else False,
                        config={"displaylogo": False})


def worst_suppliers_chart(supplier_perf: pd.DataFrame) -> go.Figure:
    worst = supplier_perf[supplier_perf["delivered_shipments"] >= 20].nsmallest(15, "on_time_rate")
    worst = worst.sort_values("on_time_rate")
    fig = go.Figure(go.Bar(
        x=worst["on_time_rate"] * 100, y=worst["supplier_name"], orientation="h",
        marker_color=[TIER_COLORS.get(t, "#888") for t in worst["reliability_tier"]],
        text=[f"{v:.0f}%" for v in worst["on_time_rate"] * 100], textposition="outside",
        customdata=worst["reliability_tier"],
        hovertemplate="%{y}<br>On-time: %{x:.1f}%<br>Tier: %{customdata}<extra></extra>",
    ))
    fig.update_layout(title="15 lowest on-time-delivery suppliers (min. 20 shipments)",
                       xaxis_title="On-time rate (%)", template=TEMPLATE, height=460,
                       margin=dict(l=140, t=60))
    return fig


def tier_delay_chart(supplier_perf: pd.DataFrame) -> go.Figure:
    grp = supplier_perf.groupby("reliability_tier").agg(
        avg_delay_days=("avg_delay_days", "mean"), suppliers=("supplier_id", "count"),
    ).reset_index().sort_values("reliability_tier")
    fig = go.Figure(go.Bar(
        x=grp["reliability_tier"], y=grp["avg_delay_days"],
        marker_color=[TIER_COLORS.get(t, "#888") for t in grp["reliability_tier"]],
        text=[f"{v:.1f}d" for v in grp["avg_delay_days"]], textposition="outside",
        customdata=grp["suppliers"],
        hovertemplate="Tier %{x}<br>Avg delay: %{y:.1f} days<br>Suppliers: %{customdata}<extra></extra>",
    ))
    fig.update_layout(title="Average delivery delay by supplier reliability tier",
                       xaxis_title="Reliability tier", yaxis_title="Avg. delay (days)",
                       template=TEMPLATE, height=380)
    return fig


def monthly_trend_chart(monthly: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=monthly["order_month"], y=monthly["total_shipments"],
                          name="Shipments", marker_color="#B7C4CC", yaxis="y"))
    fig.add_trace(go.Scatter(x=monthly["order_month"], y=monthly["on_time_rate"] * 100,
                              name="On-time rate (%)", mode="lines+markers",
                              line=dict(color=NORMAL_COLOR, width=3), yaxis="y2"))
    fig.update_layout(
        title="Monthly shipment volume & on-time rate",
        template=TEMPLATE, height=400,
        xaxis=dict(title="Order month"),
        yaxis=dict(title="Shipments"),
        yaxis2=dict(title="On-time rate (%)", overlaying="y", side="right", range=[0, 100]),
        legend=dict(orientation="h", y=1.12),
    )
    return fig


def delay_histogram(shipments: pd.DataFrame) -> go.Figure:
    # Bin in numpy rather than handing Plotly's Histogram trace the raw
    # ~16k-row column — same picture, a fraction of the embedded data.
    bins = np.linspace(shipments["delay_days"].min(), shipments["delay_days"].max(), 60)
    normal_counts, _ = np.histogram(shipments.loc[~shipments["is_anomaly"], "delay_days"], bins=bins)
    anomaly_counts, _ = np.histogram(shipments.loc[shipments["is_anomaly"], "delay_days"], bins=bins)
    centers = (bins[:-1] + bins[1:]) / 2

    fig = go.Figure()
    fig.add_trace(go.Bar(x=centers, y=normal_counts, name="Normal", marker_color=NORMAL_COLOR, opacity=0.85))
    fig.add_trace(go.Bar(x=centers, y=anomaly_counts, name="Flagged anomaly", marker_color=ANOMALY_COLOR, opacity=0.9))
    fig.update_layout(title="Delivery delay distribution", xaxis_title="Delay (days, negative = early)",
                       yaxis_title="Shipment count", barmode="stack", template=TEMPLATE, height=400,
                       bargap=0, legend=dict(orientation="h", y=1.1))
    return fig


def anomaly_scatter(shipments: pd.DataFrame) -> go.Figure:
    # Downsample the "normal" cloud for file size / render speed — a random
    # 2,000-point sample looks visually identical to the full ~16k points for
    # a density scatter, and every flagged anomaly (the interesting points)
    # is kept regardless.
    normal_full = shipments[~shipments["is_anomaly"]]
    normal = normal_full.sample(n=min(2000, len(normal_full)), random_state=42)
    anomalous = shipments[shipments["is_anomaly"]]
    fig = go.Figure()
    fig.add_trace(go.Scattergl(
        x=normal["delay_days"], y=normal["unit_cost"], mode="markers", name="Normal",
        marker=dict(color=NORMAL_COLOR, size=5, opacity=0.35),
    ))
    fig.add_trace(go.Scattergl(
        x=anomalous["delay_days"], y=anomalous["unit_cost"], mode="markers", name="Flagged anomaly",
        marker=dict(color=ANOMALY_COLOR, size=8, opacity=0.9, line=dict(width=1, color="white")),
        text=anomalous["shipment_id"],
        hovertemplate="%{text}<br>Delay: %{x:.0f}d<br>Unit cost: $%{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(title="Delay vs. unit cost — flagged anomalies",
                       xaxis_title="Delay (days)", yaxis_title="Unit cost ($, log scale)",
                       yaxis_type="log", template=TEMPLATE, height=460,
                       legend=dict(orientation="h", y=1.1))
    return fig


def category_spend_chart(category_perf: pd.DataFrame) -> go.Figure:
    cat = category_perf.sort_values("total_cost", ascending=True)
    fig = go.Figure(go.Bar(
        x=cat["total_cost"], y=cat["product_category"], orientation="h",
        marker_color="#3E5C76",
        text=[f"${v:,.0f}" for v in cat["total_cost"]], textposition="outside",
    ))
    fig.update_layout(title="Total spend by product category", xaxis_title="Total cost ($)",
                       template=TEMPLATE, height=380, margin=dict(l=160, t=60))
    return fig


def warehouse_chart(warehouse_perf: pd.DataFrame) -> go.Figure:
    wh = warehouse_perf.sort_values("on_time_rate", ascending=False)
    fig = go.Figure(go.Bar(
        x=wh["warehouse"], y=wh["on_time_rate"] * 100, marker_color="#17879C",
        text=[f"{v:.0f}%" for v in wh["on_time_rate"] * 100], textposition="outside",
    ))
    fig.update_layout(title="On-time delivery rate by warehouse", yaxis_title="On-time rate (%)",
                       template=TEMPLATE, height=380)
    return fig


def build():
    supplier_perf = pd.read_csv(PROCESSED / "supplier_performance.csv")
    category_perf = pd.read_csv(PROCESSED / "category_performance.csv")
    warehouse_perf = pd.read_csv(PROCESSED / "warehouse_performance.csv")
    monthly = pd.read_csv(PROCESSED / "monthly_trend.csv")
    shipments = pd.read_csv(PROCESSED / "shipments_with_anomalies.csv")
    anomaly_report = json.loads((REPORTS / "anomaly_report.json").read_text())
    summary = anomaly_report["summary"]

    total_shipments = int(supplier_perf["total_shipments"].sum())
    overall_on_time = (supplier_perf["delivered_shipments"] - supplier_perf["late_shipments"]).sum() \
        / supplier_perf["delivered_shipments"].sum()
    avg_lead_time = shipments["lead_time_days"].mean()
    total_spend = supplier_perf["total_cost"].sum()

    kpis = "".join([
        kpi_card("Total Shipments", f"{total_shipments:,}"),
        kpi_card("On-Time Delivery", f"{overall_on_time:.1%}"),
        kpi_card("Avg. Lead Time", f"{avg_lead_time:.1f} days"),
        kpi_card("Total Spend", f"${total_spend:,.0f}"),
        kpi_card("Anomalies Flagged", f"{summary['combined_anomalies']:,}",
                 f"{summary['detection_recall_vs_known']:.0%} recall vs. known"),
    ])

    charts = [
        (worst_suppliers_chart(supplier_perf), True),
        (tier_delay_chart(supplier_perf), False),
        (monthly_trend_chart(monthly), False),
        (warehouse_chart(warehouse_perf), False),
        (delay_histogram(shipments), False),
        (category_spend_chart(category_perf), False),
        (anomaly_scatter(shipments), False),
    ]
    chart_divs = "\n".join(
        f'<div class="chart-card">{fig_to_div(fig, include_js=first)}</div>'
        for fig, first in charts
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Supply Chain Analytics Dashboard</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 24px 32px 48px;
    background: #F4F6F8; color: #1B2733;
    font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .subtitle {{ color: #5B6B79; margin: 0 0 24px; font-size: 14px; }}
  .kpi-row {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px; margin-bottom: 28px;
  }}
  .kpi-card {{
    background: white; border-radius: 10px; padding: 18px 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .kpi-value {{ font-size: 26px; font-weight: 700; color: #17879C; }}
  .kpi-label {{ font-size: 13px; color: #5B6B79; margin-top: 4px; }}
  .kpi-sub {{ font-size: 12px; color: #93A2AF; }}
  .chart-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));
    gap: 16px;
  }}
  .chart-card {{
    background: white; border-radius: 10px; padding: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); overflow: hidden;
  }}
</style>
</head>
<body>
  <h1>Supply Chain Analytics Dashboard</h1>
  <p class="subtitle">Synthetic supplier &amp; shipment data &middot; delivery performance, supplier trends and anomaly detection</p>
  <div class="kpi-row">{kpis}</div>
  <div class="chart-grid">
{chart_divs}
  </div>
</body>
</html>
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Dashboard written to {OUT_PATH}")


if __name__ == "__main__":
    build()
