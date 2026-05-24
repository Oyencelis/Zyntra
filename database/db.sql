GRANT SELECT ON public.categories TO authenticated;
GRANT SELECT ON public.categories TO anon;
GRANT SELECT ON public.addresses TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.conversations TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.conversation_messages TO authenticated;
GRANT SELECT ON public.delivery_proofs TO authenticated;
GRANT SELECT ON public.delivery_partners TO authenticated;
GRANT SELECT ON public.notifications TO authenticated;
GRANT SELECT ON public.orders TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.order_items TO authenticated;
GRANT SELECT, UPDATE ON public.order_suborders TO authenticated;
GRANT SELECT ON public.products TO anon;
GRANT SELECT, INSERT, UPDATE ON public.products TO authenticated;
GRANT SELECT ON public.product_attachments TO anon;
GRANT SELECT, INSERT ON public.product_attachments TO authenticated;
GRANT SELECT ON public.product_reviews TO anon, authenticated;
GRANT SELECT ON public.seller_details TO authenticated;
GRANT SELECT ON public.users TO authenticated;
GRANT SELECT, INSERT, DELETE ON public.wishlists TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

ALTER TABLE public.addresses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversation_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.delivery_proofs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.delivery_partners ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_suborders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.seller_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wishlists ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.current_public_user_id()
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT u.user_id
  FROM public.users AS u
  WHERE u.auth_user_id = auth.uid()
     OR lower(u.email) = lower(COALESCE(auth.jwt() ->> 'email', ''))
  ORDER BY CASE WHEN u.auth_user_id = auth.uid() THEN 0 ELSE 1 END, u.user_id
  LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION public.current_public_role_id()
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT u.role_id
  FROM public.users AS u
  WHERE u.auth_user_id = auth.uid()
     OR lower(u.email) = lower(COALESCE(auth.jwt() ->> 'email', ''))
  ORDER BY CASE WHEN u.auth_user_id = auth.uid() THEN 0 ELSE 1 END, u.user_id
  LIMIT 1;
$$;

GRANT EXECUTE ON FUNCTION public.current_public_user_id() TO authenticated;
GRANT EXECUTE ON FUNCTION public.current_public_role_id() TO authenticated;

ALTER TABLE public.order_items ADD COLUMN IF NOT EXISTS pickup_status integer NOT NULL DEFAULT 0;
ALTER TABLE public.order_items ADD COLUMN IF NOT EXISTS pickup_rider_id integer;
ALTER TABLE public.order_items ADD COLUMN IF NOT EXISTS pickup_claimed_at timestamp with time zone;
ALTER TABLE public.order_items ADD COLUMN IF NOT EXISTS pickup_completed_at timestamp with time zone;
ALTER TABLE public.delivery_proofs ADD COLUMN IF NOT EXISTS order_item_id integer;

CREATE OR REPLACE FUNCTION public.order_item_pickup_status(p_item_status integer, p_pickup_status integer)
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT CASE
    WHEN COALESCE(p_pickup_status, 0) > 0 THEN COALESCE(p_pickup_status, 0)
    WHEN COALESCE(p_item_status, 0) IN (4, 6) THEN 4
    WHEN COALESCE(p_item_status, 0) = 3 THEN 3
    WHEN COALESCE(p_item_status, 0) = 2 THEN 1
    ELSE 0
  END;
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

CREATE OR REPLACE FUNCTION public.sync_suborder_status_from_items(p_suborder_id integer)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_counts record;
  v_next_status integer := 1;
  v_next_pickup_status integer := 0;
  v_single_rider_id integer;
BEGIN
  IF COALESCE(p_suborder_id, 0) <= 0 THEN
    RETURN NULL;
  END IF;

  SELECT
    COUNT(*) FILTER (WHERE oi.status NOT IN (5, 8)) AS active_item_count,
    COUNT(*) FILTER (WHERE oi.status = 1) AS placed_count,
    COUNT(*) FILTER (WHERE oi.status = 7) AS accepted_count,
    COUNT(*) FILTER (WHERE oi.status = 2) AS shipped_count,
    COUNT(*) FILTER (WHERE oi.status = 3) AS transit_count,
    COUNT(*) FILTER (WHERE oi.status = 4) AS delivered_count,
    COUNT(*) FILTER (WHERE oi.status = 8) AS rejected_count,
    COUNT(*) FILTER (WHERE oi.status IN (2, 3, 4, 6)) AS pickup_item_count,
    COUNT(*) FILTER (WHERE public.order_item_pickup_status(oi.status, oi.pickup_status) = 1) AS available_pickup_count,
    COUNT(*) FILTER (WHERE public.order_item_pickup_status(oi.status, oi.pickup_status) = 2) AS claimed_pickup_count,
    COUNT(*) FILTER (WHERE public.order_item_pickup_status(oi.status, oi.pickup_status) = 3) AS transit_pickup_count,
    COUNT(*) FILTER (WHERE public.order_item_pickup_status(oi.status, oi.pickup_status) = 4) AS delivered_pickup_count,
    COUNT(DISTINCT oi.pickup_rider_id) FILTER (
      WHERE oi.pickup_rider_id IS NOT NULL
        AND public.order_item_pickup_status(oi.status, oi.pickup_status) IN (2, 3, 4)
    ) AS rider_count,
    MIN(oi.pickup_rider_id) FILTER (
      WHERE oi.pickup_rider_id IS NOT NULL
        AND public.order_item_pickup_status(oi.status, oi.pickup_status) IN (2, 3, 4)
    ) AS single_rider_id,
    MIN(oi.pickup_claimed_at) FILTER (
      WHERE oi.pickup_claimed_at IS NOT NULL
        AND public.order_item_pickup_status(oi.status, oi.pickup_status) IN (2, 3, 4)
    ) AS first_claimed_at,
    MAX(oi.pickup_completed_at) FILTER (
      WHERE oi.pickup_completed_at IS NOT NULL
        AND public.order_item_pickup_status(oi.status, oi.pickup_status) = 4
    ) AS latest_completed_at
  INTO v_counts
  FROM public.order_items AS oi
  WHERE oi.suborder_id = p_suborder_id;

  IF COALESCE(v_counts.active_item_count, 0) = 0 THEN
    v_next_status := CASE WHEN COALESCE(v_counts.rejected_count, 0) > 0 THEN 8 ELSE 5 END;
  ELSIF COALESCE(v_counts.placed_count, 0) > 0 THEN
    v_next_status := 1;
  ELSIF COALESCE(v_counts.accepted_count, 0) > 0 THEN
    v_next_status := 7;
  ELSIF COALESCE(v_counts.shipped_count, 0) > 0 THEN
    v_next_status := 2;
  ELSIF COALESCE(v_counts.transit_count, 0) > 0 THEN
    v_next_status := 3;
  ELSIF COALESCE(v_counts.delivered_count, 0) > 0 THEN
    v_next_status := 4;
  ELSE
    v_next_status := 6;
  END IF;

  IF COALESCE(v_counts.pickup_item_count, 0) = 0 THEN
    v_next_pickup_status := 0;
  ELSIF COALESCE(v_counts.available_pickup_count, 0) > 0 THEN
    v_next_pickup_status := 1;
  ELSIF COALESCE(v_counts.claimed_pickup_count, 0) > 0 THEN
    v_next_pickup_status := 2;
  ELSIF COALESCE(v_counts.transit_pickup_count, 0) > 0 THEN
    v_next_pickup_status := 3;
  ELSE
    v_next_pickup_status := 4;
  END IF;

  v_single_rider_id := CASE
    WHEN COALESCE(v_counts.rider_count, 0) = 1 THEN v_counts.single_rider_id
    ELSE NULL
  END;

  UPDATE public.order_suborders
  SET status = v_next_status,
      pickup_status = v_next_pickup_status,
      pickup_rider_id = v_single_rider_id,
      pickup_claimed_at = CASE WHEN v_single_rider_id IS NOT NULL THEN v_counts.first_claimed_at ELSE NULL END,
      pickup_completed_at = CASE WHEN v_next_pickup_status = 4 THEN v_counts.latest_completed_at ELSE NULL END,
      updated_at = NOW()
  WHERE suborder_id = p_suborder_id;

  RETURN jsonb_build_object(
    'suborder_id', p_suborder_id,
    'status', v_next_status,
    'pickup_status', v_next_pickup_status,
    'pickup_rider_id', v_single_rider_id
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.rider_pickup_item_feed(p_scope text DEFAULT 'available')
RETURNS TABLE(
  order_item_id integer,
  suborder_id integer,
  order_id integer,
  order_reference text,
  sub_reference text,
  item_reference text,
  product_name text,
  quantity integer,
  order_created_at timestamp with time zone,
  status integer,
  pickup_status integer,
  pickup_rider_id integer,
  pickup_claimed_at timestamp with time zone,
  pickup_completed_at timestamp with time zone,
  updated_at timestamp with time zone,
  seller_name text,
  seller_store text,
  seller_location text,
  buyer_id integer,
  buyer_name text,
  buyer_phone text,
  subtotal numeric,
  shipping_fee numeric,
  tax_amount numeric,
  total_amount numeric,
  display_commission numeric,
  commission_label text
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  WITH context AS (
    SELECT
      public.current_public_user_id() AS rider_user_id,
      public.current_public_role_id() AS rider_role_id,
      CASE
        WHEN lower(trim(COALESCE(p_scope, 'available'))) IN ('available', 'mine') THEN lower(trim(COALESCE(p_scope, 'available')))
        ELSE 'available'
      END AS scope
  )
  SELECT
    oi.order_items_id AS order_item_id,
    os.suborder_id,
    os.order_id,
    o.reference AS order_reference,
    os.reference AS sub_reference,
    COALESCE(NULLIF(trim(COALESCE(oi.reference, '')), ''), concat(COALESCE(os.reference, o.reference, 'ORD'), '-ITEM-', oi.order_items_id)) AS item_reference,
    COALESCE(p.product_name, 'Unnamed product') AS product_name,
    COALESCE(oi.quantity, 0) AS quantity,
    o.created_at AS order_created_at,
    oi.status,
    pickup.resolved_pickup_status AS pickup_status,
    pickup.resolved_pickup_rider_id AS pickup_rider_id,
    pickup.resolved_pickup_claimed_at AS pickup_claimed_at,
    pickup.resolved_pickup_completed_at AS pickup_completed_at,
    GREATEST(
      COALESCE(pickup.resolved_pickup_completed_at, '-infinity'::timestamp with time zone),
      COALESCE(pickup.resolved_pickup_claimed_at, '-infinity'::timestamp with time zone),
      COALESCE(os.updated_at, o.created_at, NOW())
    ) AS updated_at,
    COALESCE(NULLIF(trim(concat_ws(' ', seller.firstname, seller.lastname)), ''), sd.store_name, 'Seller') AS seller_name,
    COALESCE(sd.store_name, NULLIF(trim(concat_ws(' ', seller.firstname, seller.lastname)), ''), 'Seller') AS seller_store,
    concat_ws(', ', NULLIF(sd.street, ''), NULLIF(sd.city, ''), NULLIF(sd.province, '')) AS seller_location,
    buyer.user_id AS buyer_id,
    COALESCE(NULLIF(trim(concat_ws(' ', buyer.firstname, buyer.lastname)), ''), 'Buyer') AS buyer_name,
    COALESCE(buyer.phone, '') AS buyer_phone,
    COALESCE(money.line_total, 0) AS subtotal,
    COALESCE(money.shipping_share, 0) AS shipping_fee,
    COALESCE(money.tax_share, 0) AS tax_amount,
    COALESCE(money.total_amount, 0) AS total_amount,
    CASE
      WHEN pickup.resolved_pickup_status = 4 THEN COALESCE(item_ledger.amount, legacy_ledger.amount, COALESCE(money.commission_amount, 0))
      ELSE COALESCE(money.commission_amount, 0)
    END AS display_commission,
    CASE
      WHEN pickup.resolved_pickup_status = 4 THEN 'Credited commission'
      WHEN pickup.resolved_pickup_status IN (2, 3) THEN 'Projected commission'
      ELSE 'Queued commission'
    END AS commission_label
  FROM context AS c
  INNER JOIN public.order_items AS oi ON c.rider_role_id = 4
  INNER JOIN public.order_suborders AS os ON os.suborder_id = oi.suborder_id
  INNER JOIN public.orders AS o ON o.order_id = os.order_id
  LEFT JOIN public.users AS buyer ON buyer.user_id = o.user_id
  INNER JOIN public.users AS seller ON seller.user_id = os.seller_id
  LEFT JOIN public.seller_details AS sd ON sd.user_id = os.seller_id
  LEFT JOIN public.products AS p ON p.product_id = oi.product_id
  LEFT JOIN LATERAL public.order_item_pickup_financials(oi.suborder_id, oi.order_items_id) AS money ON TRUE
  LEFT JOIN LATERAL (
    SELECT MIN(oi2.order_items_id) AS primary_item_id
    FROM public.order_items AS oi2
    WHERE oi2.suborder_id = oi.suborder_id
      AND oi2.status NOT IN (5, 8)
  ) AS primary_item ON TRUE
  LEFT JOIN LATERAL (
    SELECT
      CASE
        WHEN COALESCE(oi.pickup_status, 0) IN (2, 3, 4) THEN oi.pickup_status
        WHEN COALESCE(os.pickup_status, 0) IN (2, 3, 4) AND os.pickup_rider_id IS NOT NULL AND oi.status IN (2, 3, 4, 6) THEN os.pickup_status
        ELSE public.order_item_pickup_status(oi.status, oi.pickup_status)
      END AS resolved_pickup_status,
      CASE
        WHEN oi.pickup_rider_id IS NOT NULL THEN oi.pickup_rider_id
        WHEN COALESCE(os.pickup_status, 0) IN (2, 3, 4) AND oi.status IN (2, 3, 4, 6) THEN os.pickup_rider_id
        ELSE NULL
      END AS resolved_pickup_rider_id,
      COALESCE(
        oi.pickup_claimed_at,
        CASE
          WHEN COALESCE(os.pickup_status, 0) IN (2, 3, 4) AND oi.status IN (2, 3, 4, 6) THEN os.pickup_claimed_at
          ELSE NULL
        END
      ) AS resolved_pickup_claimed_at,
      COALESCE(
        oi.pickup_completed_at,
        CASE
          WHEN COALESCE(os.pickup_status, 0) = 4 AND oi.status IN (4, 6) THEN os.pickup_completed_at
          ELSE NULL
        END
      ) AS resolved_pickup_completed_at
  ) AS pickup ON TRUE
  LEFT JOIN LATERAL (
    SELECT wl.amount
    FROM public.wallet_ledger AS wl
    WHERE wl.user_id = pickup.resolved_pickup_rider_id
      AND wl.wallet_role = 'rider'
      AND wl.entry_kind = 'rider_commission_delivery_item'
      AND wl.reference_id = oi.order_items_id
    ORDER BY wl.ledger_id DESC
    LIMIT 1
  ) AS item_ledger ON TRUE
  LEFT JOIN LATERAL (
    SELECT wl.amount
    FROM public.wallet_ledger AS wl
    WHERE oi.order_items_id = primary_item.primary_item_id
      AND wl.user_id = pickup.resolved_pickup_rider_id
      AND wl.wallet_role = 'rider'
      AND wl.entry_kind = 'rider_commission_delivery'
      AND wl.reference_id = os.suborder_id
    ORDER BY wl.ledger_id DESC
    LIMIT 1
  ) AS legacy_ledger ON TRUE
  WHERE (
    (c.scope = 'mine' AND pickup.resolved_pickup_rider_id = c.rider_user_id AND pickup.resolved_pickup_status IN (2, 3, 4))
    OR (c.scope <> 'mine' AND pickup.resolved_pickup_status = 1 AND pickup.resolved_pickup_rider_id IS NULL)
  )
  ORDER BY updated_at DESC, oi.order_items_id DESC;
$$;

CREATE OR REPLACE FUNCTION public.live_state_snapshot()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer := public.current_public_user_id();
  v_role_id integer := COALESCE(public.current_public_role_id(), 0);
  v_header_counts record;
  v_notification_row record;
  v_message_row record;
  v_cart_row record;
  v_wishlist_row record;
  v_buyer_order_row record;
  v_seller_order_row record;
  v_rider_pickup_row record;
  v_poll_interval_ms integer := 15000;
BEGIN
  IF v_user_id IS NULL OR v_user_id <= 0 THEN
    RETURN jsonb_build_object(
      'authenticated', FALSE,
      'role_id', 0,
      'poll_interval_ms', v_poll_interval_ms,
      'counts', jsonb_build_object(
        'cart_count', 0,
        'wishlist_count', 0,
        'messages_unread_count', 0,
        'notifications_unread_count', 0
      ),
      'tokens', jsonb_build_object(
        'notifications', '',
        'messages', '',
        'cart', '',
        'wishlist', '',
        'buyer_orders', '',
        'seller_orders', '',
        'rider_pickups', ''
      )
    );
  END IF;

  SELECT
    (
      SELECT COUNT(oi.order_items_id)
      FROM public.order_items AS oi
      WHERE oi.user_id = v_user_id
        AND oi.status = 1
        AND (oi.reference = '' OR oi.reference IS NULL)
    ) AS item_count,
    (
      SELECT COUNT(w.wishlist_id)
      FROM public.wishlists AS w
      WHERE w.user_id = v_user_id
    ) AS wishlist_count,
    (
      SELECT COUNT(*)
      FROM public.conversation_messages AS cm
      INNER JOIN public.conversations AS c ON c.conversation_id = cm.conversation_id
      WHERE cm.is_read = 0
        AND (
          (c.buyer_id = v_user_id AND cm.sender_id <> v_user_id)
          OR (c.seller_id = v_user_id AND cm.sender_id <> v_user_id)
        )
    ) AS unread_count
  INTO v_header_counts;

  SELECT COUNT(*) FILTER (WHERE n.is_read = 0) AS unread_count,
         MAX(n.created_at) AS latest_created_at,
         MAX(n.notification_id) AS latest_id
  INTO v_notification_row
  FROM public.notifications AS n
  WHERE n.user_id = v_user_id;

  SELECT COUNT(*) FILTER (
           WHERE cm.is_read = 0
             AND (
               (c.buyer_id = v_user_id AND cm.sender_id <> v_user_id)
               OR (c.seller_id = v_user_id AND cm.sender_id <> v_user_id)
             )
         ) AS unread_count,
         MAX(cm.created_at) AS latest_message_at,
         MAX(cm.message_id) AS latest_message_id
  INTO v_message_row
  FROM public.conversation_messages AS cm
  INNER JOIN public.conversations AS c ON c.conversation_id = cm.conversation_id
  WHERE c.buyer_id = v_user_id OR c.seller_id = v_user_id;

  SELECT COUNT(oi.order_items_id) AS item_count,
         COALESCE(SUM(oi.quantity), 0) AS total_quantity,
         MAX(oi.order_items_id) AS latest_item_id
  INTO v_cart_row
  FROM public.order_items AS oi
  WHERE oi.user_id = v_user_id
    AND oi.status = 1
    AND (oi.reference = '' OR oi.reference IS NULL);

  SELECT COUNT(w.wishlist_id) AS item_count,
         MAX(w.wishlist_id) AS latest_id
  INTO v_wishlist_row
  FROM public.wishlists AS w
  WHERE w.user_id = v_user_id;

  SELECT COUNT(DISTINCT o.order_id) AS item_count,
         MAX(COALESCE(os.updated_at, o.updated_at, o.created_at)) AS latest_updated_at,
         MAX(os.suborder_id) AS latest_id
  INTO v_buyer_order_row
  FROM public.orders AS o
  LEFT JOIN public.order_suborders AS os ON os.order_id = o.order_id
  WHERE o.user_id = v_user_id;

  IF v_role_id = 3 THEN
    SELECT COUNT(*) AS item_count,
           MAX(os.updated_at) AS latest_updated_at,
           MAX(os.suborder_id) AS latest_id
    INTO v_seller_order_row
    FROM public.order_suborders AS os
    WHERE os.seller_id = v_user_id;
  ELSE
    SELECT 0 AS item_count,
           NULL::timestamp with time zone AS latest_updated_at,
           0 AS latest_id
    INTO v_seller_order_row;
  END IF;

  IF v_role_id = 4 THEN
    SELECT COUNT(*) AS item_count,
           MAX(
             GREATEST(
               COALESCE(oi.pickup_completed_at, '-infinity'::timestamp with time zone),
               COALESCE(oi.pickup_claimed_at, '-infinity'::timestamp with time zone),
               COALESCE(os.updated_at, '-infinity'::timestamp with time zone)
             )
           ) AS latest_updated_at,
           MAX(oi.order_items_id) AS latest_id
    INTO v_rider_pickup_row
    FROM public.order_items AS oi
    INNER JOIN public.order_suborders AS os ON os.suborder_id = oi.suborder_id
    WHERE public.order_item_pickup_status(oi.status, oi.pickup_status) = 1
       OR COALESCE(oi.pickup_rider_id, os.pickup_rider_id) = v_user_id;
  ELSE
    SELECT 0 AS item_count,
           NULL::timestamp with time zone AS latest_updated_at,
           0 AS latest_id
    INTO v_rider_pickup_row;
  END IF;

  RETURN jsonb_build_object(
    'authenticated', TRUE,
    'role_id', v_role_id,
    'poll_interval_ms', v_poll_interval_ms,
    'counts', jsonb_build_object(
      'cart_count', COALESCE(v_header_counts.item_count, 0),
      'wishlist_count', COALESCE(v_header_counts.wishlist_count, 0),
      'messages_unread_count', COALESCE(v_message_row.unread_count, v_header_counts.unread_count, 0),
      'notifications_unread_count', COALESCE(v_notification_row.unread_count, 0)
    ),
    'tokens', jsonb_build_object(
      'notifications', concat_ws(':', 'notifications', COALESCE(v_notification_row.unread_count, 0), COALESCE(v_notification_row.latest_id, 0), COALESCE(v_notification_row.latest_created_at::text, '')),
      'messages', concat_ws(':', 'messages', COALESCE(v_message_row.unread_count, 0), COALESCE(v_message_row.latest_message_id, 0), COALESCE(v_message_row.latest_message_at::text, '')),
      'cart', concat_ws(':', 'cart', COALESCE(v_cart_row.item_count, 0), COALESCE(v_cart_row.total_quantity, 0), COALESCE(v_cart_row.latest_item_id, 0)),
      'wishlist', concat_ws(':', 'wishlist', COALESCE(v_wishlist_row.item_count, 0), COALESCE(v_wishlist_row.latest_id, 0)),
      'buyer_orders', concat_ws(':', 'buyer_orders', COALESCE(v_buyer_order_row.item_count, 0), COALESCE(v_buyer_order_row.latest_id, 0), COALESCE(v_buyer_order_row.latest_updated_at::text, '')),
      'seller_orders', CASE
        WHEN v_role_id = 3 THEN concat_ws(':', 'seller_orders', COALESCE(v_seller_order_row.item_count, 0), COALESCE(v_seller_order_row.latest_id, 0), COALESCE(v_seller_order_row.latest_updated_at::text, ''))
        ELSE ''
      END,
      'rider_pickups', CASE
        WHEN v_role_id = 4 THEN concat_ws(':', 'rider_pickups', COALESCE(v_rider_pickup_row.item_count, 0), COALESCE(v_rider_pickup_row.latest_id, 0), COALESCE(v_rider_pickup_row.latest_updated_at::text, ''))
        ELSE ''
      END
    )
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.live_state_snapshot() TO authenticated;

CREATE OR REPLACE FUNCTION public.buyer_owns_order(p_order_id integer)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.orders AS o
    WHERE o.order_id = p_order_id
      AND o.user_id = public.current_public_user_id()
      AND public.current_public_role_id() = 2
  );
$$;

CREATE OR REPLACE FUNCTION public.seller_can_read_parent_order(p_order_id integer)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.order_suborders AS os
    WHERE os.order_id = p_order_id
      AND os.seller_id = public.current_public_user_id()
      AND public.current_public_role_id() = 3
  );
$$;

CREATE OR REPLACE FUNCTION public.seller_can_read_buyer_user(p_user_id integer)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.orders AS o
    INNER JOIN public.order_suborders AS os ON os.order_id = o.order_id
    WHERE o.user_id = p_user_id
      AND os.seller_id = public.current_public_user_id()
      AND public.current_public_role_id() = 3
  );
$$;

GRANT EXECUTE ON FUNCTION public.buyer_owns_order(integer) TO authenticated;
GRANT EXECUTE ON FUNCTION public.seller_can_read_parent_order(integer) TO authenticated;
GRANT EXECUTE ON FUNCTION public.seller_can_read_buyer_user(integer) TO authenticated;

CREATE OR REPLACE FUNCTION public.can_access_order_chat(
  p_buyer_id integer,
  p_counterpart_id integer,
  p_order_id integer
)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT CASE
    WHEN public.current_public_user_id() IS NULL OR p_order_id IS NULL THEN FALSE
    WHEN public.current_public_role_id() = 2 THEN EXISTS (
      SELECT 1
      FROM public.orders AS o
      WHERE o.order_id = p_order_id
        AND o.user_id = public.current_public_user_id()
        AND o.user_id = p_buyer_id
        AND EXISTS (
          SELECT 1
          FROM public.order_suborders AS os
          WHERE os.order_id = o.order_id
            AND (
              os.seller_id = p_counterpart_id
              OR os.pickup_rider_id = p_counterpart_id
            )
        )
    )
    WHEN public.current_public_role_id() = 3 THEN EXISTS (
      SELECT 1
      FROM public.orders AS o
      INNER JOIN public.order_suborders AS os ON os.order_id = o.order_id
      WHERE o.order_id = p_order_id
        AND o.user_id = p_buyer_id
        AND os.seller_id = public.current_public_user_id()
        AND p_counterpart_id = public.current_public_user_id()
    )
    WHEN public.current_public_role_id() = 4 THEN EXISTS (
      SELECT 1
      FROM public.orders AS o
      INNER JOIN public.order_suborders AS os ON os.order_id = o.order_id
      WHERE o.order_id = p_order_id
        AND o.user_id = p_buyer_id
        AND os.pickup_rider_id = public.current_public_user_id()
        AND p_counterpart_id = public.current_public_user_id()
    )
    ELSE FALSE
  END;
$$;

CREATE OR REPLACE FUNCTION public.can_access_conversation(p_conversation_id integer)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.conversations AS c
    WHERE c.conversation_id = p_conversation_id
      AND public.can_access_order_chat(c.buyer_id, c.seller_id, c.order_id)
  );
$$;

GRANT EXECUTE ON FUNCTION public.can_access_order_chat(integer, integer, integer) TO authenticated;
GRANT EXECUTE ON FUNCTION public.can_access_conversation(integer) TO authenticated;

CREATE OR REPLACE FUNCTION public.buyer_save_address(
  p_floor_unit_number text DEFAULT NULL,
  p_region text DEFAULT NULL,
  p_province text DEFAULT NULL,
  p_city_municipality text DEFAULT NULL,
  p_barangay text DEFAULT NULL,
  p_street text DEFAULT NULL,
  p_other_notes text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_address_id integer;
  v_floor_unit_number text := NULLIF(trim(COALESCE(p_floor_unit_number, '')), '');
  v_region text := NULLIF(trim(COALESCE(p_region, '')), '');
  v_province text := NULLIF(trim(COALESCE(p_province, '')), '');
  v_city_municipality text := NULLIF(trim(COALESCE(p_city_municipality, '')), '');
  v_barangay text := NULLIF(trim(COALESCE(p_barangay, '')), '');
  v_street text := NULLIF(trim(COALESCE(p_street, '')), '');
  v_other_notes text := NULLIF(trim(COALESCE(p_other_notes, '')), '');
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 2 THEN
    RAISE EXCEPTION 'Buyer access required.';
  END IF;

  IF v_region IS NULL OR v_province IS NULL OR v_city_municipality IS NULL OR v_barangay IS NULL OR v_street IS NULL THEN
    RAISE EXCEPTION 'Complete address details are required.';
  END IF;

  SELECT a.address_id
  INTO v_address_id
  FROM public.addresses AS a
  WHERE a.user_id = v_user_id
  ORDER BY a.updated_at DESC NULLS LAST, a.address_id DESC
  LIMIT 1;

  IF v_address_id IS NULL THEN
    INSERT INTO public.addresses (
      user_id,
      floor_unit_number,
      region,
      province,
      city_municipality,
      barangay,
      street,
      other_notes,
      created_at,
      updated_at
    )
    VALUES (
      v_user_id,
      v_floor_unit_number,
      v_region,
      v_province,
      v_city_municipality,
      v_barangay,
      v_street,
      v_other_notes,
      NOW(),
      NOW()
    )
    RETURNING address_id INTO v_address_id;
  ELSE
    UPDATE public.addresses
    SET floor_unit_number = v_floor_unit_number,
        region = v_region,
        province = v_province,
        city_municipality = v_city_municipality,
        barangay = v_barangay,
        street = v_street,
        other_notes = v_other_notes,
        updated_at = NOW()
    WHERE address_id = v_address_id;
  END IF;

  RETURN jsonb_build_object(
    'address_id', v_address_id,
    'floor_unit_number', v_floor_unit_number,
    'region', v_region,
    'province', v_province,
    'city_municipality', v_city_municipality,
    'barangay', v_barangay,
    'street', v_street,
    'other_notes', v_other_notes
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.buyer_save_address(text, text, text, text, text, text, text) TO authenticated;

CREATE OR REPLACE FUNCTION public.update_personal_info(
  p_firstname text,
  p_lastname text,
  p_phone text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_firstname text := NULLIF(trim(COALESCE(p_firstname, '')), '');
  v_lastname text := NULLIF(trim(COALESCE(p_lastname, '')), '');
  v_phone text := NULLIF(trim(COALESCE(p_phone, '')), '');
BEGIN
  v_user_id := public.current_public_user_id();

  IF v_user_id IS NULL OR v_user_id <= 0 THEN
    RAISE EXCEPTION 'Authenticated user required.';
  END IF;

  IF v_firstname IS NULL OR v_lastname IS NULL THEN
    RAISE EXCEPTION 'First name and last name are required.';
  END IF;

  UPDATE public.users
  SET firstname = v_firstname,
      lastname = v_lastname,
      phone = v_phone,
      updated_at = NOW()
  WHERE user_id = v_user_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Profile not found.';
  END IF;

  RETURN jsonb_build_object(
    'user_id', v_user_id,
    'firstname', v_firstname,
    'lastname', v_lastname,
    'phone', v_phone
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.update_personal_info(text, text, text) TO authenticated;

CREATE OR REPLACE FUNCTION public.get_seller_wallet_summary()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_ledger_balance numeric := 0;
  v_pending numeric := 0;
  v_available numeric := 0;
  v_last_requested_at timestamptz;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 3 THEN
    RAISE EXCEPTION 'Seller access required.';
  END IF;

  SELECT COALESCE(SUM(wl.amount), 0)
  INTO v_ledger_balance
  FROM public.wallet_ledger AS wl
  WHERE wl.user_id = v_user_id
    AND wl.wallet_role = 'seller';

  SELECT COALESCE(SUM(wr.amount), 0), MAX(wr.created_at)
  INTO v_pending, v_last_requested_at
  FROM public.withdrawal_requests AS wr
  WHERE wr.user_id = v_user_id
    AND wr.wallet_role = 'seller'
    AND wr.status = 'pending';

  v_available := GREATEST(COALESCE(v_ledger_balance, 0) - COALESCE(v_pending, 0), 0);

  RETURN jsonb_build_object(
    'wallet_role', 'seller',
    'ledger_balance', COALESCE(v_ledger_balance, 0),
    'pending_withdrawals', COALESCE(v_pending, 0),
    'available_balance', COALESCE(v_available, 0),
    'last_requested_at', v_last_requested_at
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_seller_wallet_summary() TO authenticated;

CREATE OR REPLACE FUNCTION public.seller_request_withdrawal(
  p_amount numeric,
  p_payout_notes text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_amount numeric := ROUND(COALESCE(p_amount, 0)::numeric, 2);
  v_payout_notes text := NULLIF(trim(COALESCE(p_payout_notes, '')), '');
  v_ledger_balance numeric := 0;
  v_pending numeric := 0;
  v_available numeric := 0;
  v_withdrawal_id bigint;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 3 THEN
    RAISE EXCEPTION 'Seller access required.';
  END IF;

  IF v_amount <= 0 THEN
    RAISE EXCEPTION 'Invalid withdrawal amount.';
  END IF;

  IF v_payout_notes IS NULL THEN
    RAISE EXCEPTION 'Payout notes are required.';
  END IF;

  SELECT COALESCE(SUM(wl.amount), 0)
  INTO v_ledger_balance
  FROM public.wallet_ledger AS wl
  WHERE wl.user_id = v_user_id
    AND wl.wallet_role = 'seller';

  SELECT COALESCE(SUM(wr.amount), 0)
  INTO v_pending
  FROM public.withdrawal_requests AS wr
  WHERE wr.user_id = v_user_id
    AND wr.wallet_role = 'seller'
    AND wr.status = 'pending';

  v_available := GREATEST(COALESCE(v_ledger_balance, 0) - COALESCE(v_pending, 0), 0);

  IF v_amount > v_available THEN
    RAISE EXCEPTION 'Insufficient available balance (pending withdrawals are reserved).';
  END IF;

  INSERT INTO public.withdrawal_requests (
    user_id,
    wallet_role,
    amount,
    payout_notes,
    status,
    created_at
  )
  VALUES (
    v_user_id,
    'seller',
    v_amount,
    left(v_payout_notes, 2000),
    'pending',
    NOW()
  )
  RETURNING withdrawal_id INTO v_withdrawal_id;

  INSERT INTO public.withdrawal_audit (
    withdrawal_id,
    action,
    actor_user_id,
    detail,
    created_at
  )
  VALUES (
    v_withdrawal_id,
    'created',
    v_user_id,
    left(v_payout_notes, 500),
    NOW()
  );

  RETURN jsonb_build_object(
    'withdrawal_id', v_withdrawal_id,
    'amount', v_amount,
    'status', 'pending',
    'available_balance', ROUND(v_available - v_amount, 2)
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.seller_request_withdrawal(numeric, text) TO authenticated;

CREATE OR REPLACE FUNCTION public.get_rider_wallet_summary()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_ledger_balance numeric := 0;
  v_pending numeric := 0;
  v_available numeric := 0;
  v_last_requested_at timestamptz;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 4 THEN
    RAISE EXCEPTION 'Rider access required.';
  END IF;

  SELECT COALESCE(SUM(wl.amount), 0)
  INTO v_ledger_balance
  FROM public.wallet_ledger AS wl
  WHERE wl.user_id = v_user_id
    AND wl.wallet_role = 'rider';

  SELECT
    COALESCE(SUM(CASE WHEN wr.status = 'pending' THEN wr.amount ELSE 0 END), 0),
    MAX(wr.created_at)
  INTO v_pending, v_last_requested_at
  FROM public.withdrawal_requests AS wr
  WHERE wr.user_id = v_user_id
    AND wr.wallet_role = 'rider';

  v_available := GREATEST(COALESCE(v_ledger_balance, 0) - COALESCE(v_pending, 0), 0);

  RETURN jsonb_build_object(
    'wallet_role', 'rider',
    'ledger_balance', COALESCE(v_ledger_balance, 0),
    'pending_withdrawals', COALESCE(v_pending, 0),
    'available_balance', COALESCE(v_available, 0),
    'last_requested_at', v_last_requested_at
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_rider_wallet_summary() TO authenticated;

CREATE OR REPLACE FUNCTION public.rider_request_withdrawal(
  p_amount numeric,
  p_payout_notes text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_amount numeric := ROUND(COALESCE(p_amount, 0)::numeric, 2);
  v_payout_notes text := NULLIF(trim(COALESCE(p_payout_notes, '')), '');
  v_ledger_balance numeric := 0;
  v_pending numeric := 0;
  v_available numeric := 0;
  v_withdrawal_id bigint;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 4 THEN
    RAISE EXCEPTION 'Rider access required.';
  END IF;

  IF v_amount <= 0 THEN
    RAISE EXCEPTION 'Invalid withdrawal amount.';
  END IF;

  IF v_payout_notes IS NULL THEN
    RAISE EXCEPTION 'Payout notes are required.';
  END IF;

  SELECT COALESCE(SUM(wl.amount), 0)
  INTO v_ledger_balance
  FROM public.wallet_ledger AS wl
  WHERE wl.user_id = v_user_id
    AND wl.wallet_role = 'rider';

  SELECT COALESCE(SUM(wr.amount), 0)
  INTO v_pending
  FROM public.withdrawal_requests AS wr
  WHERE wr.user_id = v_user_id
    AND wr.wallet_role = 'rider'
    AND wr.status = 'pending';

  v_available := GREATEST(COALESCE(v_ledger_balance, 0) - COALESCE(v_pending, 0), 0);

  IF v_amount > v_available THEN
    RAISE EXCEPTION 'Insufficient available balance (pending withdrawals are reserved).';
  END IF;

  INSERT INTO public.withdrawal_requests (
    user_id,
    wallet_role,
    amount,
    payout_notes,
    status,
    created_at
  )
  VALUES (
    v_user_id,
    'rider',
    v_amount,
    left(v_payout_notes, 2000),
    'pending',
    NOW()
  )
  RETURNING withdrawal_id INTO v_withdrawal_id;

  INSERT INTO public.withdrawal_audit (
    withdrawal_id,
    action,
    actor_user_id,
    detail,
    created_at
  )
  VALUES (
    v_withdrawal_id,
    'created',
    v_user_id,
    left(v_payout_notes, 500),
    NOW()
  );

  RETURN jsonb_build_object(
    'withdrawal_id', v_withdrawal_id,
    'amount', v_amount,
    'status', 'pending',
    'available_balance', ROUND(v_available - v_amount, 2)
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.rider_request_withdrawal(numeric, text) TO authenticated;

CREATE OR REPLACE FUNCTION public.seller_update_suborder_status(p_suborder_id integer, p_status integer)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_status integer := COALESCE(p_status, 0);
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 3 THEN
    RAISE EXCEPTION 'Seller access required.';
  END IF;

  IF COALESCE(p_suborder_id, 0) <= 0 THEN
    RAISE EXCEPTION 'Sub-order is required.';
  END IF;

  IF v_status NOT IN (2, 7, 8) THEN
    RAISE EXCEPTION 'Invalid seller status.';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.order_suborders AS os
    WHERE os.suborder_id = p_suborder_id
      AND os.seller_id = v_user_id
  ) THEN
    RAISE EXCEPTION 'Sub-order not found or you do not have permission to update it.';
  END IF;

  IF v_status = 2 THEN
    UPDATE public.order_suborders
    SET status = v_status,
        pickup_status = 1,
        pickup_rider_id = NULL,
        pickup_claimed_at = NULL,
        pickup_completed_at = NULL,
        updated_at = NOW()
    WHERE suborder_id = p_suborder_id
      AND seller_id = v_user_id;
  ELSE
    UPDATE public.order_suborders
    SET status = v_status,
        updated_at = NOW()
    WHERE suborder_id = p_suborder_id
      AND seller_id = v_user_id;
  END IF;

  UPDATE public.order_items
  SET status = v_status
  WHERE suborder_id = p_suborder_id;

  RETURN jsonb_build_object(
    'suborder_id', p_suborder_id,
    'status', v_status,
    'pickup_status', CASE WHEN v_status = 2 THEN 1 ELSE NULL END
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.seller_update_suborder_status(integer, integer) TO authenticated;

CREATE OR REPLACE FUNCTION public.seller_update_order_item_status(p_order_item_id integer, p_suborder_id integer, p_status integer)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_status integer := COALESCE(p_status, 0);
  v_current_status integer;
  v_previous_pickup_status integer := 0;
  v_next_status integer := 1;
  v_next_pickup_status integer := 0;
  v_active_item_count integer := 0;
  v_placed_count integer := 0;
  v_accepted_count integer := 0;
  v_rejected_count integer := 0;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 3 THEN
    RAISE EXCEPTION 'Seller access required.';
  END IF;

  IF COALESCE(p_suborder_id, 0) <= 0 THEN
    RAISE EXCEPTION 'Sub-order is required.';
  END IF;

  IF COALESCE(p_order_item_id, 0) <= 0 THEN
    RAISE EXCEPTION 'Order item is required.';
  END IF;

  IF v_status NOT IN (2, 7, 8) THEN
    RAISE EXCEPTION 'Invalid seller status.';
  END IF;

  SELECT oi.status,
         COALESCE(os.pickup_status, 0)
  INTO v_current_status,
       v_previous_pickup_status
  FROM public.order_items AS oi
  INNER JOIN public.order_suborders AS os ON os.suborder_id = oi.suborder_id
  WHERE oi.order_items_id = p_order_item_id
    AND oi.suborder_id = p_suborder_id
    AND os.seller_id = v_user_id
  LIMIT 1;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Order item not found or you do not have permission to update it.';
  END IF;

  IF v_current_status = 1 AND v_status NOT IN (7, 8) THEN
    RAISE EXCEPTION 'This item can no longer be updated to the selected status.';
  END IF;

  IF v_current_status = 7 AND v_status <> 2 THEN
    RAISE EXCEPTION 'This item can no longer be updated to the selected status.';
  END IF;

  IF v_current_status NOT IN (1, 7) THEN
    RAISE EXCEPTION 'This item can no longer be updated to the selected status.';
  END IF;

  UPDATE public.order_items
  SET status = v_status,
      pickup_status = CASE WHEN v_status = 2 THEN 1 ELSE 0 END,
      pickup_rider_id = CASE WHEN v_status = 2 THEN NULL ELSE pickup_rider_id END,
      pickup_claimed_at = CASE WHEN v_status = 2 THEN NULL ELSE pickup_claimed_at END,
      pickup_completed_at = CASE WHEN v_status = 2 THEN NULL ELSE pickup_completed_at END
  WHERE order_items_id = p_order_item_id
    AND suborder_id = p_suborder_id;

  RETURN public.sync_suborder_status_from_items(p_suborder_id)
    || jsonb_build_object(
      'order_item_id', p_order_item_id,
      'suborder_id', p_suborder_id,
      'status', v_status,
      'pickup_status_changed', CASE WHEN v_status = 2 AND v_previous_pickup_status <> 1 THEN TRUE ELSE FALSE END
    );

  SELECT COUNT(*) FILTER (WHERE oi.status NOT IN (5, 8)),
         COUNT(*) FILTER (WHERE oi.status = 1),
         COUNT(*) FILTER (WHERE oi.status = 7),
         COUNT(*) FILTER (WHERE oi.status = 8)
  INTO v_active_item_count,
       v_placed_count,
       v_accepted_count,
       v_rejected_count
  FROM public.order_items AS oi
  WHERE oi.suborder_id = p_suborder_id;

  IF v_active_item_count = 0 THEN
    v_next_status := CASE WHEN v_rejected_count > 0 THEN 8 ELSE 5 END;
  ELSIF v_placed_count > 0 THEN
    v_next_status := 1;
  ELSIF v_accepted_count > 0 THEN
    v_next_status := 7;
  ELSE
    v_next_status := 2;
    v_next_pickup_status := 1;
  END IF;

  UPDATE public.order_suborders
  SET status = v_next_status,
      pickup_status = v_next_pickup_status,
      pickup_rider_id = CASE WHEN v_next_pickup_status = 1 THEN NULL ELSE pickup_rider_id END,
      pickup_claimed_at = CASE WHEN v_next_pickup_status = 1 THEN NULL ELSE pickup_claimed_at END,
      pickup_completed_at = CASE WHEN v_next_pickup_status = 1 THEN NULL ELSE pickup_completed_at END,
      updated_at = NOW()
  WHERE suborder_id = p_suborder_id
    AND seller_id = v_user_id;

  RETURN jsonb_build_object(
    'order_item_id', p_order_item_id,
    'suborder_id', p_suborder_id,
    'status', v_status,
    'suborder_status', v_next_status,
    'pickup_status', v_next_pickup_status,
    'pickup_status_changed', CASE WHEN v_next_pickup_status = 1 AND v_previous_pickup_status <> 1 THEN TRUE ELSE FALSE END
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.seller_update_order_item_status(integer, integer, integer) TO authenticated;

CREATE OR REPLACE FUNCTION public.rider_get_pickups(p_scope text DEFAULT 'available')
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'order_item_id', r.order_item_id,
        'suborder_id', r.suborder_id,
        'order_id', r.order_id,
        'order_reference', r.order_reference,
        'sub_reference', r.sub_reference,
        'item_reference', r.item_reference,
        'product_name', r.product_name,
        'quantity', r.quantity,
        'order_created_at', r.order_created_at,
        'status', r.status,
        'pickup_status', r.pickup_status,
        'pickup_rider_id', r.pickup_rider_id,
        'pickup_claimed_at', r.pickup_claimed_at,
        'pickup_completed_at', r.pickup_completed_at,
        'updated_at', r.updated_at,
        'seller_name', r.seller_name,
        'seller_store', r.seller_store,
        'seller_location', r.seller_location,
        'buyer_id', r.buyer_id,
        'buyer_name', r.buyer_name,
        'buyer_phone', r.buyer_phone,
        'subtotal', r.subtotal,
        'shipping_fee', r.shipping_fee,
        'tax_amount', r.tax_amount,
        'total_amount', r.total_amount,
        'display_commission', r.display_commission,
        'commission_label', r.commission_label
      )
      ORDER BY r.updated_at DESC, r.order_item_id DESC
    ),
    '[]'::jsonb
  )
  FROM public.rider_pickup_item_feed(p_scope) AS r;
$$;

CREATE OR REPLACE FUNCTION public.rider_get_pickup_detail(p_order_item_id integer)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_summary record;
  v_items jsonb := '[]'::jsonb;
  v_buyer_address text;
  v_delivery_proof_count integer := 0;
  v_delivery_proof_image text;
  v_delivery_proof_captured_at timestamptz;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 4 THEN
    RAISE EXCEPTION 'Rider access required.';
  END IF;

  SELECT *
  INTO v_summary
  FROM public.rider_pickup_item_feed('mine') AS r
  WHERE r.order_item_id = p_order_item_id
  LIMIT 1;

  IF v_summary.order_item_id IS NULL THEN
    RAISE EXCEPTION 'Pickup not found.';
  END IF;

  SELECT COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'order_items_id', item_rows.order_items_id,
        'product_id', item_rows.product_id,
        'product_name', item_rows.product_name,
        'reference', item_rows.reference,
        'quantity', item_rows.quantity,
        'status', item_rows.status,
        'unit_price', item_rows.price,
        'line_total', item_rows.price * item_rows.quantity,
        'product_image', item_rows.product_image
      )
      ORDER BY item_rows.order_items_id ASC
    ),
    '[]'::jsonb
  )
  INTO v_items
  FROM (
    SELECT
      oi.order_items_id,
      oi.product_id,
      oi.quantity,
      oi.status,
      COALESCE(NULLIF(trim(COALESCE(oi.reference, '')), ''), concat(COALESCE(v_summary.sub_reference, v_summary.order_reference, 'ORD'), '-ITEM-', oi.order_items_id)) AS reference,
      COALESCE(p.product_name, 'Unnamed product') AS product_name,
      COALESCE(p.price, 0) AS price,
      (
        SELECT pa.attachment
        FROM public.product_attachments AS pa
        WHERE pa.product_id = p.product_id AND pa.status = 1
        ORDER BY pa.updated_at DESC NULLS LAST, pa.product_attachment_id DESC
        LIMIT 1
      ) AS product_image
    FROM public.order_items AS oi
    LEFT JOIN public.products AS p ON p.product_id = oi.product_id
    WHERE oi.suborder_id = v_summary.suborder_id
  ) AS item_rows;

  SELECT concat_ws(
    ', ',
    NULLIF(a.floor_unit_number, ''),
    NULLIF(a.street, ''),
    NULLIF(a.barangay, ''),
    NULLIF(a.city_municipality, ''),
    NULLIF(a.province, ''),
    NULLIF(a.region, ''),
    NULLIF(a.other_notes, '')
  )
  INTO v_buyer_address
  FROM public.addresses AS a
  WHERE a.user_id = v_summary.buyer_id
  ORDER BY a.updated_at DESC NULLS LAST, a.address_id DESC
  LIMIT 1;

  SELECT COUNT(*)::integer
  INTO v_delivery_proof_count
  FROM public.delivery_proofs AS dp
  WHERE dp.order_item_id = p_order_item_id;

  SELECT dp.image_path, dp.captured_at
  INTO v_delivery_proof_image, v_delivery_proof_captured_at
  FROM public.delivery_proofs AS dp
  WHERE dp.order_item_id = p_order_item_id
  ORDER BY dp.created_at DESC, dp.proof_id DESC
  LIMIT 1;

  RETURN jsonb_build_object(
    'order_item_id', v_summary.order_item_id,
    'suborder_id', v_summary.suborder_id,
    'order_id', v_summary.order_id,
    'order_reference', v_summary.order_reference,
    'sub_reference', v_summary.sub_reference,
    'item_reference', v_summary.item_reference,
    'product_name', v_summary.product_name,
    'quantity', v_summary.quantity,
    'order_created_at', v_summary.order_created_at,
    'status', v_summary.status,
    'pickup_status', v_summary.pickup_status,
    'pickup_rider_id', v_summary.pickup_rider_id,
    'pickup_claimed_at', v_summary.pickup_claimed_at,
    'pickup_completed_at', v_summary.pickup_completed_at,
    'updated_at', v_summary.updated_at,
    'seller_name', v_summary.seller_name,
    'seller_store', v_summary.seller_store,
    'seller_location', v_summary.seller_location,
    'buyer_id', v_summary.buyer_id,
    'buyer_name', v_summary.buyer_name,
    'buyer_phone', v_summary.buyer_phone,
    'subtotal', v_summary.subtotal,
    'shipping_fee', v_summary.shipping_fee,
    'tax_amount', v_summary.tax_amount,
    'total_amount', v_summary.total_amount,
    'display_commission', v_summary.display_commission,
    'commission_label', v_summary.commission_label,
    'buyer_address', v_buyer_address,
    'delivery_proof_count', v_delivery_proof_count,
    'delivery_proof_image', v_delivery_proof_image,
    'delivery_proof_captured_at', v_delivery_proof_captured_at,
    'items', v_items
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.rider_claim_pickup_assignment(p_order_item_id integer)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_suborder_id integer;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 4 THEN
    RAISE EXCEPTION 'Rider access required.';
  END IF;

  UPDATE public.order_items AS oi
  SET pickup_rider_id = v_user_id,
      pickup_status = 2,
      pickup_claimed_at = NOW(),
      pickup_completed_at = NULL
  WHERE oi.order_items_id = p_order_item_id
    AND public.order_item_pickup_status(oi.status, oi.pickup_status) = 1
    AND oi.pickup_rider_id IS NULL
  RETURNING oi.suborder_id INTO v_suborder_id;

  IF v_suborder_id IS NULL THEN
    RAISE EXCEPTION 'This pickup has already been claimed.';
  END IF;

  PERFORM public.sync_suborder_status_from_items(v_suborder_id);

  RETURN public.rider_get_pickup_detail(p_order_item_id);
END;
$$;

CREATE OR REPLACE FUNCTION public.rider_save_delivery_proof(
  p_order_item_id integer,
  p_image_path text,
  p_latitude double precision DEFAULT NULL,
  p_longitude double precision DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_pickup_rider_id integer;
  v_suborder_id integer;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 4 THEN
    RAISE EXCEPTION 'Rider access required.';
  END IF;

  SELECT r.suborder_id, r.pickup_rider_id
  INTO v_suborder_id, v_pickup_rider_id
  FROM public.rider_pickup_item_feed('mine') AS r
  WHERE r.order_item_id = p_order_item_id
  LIMIT 1;

  IF v_pickup_rider_id IS NULL THEN
    RAISE EXCEPTION 'Pickup not found.';
  END IF;

  IF v_pickup_rider_id IS DISTINCT FROM v_user_id THEN
    RAISE EXCEPTION 'You are not assigned to this pickup.';
  END IF;

  IF NULLIF(trim(COALESCE(p_image_path, '')), '') IS NULL THEN
    RAISE EXCEPTION 'Delivery proof image is required.';
  END IF;

  INSERT INTO public.delivery_proofs (
    suborder_id,
    order_item_id,
    rider_user_id,
    image_path,
    latitude,
    longitude
  )
  VALUES (
    v_suborder_id,
    p_order_item_id,
    v_user_id,
    trim(p_image_path),
    p_latitude,
    p_longitude
  );

  RETURN public.rider_get_pickup_detail(p_order_item_id);
END;
$$;

CREATE OR REPLACE FUNCTION public.rider_update_pickup_status(p_order_item_id integer, p_status integer)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_summary record;
  v_proof_count integer := 0;
  v_commission_amount numeric := 0;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 4 THEN
    RAISE EXCEPTION 'Rider access required.';
  END IF;

  IF p_status NOT IN (3, 4) THEN
    RAISE EXCEPTION 'Invalid status.';
  END IF;

  SELECT *
  INTO v_summary
  FROM public.rider_pickup_item_feed('mine') AS r
  WHERE r.order_item_id = p_order_item_id
  LIMIT 1;

  IF v_summary.order_item_id IS NULL THEN
    RAISE EXCEPTION 'Pickup not found.';
  END IF;

  IF v_summary.pickup_rider_id IS DISTINCT FROM v_user_id THEN
    RAISE EXCEPTION 'You are not assigned to this pickup.';
  END IF;

  IF p_status = 3 AND COALESCE(v_summary.pickup_status, 0) NOT IN (2, 3) THEN
    RAISE EXCEPTION 'Invalid pickup status transition.';
  END IF;

  IF p_status = 4 AND COALESCE(v_summary.pickup_status, 0) NOT IN (2, 3, 4) THEN
    RAISE EXCEPTION 'Invalid pickup status transition.';
  END IF;

  IF p_status = 4 THEN
    SELECT COUNT(*)::integer
    INTO v_proof_count
    FROM public.delivery_proofs
    WHERE order_item_id = p_order_item_id;

    IF COALESCE(v_proof_count, 0) < 1 THEN
      RAISE EXCEPTION 'Please upload a delivery proof photo before marking this order as delivered.';
    END IF;

    UPDATE public.order_items
    SET pickup_status = 4,
        pickup_rider_id = v_user_id,
        pickup_completed_at = NOW(),
        status = 4
    WHERE order_items_id = p_order_item_id;

    SELECT commission_amount
    INTO v_commission_amount
    FROM public.order_item_pickup_financials(v_summary.suborder_id, p_order_item_id)
    LIMIT 1;

    IF COALESCE(v_commission_amount, 0) > 0 THEN
      INSERT INTO public.wallet_ledger (user_id, wallet_role, amount, entry_kind, reference_id, note)
      SELECT v_user_id, 'rider', ROUND(v_commission_amount, 2), 'rider_commission_delivery_item', p_order_item_id, 'Rider delivery commission and product share'
      WHERE NOT EXISTS (
        SELECT 1
        FROM public.wallet_ledger AS wl
        WHERE wl.user_id = v_user_id
          AND wl.wallet_role = 'rider'
          AND wl.entry_kind = 'rider_commission_delivery_item'
          AND wl.reference_id = p_order_item_id
      );
    END IF;
  ELSE
    UPDATE public.order_items
    SET pickup_status = 3,
        pickup_rider_id = v_user_id,
        status = CASE WHEN status < 3 THEN 3 ELSE status END
    WHERE order_items_id = p_order_item_id;
  END IF;

  PERFORM public.sync_suborder_status_from_items(v_summary.suborder_id);

  RETURN public.rider_get_pickup_detail(p_order_item_id);
END;
$$;

CREATE OR REPLACE FUNCTION public.rider_dashboard_snapshot()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_aggregates record;
  v_completed_fee numeric := 0;
  v_active_fee numeric := 0;
  v_pending_withdrawals numeric := 0;
  v_available_balance numeric := 0;
  v_recent_assignments jsonb := '[]'::jsonb;
  v_available_pickups jsonb := '[]'::jsonb;
  v_notifications jsonb := '[]'::jsonb;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 4 THEN
    RAISE EXCEPTION 'Rider access required.';
  END IF;

  SELECT
    COUNT(*) AS total_trips,
    COALESCE(SUM(CASE WHEN pickup_status = 4 THEN 1 ELSE 0 END), 0) AS completed_trips,
    COALESCE(SUM(CASE WHEN pickup_status = 2 THEN 1 ELSE 0 END), 0) AS awaiting_trips,
    COALESCE(SUM(CASE WHEN pickup_status = 3 THEN 1 ELSE 0 END), 0) AS in_transit_trips,
    COALESCE(SUM(CASE WHEN pickup_status = 2 THEN display_commission ELSE 0 END), 0) AS awaiting_fee,
    COALESCE(SUM(CASE WHEN pickup_status = 3 THEN display_commission ELSE 0 END), 0) AS in_transit_fee,
    COALESCE(SUM(CASE WHEN pickup_status IN (2, 3) THEN display_commission ELSE 0 END), 0) AS active_fee
  INTO v_aggregates
  FROM public.rider_pickup_item_feed('mine');

  SELECT COALESCE(SUM(wl.amount), 0)
  INTO v_completed_fee
  FROM public.wallet_ledger AS wl
  WHERE wl.user_id = v_user_id
    AND wl.wallet_role = 'rider'
    AND wl.entry_kind IN ('rider_commission_delivery', 'rider_commission_delivery_item');

  SELECT
    COALESCE(SUM(CASE WHEN wr.status = 'pending' THEN wr.amount ELSE 0 END), 0)
  INTO v_pending_withdrawals
  FROM public.withdrawal_requests AS wr
  WHERE wr.user_id = v_user_id
    AND wr.wallet_role = 'rider';

  v_active_fee := COALESCE(v_aggregates.active_fee, 0);
  v_available_balance := GREATEST(COALESCE(v_completed_fee, 0) - COALESCE(v_pending_withdrawals, 0), 0);

  SELECT COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'reference', q.reference,
        'store_name', q.store_name,
        'total_amount', q.total_amount,
        'commission_amount', q.commission_amount,
        'pickup_status', q.pickup_status,
        'updated_at', q.updated_at
      )
      ORDER BY q.updated_at DESC
    ),
    '[]'::jsonb
  )
  INTO v_recent_assignments
  FROM (
    SELECT
      r.item_reference AS reference,
      r.seller_store AS store_name,
      r.total_amount,
      r.display_commission AS commission_amount,
      r.pickup_status,
      r.updated_at
    FROM public.rider_pickup_item_feed('mine') AS r
    ORDER BY r.updated_at DESC
    LIMIT 6
  ) AS q;

  SELECT COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'reference', q.reference,
        'store_name', q.store_name,
        'total_amount', q.total_amount,
        'commission_amount', q.commission_amount,
        'updated_at', q.updated_at
      )
      ORDER BY q.updated_at DESC
    ),
    '[]'::jsonb
  )
  INTO v_available_pickups
  FROM (
    SELECT
      r.item_reference AS reference,
      r.seller_store AS store_name,
      r.total_amount,
      r.display_commission AS commission_amount,
      r.updated_at
    FROM public.rider_pickup_item_feed('available') AS r
    ORDER BY r.updated_at DESC
    LIMIT 4
  ) AS q;

  SELECT COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'title', q.title,
        'message', q.message,
        'created_at', q.created_at
      )
      ORDER BY q.created_at DESC
    ),
    '[]'::jsonb
  )
  INTO v_notifications
  FROM (
    SELECT n.title, n.message, n.created_at
    FROM public.notifications AS n
    WHERE n.user_id = v_user_id
    ORDER BY n.created_at DESC
    LIMIT 5
  ) AS q;

  RETURN jsonb_build_object(
    'total_trips', COALESCE(v_aggregates.total_trips, 0),
    'total_fee', COALESCE(v_completed_fee, 0) + COALESCE(v_active_fee, 0),
    'completed_trips', COALESCE(v_aggregates.completed_trips, 0),
    'awaiting_trips', COALESCE(v_aggregates.awaiting_trips, 0),
    'in_transit_trips', COALESCE(v_aggregates.in_transit_trips, 0),
    'completed_fee', COALESCE(v_completed_fee, 0),
    'awaiting_fee', COALESCE(v_aggregates.awaiting_fee, 0),
    'in_transit_fee', COALESCE(v_aggregates.in_transit_fee, 0),
    'active_fee', COALESCE(v_active_fee, 0),
    'available_balance', COALESCE(v_available_balance, 0),
    'pending_withdrawals', COALESCE(v_pending_withdrawals, 0),
    'recent_assignments', v_recent_assignments,
    'available_pickups', v_available_pickups,
    'notifications', v_notifications
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.rider_earnings_snapshot()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_aggregates record;
  v_completed_fee numeric := 0;
  v_active_fee numeric := 0;
  v_pending_withdrawals numeric := 0;
  v_available_balance numeric := 0;
  v_last_requested_at timestamptz;
  v_transactions jsonb := '[]'::jsonb;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 4 THEN
    RAISE EXCEPTION 'Rider access required.';
  END IF;

  SELECT
    COUNT(*) AS total_trips,
    COALESCE(SUM(CASE WHEN pickup_status = 4 THEN 1 ELSE 0 END), 0) AS completed_trips,
    COALESCE(SUM(CASE WHEN pickup_status = 3 THEN 1 ELSE 0 END), 0) AS in_transit_trips,
    COALESCE(SUM(CASE WHEN pickup_status = 2 THEN 1 ELSE 0 END), 0) AS awaiting_trips,
    COALESCE(SUM(CASE WHEN pickup_status = 3 THEN display_commission ELSE 0 END), 0) AS in_transit_fee,
    COALESCE(SUM(CASE WHEN pickup_status = 2 THEN display_commission ELSE 0 END), 0) AS awaiting_fee,
    COALESCE(SUM(CASE WHEN pickup_status IN (2, 3) THEN display_commission ELSE 0 END), 0) AS active_fee
  INTO v_aggregates
  FROM public.rider_pickup_item_feed('mine');

  SELECT COALESCE(SUM(wl.amount), 0)
  INTO v_completed_fee
  FROM public.wallet_ledger AS wl
  WHERE wl.user_id = v_user_id
    AND wl.wallet_role = 'rider'
    AND wl.entry_kind IN ('rider_commission_delivery', 'rider_commission_delivery_item');

  SELECT
    COALESCE(SUM(CASE WHEN wr.status = 'pending' THEN wr.amount ELSE 0 END), 0),
    MAX(wr.created_at)
  INTO v_pending_withdrawals, v_last_requested_at
  FROM public.withdrawal_requests AS wr
  WHERE wr.user_id = v_user_id
    AND wr.wallet_role = 'rider';

  v_active_fee := COALESCE(v_aggregates.active_fee, 0);
  v_available_balance := GREATEST(COALESCE(v_completed_fee, 0) - COALESCE(v_pending_withdrawals, 0), 0);

  SELECT COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'reference', q.reference,
        'label', q.label,
        'amount', q.amount,
        'pickup_status', q.pickup_status,
        'updated_at', q.updated_at
      )
      ORDER BY q.updated_at DESC
    ),
    '[]'::jsonb
  )
  INTO v_transactions
  FROM (
    SELECT
      r.item_reference AS reference,
      r.product_name AS label,
      r.display_commission AS amount,
      r.pickup_status,
      r.updated_at
    FROM public.rider_pickup_item_feed('mine') AS r
    ORDER BY r.updated_at DESC
    LIMIT 10
  ) AS q;

  RETURN jsonb_build_object(
    'total_trips', COALESCE(v_aggregates.total_trips, 0),
    'total_fee', COALESCE(v_completed_fee, 0) + COALESCE(v_active_fee, 0),
    'completed_fee', COALESCE(v_completed_fee, 0),
    'in_transit_fee', COALESCE(v_aggregates.in_transit_fee, 0),
    'awaiting_fee', COALESCE(v_aggregates.awaiting_fee, 0),
    'active_fee', COALESCE(v_active_fee, 0),
    'completed_trips', COALESCE(v_aggregates.completed_trips, 0),
    'in_transit_trips', COALESCE(v_aggregates.in_transit_trips, 0),
    'awaiting_trips', COALESCE(v_aggregates.awaiting_trips, 0),
    'available_balance', COALESCE(v_available_balance, 0),
    'pending_withdrawals', COALESCE(v_pending_withdrawals, 0),
    'last_requested_at', v_last_requested_at,
    'transactions', v_transactions
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.rider_get_pickups(text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.rider_get_pickup_detail(integer) TO authenticated;
GRANT EXECUTE ON FUNCTION public.rider_claim_pickup_assignment(integer) TO authenticated;
GRANT EXECUTE ON FUNCTION public.rider_save_delivery_proof(integer, text, double precision, double precision) TO authenticated;
GRANT EXECUTE ON FUNCTION public.rider_update_pickup_status(integer, integer) TO authenticated;
GRANT EXECUTE ON FUNCTION public.rider_dashboard_snapshot() TO authenticated;
GRANT EXECUTE ON FUNCTION public.rider_earnings_snapshot() TO authenticated;

DROP POLICY IF EXISTS "Allow authenticated users to read own addresses" ON public.addresses;

CREATE POLICY "Allow authenticated users to read own addresses"
ON public.addresses
FOR SELECT
TO authenticated
USING (
  user_id = public.current_public_user_id()
);

DROP POLICY IF EXISTS "Allow authenticated riders to read own delivery partner profile" ON public.delivery_partners;

CREATE POLICY "Allow authenticated riders to read own delivery partner profile"
ON public.delivery_partners
FOR SELECT
TO authenticated
USING (
  user_id = public.current_public_user_id()
  OR lower(email) = lower(COALESCE(auth.jwt() ->> 'email', ''))
);

DROP POLICY IF EXISTS "Allow authenticated sellers to read own seller profile" ON public.seller_details;

CREATE POLICY "Allow authenticated sellers to read own seller profile"
ON public.seller_details
FOR SELECT
TO authenticated
USING (
  user_id = public.current_public_user_id()
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'categories'
      AND policyname = 'Allow authenticated users to read active categories'
  ) THEN
    CREATE POLICY "Allow authenticated users to read active categories"
    ON public.categories
    FOR SELECT
    TO authenticated
    USING (status = 1);
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'categories'
      AND policyname = 'Allow anon users to read active categories'
  ) THEN
    CREATE POLICY "Allow anon users to read active categories"
    ON public.categories
    FOR SELECT
    TO anon
    USING (status = 1);
  END IF;
END
$$;

DROP POLICY IF EXISTS "Allow authenticated users to read own notifications" ON public.notifications;

CREATE POLICY "Allow authenticated users to read own notifications"
ON public.notifications
FOR SELECT
TO authenticated
USING (user_id = public.current_public_user_id());

DROP POLICY IF EXISTS "Allow authenticated users to read active or own products" ON public.products;

CREATE POLICY "Allow authenticated users to read active or own products"
ON public.products
FOR SELECT
TO authenticated
USING (
  status = 1
  OR user_id = public.current_public_user_id()
);

DROP POLICY IF EXISTS "Allow anon users to read active products" ON public.products;

CREATE POLICY "Allow anon users to read active products"
ON public.products
FOR SELECT
TO anon
USING (status = 1);

DROP POLICY IF EXISTS "Allow authenticated sellers to insert own products" ON public.products;

CREATE POLICY "Allow authenticated sellers to insert own products"
ON public.products
FOR INSERT
TO authenticated
WITH CHECK (
  user_id = public.current_public_user_id()
  AND public.current_public_role_id() = 3
);

DROP POLICY IF EXISTS "Allow authenticated sellers to update own products" ON public.products;

CREATE POLICY "Allow authenticated sellers to update own products"
ON public.products
FOR UPDATE
TO authenticated
USING (
  user_id = public.current_public_user_id()
  AND public.current_public_role_id() = 3
)
WITH CHECK (
  user_id = public.current_public_user_id()
  AND public.current_public_role_id() = 3
);

DROP POLICY IF EXISTS "Allow authenticated users to read visible product attachments" ON public.product_attachments;

CREATE POLICY "Allow authenticated users to read visible product attachments"
ON public.product_attachments
FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1
    FROM public.products AS p
    WHERE p.product_id = product_attachments.product_id
      AND (p.status = 1 OR p.user_id = public.current_public_user_id())
  )
);

DROP POLICY IF EXISTS "Allow anon users to read active product attachments" ON public.product_attachments;

CREATE POLICY "Allow anon users to read active product attachments"
ON public.product_attachments
FOR SELECT
TO anon
USING (
  EXISTS (
    SELECT 1
    FROM public.products AS p
    WHERE p.product_id = product_attachments.product_id
      AND p.status = 1
  )
);

DROP POLICY IF EXISTS "Allow authenticated sellers to insert own product attachments" ON public.product_attachments;

CREATE POLICY "Allow authenticated sellers to insert own product attachments"
ON public.product_attachments
FOR INSERT
TO authenticated
WITH CHECK (
  EXISTS (
    SELECT 1
    FROM public.products AS p
    WHERE p.product_id = product_attachments.product_id
      AND p.user_id = public.current_public_user_id()
      AND public.current_public_role_id() = 3
  )
);

DROP POLICY IF EXISTS "Allow authenticated sellers to read own suborders" ON public.order_suborders;

CREATE POLICY "Allow authenticated sellers to read own suborders"
ON public.order_suborders
FOR SELECT
TO authenticated
USING (
  seller_id = public.current_public_user_id()
  AND public.current_public_role_id() = 3
);

DROP POLICY IF EXISTS "Allow authenticated sellers to update own suborders" ON public.order_suborders;

CREATE POLICY "Allow authenticated sellers to update own suborders"
ON public.order_suborders
FOR UPDATE
TO authenticated
USING (
  seller_id = public.current_public_user_id()
  AND public.current_public_role_id() = 3
)
WITH CHECK (
  seller_id = public.current_public_user_id()
  AND public.current_public_role_id() = 3
);

DROP POLICY IF EXISTS "Allow authenticated sellers to read own order items" ON public.order_items;

CREATE POLICY "Allow authenticated sellers to read own order items"
ON public.order_items
FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1
    FROM public.order_suborders AS os
    WHERE os.suborder_id = order_items.suborder_id
      AND os.seller_id = public.current_public_user_id()
      AND public.current_public_role_id() = 3
  )
);

DROP POLICY IF EXISTS "Allow authenticated sellers to update own order items" ON public.order_items;

CREATE POLICY "Allow authenticated sellers to update own order items"
ON public.order_items
FOR UPDATE
TO authenticated
USING (
  EXISTS (
    SELECT 1
    FROM public.order_suborders AS os
    WHERE os.suborder_id = order_items.suborder_id
      AND os.seller_id = public.current_public_user_id()
      AND public.current_public_role_id() = 3
  )
)
WITH CHECK (
  EXISTS (
    SELECT 1
    FROM public.order_suborders AS os
    WHERE os.suborder_id = order_items.suborder_id
      AND os.seller_id = public.current_public_user_id()
      AND public.current_public_role_id() = 3
  )
);

DROP POLICY IF EXISTS "Allow authenticated buyers to read own cart items" ON public.order_items;

CREATE POLICY "Allow authenticated buyers to read own cart items"
ON public.order_items
FOR SELECT
TO authenticated
USING (
  user_id = public.current_public_user_id()
  AND public.current_public_role_id() = 2
  AND status = 1
  AND COALESCE(reference, '') = ''
);

DROP POLICY IF EXISTS "Allow authenticated buyers to insert own cart items" ON public.order_items;

CREATE POLICY "Allow authenticated buyers to insert own cart items"
ON public.order_items
FOR INSERT
TO authenticated
WITH CHECK (
  user_id = public.current_public_user_id()
  AND public.current_public_role_id() = 2
  AND status = 1
  AND COALESCE(reference, '') = ''
);

DROP POLICY IF EXISTS "Allow authenticated buyers to update own cart items" ON public.order_items;

CREATE POLICY "Allow authenticated buyers to update own cart items"
ON public.order_items
FOR UPDATE
TO authenticated
USING (
  user_id = public.current_public_user_id()
  AND public.current_public_role_id() = 2
  AND status = 1
  AND COALESCE(reference, '') = ''
)
WITH CHECK (
  user_id = public.current_public_user_id()
  AND public.current_public_role_id() = 2
  AND status = 1
  AND COALESCE(reference, '') = ''
);

DROP POLICY IF EXISTS "Allow authenticated buyers to delete own cart items" ON public.order_items;

CREATE POLICY "Allow authenticated buyers to delete own cart items"
ON public.order_items
FOR DELETE
TO authenticated
USING (
  user_id = public.current_public_user_id()
  AND public.current_public_role_id() = 2
  AND status = 1
  AND COALESCE(reference, '') = ''
);

DROP POLICY IF EXISTS "Allow authenticated buyers to read own checked out order items" ON public.order_items;

CREATE POLICY "Allow authenticated buyers to read own checked out order items"
ON public.order_items
FOR SELECT
TO authenticated
USING (
  user_id = public.current_public_user_id()
  AND public.current_public_role_id() = 2
  AND COALESCE(reference, '') <> ''
);

DROP POLICY IF EXISTS "Allow authenticated buyers to read own orders" ON public.orders;

CREATE POLICY "Allow authenticated buyers to read own orders"
ON public.orders
FOR SELECT
TO authenticated
USING (
  user_id = public.current_public_user_id()
  AND public.current_public_role_id() = 2
);

DROP POLICY IF EXISTS "Allow authenticated buyers to read own suborders" ON public.order_suborders;

CREATE POLICY "Allow authenticated buyers to read own suborders"
ON public.order_suborders
FOR SELECT
TO authenticated
USING (
  public.buyer_owns_order(order_suborders.order_id)
);

DROP POLICY IF EXISTS "Allow authenticated riders to read assigned delivery proofs" ON public.delivery_proofs;

CREATE POLICY "Allow authenticated riders to read assigned delivery proofs"
ON public.delivery_proofs
FOR SELECT
TO authenticated
USING (
  public.current_public_role_id() = 4
  AND EXISTS (
    SELECT 1
    FROM public.order_suborders AS os
    WHERE os.suborder_id = delivery_proofs.suborder_id
      AND os.pickup_rider_id = public.current_public_user_id()
  )
);

DROP POLICY IF EXISTS "Allow authenticated buyers to read own order delivery proofs" ON public.delivery_proofs;

CREATE POLICY "Allow authenticated buyers to read own order delivery proofs"
ON public.delivery_proofs
FOR SELECT
TO authenticated
USING (
  public.current_public_role_id() = 2
  AND EXISTS (
    SELECT 1
    FROM public.order_suborders AS os
    INNER JOIN public.orders AS o ON o.order_id = os.order_id
    WHERE os.suborder_id = delivery_proofs.suborder_id
      AND o.user_id = public.current_public_user_id()
  )
);

CREATE OR REPLACE FUNCTION public.marketplace_setting_number(p_setting_key text, p_default numeric)
RETURNS numeric
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT COALESCE(
    (
      SELECT CASE
        WHEN trim(COALESCE(ps.setting_value, '')) ~ '^-?[0-9]+(\.[0-9]+)?$'
          THEN trim(ps.setting_value)::numeric
        ELSE NULL
      END
      FROM public.platform_settings AS ps
      WHERE ps.setting_key = p_setting_key
      LIMIT 1
    ),
    p_default
  );
$$;

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

CREATE OR REPLACE FUNCTION public.estimate_buyer_cart_shipping_for_seller(
  p_buyer_user_id integer,
  p_seller_user_id integer,
  p_group_subtotal numeric
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_threshold numeric := public.marketplace_setting_number('shipping_free_threshold', 2000);
  v_same_city numeric := public.marketplace_setting_number('shipping_same_city', 49);
  v_same_province numeric := public.marketplace_setting_number('shipping_same_province', 65);
  v_same_region numeric := public.marketplace_setting_number('shipping_same_region', 79);
  v_cross_region numeric := public.marketplace_setting_number('shipping_cross_region', 99);
  v_buyer_region text := '';
  v_buyer_province text := '';
  v_buyer_city text := '';
  v_seller_region text := '';
  v_seller_province text := '';
  v_seller_city text := '';
  v_store_name text := 'Seller';
  v_fee numeric := 0;
  v_reason text := 'free_threshold';
BEGIN
  IF COALESCE(p_group_subtotal, 0) >= v_threshold OR COALESCE(p_group_subtotal, 0) <= 0 THEN
    RETURN jsonb_build_object(
      'seller_id', p_seller_user_id,
      'store_name', v_store_name,
      'fee', 0,
      'reason', v_reason,
      'threshold', v_threshold
    );
  END IF;

  SELECT
    lower(trim(COALESCE(a.region, ''))),
    lower(trim(COALESCE(a.province, ''))),
    lower(trim(COALESCE(a.city_municipality, '')))
  INTO v_buyer_region, v_buyer_province, v_buyer_city
  FROM public.addresses AS a
  WHERE a.user_id = p_buyer_user_id
  ORDER BY COALESCE(a.updated_at, a.created_at) DESC, a.address_id DESC
  LIMIT 1;

  SELECT
    COALESCE(NULLIF(trim(sd.store_name), ''), 'Seller'),
    lower(trim(COALESCE(sd.region, ''))),
    lower(trim(COALESCE(sd.province, ''))),
    lower(trim(COALESCE(sd.city, '')))
  INTO v_store_name, v_seller_region, v_seller_province, v_seller_city
  FROM public.seller_details AS sd
  WHERE sd.user_id = p_seller_user_id
  ORDER BY COALESCE(sd.updated_at, sd.created_at) DESC, sd.seller_detail_id DESC
  LIMIT 1;

  IF v_buyer_region <> ''
     AND v_seller_region <> ''
     AND v_buyer_region = v_seller_region
     AND v_buyer_province <> ''
     AND v_seller_province <> ''
     AND v_buyer_province = v_seller_province
     AND v_buyer_city <> ''
     AND v_seller_city <> ''
     AND v_buyer_city = v_seller_city THEN
    v_fee := v_same_city;
    v_reason := 'tier_same_city';
  ELSIF v_buyer_region <> ''
     AND v_seller_region <> ''
     AND v_buyer_region = v_seller_region
     AND v_buyer_province <> ''
     AND v_seller_province <> ''
     AND v_buyer_province = v_seller_province THEN
    v_fee := v_same_province;
    v_reason := 'tier_same_province';
  ELSIF v_buyer_region <> ''
     AND v_seller_region <> ''
     AND v_buyer_region = v_seller_region THEN
    v_fee := v_same_region;
    v_reason := 'tier_same_region';
  ELSE
    v_fee := v_cross_region;
    v_reason := 'tier_cross_region';
  END IF;

  RETURN jsonb_build_object(
    'seller_id', p_seller_user_id,
    'store_name', v_store_name,
    'fee', round(v_fee, 2),
    'reason', v_reason,
    'threshold', v_threshold
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.buyer_cart_pricing_snapshot()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  seller_group record;
  v_subtotal numeric := 0;
  v_shipping_fee numeric := 0;
  v_tax_amount numeric := 0;
  v_total_amount numeric := 0;
  v_threshold numeric := public.marketplace_setting_number('shipping_free_threshold', 2000);
  v_group_shipping jsonb := '{}'::jsonb;
  v_group_fee numeric := 0;
  v_shipping_breakdown jsonb := '[]'::jsonb;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 2 THEN
    RAISE EXCEPTION 'Cart pricing is available for buyer accounts only.';
  END IF;

  FOR seller_group IN
    SELECT
      p.user_id AS seller_id,
      COALESCE(sd.store_name, 'Seller') AS store_name,
      SUM(COALESCE(p.price, 0) * oi.quantity) AS subtotal
    FROM public.order_items AS oi
    INNER JOIN public.products AS p ON p.product_id = oi.product_id
    LEFT JOIN public.seller_details AS sd ON sd.user_id = p.user_id
    WHERE oi.user_id = v_user_id
      AND oi.status = 1
      AND COALESCE(oi.reference, '') = ''
    GROUP BY p.user_id, COALESCE(sd.store_name, 'Seller')
    ORDER BY COALESCE(sd.store_name, 'Seller')
  LOOP
    v_subtotal := v_subtotal + COALESCE(seller_group.subtotal, 0);
    v_group_shipping := public.estimate_buyer_cart_shipping_for_seller(
      v_user_id,
      seller_group.seller_id,
      COALESCE(seller_group.subtotal, 0)
    );
    v_group_fee := COALESCE((v_group_shipping ->> 'fee')::numeric, 0);
    v_shipping_fee := v_shipping_fee + v_group_fee;
    v_shipping_breakdown := v_shipping_breakdown || jsonb_build_array(
      jsonb_build_object(
        'seller_id', seller_group.seller_id,
        'store_name', COALESCE(v_group_shipping ->> 'store_name', seller_group.store_name),
        'shipping_fee', round(v_group_fee, 2),
        'reason', COALESCE(v_group_shipping ->> 'reason', ''),
        'subtotal', round(COALESCE(seller_group.subtotal, 0), 2)
      )
    );
  END LOOP;

  v_tax_amount := round((v_subtotal + v_shipping_fee) * 0.01, 2);
  v_total_amount := v_subtotal + v_shipping_fee + v_tax_amount;

  RETURN jsonb_build_object(
    'subtotal', round(v_subtotal, 2),
    'shipping_fee', round(v_shipping_fee, 2),
    'tax_amount', round(v_tax_amount, 2),
    'total_amount', round(v_total_amount, 2),
    'free_shipping_threshold', round(v_threshold, 2),
    'is_shipping_free', v_shipping_fee = 0,
    'shipping_breakdown', v_shipping_breakdown
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.buyer_cart_pricing_snapshot() TO authenticated;

CREATE OR REPLACE FUNCTION public.checkout_buyer_cart(payment_method text DEFAULT 'cod')
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_payment_method text := lower(trim(COALESCE(payment_method, 'cod')));
  v_reference text;
  v_order_id integer;
  v_subtotal numeric := 0;
  v_shipping_fee numeric := 0;
  v_tax_amount numeric := 0;
  v_total_amount numeric := 0;
  v_has_address boolean := false;
  seller_group record;
  cart_item record;
  v_suborder_id integer;
  v_group_count integer := 0;
  v_allocated_tax_amount numeric := 0;
  group_index integer := 0;
  group_subtotal numeric;
  group_shipping_fee numeric;
  group_tax_amount numeric;
  group_base_amount numeric;
  group_total_amount numeric;
  group_shipping_payload jsonb := '{}'::jsonb;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 2 THEN
    RAISE EXCEPTION 'Checkout is available for buyer accounts only.';
  END IF;

  SELECT EXISTS(
    SELECT 1
    FROM public.addresses AS a
    WHERE a.user_id = v_user_id
  ) INTO v_has_address;

  IF NOT v_has_address THEN
    RAISE EXCEPTION 'Please add a shipping address before checking out.';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.order_items AS oi
    WHERE oi.user_id = v_user_id
      AND oi.status = 1
      AND COALESCE(oi.reference, '') = ''
  ) THEN
    RAISE EXCEPTION 'Your cart is empty.';
  END IF;

  FOR cart_item IN
    SELECT oi.order_items_id, oi.product_id, oi.quantity, p.product_name, p.price, p.qty, p.user_id AS seller_id
    FROM public.order_items AS oi
    INNER JOIN public.products AS p ON p.product_id = oi.product_id
    WHERE oi.user_id = v_user_id
      AND oi.status = 1
      AND COALESCE(oi.reference, '') = ''
    ORDER BY oi.order_items_id
    FOR UPDATE OF oi, p
  LOOP
    IF COALESCE(cart_item.quantity, 0) <= 0 THEN
      RAISE EXCEPTION 'Invalid cart quantity found during checkout.';
    END IF;

    IF COALESCE(cart_item.qty, 0) < cart_item.quantity THEN
      RAISE EXCEPTION '% only has % item(s) left in stock.', COALESCE(cart_item.product_name, 'This product'), COALESCE(cart_item.qty, 0);
    END IF;

    v_subtotal := v_subtotal + (COALESCE(cart_item.price, 0) * cart_item.quantity);
  END LOOP;

  FOR seller_group IN
    SELECT p.user_id AS seller_id, SUM(COALESCE(p.price, 0) * oi.quantity) AS subtotal
    FROM public.order_items AS oi
    INNER JOIN public.products AS p ON p.product_id = oi.product_id
    WHERE oi.user_id = v_user_id
      AND oi.status = 1
      AND COALESCE(oi.reference, '') = ''
    GROUP BY p.user_id
    ORDER BY p.user_id
  LOOP
    group_shipping_payload := public.estimate_buyer_cart_shipping_for_seller(
      v_user_id,
      seller_group.seller_id,
      COALESCE(seller_group.subtotal, 0)
    );
    v_shipping_fee := v_shipping_fee + COALESCE((group_shipping_payload ->> 'fee')::numeric, 0);
  END LOOP;

  v_tax_amount := round((v_subtotal + v_shipping_fee) * 0.01, 2);
  v_total_amount := v_subtotal + v_shipping_fee + v_tax_amount;
  v_reference := upper(substr(md5(clock_timestamp()::text || random()::text || v_user_id::text), 1, 12));

  INSERT INTO public.orders (user_id, reference, subtotal, shipping_fee, tax_amount, total_amount, cash_type, status)
  VALUES (v_user_id, v_reference, v_subtotal, v_shipping_fee, v_tax_amount, v_total_amount, v_payment_method, 1)
  RETURNING order_id INTO v_order_id;

  SELECT COUNT(*)
  INTO v_group_count
  FROM (
    SELECT p.user_id
    FROM public.order_items AS oi
    INNER JOIN public.products AS p ON p.product_id = oi.product_id
    WHERE oi.user_id = v_user_id
      AND oi.status = 1
      AND COALESCE(oi.reference, '') = ''
    GROUP BY p.user_id
  ) AS seller_groups;

  FOR seller_group IN
    SELECT p.user_id AS seller_id, SUM(COALESCE(p.price, 0) * oi.quantity) AS subtotal
    FROM public.order_items AS oi
    INNER JOIN public.products AS p ON p.product_id = oi.product_id
    WHERE oi.user_id = v_user_id
      AND oi.status = 1
      AND COALESCE(oi.reference, '') = ''
    GROUP BY p.user_id
    ORDER BY p.user_id
  LOOP
    group_index := group_index + 1;
    group_subtotal := COALESCE(seller_group.subtotal, 0);
    group_shipping_payload := public.estimate_buyer_cart_shipping_for_seller(
      v_user_id,
      seller_group.seller_id,
      group_subtotal
    );
    group_shipping_fee := COALESCE((group_shipping_payload ->> 'fee')::numeric, 0);
    group_base_amount := group_subtotal + group_shipping_fee;
    IF group_index < v_group_count AND (v_subtotal + v_shipping_fee) > 0 THEN
      group_tax_amount := round(v_tax_amount * group_base_amount / (v_subtotal + v_shipping_fee), 2);
    ELSE
      group_tax_amount := round(v_tax_amount - v_allocated_tax_amount, 2);
    END IF;
    v_allocated_tax_amount := v_allocated_tax_amount + group_tax_amount;
    group_total_amount := group_subtotal + group_shipping_fee + group_tax_amount;

    INSERT INTO public.order_suborders (order_id, seller_id, reference, status, subtotal, shipping_fee, tax_amount, total_amount)
    VALUES (
      v_order_id,
      seller_group.seller_id,
      v_reference || '-' || lpad(group_index::text, 2, '0'),
      1,
      group_subtotal,
      group_shipping_fee,
      group_tax_amount,
      group_total_amount
    )
    RETURNING suborder_id INTO v_suborder_id;

    FOR cart_item IN
      SELECT oi.order_items_id, oi.product_id, oi.quantity
      FROM public.order_items AS oi
      INNER JOIN public.products AS p ON p.product_id = oi.product_id
      WHERE oi.user_id = v_user_id
        AND oi.status = 1
        AND COALESCE(oi.reference, '') = ''
        AND p.user_id = seller_group.seller_id
      ORDER BY oi.order_items_id
    LOOP
      UPDATE public.products
      SET qty = qty - cart_item.quantity
      WHERE product_id = cart_item.product_id
        AND qty >= cart_item.quantity;

      IF NOT FOUND THEN
        RAISE EXCEPTION 'Unable to reserve stock for one or more products. Please refresh your cart and try again.';
      END IF;

      UPDATE public.order_items
      SET reference = v_reference,
          suborder_id = v_suborder_id,
          status = 1
      WHERE order_items_id = cart_item.order_items_id
        AND user_id = v_user_id;
    END LOOP;
  END LOOP;

  RETURN jsonb_build_object(
    'reference', v_reference,
    'order_id', v_order_id,
    'payment_method', upper(v_payment_method),
    'total_amount', to_char(v_total_amount, 'FM9999999990.00')
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.checkout_buyer_cart(text) TO authenticated;

WITH suborder_basis AS (
  SELECT
    os.suborder_id,
    os.order_id,
    COALESCE(os.subtotal, 0) + COALESCE(os.shipping_fee, 0) AS base_amount,
    COALESCE(o.tax_amount, 0) AS order_tax_amount,
    COALESCE(o.subtotal, 0) + COALESCE(o.shipping_fee, 0) AS order_base_amount,
    ROW_NUMBER() OVER (PARTITION BY os.order_id ORDER BY os.suborder_id) AS seq,
    COUNT(*) OVER (PARTITION BY os.order_id) AS total_suborders
  FROM public.order_suborders AS os
  INNER JOIN public.orders AS o ON o.order_id = os.order_id
),
preliminary AS (
  SELECT
    sb.suborder_id,
    sb.order_id,
    sb.base_amount,
    sb.order_tax_amount,
    sb.order_base_amount,
    sb.seq,
    sb.total_suborders,
    CASE
      WHEN sb.order_tax_amount = 0 OR sb.order_base_amount <= 0 THEN 0::numeric
      WHEN sb.seq < sb.total_suborders THEN ROUND(sb.order_tax_amount * sb.base_amount / sb.order_base_amount, 2)
      ELSE NULL
    END AS provisional_tax_amount
  FROM suborder_basis AS sb
),
allocated AS (
  SELECT
    p.suborder_id,
    CASE
      WHEN p.seq < p.total_suborders THEN COALESCE(p.provisional_tax_amount, 0)
      ELSE ROUND(
        p.order_tax_amount
        - COALESCE(
            SUM(COALESCE(p.provisional_tax_amount, 0)) OVER (
              PARTITION BY p.order_id
              ORDER BY p.seq
              ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ),
            0
          ),
        2
      )
    END AS allocated_tax_amount
  FROM preliminary AS p
)
UPDATE public.order_suborders AS os
SET tax_amount = COALESCE(a.allocated_tax_amount, 0),
    total_amount = ROUND(COALESCE(os.subtotal, 0) + COALESCE(os.shipping_fee, 0) + COALESCE(a.allocated_tax_amount, 0), 2)
FROM allocated AS a
WHERE os.suborder_id = a.suborder_id;

CREATE OR REPLACE FUNCTION public.buyer_confirm_order(p_reference text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_reference text := trim(COALESCE(p_reference, ''));
  v_order_id integer;
  v_updated_count integer := 0;
  v_updated_item_ids integer[] := ARRAY[]::integer[];
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 2 THEN
    RAISE EXCEPTION 'Buyer access required.';
  END IF;

  IF v_reference = '' THEN
    RAISE EXCEPTION 'Order reference is required.';
  END IF;

  SELECT o.order_id
  INTO v_order_id
  FROM public.orders AS o
  WHERE lower(COALESCE(o.reference, '')) = lower(v_reference)
    AND o.user_id = v_user_id
  LIMIT 1;

  IF v_order_id IS NULL THEN
    RAISE EXCEPTION 'Order not found.';
  END IF;

  WITH updated_items AS (
    UPDATE public.order_items
    SET status = 6
    WHERE user_id = v_user_id
      AND lower(COALESCE(reference, '')) = lower(v_reference)
      AND status = 4
    RETURNING order_items_id
  )
  SELECT COALESCE(array_agg(order_items_id), ARRAY[]::integer[]), COUNT(*)
  INTO v_updated_item_ids, v_updated_count
  FROM updated_items;

  IF COALESCE(v_updated_count, 0) <= 0 THEN
    RAISE EXCEPTION 'No delivered items to confirm for this order.';
  END IF;

  INSERT INTO public.wallet_ledger (user_id, wallet_role, amount, entry_kind, reference_id, note)
  SELECT
    os.seller_id,
    'seller',
    ROUND(COALESCE(p.price, 0) * GREATEST(COALESCE(oi.quantity, 0), 0), 2),
    'seller_cod_release_item',
    oi.order_items_id,
    'Seller balance from completed order item'
  FROM public.order_items AS oi
  INNER JOIN public.order_suborders AS os ON os.suborder_id = oi.suborder_id
  LEFT JOIN public.products AS p ON p.product_id = oi.product_id
  WHERE oi.order_items_id = ANY(v_updated_item_ids)
    AND COALESCE(os.seller_id, 0) > 0
    AND ROUND(COALESCE(p.price, 0) * GREATEST(COALESCE(oi.quantity, 0), 0), 2) > 0
    AND NOT EXISTS (
      SELECT 1
      FROM public.wallet_ledger AS wl
      WHERE wl.user_id = os.seller_id
        AND wl.wallet_role = 'seller'
        AND wl.entry_kind = 'seller_cod_release_item'
        AND wl.reference_id = oi.order_items_id
    )
    AND NOT EXISTS (
      SELECT 1
      FROM public.wallet_ledger AS wl
      WHERE wl.user_id = os.seller_id
        AND wl.wallet_role = 'seller'
        AND wl.entry_kind = 'seller_cod_release'
        AND wl.reference_id = oi.suborder_id
    );

  UPDATE public.order_suborders AS os
  SET status = 6
  WHERE os.order_id = v_order_id
    AND NOT EXISTS (
      SELECT 1
      FROM public.order_items AS oi
      WHERE oi.suborder_id = os.suborder_id
        AND oi.status NOT IN (5, 6)
    );

  IF NOT EXISTS (
    SELECT 1
    FROM public.order_items AS oi
    WHERE oi.user_id = v_user_id
      AND lower(COALESCE(oi.reference, '')) = lower(v_reference)
      AND oi.status NOT IN (5, 6)
  ) THEN
    UPDATE public.orders
    SET status = 6
    WHERE order_id = v_order_id;
  END IF;

  RETURN jsonb_build_object(
    'reference', v_reference,
    'order_id', v_order_id,
    'updated_items', v_updated_count
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.buyer_confirm_order(text) TO authenticated;

CREATE OR REPLACE FUNCTION public.buyer_submit_product_review(
  p_product_id integer,
  p_rating integer,
  p_comment text,
  p_order_item_id integer DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_product_id integer := COALESCE(p_product_id, 0);
  v_rating integer := COALESCE(p_rating, 0);
  v_comment text := trim(COALESCE(p_comment, ''));
  v_order_item_id integer;
  v_reference text;
  v_review_id integer;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 2 THEN
    RAISE EXCEPTION 'Buyer access required.';
  END IF;

  IF v_product_id <= 0 THEN
    RAISE EXCEPTION 'Product is required.';
  END IF;

  IF v_rating < 1 OR v_rating > 5 THEN
    RAISE EXCEPTION 'Rating must be between 1 and 5.';
  END IF;

  IF v_comment = '' THEN
    RAISE EXCEPTION 'Please enter a review comment.';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.products AS p
    WHERE p.product_id = v_product_id
      AND p.status = 1
  ) THEN
    RAISE EXCEPTION 'Product not found.';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.product_reviews AS pr
    WHERE pr.user_id = v_user_id
      AND pr.product_id = v_product_id
  ) THEN
    RAISE EXCEPTION 'You have already submitted a review for this product.';
  END IF;

  SELECT oi.order_items_id, oi.reference
  INTO v_order_item_id, v_reference
  FROM public.order_items AS oi
  WHERE oi.user_id = v_user_id
    AND oi.product_id = v_product_id
    AND oi.status = 6
    AND (p_order_item_id IS NULL OR oi.order_items_id = p_order_item_id)
  ORDER BY oi.order_items_id DESC
  LIMIT 1;

  IF v_order_item_id IS NULL THEN
    RAISE EXCEPTION 'You can only review products you have completed an order for.';
  END IF;

  INSERT INTO public.product_reviews (product_id, user_id, order_items_id, reference, rating, comment)
  VALUES (v_product_id, v_user_id, v_order_item_id, v_reference, v_rating, v_comment)
  RETURNING review_id INTO v_review_id;

  RETURN jsonb_build_object(
    'review_id', v_review_id,
    'product_id', v_product_id,
    'order_items_id', v_order_item_id,
    'reference', v_reference
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.buyer_submit_product_review(integer, integer, text, integer) TO authenticated;

CREATE OR REPLACE FUNCTION public.get_public_product_reviews(p_product_id integer)
RETURNS TABLE (
  review_id integer,
  rating smallint,
  comment text,
  created_at timestamp without time zone,
  reviewer_name text
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT pr.review_id,
         pr.rating,
         pr.comment,
         pr.created_at,
         COALESCE(
           NULLIF(trim(concat_ws(' ', u.firstname, u.lastname)), ''),
           'Buyer'
         ) AS reviewer_name
  FROM public.product_reviews AS pr
  INNER JOIN public.products AS p ON p.product_id = pr.product_id
  LEFT JOIN public.users AS u ON u.user_id = pr.user_id
  WHERE pr.product_id = p_product_id
    AND p.status = 1
  ORDER BY pr.created_at DESC;
$$;

GRANT EXECUTE ON FUNCTION public.get_public_product_reviews(integer) TO anon, authenticated;

CREATE OR REPLACE FUNCTION public.get_public_store_summary(p_seller_id integer)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  WITH seller AS (
    SELECT
      sd.user_id AS seller_id,
      COALESCE(NULLIF(trim(sd.store_name), ''), 'Seller Store') AS store_name,
      COALESCE(NULLIF(trim(sd.description), ''), 'Bringing you curated products from a verified seller.') AS description,
      NULLIF(trim(sd.city), '') AS city,
      NULLIF(trim(sd.province), '') AS province,
      NULLIF(trim(sd.region), '') AS region,
      concat_ws(', ', NULLIF(trim(sd.city), ''), NULLIF(trim(sd.province), ''), NULLIF(trim(sd.region), '')) AS address_text
    FROM public.seller_details AS sd
    WHERE sd.user_id = p_seller_id
      AND COALESCE(sd.status, 0) = 1
    ORDER BY COALESCE(sd.updated_at, sd.created_at) DESC, sd.seller_detail_id DESC
    LIMIT 1
  ),
  product_stats AS (
    SELECT
      COUNT(*)::integer AS products_count,
      COALESCE(SUM(COALESCE(p.qty, 0)), 0)::integer AS inventory_count
    FROM public.products AS p
    WHERE p.user_id = p_seller_id
      AND p.status = 1
  ),
  rating_stats AS (
    SELECT
      COALESCE(ROUND(AVG(pr.rating)::numeric, 1), 0) AS average_rating,
      COUNT(pr.review_id)::integer AS review_count
    FROM public.products AS p
    LEFT JOIN public.product_reviews AS pr ON pr.product_id = p.product_id
    WHERE p.user_id = p_seller_id
      AND p.status = 1
  )
  SELECT CASE
    WHEN EXISTS (SELECT 1 FROM seller) THEN jsonb_build_object(
      'seller_id', (SELECT seller_id FROM seller),
      'store_name', (SELECT store_name FROM seller),
      'description', (SELECT description FROM seller),
      'city', (SELECT city FROM seller),
      'province', (SELECT province FROM seller),
      'region', (SELECT region FROM seller),
      'address_text', (SELECT address_text FROM seller),
      'products_count', (SELECT products_count FROM product_stats),
      'inventory_count', (SELECT inventory_count FROM product_stats),
      'average_rating', (SELECT average_rating FROM rating_stats),
      'review_count', (SELECT review_count FROM rating_stats)
    )
    ELSE NULL::jsonb
  END;
$$;

GRANT EXECUTE ON FUNCTION public.get_public_store_summary(integer) TO anon, authenticated;

DROP POLICY IF EXISTS "Allow authenticated users to read active product reviews" ON public.product_reviews;

CREATE POLICY "Allow authenticated users to read active product reviews"
ON public.product_reviews
FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1
    FROM public.products AS p
    WHERE p.product_id = product_reviews.product_id
      AND p.status = 1
  )
);

DROP POLICY IF EXISTS "Allow anon users to read active product reviews" ON public.product_reviews;

CREATE POLICY "Allow anon users to read active product reviews"
ON public.product_reviews
FOR SELECT
TO anon
USING (
  EXISTS (
    SELECT 1
    FROM public.products AS p
    WHERE p.product_id = product_reviews.product_id
      AND p.status = 1
  )
);

DROP POLICY IF EXISTS "Allow authenticated sellers to read parent orders for own suborders" ON public.orders;

CREATE POLICY "Allow authenticated sellers to read parent orders for own suborders"
ON public.orders
FOR SELECT
TO authenticated
USING (
  public.seller_can_read_parent_order(orders.order_id)
);

DROP POLICY IF EXISTS "Allow sellers to read buyers tied to own orders" ON public.users;

CREATE POLICY "Allow sellers to read buyers tied to own orders"
ON public.users
FOR SELECT
TO authenticated
USING (
  auth_user_id = auth.uid()
  OR lower(email) = lower(COALESCE(auth.jwt() ->> 'email', ''))
  OR (
    public.current_public_role_id() = 3
    AND public.seller_can_read_buyer_user(users.user_id)
  )
);

DROP POLICY IF EXISTS "Allow authenticated buyers to read own wishlists" ON public.wishlists;

CREATE POLICY "Allow authenticated buyers to read own wishlists"
ON public.wishlists
FOR SELECT
TO authenticated
USING (
  user_id = public.current_public_user_id()
  AND public.current_public_role_id() = 2
);

DROP POLICY IF EXISTS "Allow authenticated buyers to insert own wishlists" ON public.wishlists;

CREATE POLICY "Allow authenticated buyers to insert own wishlists"
ON public.wishlists
FOR INSERT
TO authenticated
WITH CHECK (
  user_id = public.current_public_user_id()
  AND public.current_public_role_id() = 2
);

DROP POLICY IF EXISTS "Allow authenticated buyers to delete own wishlists" ON public.wishlists;

CREATE POLICY "Allow authenticated buyers to delete own wishlists"
ON public.wishlists
FOR DELETE
TO authenticated
USING (
  user_id = public.current_public_user_id()
  AND public.current_public_role_id() = 2
);

DROP POLICY IF EXISTS "Allow authenticated users to read accessible conversations" ON public.conversations;

CREATE POLICY "Allow authenticated users to read accessible conversations"
ON public.conversations
FOR SELECT
TO authenticated
USING (
  public.can_access_order_chat(buyer_id, seller_id, order_id)
);

DROP POLICY IF EXISTS "Allow authenticated users to insert accessible conversations" ON public.conversations;

CREATE POLICY "Allow authenticated users to insert accessible conversations"
ON public.conversations
FOR INSERT
TO authenticated
WITH CHECK (
  public.can_access_order_chat(buyer_id, seller_id, order_id)
);

DROP POLICY IF EXISTS "Allow authenticated users to update accessible conversations" ON public.conversations;

CREATE POLICY "Allow authenticated users to update accessible conversations"
ON public.conversations
FOR UPDATE
TO authenticated
USING (
  public.can_access_order_chat(buyer_id, seller_id, order_id)
)
WITH CHECK (
  public.can_access_order_chat(buyer_id, seller_id, order_id)
);

DROP POLICY IF EXISTS "Allow authenticated users to read accessible conversation messages" ON public.conversation_messages;

CREATE POLICY "Allow authenticated users to read accessible conversation messages"
ON public.conversation_messages
FOR SELECT
TO authenticated
USING (
  public.can_access_conversation(conversation_id)
);

DROP POLICY IF EXISTS "Allow authenticated users to insert accessible conversation messages" ON public.conversation_messages;

CREATE POLICY "Allow authenticated users to insert accessible conversation messages"
ON public.conversation_messages
FOR INSERT
TO authenticated
WITH CHECK (
  public.can_access_conversation(conversation_id)
  AND sender_id = public.current_public_user_id()
);

DROP POLICY IF EXISTS "Allow authenticated users to update accessible conversation messages" ON public.conversation_messages;

CREATE POLICY "Allow authenticated users to update accessible conversation messages"
ON public.conversation_messages
FOR UPDATE
TO authenticated
USING (
  public.can_access_conversation(conversation_id)
)
WITH CHECK (
  public.can_access_conversation(conversation_id)
);

DROP POLICY IF EXISTS "Allow seller product image uploads" ON storage.objects;

DROP POLICY IF EXISTS "Allow seller product image reads" ON storage.objects;

CREATE POLICY "Allow seller product image uploads"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'zyntra-uploads'
  AND name LIKE 'products/%'
  AND public.current_public_role_id() = 3
  AND split_part(name, '/', 2) = COALESCE(public.current_public_user_id(), -1)::text
);

CREATE POLICY "Allow seller product image reads"
ON storage.objects
FOR SELECT
TO anon, authenticated
USING (
  bucket_id = 'zyntra-uploads'
  AND (
    name LIKE 'product_images/%'
    OR name LIKE 'products/%'
    OR name ~ '^[0-9]+/[0-9]+/.+'
  )
);

DROP POLICY IF EXISTS "Allow rider delivery proof uploads" ON storage.objects;

CREATE POLICY "Allow rider delivery proof uploads"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'zyntra-uploads'
  AND name LIKE 'delivery_proofs/%'
  AND public.current_public_role_id() = 4
  AND split_part(name, '/', 2) = COALESCE(public.current_public_user_id(), -1)::text
);

DROP POLICY IF EXISTS "Allow authenticated delivery proof reads" ON storage.objects;

CREATE POLICY "Allow authenticated delivery proof reads"
ON storage.objects
FOR SELECT
TO authenticated
USING (
  bucket_id = 'zyntra-uploads'
  AND name LIKE 'delivery_proofs/%'
  AND public.current_public_role_id() IN (2, 4)
);
