from helpers.QueryHelpers import executeGet, executePost


ORDER_ITEM_STATUS_META = {
    2: ("Order Update", "Your checkout item is now shipped."),
    3: ("Order Update", "Your checkout item is now out for delivery."),
    4: ("Order Update", "Your checkout item has been delivered."),
    7: ("Order Update", "Your checkout item was accepted by the seller."),
    8: ("Order Update", "Your checkout item was rejected by the seller."),
}


def create_notification(user_id: int, order_id: int | None, title: str, message: str, notification_type: str = "order") -> bool:
    if not user_id or not title or not message:
        return False

    result = executePost(
        """
        INSERT INTO notifications (user_id, order_id, title, message, notification_type, is_read, created_at)
        VALUES (%s, %s, %s, %s, %s, 0, NOW())
        """,
        (user_id, order_id, title[:255], message[:2000], notification_type),
    )
    return not isinstance(result, tuple)



def notify_buyer_checkout_created(user_id: int, order_id: int, reference: str, item_names: list[str] | None = None) -> None:
    if not user_id or not order_id:
        return

    cleaned_items = [str(name).strip() for name in (item_names or []) if str(name).strip()]
    item_preview = ", ".join(cleaned_items[:3])
    if len(cleaned_items) > 3:
        item_preview += ", ..."

    title = "Order Placed"
    message = f"Your checkout order {reference} was placed successfully."
    if item_preview:
        message = f"{message} Items: {item_preview}"

    create_notification(user_id, order_id, title, message, "order")



def notify_buyer_order_item_status(order_item_id: int, status: int) -> None:
    if not order_item_id or status not in ORDER_ITEM_STATUS_META:
        return

    item_rows = executeGet(
        """
        SELECT
            oi.user_id AS buyer_user_id,
            oi.reference AS order_reference,
            oi.suborder_id,
            COALESCE(p.product_name, 'Product') AS product_name
        FROM order_items oi
        LEFT JOIN products p ON p.product_id = oi.product_id
        WHERE oi.order_items_id = %s
        LIMIT 1
        """,
        (order_item_id,),
    ) or []

    if not item_rows:
        return

    row = item_rows[0]
    buyer_user_id = row.get("buyer_user_id")
    order_reference = row.get("order_reference") or ""
    suborder_id = row.get("suborder_id")
    product_name = row.get("product_name") or "Product"

    order_id = None
    sub_reference = order_reference

    if suborder_id:
        suborder_rows = executeGet(
            """
            SELECT order_id, reference
            FROM order_suborders
            WHERE suborder_id = %s
            LIMIT 1
            """,
            (suborder_id,),
        ) or []
        if suborder_rows:
            suborder_row = suborder_rows[0]
            order_id = suborder_row.get("order_id")
            sub_reference = suborder_row.get("reference") or sub_reference

    if not order_id and buyer_user_id and order_reference:
        order_rows = executeGet(
            """
            SELECT order_id
            FROM orders
            WHERE user_id = %s AND reference = %s
            ORDER BY order_id DESC
            LIMIT 1
            """,
            (buyer_user_id, order_reference),
        ) or []
        if order_rows:
            order_id = order_rows[0].get("order_id")

    title, fallback_message = ORDER_ITEM_STATUS_META[status]

    if status == 7:
        message = f"{product_name} from checkout {order_reference} was accepted by the seller."
    elif status == 8:
        message = f"{product_name} from checkout {order_reference} was rejected by the seller."
    elif status == 2:
        message = f"{product_name} from checkout {order_reference} is shipped and being prepared for pickup."
    elif status == 3:
        message = f"{product_name} from checkout {order_reference} is now out for delivery."
    elif status == 4:
        message = f"{product_name} from checkout {order_reference} has been delivered under {sub_reference}. Please confirm the order when ready."
    else:
        message = fallback_message

    create_notification(int(buyer_user_id), int(order_id) if order_id else None, title, message, "order")
