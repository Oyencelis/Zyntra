# pyrefly: ignore [missing-import]
from datetime import datetime
from flask import render_template, request, g
from helpers.QueryHelpers import executeGet, executePost
from helpers.HelperFunction import responseData
from helpers.delivery_media import save_compressed_proof
from helpers.notification_helpers import notify_buyer_order_item_status
from helpers.wallet_finance import credit_rider_commission_for_item, rider_earnings_snapshot, calculate_rider_commission_amount
from controller.HomeController import get_user_address_details, build_product_image_url, resolve_location_name


def _ensure_rider_auth():
    if not g.authenticated or g.authenticated.get('role_id') != 4:
        return None, responseData("error", "Rider access required.", "", 401)
    return g.authenticated, None


def riderPickupDashboard():
    rider, error = _ensure_rider_auth()
    if error:
        return error

    earnings = rider_earnings_snapshot(rider['user_id'])

    return render_template(
        'views/dashboard/rider-pickups.html',
        menu=['deliveries'],
        wallet_balance=earnings.get('available_balance', 0),
        credited_earnings=earnings.get('completed_fee', 0),
        active_earnings=earnings.get('active_fee', 0),
        projected_total=earnings.get('total_fee', 0),
    )


def _format_location(*, floor_unit=None, street=None, barangay=None, city=None, province=None, region=None):
    region_display = resolve_location_name(region, 'region.json', 'region_code', 'region_name') or region
    province_display = resolve_location_name(province, 'province.json', 'province_code', 'province_name') or province
    city_display = resolve_location_name(city, 'city.json', 'city_code', 'city_name') or city
    barangay_display = resolve_location_name(barangay, 'barangay.json', 'brgy_code', 'brgy_name') or barangay

    return ", ".join(
        filter(None, [floor_unit, street, barangay_display, city_display, province_display, region_display])
    )


def _format_datetime_label(value):
    if not value:
        return None

    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return value

    return value.strftime('%B %d, %Y at %I:%M %p')


def _sync_pickup_suborder(suborder_id):
    if not suborder_id:
        return

    executeGet("SELECT public.sync_suborder_status_from_items(%s)", (suborder_id,))


def _pickup_base_query():
    return """
        SELECT
            oi.order_items_id AS order_item_id,
            os.suborder_id,
            os.order_id,
            os.reference AS sub_reference,
            COALESCE(NULLIF(TRIM(COALESCE(oi.reference, '')), ''), CONCAT(COALESCE(os.reference, o.reference, 'ORD'), '-ITEM-', oi.order_items_id)) AS item_reference,
            COALESCE(p.product_name, 'Unnamed product') AS product_name,
            COALESCE(oi.quantity, 0) AS quantity,
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
            o.reference AS order_reference,
            o.created_at AS order_created_at,
            buyer.user_id AS buyer_id,
            buyer.firstname AS buyer_firstname,
            buyer.lastname AS buyer_lastname,
            buyer.phone AS buyer_phone,
            seller.firstname AS seller_firstname,
            seller.lastname AS seller_lastname,
            sd.store_name,
            sd.region AS seller_region,
            sd.city AS seller_city,
            sd.province AS seller_province,
            sd.barangay AS seller_barangay,
            sd.street AS seller_street,
            ba.floor_unit_number AS buyer_floor_unit_number,
            ba.region AS buyer_region,
            ba.province AS buyer_province,
            ba.city_municipality AS buyer_city_municipality,
            ba.barangay AS buyer_barangay,
            ba.street AS buyer_street,
            COALESCE(money.line_total, 0) AS subtotal,
            COALESCE(money.shipping_share, 0) AS shipping_fee,
            COALESCE(money.tax_share, 0) AS tax_amount,
            COALESCE(money.total_amount, 0) AS total_amount,
            COALESCE(item_ledger.amount, legacy_ledger.amount) AS actual_commission
        FROM order_items oi
        INNER JOIN order_suborders os ON os.suborder_id = oi.suborder_id
        INNER JOIN orders o ON os.order_id = o.order_id
        LEFT JOIN users buyer ON o.user_id = buyer.user_id
        INNER JOIN users seller ON os.seller_id = seller.user_id
        LEFT JOIN seller_details sd ON sd.user_id = seller.user_id
        LEFT JOIN products p ON p.product_id = oi.product_id
        LEFT JOIN LATERAL public.order_item_pickup_financials(oi.suborder_id, oi.order_items_id) AS money ON TRUE
        LEFT JOIN LATERAL (
            SELECT MIN(oi2.order_items_id) AS primary_item_id
            FROM order_items oi2
            WHERE oi2.suborder_id = oi.suborder_id
              AND oi2.status NOT IN (5, 8)
        ) primary_item ON TRUE
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
        ) pickup ON TRUE
        LEFT JOIN LATERAL (
            SELECT wl.amount
            FROM wallet_ledger wl
            WHERE wl.user_id = pickup.resolved_pickup_rider_id
              AND wl.wallet_role = 'rider'
              AND wl.entry_kind = 'rider_commission_delivery_item'
              AND wl.reference_id = oi.order_items_id
            ORDER BY wl.ledger_id DESC
            LIMIT 1
        ) item_ledger ON TRUE
        LEFT JOIN LATERAL (
            SELECT wl.amount
            FROM wallet_ledger wl
            WHERE oi.order_items_id = primary_item.primary_item_id
              AND wl.user_id = pickup.resolved_pickup_rider_id
              AND wl.wallet_role = 'rider'
              AND wl.entry_kind = 'rider_commission_delivery'
              AND wl.reference_id = os.suborder_id
            ORDER BY wl.ledger_id DESC
            LIMIT 1
        ) legacy_ledger ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                a.floor_unit_number,
                a.region,
                a.province,
                a.city_municipality,
                a.barangay,
                a.street
            FROM addresses a
            WHERE a.user_id = buyer.user_id
            ORDER BY a.updated_at DESC, a.address_id DESC
            LIMIT 1
        ) ba ON TRUE
    """


def _pickup_query(scope):
    base_query = _pickup_base_query()

    conditions = []
    if scope == 'mine':
        conditions.append("pickup.resolved_pickup_rider_id = %s")
        conditions.append("pickup.resolved_pickup_status IN (2,3,4)")
    else:
        conditions.append("pickup.resolved_pickup_status = 1")
        conditions.append("pickup.resolved_pickup_rider_id IS NULL")

    where_clause = " WHERE " + " AND ".join(conditions)
    order_clause = " ORDER BY updated_at DESC, oi.order_items_id DESC"
    return base_query + where_clause + order_clause


def _serialize_pickup(row):
    seller_name = f"{row.get('seller_firstname', '')} {row.get('seller_lastname', '')}".strip()
    buyer_name = f"{row.get('buyer_firstname', '')} {row.get('buyer_lastname', '')}".strip()
    pickup_state = row.get('pickup_status') or 0
    shipping_fee = float(row.get('shipping_fee') or 0)
    subtotal = float(row.get('subtotal') or 0)
    convenience_fee = float(row.get('tax_amount') or 0)
    pickup_total = float(row.get('total_amount') or 0)
    if pickup_total <= 0:
        pickup_total = round(subtotal + shipping_fee + convenience_fee, 2)
    projected_commission = calculate_rider_commission_amount(shipping_fee, convenience_fee)
    actual_commission = row.get('actual_commission')
    display_commission = float(actual_commission) if actual_commission is not None else projected_commission
    commission_label = 'Credited commission' if actual_commission is not None else ('Projected commission' if pickup_state in (2, 3) else 'Queued commission')
    pickup_location = _format_location(
        street=row.get('seller_street'),
        barangay=row.get('seller_barangay'),
        city=row.get('seller_city'),
        province=row.get('seller_province'),
        region=row.get('seller_region'),
    )
    dropoff_location = _format_location(
        floor_unit=row.get('buyer_floor_unit_number'),
        street=row.get('buyer_street'),
        barangay=row.get('buyer_barangay'),
        city=row.get('buyer_city_municipality'),
        province=row.get('buyer_province'),
        region=row.get('buyer_region'),
    )
    return {
        "order_item_id": row.get('order_item_id'),
        "suborder_id": row.get('suborder_id'),
        "order_id": row.get('order_id'),
        "order_reference": row.get('order_reference'),
        "sub_reference": row.get('sub_reference'),
        "item_reference": row.get('item_reference'),
        "product_name": row.get('product_name'),
        "quantity": row.get('quantity'),
        "order_created_at": row.get('order_created_at'),
        "updated_at": row.get('updated_at'),
        "updated_at_label": _format_datetime_label(row.get('updated_at')),
        "status": row.get('status'),
        "pickup_status": pickup_state,
        "pickup_rider_id": row.get('pickup_rider_id'),
        "pickup_claimed_at": row.get('pickup_claimed_at'),
        "pickup_completed_at": row.get('pickup_completed_at'),
        "seller_name": seller_name or row.get('store_name') or 'Seller',
        "seller_store": row.get('store_name') or seller_name or 'Seller',
        "seller_location": pickup_location,
        "pickup_location": pickup_location,
        "buyer_id": row.get('buyer_id'),
        "buyer_name": buyer_name or 'Buyer',
        "buyer_phone": row.get('buyer_phone'),
        "dropoff_location": dropoff_location,
        "shipping_fee": shipping_fee,
        "subtotal": subtotal,
        "convenience_fee": convenience_fee,
        "pickup_total": pickup_total,
        "projected_commission": projected_commission,
        "actual_commission": float(actual_commission) if actual_commission is not None else None,
        "display_commission": display_commission,
        "commission_label": commission_label,
    }


def getRiderPickups():
    rider, error = _ensure_rider_auth()
    if error:
        return error

    scope = request.args.get('scope', 'available').lower()
    if scope not in ('available', 'mine'):
        scope = 'available'

    query = _pickup_query(scope)
    params = (rider['user_id'],) if scope == 'mine' else ()
    rows = executeGet(query, params)
    if isinstance(rows, tuple):
        return rows

    pickups = [_serialize_pickup(row) for row in rows]
    return responseData("success", "Pickups fetched.", pickups, 200)


def claimPickupAssignment(order_item_id):
    rider, error = _ensure_rider_auth()
    if error:
        return error

    claim_query = """
        UPDATE order_items
        SET pickup_rider_id = %s,
            pickup_status = 2,
            pickup_claimed_at = NOW(),
            pickup_completed_at = NULL
        WHERE order_items_id = %s
          AND public.order_item_pickup_status(status, pickup_status) = 1
          AND pickup_rider_id IS NULL
    """

    result = executePost(claim_query, (rider['user_id'], order_item_id))
    if isinstance(result, tuple):
        return result

    if (result or {}).get('rowcount', 0) == 0:
        return responseData("error", "This pickup has already been claimed.", "", 409)

    suborder_rows = executeGet(
        "SELECT suborder_id FROM order_items WHERE order_items_id = %s LIMIT 1",
        (order_item_id,),
    ) or []
    if suborder_rows:
        _sync_pickup_suborder(suborder_rows[0].get('suborder_id'))

    detail = _fetch_pickup_detail(order_item_id)
    return responseData("success", "Pickup assigned to you.", detail, 200)


def updatePickupStatus(order_item_id):
    rider, error = _ensure_rider_auth()
    if error:
        return error

    new_status = request.form.get('status', type=int)
    if new_status not in (3, 4):
        return responseData("error", "Invalid status.", "", 400)

    detail = _fetch_pickup_detail(order_item_id)
    if not detail:
        return responseData("error", "Pickup not found.", "", 404)

    if detail.get('pickup_rider_id') != rider['user_id']:
        return responseData("error", "You are not assigned to this pickup.", "", 403)

    current_status = detail.get('pickup_status', 0)
    allowed_previous = {3: (2, 3), 4: (2, 3, 4)}
    if current_status not in allowed_previous.get(new_status, ()): 
        return responseData("error", "Invalid pickup status transition.", "", 409)

    if new_status == 4:
        proof_rows = executeGet(
            "SELECT COUNT(*) AS c FROM delivery_proofs WHERE order_item_id = %s",
            (order_item_id,),
        ) or []
        proof_count = int(proof_rows[0].get("c") or 0) if proof_rows else 0
        if proof_count < 1:
            return responseData(
                "error",
                "Please upload a delivery proof photo before marking this order as delivered.",
                "",
                400,
            )

    set_clauses = ["pickup_status = %s"]
    params = [new_status]

    if new_status == 4:
        set_clauses.append("pickup_completed_at = NOW()")
        set_clauses.append("status = 4")
    elif new_status == 3:
        set_clauses.append("status = CASE WHEN status < 3 THEN 3 ELSE status END")

    update_query = f"""
        UPDATE order_items
        SET {', '.join(set_clauses)}
        WHERE order_items_id = %s AND pickup_rider_id = %s
    """

    params.extend([order_item_id, rider['user_id']])
    update_result = executePost(update_query, tuple(params))
    if isinstance(update_result, tuple):
        return update_result

    _sync_pickup_suborder(detail.get('suborder_id'))
    if new_status == 4:
        credit_rider_commission_for_item(order_item_id)
    notify_buyer_order_item_status(order_item_id, new_status)

    detail = _fetch_pickup_detail(order_item_id)
    return responseData("success", "Pickup status updated.", detail, 200)


def uploadDeliveryProof(order_item_id):
    rider, error = _ensure_rider_auth()
    if error:
        return error

    detail = _fetch_pickup_detail(order_item_id)
    if not detail:
        return responseData("error", "Pickup not found.", "", 404)

    if detail.get("pickup_rider_id") != rider["user_id"]:
        return responseData("error", "You are not assigned to this pickup.", "", 403)

    file = request.files.get("proof_image")
    rel_path = save_compressed_proof(file)
    if not rel_path:
        return responseData("error", "Invalid image file.", "", 400)

    lat = request.form.get("latitude")
    lng = request.form.get("longitude")
    try:
        lat_val = float(lat) if lat not in (None, "") else None
    except (TypeError, ValueError):
        lat_val = None
    try:
        lng_val = float(lng) if lng not in (None, "") else None
    except (TypeError, ValueError):
        lng_val = None

    insert_q = """
        INSERT INTO delivery_proofs (suborder_id, order_item_id, rider_user_id, image_path, latitude, longitude)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    ins = executePost(insert_q, (detail.get('suborder_id'), order_item_id, rider["user_id"], rel_path, lat_val, lng_val))
    if isinstance(ins, tuple):
        return responseData("error", "Unable to save delivery proof.", "", 500)

    return responseData("success", "Delivery proof saved.", {"image_path": rel_path}, 200)


def _fetch_pickup_detail(order_item_id):
    detail_query = _pickup_base_query() + " WHERE oi.order_items_id = %s ORDER BY updated_at DESC, oi.order_items_id DESC"

    rows = executeGet(detail_query, (order_item_id,))
    if isinstance(rows, tuple) or not rows:
        return None

    return _serialize_pickup(rows[0])


def getPickupDetail(order_item_id):
    rider, error = _ensure_rider_auth()
    if error:
        return error

    summary = _fetch_pickup_detail(order_item_id)
    if not summary:
        return responseData("error", "Pickup not found.", "", 404)

    if summary.get('pickup_rider_id') != rider['user_id']:
        return responseData("error", "You are not assigned to this pickup.", "", 403)

    items_query = """
        SELECT
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
            ) AS product_image
        FROM order_items oi
        INNER JOIN products p ON oi.product_id = p.product_id
        WHERE oi.order_items_id = %s
        ORDER BY oi.order_items_id ASC
    """

    item_rows = executeGet(items_query, (order_item_id,))
    if isinstance(item_rows, tuple):
        return item_rows

    items = []
    for row in item_rows or []:
        price = float(row.get('price') or 0)
        quantity = int(row.get('quantity') or 0)
        items.append({
            'order_items_id': row.get('order_items_id'),
            'product_name': row.get('product_name'),
            'quantity': quantity,
            'unit_price': price,
            'line_total': price * quantity,
            'product_image': build_product_image_url(row.get('product_image')),
        })

    buyer_address = None
    buyer_id = summary.get('buyer_id')
    if buyer_id:
        _, formatted_address, _ = get_user_address_details(buyer_id)
        buyer_address = formatted_address

    payload = dict(summary)
    payload['items'] = items
    payload['buyer_address'] = buyer_address

    proof_rows = executeGet(
        "SELECT COUNT(*) AS c FROM delivery_proofs WHERE order_item_id = %s",
        (order_item_id,),
    ) or []
    payload["delivery_proof_count"] = int(proof_rows[0].get("c") or 0) if proof_rows else 0

    return responseData("success", "Pickup details fetched.", payload, 200)
