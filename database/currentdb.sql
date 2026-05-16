-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.activity_logs (
  log_id bigint NOT NULL DEFAULT nextval('activity_logs_log_id_seq'::regclass),
  user_id integer,
  action character varying NOT NULL,
  path text,
  ip_address character varying,
  detail text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT activity_logs_pkey PRIMARY KEY (log_id)
);
CREATE TABLE public.addresses (
  address_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  user_id integer,
  floor_unit_number character varying DEFAULT NULL::character varying,
  region character varying DEFAULT NULL::character varying,
  province character varying DEFAULT NULL::character varying,
  city_municipality character varying DEFAULT NULL::character varying,
  barangay character varying DEFAULT NULL::character varying,
  street character varying DEFAULT NULL::character varying,
  other_notes text,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  latitude double precision,
  longitude double precision,
  CONSTRAINT addresses_pkey PRIMARY KEY (address_id)
);
CREATE TABLE public.auth_sync_errors (
  auth_sync_error_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  auth_user_id uuid,
  stage text,
  error_message text,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT auth_sync_errors_pkey PRIMARY KEY (auth_sync_error_id)
);
CREATE TABLE public.categories (
  category_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  category_name character varying DEFAULT NULL::character varying,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  status integer DEFAULT 1,
  CONSTRAINT categories_pkey PRIMARY KEY (category_id)
);
CREATE TABLE public.conversation_messages (
  message_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  conversation_id integer NOT NULL,
  sender_id integer NOT NULL,
  message_text text NOT NULL,
  is_read smallint NOT NULL DEFAULT 0,
  read_at timestamp without time zone,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT conversation_messages_pkey PRIMARY KEY (message_id)
);
CREATE TABLE public.conversations (
  conversation_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  buyer_id integer NOT NULL,
  seller_id integer NOT NULL,
  order_id integer,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT conversations_pkey PRIMARY KEY (conversation_id),
  CONSTRAINT fk_conversations_buyer FOREIGN KEY (buyer_id) REFERENCES public.users(user_id),
  CONSTRAINT fk_conversations_order FOREIGN KEY (order_id) REFERENCES public.orders(order_id),
  CONSTRAINT fk_conversations_seller FOREIGN KEY (seller_id) REFERENCES public.users(user_id)
);
CREATE TABLE public.delivery_partners (
  partner_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  user_id integer,
  full_name character varying NOT NULL,
  email character varying NOT NULL,
  phone character varying NOT NULL,
  vehicle_type character varying NOT NULL,
  plate_number character varying NOT NULL,
  region character varying NOT NULL,
  province character varying NOT NULL,
  city character varying NOT NULL,
  barangay character varying NOT NULL,
  street character varying NOT NULL,
  drivers_license_path character varying NOT NULL,
  gov_id_path character varying NOT NULL,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status integer NOT NULL DEFAULT 0,
  CONSTRAINT delivery_partners_pkey PRIMARY KEY (partner_id)
);
CREATE TABLE public.delivery_proofs (
  proof_id bigint NOT NULL DEFAULT nextval('delivery_proofs_proof_id_seq'::regclass),
  suborder_id integer NOT NULL,
  rider_user_id integer NOT NULL,
  image_path text NOT NULL,
  latitude double precision,
  longitude double precision,
  captured_at timestamp with time zone NOT NULL DEFAULT now(),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT delivery_proofs_pkey PRIMARY KEY (proof_id),
  CONSTRAINT delivery_proofs_suborder_id_fkey FOREIGN KEY (suborder_id) REFERENCES public.order_suborders(suborder_id)
);
CREATE TABLE public.notifications (
  notification_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  user_id integer NOT NULL,
  order_id integer,
  title character varying NOT NULL,
  message text NOT NULL,
  notification_type text NOT NULL DEFAULT 'order'::text CHECK (notification_type = ANY (ARRAY['order'::text, 'system'::text, 'promo'::text])),
  is_read smallint NOT NULL DEFAULT 0,
  read_at timestamp without time zone,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT notifications_pkey PRIMARY KEY (notification_id)
);
CREATE TABLE public.order_items (
  order_items_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  product_id integer NOT NULL,
  user_id integer NOT NULL,
  suborder_id integer,
  quantity integer NOT NULL,
  variant_type text NOT NULL DEFAULT 'none'::text CHECK (variant_type = ANY (ARRAY['none'::text, 'sizes'::text, 'colors'::text])),
  variant_value character varying DEFAULT NULL::character varying,
  reference character varying NOT NULL,
  status integer DEFAULT 1,
  CONSTRAINT order_items_pkey PRIMARY KEY (order_items_id)
);
CREATE TABLE public.order_suborders (
  suborder_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  order_id integer NOT NULL,
  seller_id integer NOT NULL,
  reference character varying NOT NULL,
  status integer NOT NULL DEFAULT 1,
  subtotal numeric NOT NULL DEFAULT 0.00,
  shipping_fee numeric NOT NULL DEFAULT 0.00,
  tax_amount numeric NOT NULL DEFAULT 0.00,
  total_amount numeric NOT NULL DEFAULT 0.00,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  pickup_status smallint NOT NULL DEFAULT 0,
  pickup_rider_id integer,
  pickup_claimed_at timestamp without time zone,
  pickup_completed_at timestamp without time zone,
  CONSTRAINT order_suborders_pkey PRIMARY KEY (suborder_id)
);
CREATE TABLE public.orders (
  order_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  user_id integer,
  reference character varying DEFAULT NULL::character varying,
  subtotal numeric NOT NULL,
  shipping_fee numeric NOT NULL,
  tax_amount numeric NOT NULL,
  total_amount character varying DEFAULT NULL::character varying,
  cash_type character varying NOT NULL,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  status integer DEFAULT 1,
  product_protection_opt_in boolean NOT NULL DEFAULT false,
  protection_fee numeric NOT NULL DEFAULT 0,
  CONSTRAINT orders_pkey PRIMARY KEY (order_id)
);
CREATE TABLE public.payments (
  payment_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  order_id integer,
  payment_date timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  payment_amount integer,
  status integer,
  CONSTRAINT payments_pkey PRIMARY KEY (payment_id)
);
CREATE TABLE public.platform_settings (
  setting_key character varying NOT NULL,
  setting_value text NOT NULL,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT platform_settings_pkey PRIMARY KEY (setting_key)
);
CREATE TABLE public.product_attachments (
  product_attachment_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  product_id integer,
  attachment character varying DEFAULT NULL::character varying,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  status integer DEFAULT 1,
  CONSTRAINT product_attachments_pkey PRIMARY KEY (product_attachment_id)
);
CREATE TABLE public.product_review_photos (
  photo_id bigint NOT NULL DEFAULT nextval('product_review_photos_photo_id_seq'::regclass),
  review_id integer NOT NULL,
  image_path text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT product_review_photos_pkey PRIMARY KEY (photo_id),
  CONSTRAINT product_review_photos_review_id_fkey FOREIGN KEY (review_id) REFERENCES public.product_reviews(review_id)
);
CREATE TABLE public.product_reviews (
  review_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  product_id integer NOT NULL,
  user_id integer NOT NULL,
  order_items_id integer,
  reference character varying DEFAULT NULL::character varying,
  rating smallint NOT NULL,
  comment text NOT NULL,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  seller_response text,
  seller_responded_at timestamp with time zone,
  moderation_status character varying NOT NULL DEFAULT 'approved'::character varying,
  spam_score numeric NOT NULL DEFAULT 0,
  CONSTRAINT product_reviews_pkey PRIMARY KEY (review_id)
);
CREATE TABLE public.products (
  product_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  user_id integer,
  category_id integer,
  product_name character varying DEFAULT NULL::character varying,
  description text,
  price numeric DEFAULT NULL::numeric,
  qty integer,
  variant_type text NOT NULL DEFAULT 'none'::text CHECK (variant_type = ANY (ARRAY['none'::text, 'sizes'::text, 'colors'::text])),
  variant_values text,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  status integer DEFAULT 1,
  protection_eligible boolean NOT NULL DEFAULT true,
  CONSTRAINT products_pkey PRIMARY KEY (product_id)
);
CREATE TABLE public.reviews (
  review_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  order_id integer NOT NULL,
  product_id integer NOT NULL,
  user_id integer NOT NULL,
  rating smallint NOT NULL CHECK (rating >= 1 AND rating <= 5),
  comment text,
  status smallint NOT NULL DEFAULT 1,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT reviews_pkey PRIMARY KEY (review_id)
);
CREATE TABLE public.roles (
  role_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  name character varying DEFAULT NULL::character varying,
  CONSTRAINT roles_pkey PRIMARY KEY (role_id)
);
CREATE TABLE public.seller_details (
  seller_detail_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  user_id integer NOT NULL,
  store_name character varying NOT NULL,
  description text,
  region character varying DEFAULT NULL::character varying,
  province character varying DEFAULT NULL::character varying,
  city character varying DEFAULT NULL::character varying,
  barangay character varying DEFAULT NULL::character varying,
  street character varying DEFAULT NULL::character varying,
  gov_id_path character varying DEFAULT NULL::character varying,
  business_permit_path character varying DEFAULT NULL::character varying,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status integer NOT NULL DEFAULT 0,
  latitude double precision,
  longitude double precision,
  CONSTRAINT seller_details_pkey PRIMARY KEY (seller_detail_id)
);
CREATE TABLE public.users (
  user_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  role_id integer DEFAULT 2,
  firstname character varying DEFAULT NULL::character varying,
  lastname character varying DEFAULT NULL::character varying,
  email character varying NOT NULL,
  password character varying,
  phone character varying DEFAULT NULL::character varying,
  email_verified smallint DEFAULT 0,
  email_verified_at timestamp without time zone,
  email_code_hash character varying DEFAULT NULL::character varying,
  email_code_expires_at timestamp without time zone,
  email_code_attempts smallint DEFAULT 0,
  email_code_last_sent_at timestamp without time zone,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  status integer DEFAULT 1,
  otp_last_sent_at timestamp without time zone,
  auth_user_id uuid,
  CONSTRAINT users_pkey PRIMARY KEY (user_id),
  CONSTRAINT users_auth_user_id_fkey FOREIGN KEY (auth_user_id) REFERENCES auth.users(id)
);
CREATE TABLE public.wallet_ledger (
  ledger_id bigint NOT NULL DEFAULT nextval('wallet_ledger_ledger_id_seq'::regclass),
  user_id integer NOT NULL,
  wallet_role character varying NOT NULL CHECK (wallet_role::text = ANY (ARRAY['seller'::character varying, 'rider'::character varying]::text[])),
  amount numeric NOT NULL,
  entry_kind character varying NOT NULL,
  reference_id integer,
  note text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT wallet_ledger_pkey PRIMARY KEY (ledger_id)
);
CREATE TABLE public.wishlists (
  wishlist_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  user_id integer NOT NULL,
  product_id integer NOT NULL,
  created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT wishlists_pkey PRIMARY KEY (wishlist_id)
);
CREATE TABLE public.withdrawal_audit (
  audit_id bigint NOT NULL DEFAULT nextval('withdrawal_audit_audit_id_seq'::regclass),
  withdrawal_id bigint NOT NULL,
  action text NOT NULL,
  actor_user_id integer,
  detail text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT withdrawal_audit_pkey PRIMARY KEY (audit_id),
  CONSTRAINT withdrawal_audit_withdrawal_id_fkey FOREIGN KEY (withdrawal_id) REFERENCES public.withdrawal_requests(withdrawal_id)
);
CREATE TABLE public.withdrawal_requests (
  withdrawal_id bigint NOT NULL DEFAULT nextval('withdrawal_requests_withdrawal_id_seq'::regclass),
  user_id integer NOT NULL,
  wallet_role character varying NOT NULL CHECK (wallet_role::text = ANY (ARRAY['seller'::character varying, 'rider'::character varying]::text[])),
  amount numeric NOT NULL CHECK (amount > 0::numeric),
  payout_notes text,
  status character varying NOT NULL DEFAULT 'pending'::character varying CHECK (status::text = ANY (ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying]::text[])),
  admin_note text,
  decided_by integer,
  decided_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT withdrawal_requests_pkey PRIMARY KEY (withdrawal_id)
);