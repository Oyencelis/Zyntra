CREATE OR REPLACE FUNCTION public.rider_commission_amount(p_shipping_fee numeric, p_subtotal numeric)
RETURNS numeric
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT ROUND(
    GREATEST(
      COALESCE(p_shipping_fee, 0) * public.marketplace_setting_number('rider_commission_pct_of_shipping', 70) / 100,
      0
    ),
    2
  );
$$;
