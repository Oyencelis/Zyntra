# pyrefly: ignore [missing-import]
from flask import render_template, g, redirect, url_for, request
from helpers.HelperFunction import responseData
from helpers.QueryHelpers import executeGet
from helpers.wallet_finance import (
    available_balance,
    create_withdrawal_request,
    finalize_withdrawal,
    ledger_balance,
    pending_withdrawal_total,
)


def _require_role(*allowed):
    auth = g.authenticated or {}
    if auth.get("role_id") not in allowed:
        return None, responseData("error", "Unauthorized.", "", 403)
    return auth, None


def api_wallet_summary():
    auth, err = _require_role(3, 4)
    if err:
        return err
    uid = auth.get("user_id")
    role_id = auth.get("role_id")
    wallet_role = "rider" if role_id == 4 else "seller"
    bal = float(available_balance(uid, wallet_role))
    pending = float(pending_withdrawal_total(uid, wallet_role))
    lifetime = float(ledger_balance(uid, wallet_role))
    return responseData(
        "success",
        "Wallet snapshot.",
        {"available": bal, "pending_withdrawals": pending, "lifetime_net": lifetime, "wallet_role": wallet_role},
        200,
    )


def api_wallet_withdraw():
    auth, err = _require_role(3, 4)
    if err:
        return err
    uid = auth.get("user_id")
    role_id = auth.get("role_id")
    wallet_role = "rider" if role_id == 4 else "seller"
    try:
        amount = float(request.form.get("amount") or 0)
    except (TypeError, ValueError):
        return responseData("error", "Invalid amount.", "", 400)
    notes = (request.form.get("payout_notes") or "").strip()
    wid, werr = create_withdrawal_request(uid, wallet_role, amount, notes)
    if werr:
        return responseData("error", werr, "", 400)
    return responseData("success", "Withdrawal submitted for review.", {"withdrawal_id": wid}, 200)


def admin_withdrawals_page():
    if not g.authenticated or g.authenticated.get("role_id") != 1:
        return redirect(url_for("login_page"))
    rows = executeGet(
        """
        SELECT w.*, u.firstname, u.lastname, u.email
        FROM withdrawal_requests w
        JOIN users u ON u.user_id = w.user_id
        ORDER BY w.created_at DESC
        LIMIT 200
        """,
        (),
    ) or []
    if not isinstance(rows, list):
        rows = []
    return render_template("views/dashboard/admin/withdrawals.html", withdrawals=rows, menu="withdrawals")


def admin_withdrawal_decide():
    if not g.authenticated or g.authenticated.get("role_id") != 1:
        return redirect(url_for("login_page"))
    wid = request.form.get("withdrawal_id", type=int)
    action = (request.form.get("action") or "").lower()
    note = (request.form.get("admin_note") or "").strip()
    if not wid or action not in ("approve", "reject"):
        return redirect(url_for("admin_withdrawals"))
    finalize_withdrawal(wid, g.authenticated.get("user_id"), action == "approve", note)
    return redirect(url_for("admin_withdrawals"))
