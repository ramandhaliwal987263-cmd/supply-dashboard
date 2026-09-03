-- Supply chain analysis SQL: lead times, delays, and supplier/category/
-- warehouse/monthly performance rollups. Written for SQLite (julianday() for
-- date arithmetic); the MySQL equivalent of each julianday() difference is
-- DATEDIFF(actual_delivery_date, order_date) -- see src/sql_analysis.py for
-- how this file is executed.

DROP TABLE IF EXISTS shipments_enriched;

CREATE TABLE shipments_enriched AS
SELECT
    s.*,
    sup.supplier_name,
    sup.region,
    sup.reliability_tier,
    CASE WHEN s.status = 'Delivered'
         THEN julianday(s.actual_delivery_date) - julianday(s.order_date)
         ELSE NULL END                                          AS lead_time_days,
    CASE WHEN s.status = 'Delivered'
         THEN julianday(s.actual_delivery_date) - julianday(s.expected_delivery_date)
         ELSE NULL END                                          AS delay_days,
    CASE WHEN s.status = 'Delivered'
              AND julianday(s.actual_delivery_date) > julianday(s.expected_delivery_date)
         THEN 1 ELSE 0 END                                      AS is_late
FROM shipments s
JOIN suppliers sup ON sup.supplier_id = s.supplier_id;


DROP TABLE IF EXISTS supplier_performance;

CREATE TABLE supplier_performance AS
SELECT
    supplier_id,
    supplier_name,
    region,
    reliability_tier,
    COUNT(*)                                                     AS total_shipments,
    SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END)         AS delivered_shipments,
    SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END)           AS cancelled_shipments,
    ROUND(AVG(lead_time_days), 2)                                     AS avg_lead_time_days,
    ROUND(AVG(delay_days), 2)                                           AS avg_delay_days,
    SUM(is_late)                                                          AS late_shipments,
    ROUND(1.0 * (SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END) - SUM(is_late))
          / NULLIF(SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END), 0), 4) AS on_time_rate,
    SUM(quantity)                                                           AS total_quantity,
    ROUND(SUM(total_cost), 2)                                                AS total_cost,
    ROUND(AVG(unit_cost), 2)                                                  AS avg_unit_cost
FROM shipments_enriched
GROUP BY supplier_id, supplier_name, region, reliability_tier
ORDER BY on_time_rate ASC;


DROP TABLE IF EXISTS category_performance;

CREATE TABLE category_performance AS
SELECT
    product_category,
    COUNT(*)                                                     AS total_shipments,
    ROUND(AVG(lead_time_days), 2)                                  AS avg_lead_time_days,
    ROUND(AVG(delay_days), 2)                                        AS avg_delay_days,
    ROUND(1.0 * (SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END) - SUM(is_late))
          / NULLIF(SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END), 0), 4) AS on_time_rate,
    SUM(quantity)                                                    AS total_quantity,
    ROUND(SUM(total_cost), 2)                                          AS total_cost
FROM shipments_enriched
GROUP BY product_category
ORDER BY total_cost DESC;


DROP TABLE IF EXISTS warehouse_performance;

CREATE TABLE warehouse_performance AS
SELECT
    warehouse,
    COUNT(*)                                                    AS total_shipments,
    ROUND(AVG(delay_days), 2)                                     AS avg_delay_days,
    ROUND(1.0 * (SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END) - SUM(is_late))
          / NULLIF(SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END), 0), 4) AS on_time_rate,
    ROUND(SUM(total_cost), 2)                                       AS total_cost
FROM shipments_enriched
GROUP BY warehouse
ORDER BY total_cost DESC;


DROP TABLE IF EXISTS monthly_trend;

CREATE TABLE monthly_trend AS
SELECT
    strftime('%Y-%m', order_date)                               AS order_month,
    COUNT(*)                                                     AS total_shipments,
    ROUND(AVG(delay_days), 2)                                     AS avg_delay_days,
    ROUND(1.0 * (SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END) - SUM(is_late))
          / NULLIF(SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END), 0), 4) AS on_time_rate,
    ROUND(SUM(total_cost), 2)                                       AS total_cost
FROM shipments_enriched
GROUP BY order_month
ORDER BY order_month;
