INSERT INTO platform_settings (setting_key, setting_value)
VALUES ('rider_commission_pct_of_convenience', '25')
ON CONFLICT (setting_key) DO NOTHING;

CREATE OR REPLACE FUNCTION public.rider_commission_amount(p_shipping_fee numeric, p_subtotal numeric)
RETURNS numeric
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT ROUND(
    GREATEST(
      COALESCE(p_shipping_fee, 0) * public.marketplace_setting_number('rider_commission_pct_of_shipping', 70) / 100
      + COALESCE(p_subtotal, 0) * public.marketplace_setting_number('rider_commission_pct_of_convenience', 25) / 100,
      0
    ),
    2
  );
$$;

CREATE OR REPLACE FUNCTION public.order_item_pickup_financials(p_suborder_id integer, p_order_item_id integer)
RETURNS TABLE(
  line_total numeric,
  shipping_share numeric,
  tax_share numeric,
  total_amount numeric,
  commission_amount numeric
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  WITH item_lines AS (
    SELECT
      oi.order_items_id,
      COALESCE(p.price, 0) * GREATEST(COALESCE(oi.quantity, 0), 0) AS line_total,
      oi.status,
      COALESCE(os.shipping_fee, 0) AS suborder_shipping_fee,
      COALESCE(os.tax_amount, 0) AS suborder_tax_amount
    FROM public.order_items AS oi
    INNER JOIN public.order_suborders AS os ON os.suborder_id = oi.suborder_id
    LEFT JOIN public.products AS p ON p.product_id = oi.product_id
    WHERE oi.suborder_id = p_suborder_id
  ),
  target AS (
    SELECT *
    FROM item_lines
    WHERE order_items_id = p_order_item_id
    LIMIT 1
  ),
  totals AS (
    SELECT GREATEST(COALESCE(SUM(line_total) FILTER (WHERE status NOT IN (5, 8)), 0), 0)::numeric AS active_line_total
    FROM item_lines
  )
  SELECT
    ROUND(COALESCE(t.line_total, 0), 2) AS line_total,
    ROUND(
      CASE
        WHEN totals.active_line_total > 0 THEN COALESCE(t.suborder_shipping_fee, 0) * COALESCE(t.line_total, 0) / totals.active_line_total
        ELSE 0
      END,
      2
    ) AS shipping_share,
    ROUND(
      CASE
        WHEN totals.active_line_total > 0 THEN COALESCE(t.suborder_tax_amount, 0) * COALESCE(t.line_total, 0) / totals.active_line_total
        ELSE 0
      END,
      2
    ) AS tax_share,
    ROUND(
      COALESCE(t.line_total, 0)
      + CASE
          WHEN totals.active_line_total > 0 THEN COALESCE(t.suborder_shipping_fee, 0) * COALESCE(t.line_total, 0) / totals.active_line_total
          ELSE 0
        END
      + CASE
          WHEN totals.active_line_total > 0 THEN COALESCE(t.suborder_tax_amount, 0) * COALESCE(t.line_total, 0) / totals.active_line_total
          ELSE 0
        END,
      2
    ) AS total_amount,
    public.rider_commission_amount(
      ROUND(
        CASE
          WHEN totals.active_line_total > 0 THEN COALESCE(t.suborder_shipping_fee, 0) * COALESCE(t.line_total, 0) / totals.active_line_total
          ELSE 0
        END,
        2
      ),
      ROUND(
        CASE
          WHEN totals.active_line_total > 0 THEN COALESCE(t.suborder_tax_amount, 0) * COALESCE(t.line_total, 0) / totals.active_line_total
          ELSE 0
        END,
        2
      )
    ) AS commission_amount
  FROM target AS t
  CROSS JOIN totals;
$$;
