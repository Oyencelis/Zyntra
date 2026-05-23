def notify_riders_pickup_available(suborder_id):
    if not suborder_id:
        return

    suborder_query = """
        SELECT os.order_id, os.reference AS sub_reference, o.reference AS order_reference
        FROM order_suborders os
        JOIN orders o ON os.order_id = o.order_id
        WHERE os.suborder_id = %s
        LIMIT 1
    """

    suborder_result = executeGet(suborder_query, (suborder_id,))
    if not suborder_result:
        return

    suborder = suborder_result[0]
    order_id = suborder.get('order_id')
    sub_reference = suborder.get('sub_reference') or suborder.get('order_reference')

    riders_query = """
        SELECT dp.user_id
        FROM delivery_partners dp
        JOIN users u ON dp.user_id = u.user_id
        WHERE dp.status = 1 AND u.status = 1
    """

    riders = executeGet(riders_query)
    if not riders:
        return

    insert_query = """
        INSERT INTO notifications (user_id, order_id, title, message, notification_type, is_read, created_at)
        VALUES (%s, %s, %s, %s, 'system', 0, NOW())
    """

    title = 'Pickup Available'
    message = f'Sub-order {sub_reference} is ready for pickup.' if sub_reference else 'A sub-order is ready for pickup.'

    for rider in riders:
        executePost(insert_query, (rider.get('user_id'), order_id, title, message))

from datetime import datetime, timedelta
# pyrefly: ignore [missing-import]
from flask import render_template, request, session, g, url_for, redirect
from helpers.QueryHelpers import executeGet, executePost, changeStatus
from helpers.HelperFunction import responseData, allowed_image_file, generate_random_filename, generate_random_string, init_app_locale
from helpers.SupabaseStorage import resolve_storage_url
from helpers.marketplace_settings import get_float_setting
from helpers.shipping_pricing import estimate_shipping_for_seller_group
from controller.UserController import getSellers
from middleware.auth import login_required
import json
import locale
import os
import re

init_app_locale()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PH_JSON_DIR = os.path.join(BASE_DIR, 'static', 'ph-json')
LOCATION_CACHE = {}

def build_product_image_url(attachment):
    if not attachment or attachment in ('no-image.jpg', ''):
        return '/static/images/no-image.jpg'

    if isinstance(attachment, str):
        attachment = attachment.strip()
        if attachment.startswith(('http://', 'https://')):
            return resolve_storage_url(attachment) or attachment

        url_match = re.search(r'https?://[^\s\'\"]+', attachment)
        if url_match:
            extracted_url = url_match.group(0)
            return resolve_storage_url(extracted_url) or extracted_url

    clean_path = attachment.replace('\\', '/').lstrip('/')
    if clean_path.startswith('static/'):
        return '/' + clean_path if not clean_path.startswith('/') else clean_path

    if clean_path.startswith('uploads/'):
        return f"/static/{clean_path}"

    if clean_path.startswith('products/'):
        return f"/static/uploads/{clean_path}"

    return f"/static/uploads/products/{clean_path}"

def build_delivery_proof_image_url(image_path):
    if not image_path:
        return None

    if not isinstance(image_path, str):
        image_path = str(image_path)

    image_path = image_path.strip()
    if not image_path:
        return None

    if image_path.startswith(('http://', 'https://')):
        return resolve_storage_url(image_path) or image_path

    clean_path = image_path.replace('\\', '/').lstrip('/')
    if clean_path.startswith('static/'):
        return '/' + clean_path

    if clean_path.startswith('uploads/'):
        return f"/static/{clean_path}"

    if clean_path.startswith('delivery_proofs/'):
        bucket_name = os.environ.get('SUPABASE_STORAGE_BUCKET', 'zyntra-uploads')
        storage_path = f"{bucket_name}/{clean_path}"
        return resolve_storage_url(storage_path, bucket_name=bucket_name) or f"/static/uploads/{clean_path}"

    bucket_name = os.environ.get('SUPABASE_STORAGE_BUCKET', 'zyntra-uploads')
    return resolve_storage_url(clean_path, bucket_name=bucket_name) or image_path

def load_location_cache(filename, code_key, name_key):
    cache_key = filename
    if cache_key not in LOCATION_CACHE:
        file_path = os.path.join(PH_JSON_DIR, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                LOCATION_CACHE[cache_key] = {
                    str(entry.get(code_key)): entry.get(name_key)
                    for entry in data
                    if entry.get(code_key) and entry.get(name_key)
                }
        except Exception as e:
            print(f"Unable to load {filename}: {e}")
            LOCATION_CACHE[cache_key] = {}
    return LOCATION_CACHE[cache_key]

def resolve_location_name(value, filename, code_key, name_key):
    if not value:
        return value
    cache = load_location_cache(filename, code_key, name_key)
    return cache.get(str(value), value)

def get_user_address_details(user_id):
    address_query = """
        SELECT floor_unit_number, region, province, city_municipality, barangay, street, other_notes
        FROM addresses
        WHERE user_id = %s
        ORDER BY updated_at DESC
        LIMIT 1
    """
    address_result = executeGet(address_query, (user_id,))
    user_address = address_result[0] if address_result else None
    formatted_address = None
    address_texts = {}

    if user_address:
        region_display = resolve_location_name(user_address.get('region'), 'region.json', 'region_code', 'region_name') or user_address.get('region')
        province_display = resolve_location_name(user_address.get('province'), 'province.json', 'province_code', 'province_name') or user_address.get('province')
        city_display = resolve_location_name(user_address.get('city_municipality'), 'city.json', 'city_code', 'city_name') or user_address.get('city_municipality')
        barangay_display = resolve_location_name(user_address.get('barangay'), 'barangay.json', 'brgy_code', 'brgy_name') or user_address.get('barangay')

        address_components = [
            user_address.get('floor_unit_number'),
            user_address.get('street'),
            barangay_display,
            city_display,
            province_display,
            region_display
        ]
        formatted_address = ", ".join([component for component in address_components if component])
        address_texts = {
            'region': region_display,
            'province': province_display,
            'city': city_display,
            'barangay': barangay_display
        }

    return user_address, formatted_address, address_texts

def prepare_address_for_shipping(user_address):
    if not user_address:
        return None

    shipping_address = dict(user_address)
    shipping_address['region'] = resolve_location_name(user_address.get('region'), 'region.json', 'region_code', 'region_name') or user_address.get('region')
    shipping_address['province'] = resolve_location_name(user_address.get('province'), 'province.json', 'province_code', 'province_name') or user_address.get('province')
    shipping_address['city_municipality'] = resolve_location_name(user_address.get('city_municipality'), 'city.json', 'city_code', 'city_name') or user_address.get('city_municipality')
    return shipping_address

def _scalar_result(query, params=()):
    rows = executeGet(query, params)
    if isinstance(rows, tuple):
        return {}
    if isinstance(rows, list) and rows:
        return rows[0] or {}
    return {}

def _tokenize_state(prefix, *parts):
    normalized = []
    for part in parts:
        if isinstance(part, datetime):
            normalized.append(part.isoformat())
        elif part is None:
            normalized.append('')
        else:
            normalized.append(str(part))
    return f"{prefix}:" + ':'.join(normalized)

def liveState():
    user = g.authenticated if g.authenticated else None
    if not user or not user.get('user_id'):
        return responseData(
            "success",
            "Live state fetched.",
            {
                'authenticated': False,
                'poll_interval_ms': 15000,
                'counts': {
                    'cart_count': 0,
                    'wishlist_count': 0,
                    'messages_unread_count': 0,
                    'notifications_unread_count': 0,
                },
                'tokens': {}
            },
            200
        )

    user_id = user.get('user_id')
    role_id = int(user.get('role_id') or 0)

    header_counts = _scalar_result(
        """
            SELECT
                (
                    SELECT COUNT(oi.order_items_id)
                    FROM order_items oi
                    WHERE oi.user_id = %s
                      AND oi.status = 1
                      AND (oi.reference = '' OR oi.reference IS NULL)
                ) AS item_count,
                (
                    SELECT COUNT(w.wishlist_id)
                    FROM wishlists w
                    WHERE w.user_id = %s
                ) AS wishlist_count,
                (
                    SELECT COUNT(*)
                    FROM conversation_messages cm
                    JOIN conversations c ON cm.conversation_id = c.conversation_id
                    WHERE cm.is_read = 0
                      AND (
                            (c.buyer_id = %s AND cm.sender_id != %s)
                         OR (c.seller_id = %s AND cm.sender_id != %s)
                      )
                ) AS unread_count
        """,
        (user_id, user_id, user_id, user_id, user_id, user_id)
    )

    notification_row = _scalar_result(
        """
            SELECT COUNT(*) FILTER (WHERE is_read = 0) AS unread_count,
                   MAX(created_at) AS latest_created_at,
                   MAX(notification_id) AS latest_id
            FROM notifications
            WHERE user_id = %s
        """,
        (user_id,)
    )

    message_row = _scalar_result(
        """
            SELECT
                COUNT(*) FILTER (
                    WHERE cm.is_read = 0
                      AND (
                            (c.buyer_id = %s AND cm.sender_id != %s)
                         OR (c.seller_id = %s AND cm.sender_id != %s)
                      )
                ) AS unread_count,
                MAX(cm.created_at) AS latest_message_at,
                MAX(cm.message_id) AS latest_message_id
            FROM conversation_messages cm
            JOIN conversations c ON cm.conversation_id = c.conversation_id
            WHERE c.buyer_id = %s OR c.seller_id = %s
        """,
        (user_id, user_id, user_id, user_id, user_id)
    )

    cart_row = _scalar_result(
        """
            SELECT COUNT(order_items_id) AS item_count,
                   COALESCE(SUM(quantity), 0) AS total_quantity,
                   MAX(order_items_id) AS latest_item_id
            FROM order_items
            WHERE user_id = %s
              AND status = 1
              AND (reference = '' OR reference IS NULL)
        """,
        (user_id,)
    )

    wishlist_row = _scalar_result(
        """
            SELECT COUNT(wishlist_id) AS item_count,
                   MAX(wishlist_id) AS latest_id
            FROM wishlists
            WHERE user_id = %s
        """,
        (user_id,)
    )

    buyer_order_row = _scalar_result(
        """
            SELECT COUNT(DISTINCT o.order_id) AS item_count,
                   MAX(COALESCE(os.updated_at, o.updated_at, o.created_at)) AS latest_updated_at,
                   MAX(os.suborder_id) AS latest_id
            FROM orders o
            LEFT JOIN order_suborders os ON os.order_id = o.order_id
            WHERE o.user_id = %s
        """,
        (user_id,)
    )

    seller_order_row = {}
    if role_id == 3:
        seller_order_row = _scalar_result(
            """
                SELECT COUNT(*) AS item_count,
                       MAX(updated_at) AS latest_updated_at,
                       MAX(suborder_id) AS latest_id
                FROM order_suborders
                WHERE seller_id = %s
            """,
            (user_id,)
        )

    rider_pickup_row = {}
    if role_id == 4:
        rider_pickup_row = _scalar_result(
            """
                SELECT COUNT(*) AS item_count,
                       MAX(updated_at) AS latest_updated_at,
                       MAX(suborder_id) AS latest_id
                FROM order_suborders
                WHERE pickup_status = 1
                   OR pickup_rider_id = %s
            """,
            (user_id,)
        )

    data = {
        'authenticated': True,
        'role_id': role_id,
        'poll_interval_ms': 15000,
        'counts': {
            'cart_count': int(header_counts.get('item_count') or 0),
            'wishlist_count': int(header_counts.get('wishlist_count') or 0),
            'messages_unread_count': int(message_row.get('unread_count') or header_counts.get('unread_count') or 0),
            'notifications_unread_count': int(notification_row.get('unread_count') or 0),
        },
        'tokens': {
            'notifications': _tokenize_state(
                'notifications',
                notification_row.get('unread_count') or 0,
                notification_row.get('latest_id') or 0,
                notification_row.get('latest_created_at') or ''
            ),
            'messages': _tokenize_state(
                'messages',
                message_row.get('unread_count') or 0,
                message_row.get('latest_message_id') or 0,
                message_row.get('latest_message_at') or ''
            ),
            'cart': _tokenize_state(
                'cart',
                cart_row.get('item_count') or 0,
                cart_row.get('total_quantity') or 0,
                cart_row.get('latest_item_id') or 0
            ),
            'wishlist': _tokenize_state(
                'wishlist',
                wishlist_row.get('item_count') or 0,
                wishlist_row.get('latest_id') or 0
            ),
            'buyer_orders': _tokenize_state(
                'buyer_orders',
                buyer_order_row.get('item_count') or 0,
                buyer_order_row.get('latest_id') or 0,
                buyer_order_row.get('latest_updated_at') or ''
            ),
            'seller_orders': _tokenize_state(
                'seller_orders',
                seller_order_row.get('item_count') or 0,
                seller_order_row.get('latest_id') or 0,
                seller_order_row.get('latest_updated_at') or ''
            ) if role_id == 3 else '',
            'rider_pickups': _tokenize_state(
                'rider_pickups',
                rider_pickup_row.get('item_count') or 0,
                rider_pickup_row.get('latest_id') or 0,
                rider_pickup_row.get('latest_updated_at') or ''
            ) if role_id == 4 else '',
        }
    }

    return responseData("success", "Live state fetched.", data, 200)

def getNotifications():
    user_id = g.authenticated.get('user_id') if g.authenticated else None
    if not user_id:
        return responseData("error", "Unauthorized", "", 401)

    query = """
        SELECT n.notification_id,
               n.order_id,
               n.title,
               n.message,
               n.notification_type,
               n.is_read,
               n.created_at,
               o.reference
        FROM notifications n
        LEFT JOIN orders o ON n.order_id = o.order_id
        WHERE n.user_id = %s
        ORDER BY n.created_at DESC
        LIMIT 50
    """
    results = executeGet(query, (user_id,)) or []

    if isinstance(results, tuple):
        return results

    items = []
    unread_count = 0
    for row in results:
        is_read = bool(row.get('is_read'))
        if not is_read:
            unread_count += 1

        created_at = row.get('created_at')
        if hasattr(created_at, 'strftime'):
            created_at_display = created_at.strftime("%b %d, %Y %I:%M %p")
        else:
            created_at_display = str(created_at) if created_at else ''

        items.append({
            'notification_id': row.get('notification_id'),
            'order_id': row.get('order_id'),
            'reference': row.get('reference'),
            'title': row.get('title') or 'Notification',
            'message': row.get('message') or '',
            'notification_type': row.get('notification_type') or 'system',
            'is_read': is_read,
            'created_at': created_at,
            'created_at_display': created_at_display,
        })

    return responseData(
        "success",
        "Notifications fetched successfully.",
        {
            'items': items,
            'unread_count': unread_count,
        },
        200,
    )

def markNotificationRead(notification_id):
    user_id = g.authenticated.get('user_id') if g.authenticated else None

    if not user_id:
        return responseData("error", "Unauthorized", "", 401)

    update_query = """
        UPDATE notifications
        SET is_read = 1,
            read_at = COALESCE(read_at, NOW())
        WHERE notification_id = %s AND user_id = %s
    """

    update_result = executePost(update_query, (notification_id, user_id))

    if not update_result or update_result.get('rowcount', 0) == 0:
        return responseData("error", "Notification not found.", "", 404)

    return responseData("success", "Notification marked as read.", {"notification_id": notification_id}, 200)

def markAllNotificationsRead():
    user_id = g.authenticated.get('user_id') if g.authenticated else None

    if not user_id:
        return responseData("error", "Unauthorized", "", 401)

    update_query = """
        UPDATE notifications
        SET is_read = 1,
            read_at = COALESCE(read_at, NOW())
        WHERE user_id = %s AND is_read = 0
    """

    update_result = executePost(update_query, (user_id,))

    return responseData(
        "success",
        "All notifications marked as read.",
        {"updated": update_result.get('rowcount', 0) if update_result else 0},
        200
    )

def getCategoriesInHome(condition=""):
    query = f"SELECT * FROM categories {condition}"
    results = executeGet(query)
    return results

def get_user_wishlist_ids(user_id):
    if not user_id:
        return set()

    query = "SELECT product_id FROM wishlists WHERE user_id = %s"
    results = executeGet(query, (user_id,))
    if isinstance(results, tuple) or not results:
        return set()

    return {row.get('product_id') for row in results if row.get('product_id') is not None}

def get_wishlist_items_for_user(user_id):
    query = """
        SELECT w.wishlist_id,
               p.product_id,
               p.product_name,
               p.price,
               p.qty,
               COALESCE(
                   (
                       SELECT pa.attachment
                       FROM product_attachments pa
                       WHERE pa.product_id = p.product_id AND pa.status = 1
                       ORDER BY pa.created_at ASC
                       LIMIT 1
                   ),
                   'images/no-image.jpg'
               ) AS attachment
        FROM wishlists w
        JOIN products p ON w.product_id = p.product_id
        WHERE w.user_id = %s
          AND p.status = 1
        ORDER BY w.created_at DESC
    """
    results = executeGet(query, (user_id,))
    if isinstance(results, tuple) or not results:
        return []
    return results

def get_cart_items_for_user(user_id):
    query = """
        SELECT oi.order_items_id,
               oi.product_id,
               oi.quantity,
               p.price,
               oi.status,
               oi.reference,
               p.product_name,
               p.qty AS stock,
               p.user_id AS seller_id,
               sd.store_name,
               sd.region AS seller_region,
               sd.province AS seller_province,
               sd.city AS seller_city,
               sd.latitude AS seller_latitude,
               sd.longitude AS seller_longitude,
               COALESCE(
                   (
                       SELECT pa.attachment
                       FROM product_attachments pa
                       WHERE pa.product_id = p.product_id AND pa.status = 1
                       ORDER BY pa.created_at ASC
                       LIMIT 1
                   ),
                   'images/no-image.jpg'
               ) AS attachment
        FROM order_items oi
        JOIN products p ON oi.product_id = p.product_id
        LEFT JOIN seller_details sd ON p.user_id = sd.user_id
        WHERE oi.user_id = %s
          AND oi.status = 1
          AND (oi.reference = '' OR oi.reference IS NULL)
        ORDER BY oi.order_items_id DESC
    """
    results = executeGet(query, (user_id,))
    if isinstance(results, tuple) or not results:
        return []

    for row in results:
        row['attachment'] = build_product_image_url(row.get('attachment'))

    return results

def group_cart_items_by_seller(cart_items):
    grouped = {}
    for item in cart_items or []:
        seller_id = item.get('seller_id')
        if not seller_id:
            continue
        grouped.setdefault(seller_id, []).append(item)
    return grouped

def get_shipping_settings():
    return {
        'shipping_free_threshold': get_float_setting('shipping_free_threshold', 2000.0),
        'shipping_same_city': get_float_setting('shipping_same_city', 49.0),
        'shipping_same_province': get_float_setting('shipping_same_province', 65.0),
        'shipping_same_region': get_float_setting('shipping_same_region', 79.0),
        'shipping_cross_region': get_float_setting('shipping_cross_region', 99.0),
    }

def calculate_cart_pricing(cart_items, buyer_address=None):
    seller_groups = group_cart_items_by_seller(cart_items)
    subtotal = 0
    shipping_fee = 0
    shipping_breakdown = []

    for seller_id, items in seller_groups.items():
        seller_name = items[0].get('store_name') or 'Seller'
        seller_geo = {
            'region': items[0].get('seller_region'),
            'province': items[0].get('seller_province'),
            'city': items[0].get('seller_city'),
            'latitude': items[0].get('seller_latitude'),
            'longitude': items[0].get('seller_longitude'),
        }
        group_subtotal = 0
        for item in items:
            price = float(item.get('price', 0) or 0)
            quantity = int(item.get('quantity', 0) or 0)
            group_subtotal += price * quantity

        subtotal += group_subtotal
        group_shipping_fee, shipping_reason = estimate_shipping_for_seller_group(
            group_subtotal=group_subtotal,
            buyer_address=buyer_address,
            seller_geo=seller_geo,
        )
        shipping_fee += group_shipping_fee
        shipping_breakdown.append({
            'seller_id': seller_id,
            'store_name': seller_name,
            'shipping_fee': group_shipping_fee,
            'shipping_reason': shipping_reason,
            'seller_region': seller_geo.get('region') or '',
            'seller_province': seller_geo.get('province') or '',
            'seller_city': seller_geo.get('city') or '',
        })

    tax_amount = (subtotal + shipping_fee) * 0.01
    total_amount = subtotal + shipping_fee + tax_amount
    return {
        'subtotal': subtotal,
        'shipping_fee': shipping_fee,
        'tax_amount': tax_amount,
        'total_amount': total_amount,
        'shipping_breakdown': shipping_breakdown,
    }

def calculate_order_totals(cart_items, buyer_address=None):
    pricing = calculate_cart_pricing(cart_items, buyer_address)
    return (
        pricing['subtotal'],
        pricing['shipping_fee'],
        pricing['tax_amount'],
        pricing['total_amount'],
    )

def create_order_notifications(order_id, reference, buyer_name, suborders_payload):
    if not suborders_payload:
        return

    insert_query = """
        INSERT INTO notifications (user_id, order_id, title, message, notification_type, is_read, created_at)
        VALUES (%s, %s, %s, %s, 'system', 0, NOW())
    """

    for payload in suborders_payload:
        seller_id = payload.get('seller_id')
        if not seller_id:
            continue

        sub_reference = payload.get('sub_reference') or reference
        item_names = payload.get('item_names') or []
        item_preview = ', '.join(item_names[:3])
        if len(item_names) > 3:
            item_preview += ', ...'

        title = "New Order Received"
        message = f"{buyer_name} placed sub-order {sub_reference}."
        if item_preview:
            message = f"{message} Items: {item_preview}"

        executePost(insert_query, (seller_id, order_id, title, message))

def home():
    categories = getCategoriesInHome("WHERE status = 1")
    search_query = (request.args.get('query') or '').strip()
    product_condition = "WHERE p.status = 1 AND p.qty > 0"
    product_params = None

    if search_query:
        search_term = f"%{search_query}%"
        product_condition += " AND (p.product_name LIKE %s OR p.description LIKE %s OR c.category_name LIKE %s)"
        product_params = [search_term, search_term, search_term]

    products = getProductsInHome(product_condition, page=1, per_page=12, params=product_params)
    cart_items = session.get('cart', {})

    wishlist_ids = set()
    if g.authenticated and g.authenticated.get('user_id'):
        wishlist_ids = get_user_wishlist_ids(g.authenticated.get('user_id'))

    return render_template(
        'views/home.html',
        cat_data=categories,
        prod_data=products,
        wishlist_ids=list(wishlist_ids),
        cart_items=cart_items,
    )

def shop():
    return home()

def getProductsInHome(condition="", page=1, per_page=10, params=None):
    offset = (page - 1) * per_page
    
    # Base query with proper parameterization
    base_query = """
    SELECT p.product_id, p.category_id, p.product_name, c.category_name, 
           (
               SELECT pa.attachment
               FROM product_attachments pa
               WHERE pa.product_id = p.product_id AND pa.status = 1
               ORDER BY pa.created_at ASC, pa.product_attachment_id ASC
               LIMIT 1
           ) AS attachment,
           p.description, p.price, p.qty, p.created_at, p.status 
    FROM products p 
    LEFT JOIN categories c ON p.category_id = c.category_id 
    {condition} 
    AND c.status != 2 
    ORDER BY p.created_at DESC, p.product_id DESC
    LIMIT %s OFFSET %s
    """
    
    # Format the condition (remove WHERE if it's empty to avoid SQL syntax error)
    if not condition.strip():
        condition = "WHERE 1=1"
    
    # Add LIMIT parameters to params if they exist, otherwise create new params
    if params is None:
        params = []
    
    # Execute the query with parameters
    query = base_query.format(condition=condition)
    results = executeGet(query, params + [per_page, offset])
    
    if not results:  # Check if results is empty
        return []

    # Format the results
    for product in results:
        product['formatted_price'] = locale.format_string("%0.2f", float(product['price']), grouping=True)
        if product['attachment'] is not None:
            product['attachment'] = build_product_image_url(product['attachment'])
        else:
            product['attachment'] = None
    
    return results

def loadMoreProducts():
    page = request.args.get('page', 1, type=int)
    products = getProductsInHome("WHERE p.status = 1 AND p.qty > 0", page=page)
    
    wishlist_ids = set()
    if g.authenticated and g.authenticated.get('user_id'):
        wishlist_ids = get_user_wishlist_ids(g.authenticated.get('user_id'))

    for product in products or []:
        product['is_in_wishlist'] = product.get('product_id') in wishlist_ids
    
    if products is None or products == "":
        return responseData("error", "No more products found.", [], 200)

    return responseData("success", "Products loaded successfully.", products, 200)

@login_required
def wishlistPage():
    user_id = g.authenticated.get('user_id')
    if not user_id:
        return redirect(url_for('login_page'))

    categories = getCategoriesInHome("WHERE status = 1")
    wishlist_items = get_wishlist_items_for_user(user_id)

    for item in wishlist_items:
        price = float(item.get('price', 0) or 0)
        item['formatted_price'] = locale.format_string("%0.2f", price, grouping=True)
        attachment = item.get('attachment')
        item['image_url'] = build_product_image_url(attachment)

    wishlist_ids = [item.get('product_id') for item in wishlist_items]

    return render_template(
        'views/wishlist.html',
        cat_data=categories,
        wishlist_items=wishlist_items,
        wishlist_ids=wishlist_ids
    )

def categoryPage(category_id):
    products = getProductsInCategoryGrouped(category_id)
    categories = getCategoriesInHome("WHERE status = 1")

    wishlist_ids = set()
    if g.authenticated and g.authenticated.get('user_id'):
        wishlist_ids = get_user_wishlist_ids(g.authenticated.get('user_id'))

    for product in products or []:
        product['is_in_wishlist'] = product.get('product_id') in wishlist_ids

    return render_template('views/category.html', data=products, cat_data=categories, wishlist_ids=list(wishlist_ids))

def getProductsInCategoryGrouped(category_id, page=1, per_page=10):
    offset = (page - 1) * per_page
    query = """
        SELECT p.product_id,
               p.user_id,
               p.product_name,
               p.price,
               p.status AS product_status,
               pa.product_attachment_id,
               pa.product_id AS attachment_product_id,
               pa.attachment,
               pa.status AS attachment_status,
               c.category_id,
               c.category_name,
               c.status AS category_status
        FROM products p
        LEFT JOIN product_attachments pa ON p.product_id = pa.product_id
        LEFT JOIN categories c ON p.category_id = c.category_id
        WHERE c.category_id = %s AND c.status = 1
        GROUP BY p.product_id,
                 pa.product_attachment_id,
                 c.category_id
        LIMIT %s OFFSET %s
    """
    results = executeGet(query, (category_id, per_page, offset))
    
    if not results:  # Check if results is empty
        return []  # Return an empty list or handle as needed

    for product in results:
        product['formatted_price'] = locale.format_string("%0.2f", product['price'], grouping=True)
        if 'attachment' in product and product['attachment'] is not None:
            product['attachment'] = build_product_image_url(product['attachment'])
            print(f"Image URL for {product['product_name']}: {product['attachment']}")
        else:
            product['attachment'] = None
            print(f"No image for {product['product_name']}")
    
    return results
    return results

def cart():
    categories = getCategoriesInHome("WHERE status = 1")
    user_id = g.authenticated.get('user_id')  # Get the logged-in user's ID
    if not user_id:
        return redirect(url_for('login_page'))  # Redirect to login if not authenticated

    cart_items = get_cart_items_for_user(user_id)
    user_address, formatted_address, address_texts = get_user_address_details(user_id)
    shipping_address = prepare_address_for_shipping(user_address)

    order_totals = None
    total_sum = 0
    random_order_reference = None
    shipping_settings = get_shipping_settings()

    if cart_items:
        for item in cart_items:
            price = item.get('price', 0) or 0
            quantity = item.get('quantity', 0) or 0
            total_price = quantity * price

            item['formatted_price'] = locale.format_string("%0.2f", price, grouping=True)
            item['total_price'] = locale.format_string("%0.2f", total_price, grouping=True)

            attachment = item.get('attachment')
            if attachment:
                cleaned_attachment = attachment.lstrip('/\\')
                item['attachment'] = cleaned_attachment

        pricing = calculate_cart_pricing(cart_items, shipping_address)
        subtotal = pricing['subtotal']
        shipping_fee = pricing['shipping_fee']
        tax_amount = pricing['tax_amount']
        total_amount = pricing['total_amount']
        total_sum = total_amount
        order_totals = {
            'subtotal': subtotal,
            'shipping_fee': shipping_fee,
            'tax_amount': tax_amount,
            'total_amount': total_amount,
            'formatted_subtotal': locale.format_string("%0.2f", subtotal, grouping=True),
            'formatted_shipping': locale.format_string("%0.2f", shipping_fee, grouping=True),
            'formatted_tax': locale.format_string("%0.2f", tax_amount, grouping=True),
            'formatted_total': locale.format_string("%0.2f", total_amount, grouping=True),
            'is_shipping_free': shipping_fee == 0
        }
        order_totals['shipping_breakdown'] = pricing['shipping_breakdown']
        random_order_reference = generate_random_string(10)

    return render_template(
        'views/cart.html',
        cat_data=categories,
        cart_items=cart_items,
        total_sum=total_sum,
        user_address=user_address,
        shipping_address=shipping_address,
        address_display=formatted_address,
        address_texts=address_texts,
        order_totals=order_totals,
        shipping_settings=shipping_settings,
        random_order_reference=random_order_reference
    )

def checkout():
    user_id = g.authenticated.get('user_id')
    
    if not user_id:
        return responseData("error", "User not authenticated.", [], 401)

    # Update the status of order items to 2 for the logged-in user
    query = "UPDATE order_items SET status = 2 WHERE user_id = %s AND status = 1"
    results = executeGet(query, (user_id,))

    if results:
        return responseData("success", "Checkout successful", results, 200)
    else:
        return responseData("error", "No items to checkout or update failed.", [], 400)


def submitCheckout(): 
    user_id = g.authenticated.get('user_id')
    if not user_id:
        return responseData("error", "User not authenticated.", "", 401)

    payment_method = request.form.get('payment-method')
    if not payment_method:
        return responseData("error", "Please select a payment method.", "", 200)

    # Ensure the user has a saved shipping address before allowing checkout
    buyer_address, formatted_address, _ = get_user_address_details(user_id)
    if not formatted_address:
        return responseData("error", "Please add a shipping address before checking out.", "", 200)
    shipping_address = prepare_address_for_shipping(buyer_address)

    cart_items = get_cart_items_for_user(user_id)
    if not cart_items:
        return responseData("error", "Your cart is empty.", "", 200)

    for item in cart_items:
        requested_quantity = int(item.get('quantity', 0) or 0)
        available_stock = int(item.get('stock', 0) or 0)
        product_name = item.get('product_name') or 'This product'

        if requested_quantity <= 0:
            return responseData("error", "Invalid item quantity found in your cart.", "", 200)

        if requested_quantity > available_stock:
            return responseData(
                "error",
                f"{product_name} only has {available_stock} item(s) left in stock.",
                "",
                200
            )

    pricing = calculate_cart_pricing(cart_items, shipping_address)
    subtotal = pricing['subtotal']
    shipping_fee = pricing['shipping_fee']
    tax_amount = pricing['tax_amount']
    total_amount = pricing['total_amount']
    shipping_by_seller = {
        entry.get('seller_id'): entry
        for entry in pricing.get('shipping_breakdown', [])
    }
    provided_reference = request.form.get('reference')
    reference = provided_reference if provided_reference else generate_random_string(12)
    estimated_delivery = (datetime.utcnow() + timedelta(days=5)).strftime("%B %d, %Y")

    insert_query = """
        INSERT INTO orders (user_id, reference, subtotal, shipping_fee, tax_amount, total_amount, cash_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    insert_result = executePost(
        insert_query,
        (
            user_id,
            reference,
            subtotal,
            shipping_fee,
            tax_amount,
            f"{total_amount:.2f}",
            payment_method
        )
    )

    if not insert_result or not insert_result.get('last_inserted_id'):
        return responseData("error", "Unable to create order. Please try again.", "", 200)

    order_id = insert_result.get('last_inserted_id')

    insert_payment_query = """
        INSERT INTO payments (order_id, payment_amount, status)
        VALUES (%s, %s, %s)
    """
    payment_status = 0 if payment_method.upper() == 'COD' else 1
    executePost(insert_payment_query, (order_id, int(total_amount), payment_status))

    seller_groups = group_cart_items_by_seller(cart_items)
    if not seller_groups:
        return responseData("error", "Unable to allocate items to sellers.", "", 200)

    suborders_payload = []
    for index, (seller_id, items) in enumerate(seller_groups.items(), start=1):
        if not seller_id or not items:
            continue

        group_subtotal = 0
        for cart_item in items:
            price = float(cart_item.get('price', 0) or 0)
            quantity = int(cart_item.get('quantity', 0) or 0)
            group_subtotal += price * quantity

        group_shipping_fee = float((shipping_by_seller.get(seller_id) or {}).get('shipping_fee') or 0)
        group_tax_amount = (group_subtotal + group_shipping_fee) * 0.01
        group_total_amount = group_subtotal + group_shipping_fee + group_tax_amount

        sub_reference = f"{reference}-{index:02d}"
        insert_suborder_query = """
            INSERT INTO order_suborders
                (order_id, seller_id, reference, status, subtotal, shipping_fee, tax_amount, total_amount)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        suborder_result = executePost(
            insert_suborder_query,
            (
                order_id,
                seller_id,
                sub_reference,
                1,
                f"{group_subtotal:.2f}",
                f"{group_shipping_fee:.2f}",
                f"{group_tax_amount:.2f}",
                f"{group_total_amount:.2f}"
            )
        )

        if not suborder_result or not suborder_result.get('last_inserted_id'):
            return responseData("error", "Unable to create seller sub-orders.", "", 200)

        suborder_id = suborder_result.get('last_inserted_id')
        item_names = []
        for cart_item in items:
            item_quantity = int(cart_item.get('quantity', 0) or 0)
            product_id = cart_item.get('product_id')

            update_item_query = """
                UPDATE order_items
                SET status = 1, reference = %s, suborder_id = %s
                WHERE order_items_id = %s
            """
            executePost(update_item_query, (reference, suborder_id, cart_item.get('order_items_id')))

            item_names.append(cart_item.get('product_name') or 'Product')

        suborders_payload.append({
            'seller_id': seller_id,
            'sub_reference': sub_reference,
            'item_names': item_names
        })

    buyer_first = g.authenticated.get('firstname', '') if g.authenticated else ''
    buyer_last = g.authenticated.get('lastname', '') if g.authenticated else ''
    buyer_name = f"{buyer_first} {buyer_last}".strip() or "A buyer"
    create_order_notifications(order_id, reference, buyer_name, suborders_payload)

    response_payload = {
        "reference": reference,
        "total_amount": f"{total_amount:,.2f}",
        "estimated_delivery": estimated_delivery,
        "payment_method": payment_method
    }

    return responseData("success", "Checkout successful", response_payload, 200)


def build_order_summary(order_row):
    order_row = order_row or {}

    status_labels = {
        1: 'Order Placed',
        2: 'Shipped',
        3: 'Out for Delivery',
        4: 'Delivered',
        5: 'Cancelled',
        6: 'Completed',
        7: 'Accepted',
        8: 'Rejected',
    }

    def _to_float(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _format_currency(value):
        return locale.format_string("%0.2f", value, grouping=True)

    status = int(order_row.get('status_override') or order_row.get('status') or 1)
    created_at = order_row.get('created_at')

    if isinstance(created_at, datetime):
        created_at_text = created_at.strftime("%B %d, %Y")
        estimated_delivery = (created_at + timedelta(days=5)).strftime("%B %d, %Y")
    else:
        created_at_text = created_at or ''
        estimated_delivery = (datetime.utcnow() + timedelta(days=5)).strftime("%B %d, %Y")

    subtotal = _to_float(order_row.get('subtotal'))
    shipping_fee = _to_float(order_row.get('shipping_fee'))
    tax_amount = _to_float(order_row.get('tax_amount'))
    total_amount = _to_float(order_row.get('total_amount'))

    base_total = subtotal + shipping_fee
    computed_tax_amount = round(base_total * 0.01, 2) if base_total > 0 else 0.0

    if base_total > 0 and tax_amount <= 0:
        tax_amount = computed_tax_amount

    expected_total_amount = subtotal + shipping_fee + tax_amount
    if base_total > 0 and (total_amount <= 0 or abs(total_amount - base_total) < 0.01):
        total_amount = expected_total_amount

    payment_method_raw = (order_row.get('cash_type') or order_row.get('payment_method') or 'cod').strip()
    payment_method = payment_method_raw.upper() if payment_method_raw else 'COD'

    return {
        'order_id': order_row.get('order_id'),
        'reference': order_row.get('reference') or '',
        'created_at': created_at_text,
        'estimated_delivery': estimated_delivery,
        'status': status,
        'status_text': status_labels.get(status, 'Processing'),
        'subtotal_raw': subtotal,
        'shipping_fee_raw': shipping_fee,
        'tax_amount_raw': tax_amount,
        'total_amount_raw': total_amount,
        'subtotal': _format_currency(subtotal),
        'shipping_fee': _format_currency(shipping_fee),
        'tax_amount': _format_currency(tax_amount),
        'total_amount': _format_currency(total_amount),
        'payment_method': payment_method,
    }


def get_order_items_by_reference(reference):
    query = """
        SELECT
            oi.order_items_id,
            oi.product_id,
            oi.quantity,
            oi.status,
            oi.reference,
            oi.variant_type,
            oi.variant_value,
            p.product_name,
            p.price,
            p.user_id AS seller_id,
            sd.store_name,
            os.shipping_fee AS shipping_fee_raw,
            COALESCE(
                (
                    SELECT pa.attachment
                    FROM product_attachments pa
                    WHERE pa.product_id = p.product_id AND pa.status = 1
                    ORDER BY pa.updated_at DESC, pa.product_attachment_id DESC
                    LIMIT 1
                ),
                'images/no-image.jpg'
            ) AS attachment
        FROM order_items oi
        INNER JOIN products p ON oi.product_id = p.product_id
        LEFT JOIN seller_details sd ON p.user_id = sd.user_id
        LEFT JOIN order_suborders os ON oi.suborder_id = os.suborder_id
        WHERE oi.reference = %s
        ORDER BY oi.order_items_id ASC
    """

    results = executeGet(query, (reference,))
    if not isinstance(results, list) or not results:
        return []

    status_labels = {
        1: 'Order Placed',
        2: 'Shipped',
        3: 'Out for Delivery',
        4: 'Delivered',
        5: 'Cancelled',
        6: 'Completed',
        7: 'Accepted',
        8: 'Rejected',
    }

    formatted_items = []
    for row in results:
        price = float(row.get('price', 0) or 0)
        quantity = int(row.get('quantity', 0) or 0)
        line_total = price * quantity
        status = int(row.get('status') or 1)

        formatted_items.append({
            'order_items_id': row.get('order_items_id'),
            'product_id': row.get('product_id'),
            'product_name': row.get('product_name') or 'Product',
            'quantity': quantity,
            'price_raw': price,
            'formatted_price': locale.format_string("%0.2f", price, grouping=True),
            'formatted_total': locale.format_string("%0.2f", line_total, grouping=True),
            'seller_id': row.get('seller_id'),
            'store_name': row.get('store_name') or 'Seller',
            'attachment': build_product_image_url(row.get('attachment')),
            'status': status,
            'status_text': status_labels.get(status, 'Processing'),
            'shipping_fee_raw': float(row.get('shipping_fee_raw', 0) or 0),
            'reference': row.get('reference') or reference,
            'variant_type': row.get('variant_type') or 'none',
            'variant_value': row.get('variant_value'),
        })

    return formatted_items


def build_timeline_steps(order_status):
    steps = [
        {"title": "Order Placed", "description": "We received your order."},
        {"title": "Shipped", "description": "Your items left our facility."},
        {"title": "Out for Delivery", "description": "Courier is on the way."},
        {"title": "Delivered", "description": "Package delivered."},
    ]

    current_status = order_status or 1
    for index, step in enumerate(steps, start=1):
        step['completed'] = current_status >= index
        step['active'] = current_status == index
        step['step_number'] = index
    return steps


def orderTrackingHub():
    user_id = g.authenticated.get('user_id')
    if not user_id:
        return redirect(url_for('login_page'))

    orders_query = """
        SELECT o.*, u.firstname, u.lastname
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.user_id
        WHERE o.user_id = %s
        ORDER BY o.created_at DESC
    """
    orders_result = executeGet(orders_query, (user_id,)) or []

    categories = getCategoriesInHome("WHERE status = 1")
    user_address, formatted_address, address_texts = get_user_address_details(user_id)

    placed_orders = []
    shipped_orders = []
    out_for_delivery_orders = []
    delivered_orders = []
    completed_orders = []
    cancelled_orders = []
    accepted_orders = []
    rejected_orders = []

    status_buckets = {
        1: placed_orders,
        2: shipped_orders,
        3: out_for_delivery_orders,
        4: delivered_orders,
        5: cancelled_orders,
        6: completed_orders,
        7: accepted_orders,
        8: rejected_orders,
    }

    for order in orders_result:
        max_sub_status = max((sub.get('sub_status', 0) for sub in executeGet(
            """
                SELECT MAX(os.status) AS sub_status
                FROM order_suborders os
                WHERE os.order_id = %s
            """,
            (order.get('order_id'),)
        ) or []), default=0)

        summary = build_order_summary({**order, 'status_override': max(order.get('status', 1) or 1, max_sub_status or 0)})
        items = get_order_items_by_reference(summary['reference'])

        if not items:
            fallback_status = int(summary.get('status', 1) or 1)

            # Clamp into known buckets while respecting explicit Accepted/Rejected
            if fallback_status < 1:
                fallback_status = 1
            if fallback_status not in status_buckets:
                # Any unknown high status should fall back to Completed bucket
                if fallback_status > 8:
                    fallback_status = 6

            shipping_fee_raw = float(order.get('shipping_fee', 0) or 0)
            fallback_shipping = 'Free' if shipping_fee_raw == 0 else f"₱{locale.format_string('%0.2f', shipping_fee_raw, grouping=True)}"
            fallback_entry = {
                'reference': summary['reference'],
                'product_name': 'Order Processing',
                'quantity': 0,
                'formatted_total': summary.get('total_amount'),
                'formatted_price': summary.get('total_amount'),
                'store_name': 'Seller',
                'attachment': None,
                'status': fallback_status,
                'status_text': summary.get('status_text', 'Processing'),
                'order_created_at': summary.get('created_at'),
                'estimated_delivery': summary.get('estimated_delivery'),
                'shipping_label': fallback_shipping,
                'payment_method': summary.get('payment_method') or '—'
            }
            status_buckets.get(fallback_status, placed_orders).append(fallback_entry)
            continue

        for item in items:
            entry_status = int(item.get('status') or 1)

            # Clamp into known buckets while respecting explicit Accepted/Rejected
            if entry_status < 1:
                entry_status = 1
            if entry_status not in status_buckets:
                if entry_status > 8:
                    entry_status = 6

            shipping_fee = float(item.get('shipping_fee_raw', 0) or 0)
            shipping_label = 'Free' if shipping_fee == 0 else f"₱{locale.format_string('%0.2f', shipping_fee, grouping=True)}"

            entry = {
                'reference': summary['reference'],
                'product_id': item.get('product_id'),
                'product_name': item.get('product_name', 'Product'),
                'quantity': item.get('quantity', 1),
                'formatted_total': item.get('formatted_total', '0.00'),
                'formatted_price': item.get('formatted_price', '0.00'),
                'store_name': item.get('store_name', 'Seller'),
                'attachment': item.get('attachment'),
                'status': entry_status,
                'status_text': item.get('status_text', 'Processing'),
                'order_created_at': summary.get('created_at'),
                'estimated_delivery': summary.get('estimated_delivery'),
                'shipping_label': shipping_label,
                'payment_method': summary.get('payment_method') or '—'
            }

            status_buckets.get(entry_status, placed_orders).append(entry)

    return render_template(
        'views/order-tracking-hub.html',
        cat_data=categories,
        placed_orders=placed_orders,
        shipped_orders=shipped_orders,
        out_for_delivery_orders=out_for_delivery_orders,
        delivered_orders=delivered_orders,
        completed_orders=completed_orders,
        cancelled_orders=cancelled_orders,
        accepted_orders=accepted_orders,
        rejected_orders=rejected_orders,
        shipping_address=formatted_address,
        user_address=user_address,
        address_texts=address_texts
    )


def confirmOrder(reference):
    """Buyer confirms a delivered order.

    Transitions item-level status 4 (Delivered) to 6 (Completed) for the given
    order reference, but only for the authenticated buyer.
    """
    user_id = g.authenticated.get('user_id') if g.authenticated else None
    if not user_id:
        return responseData("error", "User not authenticated.", "", 401)

    # Ensure the order belongs to this buyer
    order_query = """
        SELECT order_id
        FROM orders
        WHERE reference = %s AND user_id = %s
        LIMIT 1
    """
    order_rows = executeGet(order_query, (reference, user_id))
    if not order_rows:
        return responseData("error", "Order not found.", "", 404)

    order_id = order_rows[0].get('order_id')

    # Only update items that are currently Delivered (4)
    items_query = """
        SELECT oi.order_items_id, oi.suborder_id
        FROM order_items oi
        WHERE oi.reference = %s AND oi.status = 4
    """
    items = executeGet(items_query, (reference,)) or []
    if not items:
        return responseData("error", "No delivered items to confirm for this order.", "", 400)

    # Mark these items as Completed (6)
    update_items_query = """
        UPDATE order_items
        SET status = 6
        WHERE reference = %s AND status = 4
    """
    executePost(update_items_query, (reference,))

    # Optionally bump suborders and order status to 6 when all items are completed or cancelled
    # Update suborders whose items are all in (5=Cancelled, 6=Completed)
    update_suborders_query = """
        UPDATE order_suborders os
        SET status = 6
        WHERE os.order_id = %s
          AND NOT EXISTS (
            SELECT 1
            FROM order_items oi
            WHERE oi.suborder_id = os.suborder_id
              AND oi.status NOT IN (5, 6)
          )
    """
    executePost(update_suborders_query, (order_id,))

    # If all items under this order reference are now in (5,6), mark the order as 6
    remaining_items_query = """
        SELECT COUNT(*) AS remaining
        FROM order_items
        WHERE reference = %s AND status NOT IN (5, 6)
    """
    remaining = executeGet(remaining_items_query, (reference,)) or []
    if remaining and int(remaining[0].get('remaining') or 0) == 0:
        executePost("UPDATE orders SET status = 6 WHERE order_id = %s", (order_id,))

    return responseData("success", "Order confirmed.", {"reference": reference}, 200)


def orderList():
    if not g.authenticated:
        return redirect(url_for('login_page'))

    seller_id = g.authenticated.get('user_id')
    if not seller_id:
        return redirect(url_for('login_page'))

    orders_query = """
        SELECT o.order_id,
               o.reference,
               o.created_at,
               MAX(os.status) AS status,
               o.subtotal,
               o.shipping_fee,
               o.tax_amount,
               o.total_amount,
               buyer.firstname AS buyer_firstname,
               buyer.lastname AS buyer_lastname,
               buyer.email AS buyer_email,
               buyer.phone AS buyer_phone,
               COUNT(oi.order_items_id) AS item_count
        FROM orders o
        INNER JOIN order_suborders os ON os.order_id = o.order_id
        INNER JOIN order_items oi ON oi.suborder_id = os.suborder_id
        INNER JOIN products p ON oi.product_id = p.product_id
        LEFT JOIN users buyer ON o.user_id = buyer.user_id
        WHERE os.seller_id = %s
        GROUP BY o.order_id, o.reference, o.created_at,
                 o.subtotal, o.shipping_fee, o.tax_amount, o.total_amount,
                 buyer.firstname, buyer.lastname, buyer.email, buyer.phone
        ORDER BY o.created_at DESC
    """

    orders_result = executeGet(orders_query, (seller_id,)) or []

    status_labels = {
        1: 'Order Placed',
        2: 'Shipped',
        3: 'Out for Delivery',
        4: 'Delivered',
        5: 'Cancelled',
        6: 'Completed',
        7: 'Accepted',
        8: 'Rejected',
    }

    formatted_orders = []
    for order in orders_result:
        total_amount = order.get('total_amount')
        try:
            total_amount = float(total_amount)
        except (TypeError, ValueError):
            total_amount = 0.0

        item = {
            'order_id': order.get('order_id'),
            'reference': order.get('reference'),
            'created_at': order.get('created_at'),
            'status': order.get('status') or 1,
            'status_label': status_labels.get(order.get('status') or 1, 'Processing'),
            'subtotal': order.get('subtotal') or 0,
            'shipping_fee': order.get('shipping_fee') or 0,
            'tax_amount': order.get('tax_amount') or 0,
            'total_amount': total_amount,
            'item_count': order.get('item_count') or 0,
            'buyer_name': f"{order.get('buyer_firstname', '')} {order.get('buyer_lastname', '')}".strip() or 'N/A',
            'buyer_email': order.get('buyer_email'),
            'buyer_phone': order.get('buyer_phone')
        }
        formatted_orders.append(item)

    return render_template('views/orders/order-list.html', orders=formatted_orders, menu=['orders', 'order-list'])


def getSellerOrderItems(seller_id):
    order_items_query = """
        SELECT
            os.suborder_id,
            os.reference AS sub_reference,
            os.status AS sub_status,
            os.shipping_fee AS sub_shipping_fee,
            os.tax_amount AS sub_tax_amount,
            os.updated_at AS sub_updated_at,
            os.created_at AS sub_created_at,
            o.reference AS order_reference,
            o.created_at AS order_created_at,
            buyer.user_id AS buyer_id,
            buyer.firstname AS buyer_firstname,
            buyer.lastname AS buyer_lastname,
            buyer.email AS buyer_email,
            oi.order_items_id,
            oi.quantity,
            oi.status AS item_status,
            oi.reference,
            p.product_name,
            p.price AS unit_price,
            (
                SELECT pa.attachment
                FROM product_attachments pa
                WHERE pa.product_id = p.product_id AND pa.status = 1
                ORDER BY pa.updated_at DESC, pa.product_attachment_id DESC
                LIMIT 1
            ) AS product_image
        FROM order_suborders os
        INNER JOIN orders o ON os.order_id = o.order_id
        INNER JOIN order_items oi ON oi.suborder_id = os.suborder_id
        INNER JOIN products p ON oi.product_id = p.product_id
        LEFT JOIN users buyer ON o.user_id = buyer.user_id
        WHERE os.seller_id = %s
        ORDER BY os.updated_at DESC, oi.order_items_id DESC
    """

    rows = executeGet(order_items_query, (seller_id,))
    if not isinstance(rows, list):
        return rows

    rows = rows or []
    grouped_orders = {}
    for row in rows:
        suborder_id = row.get('suborder_id')
        if not suborder_id:
            continue

        if suborder_id not in grouped_orders:
            grouped_orders[suborder_id] = {
                'suborder_id': suborder_id,
                'sub_reference': row.get('sub_reference'),
                'reference': row.get('order_reference') or row.get('reference'),
                'buyer_id': row.get('buyer_id'),
                'buyer_name': f"{row.get('buyer_firstname', '')} {row.get('buyer_lastname', '')}".strip() or 'N/A',
                'buyer_email': row.get('buyer_email') or '',
                'updated_at': row.get('sub_updated_at') or row.get('sub_created_at'),
                'item_list': [],
                'group_status': row.get('sub_status') or 1,
                'shipping_fee': float(row.get('sub_shipping_fee') or 0),
                'tax_amount': float(row.get('sub_tax_amount') or 0)
            }

        unit_price = float(row.get('unit_price') or 0)
        quantity = int(row.get('quantity') or 0)
        item_payload = {
            'order_items_id': row.get('order_items_id'),
            'product_name': row.get('product_name'),
            'quantity': quantity,
            'status': row.get('item_status') or 1,
            'unit_price': unit_price,
            'line_total': unit_price * quantity,
            'product_image': build_product_image_url(row.get('product_image') or ''),
            'reference': row.get('reference') or row.get('sub_reference') or row.get('order_reference'),
            'line_reference': f"{row.get('sub_reference') or row.get('order_reference') or 'ORD'}-ITEM-{row.get('order_items_id')}",
            'updated_at': row.get('sub_updated_at') or row.get('order_created_at')
        }
        grouped_orders[suborder_id]['item_list'].append(item_payload)

    ordered_groups = sorted(grouped_orders.values(), key=lambda entry: entry.get('updated_at') or datetime.utcnow(), reverse=True)
    return ordered_groups


def _sync_suborder_status_from_items(suborder_id):
    if not suborder_id:
        return None

    items_query = """
        SELECT status
        FROM order_items
        WHERE suborder_id = %s
        ORDER BY order_items_id ASC
    """
    item_rows = executeGet(items_query, (suborder_id,)) or []
    if not item_rows:
        return None

    item_statuses = [int(row.get('status') or 1) for row in item_rows]
    active_statuses = [status for status in item_statuses if status not in (5, 8)]

    next_status = 1
    next_pickup_status = 0

    if not active_statuses:
        next_status = 8 if any(status == 8 for status in item_statuses) else 5
    elif any(status == 1 for status in active_statuses):
        next_status = 1
    elif any(status == 7 for status in active_statuses):
        next_status = 7
    else:
        next_status = 2
        next_pickup_status = 1

    current_query = """
        SELECT pickup_status
        FROM order_suborders
        WHERE suborder_id = %s
        LIMIT 1
    """
    current_rows = executeGet(current_query, (suborder_id,)) or []
    previous_pickup_status = int(current_rows[0].get('pickup_status') or 0) if current_rows else 0

    update_query = """
        UPDATE order_suborders
        SET status = %s,
            pickup_status = %s,
            pickup_rider_id = CASE WHEN %s = 1 THEN NULL ELSE pickup_rider_id END,
            pickup_claimed_at = CASE WHEN %s = 1 THEN NULL ELSE pickup_claimed_at END,
            pickup_completed_at = CASE WHEN %s = 1 THEN NULL ELSE pickup_completed_at END,
            updated_at = NOW()
        WHERE suborder_id = %s
    """
    executePost(
        update_query,
        (
            next_status,
            next_pickup_status,
            next_pickup_status,
            next_pickup_status,
            next_pickup_status,
            suborder_id,
        )
    )

    if next_pickup_status == 1 and previous_pickup_status != 1:
        notify_riders_pickup_available(suborder_id)

    return {
        'status': next_status,
        'pickup_status': next_pickup_status,
    }


def get_suborders_for_order(order_id):
    suborders_query = """
        SELECT
            os.suborder_id,
            os.reference AS sub_reference,
            os.status AS sub_status,
            os.shipping_fee AS sub_shipping_fee,
            os.updated_at,
            os.created_at,
            os.seller_id,
            os.pickup_rider_id,
            dp.user_id AS rider_user_id,
            dp.full_name AS rider_full_name,
            dp.phone AS rider_phone,
            dp.vehicle_type AS rider_vehicle_type,
            dp.plate_number AS rider_plate_number,
            seller.firstname AS seller_firstname,
            seller.lastname AS seller_lastname,
            sd.store_name,
            oi.order_items_id,
            oi.quantity,
            p.product_name,
            p.price,
            (
                SELECT pa.attachment
                FROM product_attachments pa
                WHERE pa.product_id = p.product_id AND pa.status = 1
                ORDER BY pa.updated_at DESC, pa.product_attachment_id DESC
                LIMIT 1
            ) AS product_image,
            (
                SELECT dpf.image_path
                FROM delivery_proofs dpf
                WHERE dpf.suborder_id = os.suborder_id
                ORDER BY dpf.created_at DESC, dpf.proof_id DESC
                LIMIT 1
            ) AS delivery_proof_image,
            (
                SELECT dpf.captured_at
                FROM delivery_proofs dpf
                WHERE dpf.suborder_id = os.suborder_id
                ORDER BY dpf.created_at DESC, dpf.proof_id DESC
                LIMIT 1
            ) AS delivery_proof_captured_at
        FROM order_suborders os
        INNER JOIN users seller ON os.seller_id = seller.user_id
        LEFT JOIN seller_details sd ON sd.user_id = seller.user_id
        LEFT JOIN delivery_partners dp ON os.pickup_rider_id = dp.user_id
        INNER JOIN order_items oi ON oi.suborder_id = os.suborder_id
        INNER JOIN products p ON oi.product_id = p.product_id
        WHERE os.order_id = %s
        ORDER BY os.created_at ASC, os.suborder_id ASC, oi.order_items_id ASC
    """

    rows = executeGet(suborders_query, (order_id,))
    if not isinstance(rows, list):
        return rows

    rows = rows or []
    grouped = {}
    for row in rows:
        suborder_id = row.get('suborder_id')
        if not suborder_id:
            continue

        if suborder_id not in grouped:
            seller_name = f"{row.get('seller_firstname', '')} {row.get('seller_lastname', '')}".strip()
            store_name = row.get('store_name') or seller_name or 'Seller'
            delivery_proof_captured_at = row.get('delivery_proof_captured_at')
            if isinstance(delivery_proof_captured_at, datetime):
                delivery_proof_captured_at = delivery_proof_captured_at.strftime("%B %d, %Y %I:%M %p")
            grouped[suborder_id] = {
                'suborder_id': suborder_id,
                'sub_reference': row.get('sub_reference'),
                'status': row.get('sub_status') or 1,
                'updated_at': row.get('updated_at') or row.get('created_at'),
                'seller_name': seller_name or 'Seller',
                'store_name': store_name,
                'rider_user_id': row.get('rider_user_id'),
                'rider_name': row.get('rider_full_name'),
                'rider_phone': row.get('rider_phone'),
                'rider_vehicle': row.get('rider_vehicle_type'),
                'rider_plate': row.get('rider_plate_number'),
                'delivery_proof_image': build_delivery_proof_image_url(row.get('delivery_proof_image')),
                'delivery_proof_captured_at': delivery_proof_captured_at,
                'items': [],
                'shipping_fee': float(row.get('sub_shipping_fee') or 0)
            }

        price = float(row.get('price', 0) or 0)
        quantity = int(row.get('quantity', 0) or 0)
        item_payload = {
            'order_items_id': row.get('order_items_id'),
            'product_name': row.get('product_name'),
            'quantity': quantity,
            'unit_price': price,
            'line_total': price * quantity,
            'product_image': build_product_image_url(row.get('product_image') or '')
        }
        grouped[suborder_id]['items'].append(item_payload)

    ordered = sorted(grouped.values(), key=lambda entry: entry.get('updated_at') or datetime.utcnow())
    return ordered


def orderManagement():
    if not g.authenticated or g.authenticated.get('role_id') != 3:
        return redirect(url_for('login_page'))

    seller_id = g.authenticated.get('user_id')
    order_groups = getSellerOrderItems(seller_id)

    if not isinstance(order_groups, list):
        return order_groups

    return render_template('views/orders/order-management.html', order_groups=order_groups, menu=['orders', 'order-management'])


def updateSuborderStatus():
    if not g.authenticated or g.authenticated.get('role_id') != 3:
        return responseData("error", "Unauthorized", "", 401)

    seller_id = g.authenticated.get('user_id')
    order_item_id = request.form.get('order_item_id', type=int)
    suborder_id = request.form.get('suborder_id', type=int)
    status = request.form.get('status', type=int)

    # Allow seller to mark suborders as Shipped, Out for Delivery, Delivered,
    # Accepted, or Rejected. Accepted/Rejected do not affect rider pickup state.
    if not suborder_id or not order_item_id or status not in (2, 7, 8):
        return responseData("error", "Invalid request payload", "", 400)

    ownership_query = """
        SELECT oi.order_items_id,
               oi.status,
               oi.suborder_id
        FROM order_items oi
        INNER JOIN order_suborders os ON os.suborder_id = oi.suborder_id
        WHERE oi.order_items_id = %s
          AND oi.suborder_id = %s
          AND os.seller_id = %s
        LIMIT 1
    """
    ownership = executeGet(ownership_query, (order_item_id, suborder_id, seller_id))
    if not ownership:
        return responseData("error", "Order item not found or you do not have permission to update it.", "", 404)

    current_status = int(ownership[0].get('status') or 1)
    allowed_transitions = {
        1: (7, 8),
        7: (2,),
    }
    if status not in allowed_transitions.get(current_status, ()): 
        return responseData("error", "This item can no longer be updated to the selected status.", "", 400)

    update_items_query = """
        UPDATE order_items
        SET status = %s
        WHERE order_items_id = %s AND suborder_id = %s
    """
    item_update_result = executePost(update_items_query, (status, order_item_id, suborder_id))
    if isinstance(item_update_result, tuple):
        return item_update_result

    _sync_suborder_status_from_items(suborder_id)

    status_labels = {
        2: 'Shipped',
        7: 'Accepted',
        8: 'Rejected'
    }

    return responseData("success", f"Item marked as {status_labels.get(status, 'updated')}.", {"order_item_id": order_item_id, "suborder_id": suborder_id}, 200)


def orderTracking(reference):
    user_id = g.authenticated.get('user_id')
    if not user_id:
        return redirect(url_for('login_page'))

    orders_query = """
        SELECT o.*, u.firstname, u.lastname
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.user_id
        WHERE o.user_id = %s AND o.reference = %s
        LIMIT 1
    """
    order_row = executeGet(orders_query, (user_id, reference))
    if not order_row:
        return redirect(url_for('order_tracking_hub'))

    order_data = order_row[0]
    summary = build_order_summary(order_data)
    items = get_order_items_by_reference(summary['reference'])
    status_sequence = (1, 2, 3, 4)
    item_groups = {status: [] for status in status_sequence}
    for item in items:
        status = int(item.get('status') or 1)
        if status < 1:
            status = 1
        elif status > 4:
            status = 4
        item_groups.setdefault(status, []).append(item)

    status_counts = {status: len(item_groups.get(status, [])) for status in status_sequence}
    active_status = summary.get('status', 1) or 1
    if active_status not in status_sequence or not item_groups.get(active_status):
        active_status = next((status for status in status_sequence if item_groups.get(status)), 1)
    total_status_items = sum(status_counts.values())
    timeline_steps = build_timeline_steps(summary['status'])
    suborders = get_suborders_for_order(order_data.get('order_id'))
    if isinstance(suborders, tuple):
        suborders = []

    shipping_breakdown = []
    seen_suborders = set()
    for suborder in suborders or []:
        suborder_id = suborder.get('suborder_id')
        if not suborder_id or suborder_id in seen_suborders:
            continue
        seen_suborders.add(suborder_id)
        shipping_breakdown.append({
            'seller_id': suborder.get('seller_id'),
            'store_name': suborder.get('store_name') or 'Seller',
            'shipping_fee': float(suborder.get('shipping_fee') or 0),
        })
    summary['shipping_breakdown'] = shipping_breakdown

    # Determine primary seller for buyer<>seller chat (first seller in this order)
    primary_seller_id = None
    primary_seller_name = None
    for item in items or []:
        seller_id = item.get('seller_id')
        if seller_id and primary_seller_id is None:
            primary_seller_id = seller_id
            primary_seller_name = item.get('store_name') or item.get('product_name') or 'Seller'

    # Determine rider chat target: first suborder that has an assigned rider and is at least shipped.
    # This allows buyer↔rider chat for Shipped, Out for Delivery, and Delivered shipments.
    rider_chat = None
    for sub in suborders or []:
        status = int(sub.get('status') or 1)
        if status >= 2 and status <= 4 and sub.get('rider_user_id'):
            rider_chat = {
                'rider_user_id': sub.get('rider_user_id'),
                'rider_name': sub.get('rider_name'),
                'rider_phone': sub.get('rider_phone'),
                'rider_vehicle': sub.get('rider_vehicle'),
                'rider_plate': sub.get('rider_plate'),
            }
            break

    user_address, formatted_address, _ = get_user_address_details(user_id)
    categories = getCategoriesInHome("WHERE status = 1")

    return render_template(
        'views/order-tracking.html',
        cat_data=categories,
        order_summary=summary,
        order_items=items,
        suborders=suborders,
        item_groups=item_groups,
        status_counts=status_counts,
        active_status=active_status,
        total_status_items=total_status_items,
        timeline_steps=timeline_steps,
        shipping_address=formatted_address,
        user_address=user_address,
        can_cancel=summary['status'] == 1,
        seller_chat_seller_id=primary_seller_id,
        seller_chat_seller_name=primary_seller_name,
        rider_chat=rider_chat
    )


def orderTrackingLatest():
    user_id = g.authenticated.get('user_id') if g.authenticated else None
    if not user_id:
        return redirect(url_for('login_page'))

    latest_order_query = """
        SELECT reference
        FROM orders
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """
    latest_order = executeGet(latest_order_query, (user_id,))

    if not latest_order:
        return redirect(url_for('cart_page'))

    latest_reference = latest_order[0].get('reference')
    if not latest_reference:
        return redirect(url_for('cart_page'))

    return redirect(url_for('order_tracking', reference=latest_reference))


def cancelOrder(reference):
    user_id = g.authenticated.get('user_id') if g.authenticated else None
    if not user_id:
        return responseData("error", "User not authenticated.", "", 401)

    order_query = """
        SELECT order_id, status
        FROM orders
        WHERE reference = %s AND user_id = %s
        LIMIT 1
    """
    order_result = executeGet(order_query, (reference, user_id))

    if not order_result:
        return responseData("error", "Order not found.", "", 404)

    status = order_result[0].get('status', 1)
    if status != 1:
        return responseData("error", "This order can no longer be canceled.", "", 200)

    executePost("DELETE FROM order_items WHERE reference = %s", (reference,))
    executePost("DELETE FROM orders WHERE reference = %s AND user_id = %s", (reference, user_id))

    return responseData("success", "Order removed successfully.", {"reference": reference}, 200)


def cancelOrderItem(order_item_id):
    user_id = g.authenticated.get('user_id') if g.authenticated else None
    if not user_id:
        return responseData("error", "User not authenticated.", "", 401)

    item_query = """
        SELECT
            oi.order_items_id,
            oi.reference,
            oi.status,
            oi.suborder_id
        FROM order_items oi
        INNER JOIN orders o ON o.reference = oi.reference
        WHERE oi.order_items_id = %s AND o.user_id = %s
        LIMIT 1
    """

    item_rows = executeGet(item_query, (order_item_id, user_id))
    if not item_rows:
        return responseData("error", "Order item not found.", "", 404)

    item = item_rows[0]
    if (item.get('status') or 1) != 1:
        return responseData("error", "This item can no longer be canceled.", "", 400)

    update_item_query = """
        UPDATE order_items
        SET status = 5
        WHERE order_items_id = %s
    """
    executePost(update_item_query, (order_item_id,))

    suborder_id = item.get('suborder_id')
    if suborder_id:
        remaining_sub_items = executeGet(
            "SELECT COUNT(*) AS remaining FROM order_items WHERE suborder_id = %s AND status <> 5",
            (suborder_id,)
        )
        if not remaining_sub_items or remaining_sub_items[0].get('remaining', 0) == 0:
            executePost("UPDATE order_suborders SET status = 5 WHERE suborder_id = %s", (suborder_id,))

    reference = item.get('reference')
    remaining_order_items = executeGet(
        "SELECT COUNT(*) AS remaining FROM order_items WHERE reference = %s AND status <> 5",
        (reference,)
    )
    if not remaining_order_items or remaining_order_items[0].get('remaining', 0) == 0:
        executePost("UPDATE orders SET status = 5 WHERE reference = %s AND user_id = %s", (reference, user_id))

    return responseData("success", "Item canceled successfully.", {"order_item_id": order_item_id}, 200)