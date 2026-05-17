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

CREATE OR REPLACE FUNCTION public.rider_get_pickups(p_scope text DEFAULT 'available')
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_scope text := lower(trim(COALESCE(p_scope, 'available')));
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 4 THEN
    RAISE EXCEPTION 'Rider access required.';
  END IF;

  IF v_scope NOT IN ('available', 'mine') THEN
    v_scope := 'available';
  END IF;

  RETURN COALESCE((
    SELECT jsonb_agg(
      jsonb_build_object(
        'suborder_id', q.suborder_id,
        'order_id', q.order_id,
        'order_reference', q.order_reference,
        'sub_reference', q.sub_reference,
        'order_created_at', q.order_created_at,
        'status', q.status,
        'pickup_status', q.pickup_status,
        'pickup_rider_id', q.pickup_rider_id,
        'pickup_claimed_at', q.pickup_claimed_at,
        'pickup_completed_at', q.pickup_completed_at,
        'updated_at', q.updated_at,
        'seller_name', COALESCE(NULLIF(trim(concat_ws(' ', q.seller_firstname, q.seller_lastname)), ''), q.store_name, 'Seller'),
        'seller_store', COALESCE(q.store_name, NULLIF(trim(concat_ws(' ', q.seller_firstname, q.seller_lastname)), ''), 'Seller'),
        'seller_location', concat_ws(', ', NULLIF(q.seller_street, ''), NULLIF(q.seller_city, ''), NULLIF(q.seller_province, '')),
        'buyer_id', q.buyer_id,
        'buyer_name', COALESCE(NULLIF(trim(concat_ws(' ', q.buyer_firstname, q.buyer_lastname)), ''), 'Buyer'),
        'buyer_phone', q.buyer_phone,
        'subtotal', q.subtotal,
        'shipping_fee', q.shipping_fee,
        'tax_amount', q.tax_amount,
        'total_amount', q.total_amount,
        'display_commission', q.display_commission,
        'commission_label', q.commission_label
      )
      ORDER BY q.updated_at DESC
    )
    FROM (
      SELECT
        os.suborder_id,
        os.order_id,
        os.reference AS sub_reference,
        os.status,
        os.pickup_status,
        os.pickup_rider_id,
        os.pickup_claimed_at,
        os.pickup_completed_at,
        os.updated_at,
        o.reference AS order_reference,
        o.created_at AS order_created_at,
        buyer.user_id AS buyer_id,
        buyer.firstname AS buyer_firstname,
        buyer.lastname AS buyer_lastname,
        buyer.phone AS buyer_phone,
        os.subtotal,
        os.shipping_fee,
        os.tax_amount,
        os.total_amount,
        seller.firstname AS seller_firstname,
        seller.lastname AS seller_lastname,
        sd.store_name,
        sd.city AS seller_city,
        sd.province AS seller_province,
        sd.street AS seller_street,
        CASE
          WHEN os.pickup_status = 4 THEN COALESCE(
            (
              SELECT wl.amount
              FROM public.wallet_ledger AS wl
              WHERE wl.user_id = os.pickup_rider_id
                AND wl.wallet_role = 'rider'
                AND wl.entry_kind = 'rider_commission_delivery'
                AND wl.reference_id = os.suborder_id
              ORDER BY wl.ledger_id DESC
              LIMIT 1
            ),
            public.rider_commission_amount(os.shipping_fee, os.subtotal)
          )
          ELSE public.rider_commission_amount(os.shipping_fee, os.subtotal)
        END AS display_commission,
        CASE
          WHEN os.pickup_status = 4 THEN 'Credited commission'
          WHEN os.pickup_status IN (2, 3) THEN 'Projected commission'
          ELSE 'Queued commission'
        END AS commission_label
      FROM public.order_suborders AS os
      INNER JOIN public.orders AS o ON os.order_id = o.order_id
      LEFT JOIN public.users AS buyer ON o.user_id = buyer.user_id
      INNER JOIN public.users AS seller ON os.seller_id = seller.user_id
      LEFT JOIN public.seller_details AS sd ON sd.user_id = seller.user_id
      WHERE (
        (v_scope = 'mine' AND os.pickup_rider_id = v_user_id AND os.pickup_status IN (2, 3, 4))
        OR (v_scope <> 'mine' AND os.pickup_status = 1 AND os.pickup_rider_id IS NULL)
      )
    ) AS q
  ), '[]'::jsonb);
END;
$$;

CREATE OR REPLACE FUNCTION public.rider_get_pickup_detail(p_suborder_id integer)
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

  SELECT
    os.suborder_id,
    os.order_id,
    os.reference AS sub_reference,
    os.status,
    os.pickup_status,
    os.pickup_rider_id,
    os.pickup_claimed_at,
    os.pickup_completed_at,
    os.updated_at,
    o.reference AS order_reference,
    o.created_at AS order_created_at,
    buyer.user_id AS buyer_id,
    buyer.firstname AS buyer_firstname,
    buyer.lastname AS buyer_lastname,
    buyer.phone AS buyer_phone,
    os.subtotal,
    os.shipping_fee,
    os.tax_amount,
    os.total_amount,
    seller.firstname AS seller_firstname,
    seller.lastname AS seller_lastname,
    sd.store_name,
    sd.city AS seller_city,
    sd.province AS seller_province,
    sd.street AS seller_street,
    CASE
      WHEN os.pickup_status = 4 THEN COALESCE(
        (
          SELECT wl.amount
          FROM public.wallet_ledger AS wl
          WHERE wl.user_id = os.pickup_rider_id
            AND wl.wallet_role = 'rider'
            AND wl.entry_kind = 'rider_commission_delivery'
            AND wl.reference_id = os.suborder_id
          ORDER BY wl.ledger_id DESC
          LIMIT 1
        ),
        public.rider_commission_amount(os.shipping_fee, os.subtotal)
      )
      ELSE public.rider_commission_amount(os.shipping_fee, os.subtotal)
    END AS display_commission,
    CASE
      WHEN os.pickup_status = 4 THEN 'Credited commission'
      WHEN os.pickup_status IN (2, 3) THEN 'Projected commission'
      ELSE 'Queued commission'
    END AS commission_label
  INTO v_summary
  FROM public.order_suborders AS os
  INNER JOIN public.orders AS o ON os.order_id = o.order_id
  LEFT JOIN public.users AS buyer ON o.user_id = buyer.user_id
  INNER JOIN public.users AS seller ON os.seller_id = seller.user_id
  LEFT JOIN public.seller_details AS sd ON sd.user_id = seller.user_id
  WHERE os.suborder_id = p_suborder_id;

  IF v_summary.suborder_id IS NULL THEN
    RAISE EXCEPTION 'Pickup not found.';
  END IF;

  IF v_summary.pickup_rider_id IS DISTINCT FROM v_user_id THEN
    RAISE EXCEPTION 'You are not assigned to this pickup.';
  END IF;

  SELECT COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'order_items_id', item_rows.order_items_id,
        'product_id', item_rows.product_id,
        'product_name', item_rows.product_name,
        'quantity', item_rows.quantity,
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
      p.product_name,
      COALESCE(p.price, 0) AS price,
      (
        SELECT pa.attachment
        FROM public.product_attachments AS pa
        WHERE pa.product_id = p.product_id AND pa.status = 1
        ORDER BY pa.updated_at DESC NULLS LAST, pa.product_attachment_id DESC
        LIMIT 1
      ) AS product_image
    FROM public.order_items AS oi
    INNER JOIN public.products AS p ON oi.product_id = p.product_id
    WHERE oi.suborder_id = p_suborder_id
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
  WHERE dp.suborder_id = p_suborder_id;

  SELECT dp.image_path, dp.captured_at
  INTO v_delivery_proof_image, v_delivery_proof_captured_at
  FROM public.delivery_proofs AS dp
  WHERE dp.suborder_id = p_suborder_id
  ORDER BY dp.created_at DESC, dp.proof_id DESC
  LIMIT 1;

  RETURN jsonb_build_object(
    'suborder_id', v_summary.suborder_id,
    'order_id', v_summary.order_id,
    'order_reference', v_summary.order_reference,
    'sub_reference', v_summary.sub_reference,
    'order_created_at', v_summary.order_created_at,
    'status', v_summary.status,
    'pickup_status', v_summary.pickup_status,
    'pickup_rider_id', v_summary.pickup_rider_id,
    'pickup_claimed_at', v_summary.pickup_claimed_at,
    'pickup_completed_at', v_summary.pickup_completed_at,
    'updated_at', v_summary.updated_at,
    'seller_name', COALESCE(NULLIF(trim(concat_ws(' ', v_summary.seller_firstname, v_summary.seller_lastname)), ''), v_summary.store_name, 'Seller'),
    'seller_store', COALESCE(v_summary.store_name, NULLIF(trim(concat_ws(' ', v_summary.seller_firstname, v_summary.seller_lastname)), ''), 'Seller'),
    'seller_location', concat_ws(', ', NULLIF(v_summary.seller_street, ''), NULLIF(v_summary.seller_city, ''), NULLIF(v_summary.seller_province, '')),
    'buyer_id', v_summary.buyer_id,
    'buyer_name', COALESCE(NULLIF(trim(concat_ws(' ', v_summary.buyer_firstname, v_summary.buyer_lastname)), ''), 'Buyer'),
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

CREATE OR REPLACE FUNCTION public.rider_claim_pickup_assignment(p_suborder_id integer)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 4 THEN
    RAISE EXCEPTION 'Rider access required.';
  END IF;

  UPDATE public.order_suborders
  SET pickup_rider_id = v_user_id,
      pickup_status = 2,
      pickup_claimed_at = NOW(),
      updated_at = NOW()
  WHERE suborder_id = p_suborder_id
    AND pickup_status = 1
    AND pickup_rider_id IS NULL;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'This pickup has already been claimed.';
  END IF;

  RETURN public.rider_get_pickup_detail(p_suborder_id);
END;
$$;

CREATE OR REPLACE FUNCTION public.rider_save_delivery_proof(
  p_suborder_id integer,
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
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 4 THEN
    RAISE EXCEPTION 'Rider access required.';
  END IF;

  SELECT pickup_rider_id
  INTO v_pickup_rider_id
  FROM public.order_suborders
  WHERE suborder_id = p_suborder_id;

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
    rider_user_id,
    image_path,
    latitude,
    longitude
  )
  VALUES (
    p_suborder_id,
    v_user_id,
    trim(p_image_path),
    p_latitude,
    p_longitude
  );

  RETURN public.rider_get_pickup_detail(p_suborder_id);
END;
$$;

CREATE OR REPLACE FUNCTION public.rider_update_pickup_status(p_suborder_id integer, p_status integer)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id integer;
  v_role_id integer;
  v_pickup_rider_id integer;
  v_pickup_status integer;
  v_proof_count integer := 0;
BEGIN
  v_user_id := public.current_public_user_id();
  v_role_id := public.current_public_role_id();

  IF v_user_id IS NULL OR v_user_id <= 0 OR v_role_id <> 4 THEN
    RAISE EXCEPTION 'Rider access required.';
  END IF;

  IF p_status NOT IN (3, 4) THEN
    RAISE EXCEPTION 'Invalid status.';
  END IF;

  SELECT pickup_rider_id, pickup_status
  INTO v_pickup_rider_id, v_pickup_status
  FROM public.order_suborders
  WHERE suborder_id = p_suborder_id;

  IF v_pickup_rider_id IS NULL AND v_pickup_status IS NULL THEN
    RAISE EXCEPTION 'Pickup not found.';
  END IF;

  IF v_pickup_rider_id IS DISTINCT FROM v_user_id THEN
    RAISE EXCEPTION 'You are not assigned to this pickup.';
  END IF;

  IF p_status = 3 AND COALESCE(v_pickup_status, 0) NOT IN (2, 3) THEN
    RAISE EXCEPTION 'Invalid pickup status transition.';
  END IF;

  IF p_status = 4 AND COALESCE(v_pickup_status, 0) NOT IN (2, 3, 4) THEN
    RAISE EXCEPTION 'Invalid pickup status transition.';
  END IF;

  IF p_status = 4 THEN
    SELECT COUNT(*)::integer
    INTO v_proof_count
    FROM public.delivery_proofs
    WHERE suborder_id = p_suborder_id;

    IF COALESCE(v_proof_count, 0) < 1 THEN
      RAISE EXCEPTION 'Please upload a delivery proof photo before marking this order as delivered.';
    END IF;

    UPDATE public.order_suborders
    SET pickup_status = 4,
        pickup_completed_at = NOW(),
        status = 4,
        updated_at = NOW()
    WHERE suborder_id = p_suborder_id
      AND pickup_rider_id = v_user_id;

    UPDATE public.order_items
    SET status = 4
    WHERE suborder_id = p_suborder_id
      AND status <> 5;

    PERFORM public.credit_rider_commission_for_suborder(p_suborder_id);
  ELSE
    UPDATE public.order_suborders
    SET pickup_status = 3,
        status = CASE WHEN status < 3 THEN 3 ELSE status END,
        updated_at = NOW()
    WHERE suborder_id = p_suborder_id
      AND pickup_rider_id = v_user_id;

    UPDATE public.order_items
    SET status = CASE WHEN status < 3 THEN 3 ELSE status END
    WHERE suborder_id = p_suborder_id;
  END IF;

  RETURN public.rider_get_pickup_detail(p_suborder_id);
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
  v_in_transit_fee numeric := 0;
  v_awaiting_fee numeric := 0;
  v_delivered_pending_fee numeric := 0;
  v_active_fee numeric := 0;
  v_available_balance numeric := 0;
  v_pending_withdrawals numeric := 0;
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
    COALESCE(SUM(CASE WHEN pickup_status IN (0, 1) THEN 1 ELSE 0 END), 0) AS awaiting_trips,
    COALESCE(SUM(CASE WHEN pickup_status IN (2, 3) THEN 1 ELSE 0 END), 0) AS in_transit_trips,
    COALESCE(SUM(CASE WHEN pickup_status IN (0, 1) THEN shipping_fee ELSE 0 END), 0) AS awaiting_shipping_fee,
    COALESCE(SUM(CASE WHEN pickup_status IN (0, 1) THEN subtotal ELSE 0 END), 0) AS awaiting_subtotal,
    COALESCE(SUM(CASE WHEN pickup_status IN (2, 3) THEN shipping_fee ELSE 0 END), 0) AS in_transit_shipping_fee,
    COALESCE(SUM(CASE WHEN pickup_status IN (2, 3) THEN subtotal ELSE 0 END), 0) AS in_transit_subtotal
  INTO v_aggregates
  FROM public.order_suborders
  WHERE pickup_rider_id = v_user_id;

  SELECT COALESCE(SUM(wl.amount), 0)
  INTO v_completed_fee
  FROM public.wallet_ledger AS wl
  WHERE wl.user_id = v_user_id
    AND wl.wallet_role = 'rider'
    AND wl.entry_kind = 'rider_commission_delivery';

  SELECT
    COALESCE(SUM(CASE WHEN wr.status = 'pending' THEN wr.amount ELSE 0 END), 0)
  INTO v_pending_withdrawals
  FROM public.withdrawal_requests AS wr
  WHERE wr.user_id = v_user_id
    AND wr.wallet_role = 'rider';

  SELECT COALESCE(SUM(public.rider_commission_amount(os.shipping_fee, os.subtotal)), 0)
  INTO v_delivered_pending_fee
  FROM public.order_suborders AS os
  WHERE os.pickup_rider_id = v_user_id
    AND os.pickup_status = 4
    AND NOT EXISTS (
      SELECT 1
      FROM public.wallet_ledger AS wl
      WHERE wl.user_id = v_user_id
        AND wl.wallet_role = 'rider'
        AND wl.entry_kind = 'rider_commission_delivery'
        AND wl.reference_id = os.suborder_id
    );

  v_in_transit_fee := public.rider_commission_amount(v_aggregates.in_transit_shipping_fee, v_aggregates.in_transit_subtotal);
  v_awaiting_fee := public.rider_commission_amount(v_aggregates.awaiting_shipping_fee, v_aggregates.awaiting_subtotal);
  v_active_fee := COALESCE(v_in_transit_fee, 0) + COALESCE(v_awaiting_fee, 0) + COALESCE(v_delivered_pending_fee, 0);
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
      os.reference,
      os.total_amount,
      os.pickup_status,
      os.updated_at,
      COALESCE(sd.store_name, 'Seller') AS store_name,
      COALESCE(
        (
          SELECT wl.amount
          FROM public.wallet_ledger AS wl
          WHERE wl.user_id = v_user_id
            AND wl.wallet_role = 'rider'
            AND wl.entry_kind = 'rider_commission_delivery'
            AND wl.reference_id = os.suborder_id
          ORDER BY wl.ledger_id DESC
          LIMIT 1
        ),
        public.rider_commission_amount(os.shipping_fee, os.subtotal)
      ) AS commission_amount
    FROM public.order_suborders AS os
    LEFT JOIN public.seller_details AS sd ON sd.user_id = os.seller_id
    WHERE os.pickup_rider_id = v_user_id
    ORDER BY os.updated_at DESC
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
      os.reference,
      os.total_amount,
      os.updated_at,
      COALESCE(sd.store_name, 'Seller') AS store_name,
      public.rider_commission_amount(os.shipping_fee, os.subtotal) AS commission_amount
    FROM public.order_suborders AS os
    LEFT JOIN public.seller_details AS sd ON sd.user_id = os.seller_id
    WHERE os.pickup_status = 1
      AND (os.pickup_rider_id IS NULL OR os.pickup_rider_id = 0)
    ORDER BY os.updated_at DESC
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
    'awaiting_fee', COALESCE(v_awaiting_fee, 0),
    'in_transit_fee', COALESCE(v_in_transit_fee, 0),
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
  v_in_transit_fee numeric := 0;
  v_awaiting_fee numeric := 0;
  v_delivered_pending_fee numeric := 0;
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
    COALESCE(SUM(CASE WHEN pickup_status IN (2, 3) THEN 1 ELSE 0 END), 0) AS in_transit_trips,
    COALESCE(SUM(CASE WHEN pickup_status IN (0, 1) THEN 1 ELSE 0 END), 0) AS awaiting_trips,
    COALESCE(SUM(CASE WHEN pickup_status IN (2, 3) THEN shipping_fee ELSE 0 END), 0) AS in_transit_shipping_fee,
    COALESCE(SUM(CASE WHEN pickup_status IN (2, 3) THEN subtotal ELSE 0 END), 0) AS in_transit_subtotal,
    COALESCE(SUM(CASE WHEN pickup_status IN (0, 1) THEN shipping_fee ELSE 0 END), 0) AS awaiting_shipping_fee,
    COALESCE(SUM(CASE WHEN pickup_status IN (0, 1) THEN subtotal ELSE 0 END), 0) AS awaiting_subtotal
  INTO v_aggregates
  FROM public.order_suborders
  WHERE pickup_rider_id = v_user_id;

  SELECT COALESCE(SUM(wl.amount), 0)
  INTO v_completed_fee
  FROM public.wallet_ledger AS wl
  WHERE wl.user_id = v_user_id
    AND wl.wallet_role = 'rider'
    AND wl.entry_kind = 'rider_commission_delivery';

  SELECT
    COALESCE(SUM(CASE WHEN wr.status = 'pending' THEN wr.amount ELSE 0 END), 0),
    MAX(wr.created_at)
  INTO v_pending_withdrawals, v_last_requested_at
  FROM public.withdrawal_requests AS wr
  WHERE wr.user_id = v_user_id
    AND wr.wallet_role = 'rider';

  SELECT COALESCE(SUM(public.rider_commission_amount(os.shipping_fee, os.subtotal)), 0)
  INTO v_delivered_pending_fee
  FROM public.order_suborders AS os
  WHERE os.pickup_rider_id = v_user_id
    AND os.pickup_status = 4
    AND NOT EXISTS (
      SELECT 1
      FROM public.wallet_ledger AS wl
      WHERE wl.user_id = v_user_id
        AND wl.wallet_role = 'rider'
        AND wl.entry_kind = 'rider_commission_delivery'
        AND wl.reference_id = os.suborder_id
    );

  v_in_transit_fee := public.rider_commission_amount(v_aggregates.in_transit_shipping_fee, v_aggregates.in_transit_subtotal);
  v_awaiting_fee := public.rider_commission_amount(v_aggregates.awaiting_shipping_fee, v_aggregates.awaiting_subtotal);
  v_active_fee := COALESCE(v_in_transit_fee, 0) + COALESCE(v_awaiting_fee, 0) + COALESCE(v_delivered_pending_fee, 0);
  v_available_balance := GREATEST(COALESCE(v_completed_fee, 0) - COALESCE(v_pending_withdrawals, 0), 0);

  SELECT COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'reference', q.reference,
        'label', 'Delivery',
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
      os.reference,
      os.pickup_status,
      os.updated_at,
      CASE
        WHEN os.pickup_status = 4 THEN COALESCE(
          (
            SELECT wl.amount
            FROM public.wallet_ledger AS wl
            WHERE wl.user_id = v_user_id
              AND wl.wallet_role = 'rider'
              AND wl.entry_kind = 'rider_commission_delivery'
              AND wl.reference_id = os.suborder_id
            ORDER BY wl.ledger_id DESC
            LIMIT 1
          ),
          public.rider_commission_amount(os.shipping_fee, os.subtotal)
        )
        ELSE public.rider_commission_amount(os.shipping_fee, os.subtotal)
      END AS amount
    FROM public.order_suborders AS os
    WHERE os.pickup_rider_id = v_user_id
    ORDER BY os.updated_at DESC
    LIMIT 10
  ) AS q;

  RETURN jsonb_build_object(
    'total_trips', COALESCE(v_aggregates.total_trips, 0),
    'total_fee', COALESCE(v_completed_fee, 0) + COALESCE(v_active_fee, 0),
    'completed_fee', COALESCE(v_completed_fee, 0),
    'in_transit_fee', COALESCE(v_in_transit_fee, 0),
    'awaiting_fee', COALESCE(v_awaiting_fee, 0),
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

CREATE OR REPLACE FUNCTION public.credit_rider_commission_for_suborder(p_suborder_id integer)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_rider_id integer;
  v_shipping_fee numeric := 0;
  v_subtotal numeric := 0;
  v_amount numeric := 0;
BEGIN
  SELECT os.pickup_rider_id, COALESCE(os.shipping_fee, 0), COALESCE(os.subtotal, 0)
  INTO v_rider_id, v_shipping_fee, v_subtotal
  FROM public.order_suborders AS os
  WHERE os.suborder_id = p_suborder_id
  LIMIT 1;

  IF COALESCE(v_rider_id, 0) <= 0 THEN
    RETURN;
  END IF;

  v_amount := public.rider_commission_amount(v_shipping_fee, v_subtotal);
  IF COALESCE(v_amount, 0) <= 0 THEN
    RETURN;
  END IF;

  INSERT INTO public.wallet_ledger (
    user_id,
    wallet_role,
    amount,
    entry_kind,
    reference_id,
    note
  )
  SELECT
    v_rider_id,
    'rider',
    v_amount,
    'rider_commission_delivery',
    p_suborder_id,
    'Rider delivery commission and product share'
  WHERE NOT EXISTS (
    SELECT 1
    FROM public.wallet_ledger AS wl
    WHERE wl.user_id = v_rider_id
      AND wl.wallet_role = 'rider'
      AND wl.entry_kind = 'rider_commission_delivery'
      AND wl.reference_id = p_suborder_id
  );
END;
$$;

REVOKE ALL ON FUNCTION public.credit_rider_commission_for_suborder(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.credit_rider_commission_for_suborder(integer) FROM anon;
REVOKE ALL ON FUNCTION public.credit_rider_commission_for_suborder(integer) FROM authenticated;

INSERT INTO public.wallet_ledger (
  user_id,
  wallet_role,
  amount,
  entry_kind,
  reference_id,
  note
)
SELECT
  os.pickup_rider_id,
  'rider',
  public.rider_commission_amount(os.shipping_fee, os.subtotal),
  'rider_commission_delivery',
  os.suborder_id,
  'Rider delivery commission and product share'
FROM public.order_suborders AS os
WHERE os.pickup_status = 4
  AND COALESCE(os.pickup_rider_id, 0) > 0
  AND public.rider_commission_amount(os.shipping_fee, os.subtotal) > 0
  AND NOT EXISTS (
    SELECT 1
    FROM public.wallet_ledger AS wl
    WHERE wl.user_id = os.pickup_rider_id
      AND wl.wallet_role = 'rider'
      AND wl.entry_kind = 'rider_commission_delivery'
      AND wl.reference_id = os.suborder_id
  );

CREATE OR REPLACE FUNCTION public.credit_seller_for_completed_suborder(p_suborder_id integer)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_seller_id integer;
  v_subtotal numeric := 0;
  v_status integer := 0;
BEGIN
  SELECT os.seller_id, COALESCE(os.subtotal, 0), COALESCE(os.status, 0)
  INTO v_seller_id, v_subtotal, v_status
  FROM public.order_suborders AS os
  WHERE os.suborder_id = p_suborder_id
  LIMIT 1;

  IF COALESCE(v_status, 0) <> 6 OR COALESCE(v_seller_id, 0) <= 0 OR COALESCE(v_subtotal, 0) <= 0 THEN
    RETURN;
  END IF;

  INSERT INTO public.wallet_ledger (
    user_id,
    wallet_role,
    amount,
    entry_kind,
    reference_id,
    note
  )
  SELECT
    v_seller_id,
    'seller',
    v_subtotal,
    'seller_cod_release',
    p_suborder_id,
    'Seller balance from completed sub-order'
  WHERE NOT EXISTS (
    SELECT 1
    FROM public.wallet_ledger AS wl
    WHERE wl.user_id = v_seller_id
      AND wl.wallet_role = 'seller'
      AND wl.entry_kind = 'seller_cod_release'
      AND wl.reference_id = p_suborder_id
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.ensure_seller_credits_for_order(p_order_id integer)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_suborder record;
BEGIN
  FOR v_suborder IN
    SELECT os.suborder_id
    FROM public.order_suborders AS os
    WHERE os.order_id = p_order_id
      AND os.status = 6
  LOOP
    PERFORM public.credit_seller_for_completed_suborder(v_suborder.suborder_id);
  END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION public.credit_seller_for_completed_suborder(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.credit_seller_for_completed_suborder(integer) FROM anon;
REVOKE ALL ON FUNCTION public.credit_seller_for_completed_suborder(integer) FROM authenticated;
REVOKE ALL ON FUNCTION public.ensure_seller_credits_for_order(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.ensure_seller_credits_for_order(integer) FROM anon;
REVOKE ALL ON FUNCTION public.ensure_seller_credits_for_order(integer) FROM authenticated;

INSERT INTO public.wallet_ledger (
  user_id,
  wallet_role,
  amount,
  entry_kind,
  reference_id,
  note
)
SELECT
  os.seller_id,
  'seller',
  COALESCE(os.subtotal, 0),
  'seller_cod_release',
  os.suborder_id,
  'Seller balance from completed sub-order'
FROM public.order_suborders AS os
WHERE os.status = 6
  AND COALESCE(os.seller_id, 0) > 0
  AND COALESCE(os.subtotal, 0) > 0
  AND NOT EXISTS (
    SELECT 1
    FROM public.wallet_ledger AS wl
    WHERE wl.user_id = os.seller_id
      AND wl.wallet_role = 'seller'
      AND wl.entry_kind = 'seller_cod_release'
      AND wl.reference_id = os.suborder_id
  );

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

  UPDATE public.order_items
  SET status = 6
  WHERE user_id = v_user_id
    AND lower(COALESCE(reference, '')) = lower(v_reference)
    AND status = 4;

  GET DIAGNOSTICS v_updated_count = ROW_COUNT;

  IF COALESCE(v_updated_count, 0) <= 0 THEN
    RAISE EXCEPTION 'No delivered items to confirm for this order.';
  END IF;

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

  PERFORM public.ensure_seller_credits_for_order(v_order_id);

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
