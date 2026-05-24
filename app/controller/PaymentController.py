from datetime import datetime
# pyrefly: ignore [missing-import]
from flask import render_template, g, redirect, url_for
from helpers.QueryHelpers import executeGet
from helpers.wallet_finance import available_balance, pending_withdrawal_total, rider_earnings_snapshot, seller_earnings_snapshot, calculate_rider_commission_amount

ORDER_STATUS_LABELS = {
    1: "Order Placed",
    2: "Packed / Shipped",
    3: "Out for Delivery",
    4: "Delivered",
    5: "Cancelled",
    6: "Completed",
    7: "Accepted",
    8: "Rejected",
}

PICKUP_STATUS_LABELS = {
    0: "Pending",
    1: "Awaiting Pickup",
    2: "Claimed",
    3: "In Transit",
    4: "Delivered",
}

ORDER_BADGE_CLASSES = {
    1: "bg-label-secondary",
    2: "bg-label-info",
    3: "bg-label-primary",
    4: "bg-label-success",
    5: "bg-label-danger",
    6: "bg-label-success",
    7: "bg-label-primary",
    8: "bg-label-dark",
}

PICKUP_BADGE_CLASSES = {
    0: "bg-label-secondary",
    1: "bg-label-secondary",
    2: "bg-label-info",
    3: "bg-label-primary",
    4: "bg-label-success",
}


def paymentDashboard():
    if not g.authenticated:
        return redirect(url_for('login_page'))

    user_id = g.authenticated.get('user_id')
    role_id = g.authenticated.get('role_id')
    if not user_id:
        return redirect(url_for('login_page'))

    is_rider = role_id == 4
    wallet_role = None
    wallet_available = None
    wallet_pending = None
    if is_rider:
        wallet_role = "rider"
    elif role_id == 3:
        wallet_role = "seller"
    if wallet_role:
        wallet_available = float(available_balance(user_id, wallet_role))
        wallet_pending = float(pending_withdrawal_total(user_id, wallet_role))

    if is_rider:
        aggregates = _get_rider_aggregates(user_id)
        summary_cards = _build_rider_summary_cards(aggregates)
        payout_breakdown = _build_rider_breakdown_cards(aggregates)
        transactions = _get_rider_transactions(user_id)
        hero = {
            "eyebrow": "Delivery earnings overview",
            "title": "Rider Earnings & Payouts",
            "subtitle": "Track completed trips, pending drops, and funds waiting to be released.",
            "meta_label": "Projected rider earnings to date",
            "meta_value": _format_currency(aggregates.get('total_fee')),
        }
        menu = ['earnings']
    else:
        aggregates = _get_seller_aggregates(user_id)
        summary_cards = _build_seller_summary_cards(aggregates)
        payout_breakdown = _build_seller_breakdown_cards(aggregates)
        transactions = _get_seller_transactions(user_id)
        hero = {
            "eyebrow": "Store income snapshot",
            "title": "Seller Payments & Payouts",
            "subtitle": "Monitor completed sales, pending releases, and cancelled orders in one place.",
            "meta_label": "Lifetime gross sales",
            "meta_value": _format_currency(aggregates.get('total_revenue')),
        }
        menu = ['payment']

    return render_template(
        'views/dashboard/payment.html',
        role_id=role_id,
        is_rider=is_rider,
        hero=hero,
        summary_cards=summary_cards,
        payout_breakdown=payout_breakdown,
        transactions=transactions,
        menu=menu,
        wallet_role=wallet_role,
        wallet_available=wallet_available,
        wallet_pending=wallet_pending,
    )


def _get_rider_aggregates(user_id):
    return rider_earnings_snapshot(user_id)


def _get_seller_aggregates(user_id):
    return seller_earnings_snapshot(user_id)


def _build_rider_summary_cards(aggregates):
    return [
        {
            'label': 'Total Deliveries',
            'value': f"{aggregates.get('total_trips', 0):,}",
            'helper': 'All assignments ever linked to your rider ID'
        },
        {
            'label': 'Completed Drops',
            'value': f"{aggregates.get('completed_trips', 0):,}",
            'helper': 'Deliveries released to customers'
        },
        {
            'label': 'Active Trips',
            'value': f"{aggregates.get('in_transit_trips', 0):,}",
            'helper': 'Currently claimed or in transit'
        },
        {
            'label': 'Total Earnings',
            'value': _format_currency(aggregates.get('total_fee')),
            'helper': 'Credited plus projected rider commissions'
        }
    ]


def _build_seller_summary_cards(aggregates):
    return [
        {
            'label': 'Items Received',
            'value': f"{aggregates.get('total_orders', 0):,}",
            'helper': 'Order items routed to your store'
        },
        {
            'label': 'Completed Items',
            'value': f"{aggregates.get('completed_orders', 0):,}",
            'helper': 'Buyer-confirmed completed items'
        },
        {
            'label': 'Items in Progress',
            'value': f"{aggregates.get('processing_orders', 0):,}",
            'helper': 'Items awaiting fulfillment or delivery'
        },
        {
            'label': 'Gross Sales',
            'value': _format_currency(aggregates.get('total_revenue')),
            'helper': 'Product line totals only'
        }
    ]


def _build_rider_breakdown_cards(aggregates):
    return [
        {
            'label': 'Completed payouts',
            'amount': _format_currency(aggregates.get('completed_fee')),
            'caption': f"{aggregates.get('completed_trips', 0):,} drops settled",
            'badge_class': 'bg-label-success'
        },
        {
            'label': 'In-transit earnings',
            'amount': _format_currency(aggregates.get('in_transit_fee')),
            'caption': f"{aggregates.get('in_transit_trips', 0):,} drops en route",
            'badge_class': 'bg-label-info'
        },
        {
            'label': 'Awaiting pickup',
            'amount': _format_currency(aggregates.get('awaiting_fee')),
            'caption': f"{aggregates.get('awaiting_trips', 0):,} drops queued for claim",
            'badge_class': 'bg-label-warning'
        }
    ]


def _build_seller_breakdown_cards(aggregates):
    return [
        {
            'label': 'Ready for release',
            'amount': _format_currency(aggregates.get('completed_payout')),
            'caption': f"{aggregates.get('completed_orders', 0):,} items completed",
            'badge_class': 'bg-label-success'
        },
        {
            'label': 'Processing balance',
            'amount': _format_currency(aggregates.get('processing_revenue')),
            'caption': f"{aggregates.get('processing_orders', 0):,} items in queue",
            'badge_class': 'bg-label-info'
        },
        {
            'label': 'Cancelled value',
            'amount': _format_currency(aggregates.get('cancelled_revenue')),
            'caption': f"{aggregates.get('cancelled_orders', 0):,} items cancelled",
            'badge_class': 'bg-label-danger'
        }
    ]


def _get_rider_transactions(user_id):
    query = """
        SELECT 
            os.reference, os.status, os.pickup_status, os.shipping_fee, os.tax_amount, os.updated_at, os.suborder_id,
            (SELECT amount FROM wallet_ledger wl WHERE wl.user_id = %s AND wl.wallet_role = 'rider' AND wl.entry_kind = 'rider_commission_delivery' AND wl.reference_id = os.suborder_id LIMIT 1) AS actual_commission
        FROM order_suborders os
        WHERE os.pickup_rider_id = %s
        ORDER BY os.updated_at DESC
        LIMIT 10
    """
    rows = executeGet(query, (user_id, user_id)) or []
    transactions = []
    for row in rows:
        pickup_status = row.get('pickup_status') or 0
        actual_commission = row.get('actual_commission')
        if actual_commission is not None:
            commission = float(actual_commission)
            label = 'Credited commission'
        else:
            commission = calculate_rider_commission_amount(row.get('shipping_fee'), row.get('tax_amount'))
            label = 'Projected commission' if pickup_status in (2, 3) else 'Queued commission'
            
        transactions.append({
            'reference': row.get('reference'),
            'label': label,
            'amount': _format_currency(commission),
            'status_text': PICKUP_STATUS_LABELS.get(pickup_status, 'Pending'),
            'badge_class': PICKUP_BADGE_CLASSES.get(pickup_status, 'bg-label-secondary'),
            'timestamp': _format_datetime(row.get('updated_at')),
        })
    return transactions


def _get_seller_transactions(user_id):
    query = """
        SELECT
            COALESCE(oi.reference, os.reference) AS reference,
            oi.status,
            COALESCE(p.price, 0) * GREATEST(COALESCE(oi.quantity, 0), 0) AS line_total,
            os.updated_at
        FROM order_items oi
        INNER JOIN order_suborders os ON os.suborder_id = oi.suborder_id
        LEFT JOIN products p ON p.product_id = oi.product_id
        WHERE os.seller_id = %s
        ORDER BY os.updated_at DESC, oi.order_items_id DESC
        LIMIT 10
    """
    rows = executeGet(query, (user_id,)) or []
    transactions = []
    for row in rows:
        status = row.get('status') or 1
        transactions.append({
            'reference': row.get('reference'),
            'label': 'Order item',
            'amount': _format_currency(row.get('line_total')),
            'status_text': ORDER_STATUS_LABELS.get(status, 'Processing'),
            'badge_class': ORDER_BADGE_CLASSES.get(status, 'bg-label-secondary'),
            'timestamp': _format_datetime(row.get('updated_at')),
        })
    return transactions


def _format_currency(value):
    amount = _safe_number(value)
    return f"₱{amount:,.2f}"


def _safe_number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _format_datetime(value):
    if not value:
        return ''
    if isinstance(value, datetime):
        dt_value = value
    else:
        value_str = str(value).split('.')[0]
        try:
            dt_value = datetime.strptime(value_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return str(value)
    return dt_value.strftime("%b %d, %Y %I:%M %p")
