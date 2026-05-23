CREATE INDEX IF NOT EXISTS idx_order_items_active_cart_user
ON public.order_items (user_id, status, order_items_id DESC)
WHERE reference = '' OR reference IS NULL;

CREATE INDEX IF NOT EXISTS idx_order_items_suborder_status
ON public.order_items (suborder_id, status);

CREATE INDEX IF NOT EXISTS idx_order_items_product_user
ON public.order_items (product_id, user_id);

CREATE INDEX IF NOT EXISTS idx_wishlists_user_created
ON public.wishlists (user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_wishlists_user_product
ON public.wishlists (user_id, product_id);

CREATE INDEX IF NOT EXISTS idx_conversations_buyer_updated
ON public.conversations (buyer_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversations_seller_updated
ON public.conversations (seller_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_created
ON public.conversation_messages (conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversation_messages_unread_lookup
ON public.conversation_messages (conversation_id, is_read, sender_id);

CREATE INDEX IF NOT EXISTS idx_notifications_user_created
ON public.notifications (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
ON public.notifications (user_id, is_read);

CREATE INDEX IF NOT EXISTS idx_products_status_created
ON public.products (status, created_at DESC, product_id DESC);

CREATE INDEX IF NOT EXISTS idx_products_category_status
ON public.products (category_id, status, product_id);

CREATE INDEX IF NOT EXISTS idx_products_user_status_updated
ON public.products (user_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_product_attachments_product_status_created
ON public.product_attachments (product_id, status, created_at ASC, product_attachment_id ASC);

CREATE INDEX IF NOT EXISTS idx_categories_status
ON public.categories (status);

CREATE INDEX IF NOT EXISTS idx_addresses_user_updated
ON public.addresses (user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_orders_user_created
ON public.orders (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_orders_created
ON public.orders (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_order_suborders_seller_updated
ON public.order_suborders (seller_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_order_suborders_seller_status
ON public.order_suborders (seller_id, status);

CREATE INDEX IF NOT EXISTS idx_order_suborders_order_status
ON public.order_suborders (order_id, status);

CREATE INDEX IF NOT EXISTS idx_order_suborders_pickup_rider_updated
ON public.order_suborders (pickup_rider_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_order_suborders_pickup_status_updated
ON public.order_suborders (pickup_status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_seller_details_user_status
ON public.seller_details (user_id, status);

CREATE INDEX IF NOT EXISTS idx_seller_details_status_updated
ON public.seller_details (status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_delivery_partners_user_status
ON public.delivery_partners (user_id, status);

CREATE INDEX IF NOT EXISTS idx_delivery_partners_status_updated
ON public.delivery_partners (status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_users_role_status_updated
ON public.users (role_id, status, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower
ON public.users (lower(email));

CREATE INDEX IF NOT EXISTS idx_users_auth_user_id
ON public.users (auth_user_id);

CREATE INDEX IF NOT EXISTS idx_wallet_ledger_user_role
ON public.wallet_ledger (user_id, wallet_role);

CREATE INDEX IF NOT EXISTS idx_wallet_ledger_dedupe_lookup
ON public.wallet_ledger (entry_kind, reference_id, user_id);

CREATE INDEX IF NOT EXISTS idx_withdrawal_requests_user_role_status
ON public.withdrawal_requests (user_id, wallet_role, status);

CREATE INDEX IF NOT EXISTS idx_withdrawal_requests_created
ON public.withdrawal_requests (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_delivery_proofs_suborder
ON public.delivery_proofs (suborder_id);
