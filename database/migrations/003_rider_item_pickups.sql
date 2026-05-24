ALTER TABLE public.order_items ADD COLUMN IF NOT EXISTS pickup_status integer NOT NULL DEFAULT 0;
ALTER TABLE public.order_items ADD COLUMN IF NOT EXISTS pickup_rider_id integer;
ALTER TABLE public.order_items ADD COLUMN IF NOT EXISTS pickup_claimed_at timestamp with time zone;
ALTER TABLE public.order_items ADD COLUMN IF NOT EXISTS pickup_completed_at timestamp with time zone;
ALTER TABLE public.delivery_proofs ADD COLUMN IF NOT EXISTS order_item_id integer;

CREATE INDEX IF NOT EXISTS idx_order_items_pickup_lookup
ON public.order_items (pickup_status, pickup_rider_id, suborder_id, order_items_id);

CREATE INDEX IF NOT EXISTS idx_delivery_proofs_order_item
ON public.delivery_proofs (order_item_id);

UPDATE public.order_items AS oi
SET pickup_status = CASE
      WHEN oi.status IN (4, 6) THEN 4
      WHEN oi.status = 3 THEN 3
      WHEN oi.status = 2 THEN CASE WHEN COALESCE(os.pickup_status, 0) IN (2, 3, 4) THEN os.pickup_status ELSE 1 END
      ELSE 0
    END,
    pickup_rider_id = CASE
      WHEN COALESCE(os.pickup_status, 0) IN (2, 3, 4) AND oi.status IN (2, 3, 4, 6) THEN os.pickup_rider_id
      ELSE NULL
    END,
    pickup_claimed_at = CASE
      WHEN COALESCE(os.pickup_status, 0) IN (2, 3, 4) AND oi.status IN (2, 3, 4, 6) THEN os.pickup_claimed_at
      ELSE NULL
    END,
    pickup_completed_at = CASE
      WHEN COALESCE(os.pickup_status, 0) = 4 AND oi.status IN (4, 6) THEN os.pickup_completed_at
      ELSE NULL
    END
FROM public.order_suborders AS os
WHERE os.suborder_id = oi.suborder_id;

DROP FUNCTION IF EXISTS public.rider_get_pickup_detail(integer);
DROP FUNCTION IF EXISTS public.rider_claim_pickup_assignment(integer);
DROP FUNCTION IF EXISTS public.rider_save_delivery_proof(integer, text, double precision, double precision);
DROP FUNCTION IF EXISTS public.rider_update_pickup_status(integer, integer);

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
      ROUND(COALESCE(t.line_total, 0), 2)
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
      pickup_rider_id = CASE WHEN v_next_pickup_status IN (2, 3, 4) THEN v_single_rider_id ELSE NULL END,
      pickup_claimed_at = CASE WHEN v_next_pickup_status IN (2, 3, 4) AND v_single_rider_id IS NOT NULL THEN v_counts.first_claimed_at ELSE NULL END,
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
END;
$$;

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
        WHERE pa.product_id = oi.product_id AND pa.status = 1
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

  IF NULLIF(trim(COALESCE(p_image_path, '')), '') IS NULL THEN
    RAISE EXCEPTION 'Delivery proof image is required.';
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
    WHERE order_items_id = p_order_item_id
      ;

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

  SELECT COALESCE(SUM(CASE WHEN wr.status = 'pending' THEN wr.amount ELSE 0 END), 0)
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
    'total_fee', COALESCE(v_completed_fee, 0) + COALESCE(v_aggregates.active_fee, 0),
    'completed_fee', COALESCE(v_completed_fee, 0),
    'in_transit_fee', COALESCE(v_aggregates.in_transit_fee, 0),
    'awaiting_fee', COALESCE(v_aggregates.awaiting_fee, 0),
    'active_fee', COALESCE(v_aggregates.active_fee, 0),
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

GRANT EXECUTE ON FUNCTION public.seller_update_order_item_status(integer, integer, integer) TO authenticated;
GRANT EXECUTE ON FUNCTION public.rider_get_pickups(text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.rider_get_pickup_detail(integer) TO authenticated;
GRANT EXECUTE ON FUNCTION public.rider_claim_pickup_assignment(integer) TO authenticated;
GRANT EXECUTE ON FUNCTION public.rider_save_delivery_proof(integer, text, double precision, double precision) TO authenticated;
GRANT EXECUTE ON FUNCTION public.rider_update_pickup_status(integer, integer) TO authenticated;
GRANT EXECUTE ON FUNCTION public.rider_dashboard_snapshot() TO authenticated;
GRANT EXECUTE ON FUNCTION public.rider_earnings_snapshot() TO authenticated;
GRANT EXECUTE ON FUNCTION public.live_state_snapshot() TO authenticated;
