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
    shipping = float(rows[0].get("shipping_fee") or 0)
    subtotal = float(rows[0].get("subtotal") or 0)
    
    ship_pct = get_float_setting("rider_commission_pct_of_shipping", 70.0) / 100.0
    prod_pct = get_float_setting("rider_commission_pct_of_product", 5.0) / 100.0
    
    amount = round(max(0.0, (shipping * ship_pct) + (subtotal * prod_pct)), 2)
    if amount <= 0:
        return
    rid = int(rider_id)
    if _ledger_exists("rider_commission_delivery", suborder_id, rid):
        return
    _ledger_insert(rid, "rider", _d(amount), "rider_commission_delivery", suborder_id, "Rider delivery commission and product share")


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
