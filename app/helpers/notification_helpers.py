from helpers.QueryHelpers import executeGet, executePost


ORDER_ITEM_STATUS_META = {
    2: ("Order Update", "Your checkout item is now shipped."),
    3: ("Order Update", "Your checkout item is now out for delivery."),
    4: ("Order Update", "Your checkout item has been delivered."),
    7: ("Order Update", "Your checkout item was accepted by the seller."),
    8: ("Order Update", "Your checkout item was rejected by the seller."),
}


def create_notification(user_id: int, order_id: int | None, title: str, message: str, notification_type: str = "order") -> None:
    if not user_id or not title or not message:
        return

    executePost(
        """
        INSERT INTO notifications (user_id, order_id, title, message, notification_type, is_read, created_at)
        VALUES (%s, %s, %s, %s, %s, 0, NOW())
        """,
        (user_id, order_id, title[:255], message[:2000], notification_type),
    )



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

    rows = executeGet(
        """
        SELECT
            o.user_id AS buyer_user_id,
            o.order_id,
            o.reference AS order_reference,
            os.reference AS sub_reference,
            COALESCE(p.product_name, 'Product') AS product_name
        FROM order_items oi
        INNER JOIN order_suborders os ON os.suborder_id = oi.suborder_id
        INNER JOIN orders o ON o.order_id = os.order_id
        LEFT JOIN products p ON p.product_id = oi.product_id
        WHERE oi.order_items_id = %s
        LIMIT 1
        """,
        (order_item_id,),
    ) or []

    if not rows:
        return

    row = rows[0]
    buyer_user_id = row.get("buyer_user_id")
    order_id = row.get("order_id")
    order_reference = row.get("order_reference") or ""
    sub_reference = row.get("sub_reference") or order_reference
    product_name = row.get("product_name") or "Product"

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

    create_notification(int(buyer_user_id), int(order_id), title, message, "order")
