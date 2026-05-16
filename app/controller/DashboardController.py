from datetime import datetime, timedelta
from flask import render_template, g, redirect, url_for
from helpers.QueryHelpers import executeGet
from helpers.wallet_finance import rider_earnings_snapshot, calculate_rider_commission_amount

ORDER_STATUS_BADGES = {
    1: ('Order Placed', 'bg-label-secondary'),
    2: ('Preparing', 'bg-label-info'),
    3: ('Out for Delivery', 'bg-label-primary'),
    4: ('Delivered', 'bg-label-success'),
    5: ('Cancelled', 'bg-label-danger'),
    6: ('Completed', 'bg-label-success'),
    7: ('Completed', 'bg-label-success'),
    8: ('On Hold', 'bg-label-warning'),
}

PICKUP_STATUS_BADGES = {
    0: ('Pending', 'bg-label-secondary'),
    1: ('Awaiting Pickup', 'bg-label-warning'),
    2: ('Claimed', 'bg-label-info'),
    3: ('In Transit', 'bg-label-primary'),
    4: ('Delivered', 'bg-label-success'),
}


def dashboardIndex():
    if not g.authenticated:
        return redirect(url_for('login_page'))

    role_id = g.authenticated.get('role_id')
    user_id = g.authenticated.get('user_id')
    user_name = g.authenticated.get('firstname') or 'there'

    if role_id == 1:
        context = _build_admin_context()
    elif role_id == 4:
        context = _build_rider_context(user_id)
    else:
        context = _build_seller_context(user_id)

    context.update({
        'role_id': role_id,
        'user_name': user_name,
    })

    active_menu = ['dashboard', 'analytics']
    return render_template('views/dashboard/index.html', menu=active_menu, **context)


def _build_admin_context():
    counts = (executeGet("""
        SELECT 
            COUNT(*) AS total_users,
            SUM(role_id = 3) AS sellers,
            SUM(role_id = 4) AS riders,
            SUM(role_id = 2) AS buyers
        FROM users
        WHERE status = 1
    """) or [{}])[0]

    summary = (executeGet("""
        SELECT
            COUNT(*) AS total_suborders,
            COALESCE(SUM(total_amount), 0) AS gross_merchandise,
            SUM(CASE WHEN status IN (1,2,3) THEN 1 ELSE 0 END) AS processing_orders,
            SUM(CASE WHEN status IN (4,6,7) THEN 1 ELSE 0 END) AS completed_orders,
            SUM(CASE WHEN status IN (5,8) THEN 1 ELSE 0 END) AS cancelled_orders
        FROM order_suborders
    """) or [{}])[0]

    today = (executeGet("""
        SELECT
            COUNT(*) AS orders_today,
            COALESCE(SUM(CAST(total_amount AS DECIMAL(12,2))), 0) AS revenue_today
        FROM orders
        WHERE created_at >= NOW() - INTERVAL 1 DAY
    """) or [{}])[0]

    recent_orders = executeGet("""
        SELECT 
            o.reference,
            o.total_amount,
            o.created_at,
            CONCAT(COALESCE(u.firstname, ''), ' ', COALESCE(u.lastname, '')) AS customer_name,
            MIN(os.status) AS sub_status
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.user_id
        LEFT JOIN order_suborders os ON os.order_id = o.order_id
        ORDER BY o.created_at DESC
        LIMIT 6
    """) or []

    top_sellers = executeGet("""
        SELECT 
            COALESCE(sd.store_name, CONCAT('Seller ', u.firstname)) AS store_name,
            COUNT(os.suborder_id) AS order_count,
            COALESCE(SUM(os.total_amount), 0) AS revenue
        FROM order_suborders os
        LEFT JOIN seller_details sd ON sd.user_id = os.seller_id
        LEFT JOIN users u ON u.user_id = os.seller_id
        GROUP BY os.seller_id
        ORDER BY revenue DESC
        LIMIT 4
    """) or []

    recent_users = executeGet("""
        SELECT firstname, lastname, role_id, created_at
        FROM users
        ORDER BY created_at DESC
        LIMIT 5
    """) or []

    stat_cards = [
        {
            'label': 'Active users',
            'value': f"{_safe_int(counts.get('total_users')):,}",
            'helper': 'Verified marketplace members',
            'icon': 'bx bxs-user-check',
            'trend': f"+{_safe_int(today.get('orders_today'))} orders today",
            'trend_class': 'text-success'
        },
        {
            'label': 'Sellers online',
            'value': f"{_safe_int(counts.get('sellers')):,}",
            'helper': 'Approved storefronts',
            'icon': 'bx bxs-store',
            'trend': 'Stable',
            'trend_class': 'text-muted'
        },
        {
            'label': 'Active riders',
            'value': f"{_safe_int(counts.get('riders')):,}",
            'helper': 'Cleared for pickups',
            'icon': 'bx bxs-bolt',
            'trend': 'Fleet ready',
            'trend_class': 'text-primary'
        },
        {
            'label': 'GMV today',
            'value': _format_currency(today.get('revenue_today')),
            'helper': f"{_safe_int(today.get('orders_today'))} orders in last 24h",
            'icon': 'bx bxs-credit-card',
            'trend': 'Live',
            'trend_class': 'text-success'
        },
    ]

    total_orders = max(_safe_int(summary.get('total_suborders')), 1)
    progress_cards = [
        {
            'label': 'Completed orders',
            'amount': f"{_safe_int(summary.get('completed_orders')):,}",
            'caption': _percent(summary.get('completed_orders'), total_orders),
            'badge_class': 'bg-label-success'
        },
        {
            'label': 'In progress',
            'amount': f"{_safe_int(summary.get('processing_orders')):,}",
            'caption': _percent(summary.get('processing_orders'), total_orders),
            'badge_class': 'bg-label-info'
        },
        {
            'label': 'Cancelled',
            'amount': f"{_safe_int(summary.get('cancelled_orders')):,}",
            'caption': _percent(summary.get('cancelled_orders'), total_orders),
            'badge_class': 'bg-label-danger'
        },
    ]

    table = {
        'title': 'Recent marketplace orders',
        'columns': [
            {'key': 'reference', 'label': 'Order Ref'},
            {'key': 'customer', 'label': 'Customer'},
            {'key': 'amount', 'label': 'Amount'},
            {'key': 'status', 'label': 'Status'},
            {'key': 'created_at', 'label': 'Created'},
        ],
        'rows': [
            {
                'reference': row.get('reference'),
                'customer': row.get('customer_name').strip() or 'Guest',
                'amount': _format_currency(row.get('total_amount')),
                'status': _status_badge(row.get('sub_status'), ORDER_STATUS_BADGES),
                'created_at': _format_datetime(row.get('created_at')),
            } for row in recent_orders
        ],
        'empty_text': 'No orders have been placed yet.'
    }

    spotlight_cards = [
        {
            'title': 'Top sellers by revenue',
            'items': [
                {
                    'primary': seller.get('store_name') or 'Seller',
                    'secondary': _format_currency(seller.get('revenue')),
                    'meta': f"{_safe_int(seller.get('order_count')):,} orders"
                } for seller in top_sellers
            ]
        }
    ]

    feed_items = [
        {
            'title': f"New { _role_label(user.get('role_id')) }",
            'subtitle': f"{user.get('firstname', '')} {user.get('lastname', '')}".strip() or 'Unnamed user',
            'timestamp': _format_datetime(user.get('created_at'))
        } for user in recent_users
    ]

    hero = {
        'eyebrow': 'Platform health',
        'title': 'Operational overview',
        'subtitle': 'Monitor buyers, sellers, and riders from one command center.',
        'meta_label': 'Lifetime GMV',
        'meta_value': _format_currency(summary.get('gross_merchandise')),
        'cta_label': 'View orders',
        'cta_href': '/order-list'
    }

    return {
        'hero': hero,
        'stat_cards': stat_cards,
        'progress_cards': progress_cards,
        'table': table,
        'spotlight_cards': spotlight_cards,
        'feed_items': feed_items,
    }


def _build_seller_context(user_id):
    store = (executeGet("""
        SELECT store_name
        FROM seller_details
        WHERE user_id = %s
        LIMIT 1
    """, (user_id,)) or [{}])[0]

    aggregates = (executeGet("""
        SELECT
            COUNT(*) AS total_orders,
            SUM(total_amount) AS total_revenue,
            SUM(CASE WHEN status IN (4,6,7) THEN 1 ELSE 0 END) AS completed_orders,
            SUM(CASE WHEN status IN (1,2,3) THEN 1 ELSE 0 END) AS processing_orders,
            SUM(CASE WHEN status IN (5,8) THEN 1 ELSE 0 END) AS cancelled_orders,
            SUM(CASE WHEN status IN (4,6,7) THEN total_amount ELSE 0 END) AS completed_revenue,
            SUM(CASE WHEN status IN (1,2,3) THEN total_amount ELSE 0 END) AS processing_revenue,
            SUM(CASE WHEN status IN (5,8) THEN total_amount ELSE 0 END) AS cancelled_revenue
        FROM order_suborders
        WHERE seller_id = %s
    """, (user_id,)) or [{}])[0]

    products_snapshot = (executeGet("""
        SELECT 
            COUNT(*) AS live_products,
            COALESCE(SUM(qty), 0) AS total_inventory
        FROM products
        WHERE user_id = %s AND status = 1
    """, (user_id,)) or [{}])[0]

    low_stock = executeGet("""
        SELECT product_name, qty, status
        FROM products
        WHERE user_id = %s
        ORDER BY qty ASC, updated_at DESC
        LIMIT 5
    """, (user_id,)) or []

    recent_orders = executeGet("""
        SELECT 
            os.reference,
            os.total_amount,
            os.status,
            os.updated_at,
            o.reference AS master_reference,
            CONCAT(COALESCE(u.firstname, ''), ' ', COALESCE(u.lastname, '')) AS buyer_name,
            (
                SELECT COALESCE(SUM(quantity), 0)
                FROM order_items oi
                WHERE oi.suborder_id = os.suborder_id
            ) AS item_count
        FROM order_suborders os
        JOIN orders o ON o.order_id = os.order_id
        LEFT JOIN users u ON o.user_id = u.user_id
        WHERE os.seller_id = %s
        ORDER BY os.updated_at DESC
        LIMIT 6
    """, (user_id,)) or []

    notifications = executeGet("""
        SELECT title, message, created_at
        FROM notifications
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 5
    """, (user_id,)) or []

    stat_cards = [
        {
            'label': 'Orders received',
            'value': f"{_safe_int(aggregates.get('total_orders')):,}",
            'helper': 'All-time sub-orders',
            'icon': 'bx bxs-package'
        },
        {
            'label': 'In progress',
            'value': f"{_safe_int(aggregates.get('processing_orders')):,}",
            'helper': 'Awaiting fulfillment',
            'icon': 'bx bxs-hourglass'
        },
        {
            'label': 'Completed',
            'value': f"{_safe_int(aggregates.get('completed_orders')):,}",
            'helper': 'Delivered or settled',
            'icon': 'bx bxs-check-circle'
        },
        {
            'label': 'Gross revenue',
            'value': _format_currency(aggregates.get('total_revenue')),
            'helper': 'Including shipping & tax',
            'icon': 'bx bxs-bar-chart-alt-2'
        },
    ]

    total_orders = max(_safe_int(aggregates.get('total_orders')), 1)
    progress_cards = [
        {
            'label': 'Ready for release',
            'amount': _format_currency(aggregates.get('completed_revenue')),
            'caption': _percent(aggregates.get('completed_orders'), total_orders),
            'badge_class': 'bg-label-success'
        },
        {
            'label': 'Processing balance',
            'amount': _format_currency(aggregates.get('processing_revenue')),
            'caption': _percent(aggregates.get('processing_orders'), total_orders),
            'badge_class': 'bg-label-info'
        },
        {
            'label': 'Cancelled value',
            'amount': _format_currency(aggregates.get('cancelled_revenue')),
            'caption': _percent(aggregates.get('cancelled_orders'), total_orders),
            'badge_class': 'bg-label-danger'
        },
    ]

    table = {
        'title': 'Recent orders routed to you',
        'columns': [
            {'key': 'reference', 'label': 'Sub-order'},
            {'key': 'customer', 'label': 'Buyer'},
            {'key': 'items', 'label': 'Items'},
            {'key': 'amount', 'label': 'Amount'},
            {'key': 'status', 'label': 'Status'},
            {'key': 'created_at', 'label': 'Updated'},
        ],
        'rows': [
            {
                'reference': row.get('reference'),
                'customer': row.get('buyer_name').strip() or 'Customer',
                'items': f"{_safe_int(row.get('item_count'))} item(s)",
                'amount': _format_currency(row.get('total_amount')),
                'status': _status_badge(row.get('status'), ORDER_STATUS_BADGES),
                'created_at': _format_datetime(row.get('updated_at')),
            } for row in recent_orders
        ],
        'empty_text': 'No orders yet.'
    }

    spotlight_cards = [
        {
            'title': 'Inventory watchlist',
            'items': [
                {
                    'primary': product.get('product_name'),
                    'secondary': f"{_safe_int(product.get('qty'))} pcs left",
                    'meta': 'Active' if product.get('status') == 1 else 'Inactive'
                } for product in low_stock
            ]
        },
        {
            'title': 'Catalog health',
            'items': [
                {
                    'primary': 'Live listings',
                    'secondary': f"{_safe_int(products_snapshot.get('live_products')):,}",
                    'meta': 'Approved products'
                },
                {
                    'primary': 'Total inventory',
                    'secondary': f"{_safe_int(products_snapshot.get('total_inventory')):,} units",
                    'meta': 'Across all live SKUs'
                }
            ]
        }
    ]

    feed_items = [
        {
            'title': note.get('title'),
            'subtitle': note.get('message'),
            'timestamp': _format_datetime(note.get('created_at'))
        } for note in notifications
    ]

    hero = {
        'eyebrow': 'Store performance',
        'title': f"{store.get('store_name') or 'Your store'} at a glance",
        'subtitle': 'See orders, balances, and catalog health in real time.',
        'meta_label': 'Ready for release',
        'meta_value': _format_currency(aggregates.get('completed_revenue')),
        'cta_label': 'Manage products',
        'cta_href': '/product'
    }

    return {
        'hero': hero,
        'stat_cards': stat_cards,
        'progress_cards': progress_cards,
        'table': table,
        'spotlight_cards': spotlight_cards,
        'feed_items': feed_items,
    }


def _build_rider_context(user_id):
    aggregates = rider_earnings_snapshot(user_id)

    assigned_suborders = executeGet("""
        SELECT 
            os.suborder_id,
            os.reference,
            os.shipping_fee,
            os.subtotal,
            os.pickup_status,
            os.updated_at,
            COALESCE(sd.store_name, 'Seller') AS store_name,
            (
                SELECT wl.amount
                FROM wallet_ledger wl
                WHERE wl.user_id = %s
                  AND wl.wallet_role = 'rider'
                  AND wl.entry_kind = 'rider_commission_delivery'
                  AND wl.reference_id = os.suborder_id
                LIMIT 1
            ) AS actual_commission
        FROM order_suborders os
        LEFT JOIN seller_details sd ON sd.user_id = os.seller_id
        WHERE os.pickup_rider_id = %s
        ORDER BY os.updated_at DESC
        LIMIT 6
    """, (user_id, user_id)) or []

    available_pickups = executeGet("""
        SELECT 
            os.suborder_id,
            os.reference,
            os.shipping_fee,
            os.subtotal,
            os.updated_at,
            COALESCE(sd.store_name, 'Seller') AS store_name
        FROM order_suborders os
        LEFT JOIN seller_details sd ON sd.user_id = os.seller_id
        WHERE os.pickup_status = 1
          AND (os.pickup_rider_id IS NULL OR os.pickup_rider_id = 0)
        ORDER BY os.updated_at DESC
        LIMIT 4
    """) or []

    notifications = executeGet("""
        SELECT title, message, created_at
        FROM notifications
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 5
    """, (user_id,)) or []

    stat_cards = [
        {
            'label': 'Total assignments',
            'value': f"{_safe_int(aggregates.get('total_trips')):,}",
            'helper': 'All-time linked drops',
            'icon': 'bx bxs-map'
        },
        {
            'label': 'Awaiting pickup',
            'value': f"{_safe_int(aggregates.get('awaiting_trips')):,}",
            'helper': 'Queue at hub',
            'icon': 'bx bxs-package'
        },
        {
            'label': 'In transit',
            'value': f"{_safe_int(aggregates.get('in_transit_trips')):,}",
            'helper': 'Currently on the road',
            'icon': 'bx bxs-truck'
        },
        {
            'label': 'Lifetime earnings',
            'value': _format_currency(aggregates.get('total_fee')),
            'helper': 'Credited plus projected rider commissions',
            'icon': 'bx bxs-wallet',
            'trend': f"Available {_format_currency(aggregates.get('available_balance'))}",
            'trend_class': 'text-success'
        },
    ]

    total_trips = max(_safe_int(aggregates.get('total_trips')), 1)
    progress_cards = [
        {
            'label': 'Completed payouts',
            'amount': _format_currency(aggregates.get('completed_fee')),
            'caption': _percent(aggregates.get('completed_trips'), total_trips),
            'badge_class': 'bg-label-success'
        },
        {
            'label': 'In-transit earnings',
            'amount': _format_currency(aggregates.get('in_transit_fee')),
            'caption': _percent(aggregates.get('in_transit_trips'), total_trips),
            'badge_class': 'bg-label-info'
        },
        {
            'label': 'Awaiting pickup',
            'amount': _format_currency(aggregates.get('awaiting_fee')),
            'caption': _percent(aggregates.get('awaiting_trips'), total_trips),
            'badge_class': 'bg-label-warning'
        },
    ]

    table = {
        'title': 'Assigned deliveries',
        'columns': [
            {'key': 'reference', 'label': 'Sub-order'},
            {'key': 'customer', 'label': 'Store'},
            {'key': 'amount', 'label': 'Earnings'},
            {'key': 'status', 'label': 'Status'},
            {'key': 'created_at', 'label': 'Updated'},
        ],
        'rows': [
            {
                'reference': row.get('reference'),
                'customer': row.get('store_name'),
                'amount': _format_currency(row.get('actual_commission') if row.get('actual_commission') is not None else calculate_rider_commission_amount(row.get('shipping_fee'), row.get('subtotal'))),
                'status': _status_badge(row.get('pickup_status'), PICKUP_STATUS_BADGES),
                'created_at': _format_datetime(row.get('updated_at')),
            } for row in assigned_suborders
        ],
        'empty_text': 'No deliveries assigned yet.'
    }

    spotlight_cards = [
        {
            'title': 'Available pickups',
            'items': [
                {
                    'primary': pickup.get('store_name'),
                    'secondary': _format_currency(calculate_rider_commission_amount(pickup.get('shipping_fee'), pickup.get('subtotal'))),
                    'meta': _format_datetime(pickup.get('updated_at'))
                } for pickup in available_pickups
            ]
        }
    ]

    feed_items = [
        {
            'title': note.get('title'),
            'subtitle': note.get('message'),
            'timestamp': _format_datetime(note.get('created_at'))
        } for note in notifications
    ]

    hero = {
        'eyebrow': 'Delivery ops',
        'title': 'Trips, fees, and pickups in one view',
        'subtitle': 'Track what is waiting, in transit, and already delivered.',
        'meta_label': 'Projected total earnings',
        'meta_value': _format_currency(aggregates.get('total_fee')),
        'cta_label': 'Go to earnings',
        'cta_href': '/rider-earnings'
    }

    return {
        'hero': hero,
        'stat_cards': stat_cards,
        'progress_cards': progress_cards,
        'table': table,
        'spotlight_cards': spotlight_cards,
        'feed_items': feed_items,
    }


def _safe_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _format_currency(value):
    amount = _safe_number(value)
    return f"₱{amount:,.2f}"


def _format_datetime(value):
    if not value:
        return '—'
    if isinstance(value, datetime):
        dt = value
    else:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                dt = datetime.strptime(str(value), fmt)
                break
            except ValueError:
                dt = None
        if dt is None:
            return str(value)
    return dt.strftime("%b %d, %Y · %I:%M %p")


def _status_badge(status, mapping):
    label, klass = mapping.get(int(status) if status is not None else -1, ('Processing', 'bg-label-info'))
    return {'label': label, 'class': klass}


def _percent(part, total):
    part_value = _safe_number(part)
    total_value = max(_safe_number(total), 1)
    return f"{(part_value / total_value) * 100:,.1f}%"


def _role_label(role_id):
    return {
        1: 'Admin',
        2: 'Buyer',
        3: 'Seller',
        4: 'Rider'
    }.get(role_id, 'User')