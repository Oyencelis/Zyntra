"""Wallet ledger, rider commission, seller COD release, withdrawals."""
from __future__ import annotations

from decimal import Decimal

from helpers.QueryHelpers import executeGet, executePost
from helpers.marketplace_settings import get_float_setting


def _d(val) -> Decimal:
    try:
        return Decimal(str(val or 0))
    except Exception:
        return Decimal("0")


def ledger_balance(user_id: int, wallet_role: str) -> Decimal:
    rows = executeGet(
        """
        SELECT COALESCE(SUM(amount), 0) AS bal
        FROM wallet_ledger
        WHERE user_id = %s AND wallet_role = %s
        """,
        (user_id, wallet_role),
    ) or []
    if not rows:
        return Decimal("0")
    return _d(rows[0].get("bal"))


def pending_withdrawal_total(user_id: int, wallet_role: str) -> Decimal:
    rows = executeGet(
        """
        SELECT COALESCE(SUM(amount), 0) AS p
        FROM withdrawal_requests
        WHERE user_id = %s AND wallet_role = %s AND status = 'pending'
        """,
        (user_id, wallet_role),
    ) or []
    if not rows:
        return Decimal("0")
    return _d(rows[0].get("p"))


def available_balance(user_id: int, wallet_role: str) -> Decimal:
    return ledger_balance(user_id, wallet_role) - pending_withdrawal_total(user_id, wallet_role)


def calculate_rider_commission_amount(shipping_fee, subtotal) -> float:
    shipping = float(shipping_fee or 0)
    subtotal_amount = float(subtotal or 0)
    ship_pct = get_float_setting("rider_commission_pct_of_shipping", 70.0) / 100.0
    prod_pct = get_float_setting("rider_commission_pct_of_product", 5.0) / 100.0
    return round(max(0.0, (shipping * ship_pct) + (subtotal_amount * prod_pct)), 2)


def rider_earnings_snapshot(user_id: int) -> dict[str, float | int]:
    active_rows = executeGet(
        """
        WITH pickup_rows AS (
            SELECT
                CASE
                    WHEN COALESCE(oi.pickup_status, 0) IN (2, 3, 4) THEN oi.pickup_status
                    WHEN COALESCE(os.pickup_status, 0) IN (2, 3, 4) AND os.pickup_rider_id IS NOT NULL AND oi.status IN (2, 3, 4, 6) THEN os.pickup_status
                    ELSE public.order_item_pickup_status(oi.status, oi.pickup_status)
                END AS pickup_status,
                CASE
                    WHEN oi.pickup_rider_id IS NOT NULL THEN oi.pickup_rider_id
                    WHEN COALESCE(os.pickup_status, 0) IN (2, 3, 4) AND oi.status IN (2, 3, 4, 6) THEN os.pickup_rider_id
                    ELSE NULL
                END AS pickup_rider_id,
                COALESCE(money.commission_amount, 0) AS commission_amount
            FROM order_items oi
            INNER JOIN order_suborders os ON os.suborder_id = oi.suborder_id
            LEFT JOIN LATERAL public.order_item_pickup_financials(oi.suborder_id, oi.order_items_id) AS money ON TRUE
        )
        SELECT
            COUNT(*) AS total_trips,
            SUM(CASE WHEN pickup_status = 3 THEN commission_amount ELSE 0 END) AS in_transit_fee,
            SUM(CASE WHEN pickup_status = 2 THEN commission_amount ELSE 0 END) AS awaiting_fee,
            SUM(CASE WHEN pickup_status = 3 THEN 1 ELSE 0 END) AS in_transit_trips,
            SUM(CASE WHEN pickup_status = 2 THEN 1 ELSE 0 END) AS awaiting_trips,
            SUM(CASE WHEN pickup_status = 4 THEN 1 ELSE 0 END) AS completed_trips
        FROM pickup_rows
        WHERE pickup_rider_id = %s
          AND pickup_status IN (2, 3, 4)
        """,
        (user_id,),
    ) or []
    active = active_rows[0] if active_rows else {}

    completed_rows = executeGet(
        """
        SELECT COALESCE(SUM(amount), 0) AS completed_fee
        FROM wallet_ledger
        WHERE user_id = %s AND wallet_role = 'rider' AND entry_kind IN ('rider_commission_delivery', 'rider_commission_delivery_item')
        """,
        (user_id,),
    ) or []
    completed_fee = float((completed_rows[0] if completed_rows else {}).get("completed_fee") or 0)

    in_transit_fee = float(active.get("in_transit_fee") or 0)
    awaiting_fee = float(active.get("awaiting_fee") or 0)
    active_fee = round(in_transit_fee + awaiting_fee, 2)
    total_fee = round(completed_fee + active_fee, 2)
    available = float(available_balance(user_id, "rider"))
    pending = float(pending_withdrawal_total(user_id, "rider"))

    return {
        "total_trips": int(active.get("total_trips") or 0),
        "completed_trips": int(active.get("completed_trips") or 0),
        "in_transit_trips": int(active.get("in_transit_trips") or 0),
        "awaiting_trips": int(active.get("awaiting_trips") or 0),
        "completed_fee": completed_fee,
        "in_transit_fee": in_transit_fee,
        "awaiting_fee": awaiting_fee,
        "active_fee": active_fee,
        "total_fee": total_fee,
        "available_balance": available,
        "pending_withdrawals": pending,
    }


def seller_earnings_snapshot(user_id: int) -> dict[str, float | int]:
    rows = executeGet(
        """
        WITH item_values AS (
            SELECT
                oi.order_items_id,
                oi.status,
                COALESCE(p.price, 0) * GREATEST(COALESCE(oi.quantity, 0), 0) AS line_total
            FROM order_items oi
            INNER JOIN order_suborders os ON os.suborder_id = oi.suborder_id
            LEFT JOIN products p ON p.product_id = oi.product_id
            WHERE os.seller_id = %s
        )
        SELECT
            COUNT(*) AS total_orders,
            SUM(CASE WHEN status = 6 THEN 1 ELSE 0 END) AS completed_orders,
            SUM(CASE WHEN status NOT IN (5, 6, 8) THEN 1 ELSE 0 END) AS processing_orders,
            SUM(CASE WHEN status IN (5, 8) THEN 1 ELSE 0 END) AS cancelled_orders,
            COALESCE(SUM(line_total), 0) AS total_revenue,
            COALESCE(SUM(CASE WHEN status = 6 THEN line_total ELSE 0 END), 0) AS completed_revenue,
            COALESCE(SUM(CASE WHEN status NOT IN (5, 6, 8) THEN line_total ELSE 0 END), 0) AS processing_revenue,
            COALESCE(SUM(CASE WHEN status IN (5, 8) THEN line_total ELSE 0 END), 0) AS cancelled_revenue
        FROM item_values
        """,
        (user_id,),
    ) or []
    row = rows[0] if rows else {}

    released_balance = float(ledger_balance(user_id, "seller"))
    pending = float(pending_withdrawal_total(user_id, "seller"))
    available = float(available_balance(user_id, "seller"))

    total_orders = int(row.get("total_orders") or 0)
    completed_orders = int(row.get("completed_orders") or 0)
    processing_orders = int(row.get("processing_orders") or 0)
    cancelled_orders = int(row.get("cancelled_orders") or 0)
    processed_count = completed_orders + processing_orders + cancelled_orders
    remaining_orders = max(total_orders - processed_count, 0)

    total_revenue = float(row.get("total_revenue") or 0)
    completed_revenue = float(row.get("completed_revenue") or 0)
    processing_revenue = float(row.get("processing_revenue") or 0)
    cancelled_revenue = float(row.get("cancelled_revenue") or 0)
    accounted_revenue = completed_revenue + processing_revenue + cancelled_revenue
    remaining_revenue = max(total_revenue - accounted_revenue, 0.0)

    return {
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "processing_orders": processing_orders,
        "cancelled_orders": cancelled_orders,
        "remaining_orders": remaining_orders,
        "total_revenue": total_revenue,
        "completed_revenue": completed_revenue,
        "completed_payout": max(released_balance, 0.0),
        "processing_revenue": processing_revenue,
        "cancelled_revenue": cancelled_revenue,
        "remaining_revenue": remaining_revenue,
        "available_balance": available,
        "pending_withdrawals": pending,
        "ledger_balance": released_balance,
    }


def _ledger_exists(entry_kind: str, reference_id: int | None, user_id: int) -> bool:
    rows = executeGet(
        """
        SELECT ledger_id FROM wallet_ledger
        WHERE entry_kind = %s AND reference_id IS NOT DISTINCT FROM %s AND user_id = %s
        LIMIT 1
        """,
        (entry_kind, reference_id, user_id),
    ) or []
    return bool(rows)


def _ledger_insert(user_id: int, wallet_role: str, amount: Decimal, entry_kind: str, reference_id: int | None, note: str):
    res = executePost(
        """
        INSERT INTO wallet_ledger (user_id, wallet_role, amount, entry_kind, reference_id, note)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (user_id, wallet_role, str(amount), entry_kind, reference_id, note),
    )
    return not isinstance(res, tuple)


def credit_rider_commission_for_suborder(suborder_id: int) -> None:
    rows = executeGet(
        """
        SELECT os.pickup_rider_id AS rider_id,
               os.shipping_fee,
               os.subtotal
        FROM order_suborders os
        WHERE os.suborder_id = %s
        LIMIT 1
        """,
        (suborder_id,),
    ) or []
    if not rows:
        return
    rider_id = rows[0].get("rider_id")
    if not rider_id:
        return
    amount = calculate_rider_commission_amount(rows[0].get("shipping_fee"), rows[0].get("subtotal"))
    if amount <= 0:
        return
    rid = int(rider_id)
    if _ledger_exists("rider_commission_delivery", suborder_id, rid):
        return
    _ledger_insert(rid, "rider", _d(amount), "rider_commission_delivery", suborder_id, "Rider delivery commission and product share")


def credit_rider_commission_for_item(order_item_id: int) -> None:
    rows = executeGet(
        """
        SELECT oi.pickup_rider_id AS rider_id,
               money.commission_amount
        FROM order_items oi
        LEFT JOIN LATERAL public.order_item_pickup_financials(oi.suborder_id, oi.order_items_id) AS money ON TRUE
        WHERE oi.order_items_id = %s
        LIMIT 1
        """,
        (order_item_id,),
    ) or []
    if not rows:
        return
    rider_id = rows[0].get("rider_id")
    if not rider_id:
        return
    amount = float(rows[0].get("commission_amount") or 0)
    if amount <= 0:
        return
    rid = int(rider_id)
    if _ledger_exists("rider_commission_delivery_item", order_item_id, rid):
        return
    _ledger_insert(rid, "rider", _d(amount), "rider_commission_delivery_item", order_item_id, "Rider delivery commission and product share")


def credit_seller_for_completed_suborder(suborder_id: int) -> None:
    rows = executeGet(
        """
        SELECT os.seller_id,
               os.subtotal,
               os.status
        FROM order_suborders os
        WHERE os.suborder_id = %s
        LIMIT 1
        """,
        (suborder_id,),
    ) or []
    if not rows:
        return
    if int(rows[0].get("status") or 0) != 6:
        return
    seller_id = rows[0].get("seller_id")
    if not seller_id:
        return
    sid = int(seller_id)
    if _ledger_exists("seller_cod_release", suborder_id, sid):
        return
    subtotal = float(rows[0].get("subtotal") or 0)
    amount = round(max(0.0, subtotal), 2)
    if amount <= 0:
        return
    _ledger_insert(sid, "seller", _d(amount), "seller_cod_release", suborder_id, "Seller balance from completed sub-order")


def credit_seller_for_completed_item(order_item_id: int) -> None:
    rows = executeGet(
        """
        SELECT
            os.seller_id,
            oi.suborder_id,
            oi.status,
            COALESCE(p.price, 0) * GREATEST(COALESCE(oi.quantity, 0), 0) AS line_total
        FROM order_items oi
        INNER JOIN order_suborders os ON os.suborder_id = oi.suborder_id
        LEFT JOIN products p ON p.product_id = oi.product_id
        WHERE oi.order_items_id = %s
        LIMIT 1
        """,
        (order_item_id,),
    ) or []
    if not rows:
        return
    status = int(rows[0].get("status") or 0)
    if status != 6:
        return
    seller_id = rows[0].get("seller_id")
    if not seller_id:
        return
    sid = int(seller_id)
    suborder_id = rows[0].get("suborder_id")
    if _ledger_exists("seller_cod_release_item", order_item_id, sid):
        return
    if suborder_id and _ledger_exists("seller_cod_release", suborder_id, sid):
        return
    amount = round(max(0.0, float(rows[0].get("line_total") or 0)), 2)
    if amount <= 0:
        return
    _ledger_insert(sid, "seller", _d(amount), "seller_cod_release_item", order_item_id, "Seller balance from completed order item")


def ensure_seller_credits_for_order(order_id: int):
    subs = executeGet(
        """
        SELECT suborder_id
        FROM order_suborders
        WHERE order_id = %s AND status = 6
        """,
        (order_id,),
    ) or []
    if not isinstance(subs, list):
        return
    for row in subs:
        sid = row.get("suborder_id")
        if sid:
            credit_seller_for_completed_suborder(int(sid))


def create_withdrawal_request(user_id: int, wallet_role: str, amount: float, payout_notes: str):
    bal = available_balance(user_id, wallet_role)
    if amount <= 0:
        return None, "Invalid amount."
    if _d(amount) > bal:
        return None, "Insufficient available balance (pending withdrawals are reserved)."
    wr = executePost(
        """
        INSERT INTO withdrawal_requests (user_id, wallet_role, amount, payout_notes, status)
        VALUES (%s, %s, %s, %s, 'pending')
        """,
        (user_id, wallet_role, f"{amount:.2f}", payout_notes[:2000] if payout_notes else None),
    )
    if isinstance(wr, tuple) or not wr or not wr.get("last_inserted_id"):
        return None, "Unable to submit withdrawal."
    wid = wr.get("last_inserted_id")
    executePost(
        """
        INSERT INTO withdrawal_audit (withdrawal_id, action, actor_user_id, detail)
        VALUES (%s, 'created', %s, %s)
        """,
        (wid, user_id, payout_notes[:500] if payout_notes else ""),
    )
    return wid, None


def finalize_withdrawal(withdrawal_id: int, admin_user_id: int, approve: bool, admin_note: str | None):
    rows = executeGet(
        "SELECT withdrawal_id, user_id, wallet_role, amount, status FROM withdrawal_requests WHERE withdrawal_id = %s",
        (withdrawal_id,),
    ) or []
    if not rows:
        return False, "Not found."
    row = rows[0]
    if row.get("status") != "pending":
        return False, "Already processed."

    uid = int(row["user_id"])
    role = row["wallet_role"]
    amount = _d(row["amount"])

    if approve:
        bal = available_balance(uid, role)
        if amount > bal:
            return False, "User balance changed; cannot approve."
        if _ledger_exists("withdrawal_payout", withdrawal_id, uid):
            return False, "Withdrawal already settled in ledger."
        debit = executePost(
            """
            INSERT INTO wallet_ledger (user_id, wallet_role, amount, entry_kind, reference_id, note)
            VALUES (%s, %s, %s, 'withdrawal_payout', %s, %s)
            """,
            (uid, role, str(-amount), withdrawal_id, (admin_note or "Withdrawal approved")[:500]),
        )
        if isinstance(debit, tuple):
            return False, "Ledger error."
        executePost(
            """
            UPDATE withdrawal_requests
            SET status = 'approved', admin_note = %s, decided_by = %s, decided_at = NOW()
            WHERE withdrawal_id = %s
            """,
            (admin_note, admin_user_id, withdrawal_id),
        )
        executePost(
            """
            INSERT INTO withdrawal_audit (withdrawal_id, action, actor_user_id, detail)
            VALUES (%s, 'approved', %s, %s)
            """,
            (withdrawal_id, admin_user_id, admin_note or ""),
        )
        return True, None

    executePost(
        """
        UPDATE withdrawal_requests
        SET status = 'rejected', admin_note = %s, decided_by = %s, decided_at = NOW()
        WHERE withdrawal_id = %s
        """,
        (admin_note, admin_user_id, withdrawal_id),
    )
    executePost(
        """
        INSERT INTO withdrawal_audit (withdrawal_id, action, actor_user_id, detail)
        VALUES (%s, 'rejected', %s, %s)
        """,
        (withdrawal_id, admin_user_id, admin_note or ""),
    )
    return True, None
