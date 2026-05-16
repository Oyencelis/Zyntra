from datetime import datetime
# pyrefly: ignore [missing-import]
from flask import render_template, g, redirect, url_for
from helpers.QueryHelpers import executeGet
from helpers.wallet_finance import available_balance, pending_withdrawal_total

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
            "meta_label": "Total shipping earnings to date",
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
    from helpers.wallet_finance import get_float_setting
    ship_pct = get_float_setting("rider_commission_pct_of_shipping", 70.0) / 100.0
    prod_pct = get_float_setting("rider_commission_pct_of_product", 5.0) / 100.0

    # Query for pending / active trips
    query_active = """
        SELECT
            COUNT(*) AS total_trips,
            SUM(CASE WHEN pickup_status IN (2, 3) THEN (shipping_fee * %s) + (subtotal * %s) ELSE 0 END) AS in_transit_fee,
            SUM(CASE WHEN pickup_status IN (0, 1) THEN (shipping_fee * %s) + (subtotal * %s) ELSE 0 END) AS awaiting_fee,
            SUM(CASE WHEN pickup_status IN (2, 3) THEN 1 ELSE 0 END) AS in_transit_trips,
            SUM(CASE WHEN pickup_status IN (0, 1) THEN 1 ELSE 0 END) AS awaiting_trips,
            SUM(CASE WHEN pickup_status = 4 THEN 1 ELSE 0 END) AS completed_trips
        FROM order_suborders
        WHERE pickup_rider_id = %s
    """
    rows_active = executeGet(query_active, (ship_pct, prod_pct, ship_pct, prod_pct, user_id))
    active = rows_active[0] if rows_active else {}
    
    # Query for completed commission from wallet ledger
    query_completed = """
        SELECT COALESCE(SUM(amount), 0) AS completed_fee
        FROM wallet_ledger
        WHERE user_id = %s AND wallet_role = 'rider' AND entry_kind = 'rider_commission_delivery'
    """
    rows_completed = executeGet(query_completed, (user_id,))
    completed_fee = float(rows_completed[0]['completed_fee']) if rows_completed else 0.0

    total_trips = _safe_int(active.get('total_trips'))
    completed_trips = _safe_int(active.get('completed_trips'))
    in_transit_trips = _safe_int(active.get('in_transit_trips'))
    awaiting_trips = _safe_int(active.get('awaiting_trips'))
    
    in_transit_fee = _safe_number(active.get('in_transit_fee'))
    awaiting_fee = _safe_number(active.get('awaiting_fee'))
    total_fee = completed_fee + in_transit_fee + awaiting_fee

    return {
        'total_trips': total_trips,
        'total_fee': total_fee,
        'completed_fee': completed_fee,
        'in_transit_fee': in_transit_fee,
        'awaiting_fee': awaiting_fee,
        'completed_trips': completed_trips,
        'in_transit_trips': in_transit_trips,
        'awaiting_trips': awaiting_trips,
    }


def _get_seller_aggregates(user_id):
    query = """
        SELECT
            COUNT(*) AS total_orders,
            SUM(total_amount) AS total_revenue,
            SUM(CASE WHEN status IN (4, 6, 7) THEN total_amount ELSE 0 END) AS completed_revenue,
            SUM(CASE WHEN status IN (1, 2, 3) THEN total_amount ELSE 0 END) AS processing_revenue,
            SUM(CASE WHEN status IN (5, 8) THEN total_amount ELSE 0 END) AS cancelled_revenue,
            SUM(CASE WHEN status IN (4, 6, 7) THEN 1 ELSE 0 END) AS completed_orders,
            SUM(CASE WHEN status IN (1, 2, 3) THEN 1 ELSE 0 END) AS processing_orders,
            SUM(CASE WHEN status IN (5, 8) THEN 1 ELSE 0 END) AS cancelled_orders
        FROM order_suborders
        WHERE seller_id = %s
    """
    rows = executeGet(query, (user_id,)) or []
    row = rows[0] if rows else {}
    total_orders = _safe_int(row.get('total_orders'))
    completed_orders = _safe_int(row.get('completed_orders'))
    processing_orders = _safe_int(row.get('processing_orders'))
    cancelled_orders = _safe_int(row.get('cancelled_orders'))
    processed_count = completed_orders + processing_orders + cancelled_orders
    remaining_orders = max(total_orders - processed_count, 0)

    total_revenue = _safe_number(row.get('total_revenue'))
    completed_revenue = _safe_number(row.get('completed_revenue'))
    processing_revenue = _safe_number(row.get('processing_revenue'))
    cancelled_revenue = _safe_number(row.get('cancelled_revenue'))
    accounted_revenue = completed_revenue + processing_revenue + cancelled_revenue
    remaining_revenue = max(total_revenue - accounted_revenue, 0.0)

    return {
        'total_orders': total_orders,
        'completed_orders': completed_orders,
        'processing_orders': processing_orders,
        'cancelled_orders': cancelled_orders,
        'remaining_orders': remaining_orders,
        'total_revenue': total_revenue,
        'completed_revenue': completed_revenue,
        'processing_revenue': processing_revenue,
        'cancelled_revenue': cancelled_revenue,
        'remaining_revenue': remaining_revenue,
    }


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
            'helper': 'Shipping fees assigned to you'
        }
    ]


def _build_seller_summary_cards(aggregates):
    return [
        {
            'label': 'Orders Received',
            'value': f"{aggregates.get('total_orders', 0):,}",
            'helper': 'Sub-orders routed to your store'
        },
        {
            'label': 'Completed Orders',
            'value': f"{aggregates.get('completed_orders', 0):,}",
            'helper': 'Released or settled orders'
        },
        {
            'label': 'Orders in Progress',
            'value': f"{aggregates.get('processing_orders', 0):,}",
            'helper': 'Awaiting fulfillment or delivery'
        },
        {
            'label': 'Gross Sales',
            'value': _format_currency(aggregates.get('total_revenue')),
            'helper': 'Including shipping and tax components'
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
            'caption': f"{aggregates.get('awaiting_trips', 0):,} drops queued",
            'badge_class': 'bg-label-warning'
        }
    ]


def _build_seller_breakdown_cards(aggregates):
    return [
        {
            'label': 'Ready for release',
            'amount': _format_currency(aggregates.get('completed_revenue')),
            'caption': f"{aggregates.get('completed_orders', 0):,} orders completed",
            'badge_class': 'bg-label-success'
        },
        {
            'label': 'Processing balance',
            'amount': _format_currency(aggregates.get('processing_revenue')),
            'caption': f"{aggregates.get('processing_orders', 0):,} orders in queue",
            'badge_class': 'bg-label-info'
        },
        {
            'label': 'Cancelled value',
            'amount': _format_currency(aggregates.get('cancelled_revenue')),
            'caption': f"{aggregates.get('cancelled_orders', 0):,} orders cancelled",
            'badge_class': 'bg-label-danger'
        }
    ]


def _get_rider_transactions(user_id):
    from helpers.wallet_finance import get_float_setting
    ship_pct = get_float_setting("rider_commission_pct_of_shipping", 70.0) / 100.0
    prod_pct = get_float_setting("rider_commission_pct_of_product", 5.0) / 100.0

    query = """
        SELECT 
            os.reference, os.status, os.pickup_status, os.shipping_fee, os.subtotal, os.updated_at, os.suborder_id,
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
        else:
            shipping = float(row.get('shipping_fee') or 0)
            subtotal = float(row.get('subtotal') or 0)
            commission = max(0.0, (shipping * ship_pct) + (subtotal * prod_pct))
            
        transactions.append({
            'reference': row.get('reference'),
            'label': 'Delivery Commission',
            'amount': _format_currency(commission),
            'status_text': PICKUP_STATUS_LABELS.get(pickup_status, 'Pending'),
            'badge_class': PICKUP_BADGE_CLASSES.get(pickup_status, 'bg-label-secondary'),
            'timestamp': _format_datetime(row.get('updated_at')),
        })
    return transactions


def _get_seller_transactions(user_id):
    query = """
        SELECT reference, status, total_amount, updated_at
        FROM order_suborders
        WHERE seller_id = %s
        ORDER BY updated_at DESC
        LIMIT 10
    """
    rows = executeGet(query, (user_id,)) or []
    transactions = []
    for row in rows:
        status = row.get('status') or 1
        transactions.append({
            'reference': row.get('reference'),
            'label': 'Order',
            'amount': _format_currency(row.get('total_amount')),
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
