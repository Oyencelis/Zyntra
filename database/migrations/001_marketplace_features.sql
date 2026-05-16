-- Zyntra marketplace upgrade (PostgreSQL / Supabase)
-- Run once against your app database. Safe to re-run for IF NOT EXISTS / DO blocks.

-- Configurable platform settings (string values; app parses types)
CREATE TABLE IF NOT EXISTS platform_settings (
    setting_key   VARCHAR(64) PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO platform_settings (setting_key, setting_value) VALUES
    ('protection_enabled', 'true'),
    ('protection_pct_of_subtotal', '1.5'),
    ('protection_fee_min', '5'),
    ('protection_fee_max', '199'),
    ('shipping_free_threshold', '2000'),
    ('shipping_same_city', '49'),
    ('shipping_same_province', '65'),
    ('shipping_same_region', '79'),
    ('shipping_cross_region', '99'),
    ('rider_commission_pct_of_shipping', '70'),
    ('distance_shipping_base', '39'),
    ('distance_shipping_per_km', '12'),
    ('distance_shipping_max', '250')
ON CONFLICT (setting_key) DO NOTHING;

-- Buyer / seller geo (optional; when both set, distance-based shipping is used)
ALTER TABLE addresses ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;
ALTER TABLE addresses ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;

ALTER TABLE seller_details ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;
ALTER TABLE seller_details ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;

-- Product protection eligibility flag
ALTER TABLE products ADD COLUMN IF NOT EXISTS protection_eligible BOOLEAN NOT NULL DEFAULT TRUE;

-- Order-level protection (COD add-on)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS product_protection_opt_in BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS protection_fee NUMERIC(12,2) NOT NULL DEFAULT 0;

-- Proof of delivery per sub-order (history supported; latest used in UI)
CREATE TABLE IF NOT EXISTS delivery_proofs (
    proof_id       BIGSERIAL PRIMARY KEY,
    suborder_id    INTEGER NOT NULL REFERENCES order_suborders(suborder_id) ON DELETE CASCADE,
    rider_user_id  INTEGER NOT NULL,
    image_path     TEXT NOT NULL,
    latitude       DOUBLE PRECISION,
    longitude      DOUBLE PRECISION,
    captured_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_delivery_proofs_suborder ON delivery_proofs (suborder_id);

-- Signed ledger: positive credits, negative debits (withdrawals)
CREATE TABLE IF NOT EXISTS wallet_ledger (
    ledger_id     BIGSERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    wallet_role   VARCHAR(16) NOT NULL CHECK (wallet_role IN ('seller', 'rider')),
    amount        NUMERIC(14,2) NOT NULL,
    entry_kind    VARCHAR(64) NOT NULL,
    reference_id  INTEGER,
    note          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT wallet_ledger_dedupe UNIQUE (entry_kind, reference_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_wallet_ledger_user ON wallet_ledger (user_id, wallet_role);

CREATE TABLE IF NOT EXISTS withdrawal_requests (
    withdrawal_id BIGSERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    wallet_role   VARCHAR(16) NOT NULL CHECK (wallet_role IN ('seller', 'rider')),
    amount        NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    payout_notes  TEXT,
    status        VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    admin_note    TEXT,
    decided_by    INTEGER,
    decided_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_withdrawal_user ON withdrawal_requests (user_id, status);

CREATE TABLE IF NOT EXISTS withdrawal_audit (
    audit_id       BIGSERIAL PRIMARY KEY,
    withdrawal_id  BIGINT NOT NULL REFERENCES withdrawal_requests(withdrawal_id) ON DELETE CASCADE,
    action          TEXT NOT NULL,
    actor_user_id   INTEGER,
    detail          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Reviews: seller reply, moderation, photos
ALTER TABLE product_reviews ADD COLUMN IF NOT EXISTS seller_response TEXT;
ALTER TABLE product_reviews ADD COLUMN IF NOT EXISTS seller_responded_at TIMESTAMPTZ;
ALTER TABLE product_reviews ADD COLUMN IF NOT EXISTS moderation_status VARCHAR(24) NOT NULL DEFAULT 'approved';
ALTER TABLE product_reviews ADD COLUMN IF NOT EXISTS spam_score NUMERIC(6,4) NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS product_review_photos (
    photo_id    BIGSERIAL PRIMARY KEY,
    review_id   INTEGER NOT NULL REFERENCES product_reviews(review_id) ON DELETE CASCADE,
    image_path  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_photos_review ON product_review_photos (review_id);

-- Lightweight security / audit trail (append-only)
CREATE TABLE IF NOT EXISTS activity_logs (
    log_id      BIGSERIAL PRIMARY KEY,
    user_id     INTEGER,
    action      VARCHAR(128) NOT NULL,
    path        TEXT,
    ip_address  VARCHAR(64),
    detail      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
