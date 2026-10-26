"""Listings (section 7.5, P2-T03a1); the tables hanging on them follow in P2-T03a2.

Additions to the spec, recorded in docs/plans/P2-catalogue-annonces.md:
- `short_id` (E10): 10 random base-62 characters, for the URL `/annonce/[slug]-[short_id]`.
- `location_source`, `location_source_id` (E14): the seller's address or zone the position was
  taken from; a new source draws a new public offset, reading it again never does.
- `embedding VECTOR(1024)` and `embedding_model` (E5): the dimension of the AWS model; the
  model is named whenever there is an embedding.
- Value checks the spec leaves implicit: country code, currency, sale modes of section 4,
  counters, quality score 0-100, minimum offer at most the price.
- Listings are hidden by `deleted_at`; rows are deleted only with an account's erasure.

Indexes of 7.5, except `listings_search_idx` (P3) and the HNSW index on `embedding` (P2-T11).

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-26
"""

from trovelya.core.migrations.sql import execute_script

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE listings (
  id                     UUID PRIMARY KEY,
  short_id               TEXT NOT NULL UNIQUE CHECK (short_id ~ '^[0-9A-Za-z]{10}$'),
  seller_id              UUID NOT NULL REFERENCES users(id),
  shop_id                UUID,
  product_variant_id     UUID,
  status                 listing_status NOT NULL DEFAULT 'draft',
  title                  TEXT NOT NULL CHECK (char_length(title) BETWEEN 5 AND 120),
  description            TEXT NOT NULL CHECK (char_length(description) BETWEEN 20 AND 5000),
  category_id            UUID NOT NULL REFERENCES categories(id),
  brand_id               UUID REFERENCES brands(id),
  condition              item_condition NOT NULL,
  attributes             JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(attributes) = 'object'),
  price_minor            BIGINT NOT NULL CHECK (price_minor BETWEEN 100 AND 100000000),
  currency               CHAR(3) NOT NULL DEFAULT 'EUR' CHECK (currency ~ '^[A-Z]{3}$'),
  original_price_minor   BIGINT CHECK (original_price_minor > 0),
  quantity               INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
  accepts_offers         BOOLEAN NOT NULL DEFAULT true,
  min_offer_minor        BIGINT,
  handover_enabled       BOOLEAN NOT NULL DEFAULT true,
  shipping_enabled       BOOLEAN NOT NULL DEFAULT true,
  parcel_size            TEXT CHECK (parcel_size IN ('xs','s','m','l','xl')),
  weight_g               INTEGER CHECK (weight_g > 0),
  location               GEOGRAPHY(Point,4326) NOT NULL,
  location_public        GEOGRAPHY(Point,4326) NOT NULL,
  h3_r7                  BIGINT NOT NULL,
  h3_r9                  BIGINT NOT NULL,
  place_name             TEXT NOT NULL CHECK (char_length(place_name) BETWEEN 1 AND 120),
  country_code           CHAR(2) NOT NULL CHECK (country_code ~ '^[A-Z]{2}$'),
  location_source        TEXT NOT NULL CHECK (location_source IN ('address','zone')),
  location_source_id     UUID NOT NULL,
  sale_modes             TEXT[] NOT NULL DEFAULT '{fixed_price}' CHECK (
    cardinality(sale_modes) > 0 AND array_position(sale_modes, NULL) IS NULL
    AND sale_modes <@ ARRAY['fixed_price','auction','live','drop','group_buy']
  ),
  is_boosted_until       TIMESTAMPTZ,
  open_to_swap           BOOLEAN NOT NULL DEFAULT false,
  passport_id            UUID,
  quality_score          SMALLINT NOT NULL DEFAULT 0 CHECK (quality_score BETWEEN 0 AND 100),
  search_document        TSVECTOR,
  embedding              VECTOR(1024),
  embedding_model        TEXT,
  resale_from_order_item_id UUID,
  published_at           TIMESTAMPTZ,
  sold_at                TIMESTAMPTZ,
  expires_at             TIMESTAMPTZ,
  view_count             INTEGER NOT NULL DEFAULT 0 CHECK (view_count >= 0),
  favorite_count         INTEGER NOT NULL DEFAULT 0 CHECK (favorite_count >= 0),
  version                INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at             TIMESTAMPTZ,
  CONSTRAINT listings_min_offer_check CHECK (min_offer_minor BETWEEN 1 AND price_minor),
  CONSTRAINT listings_embedding_model_check
    CHECK ((embedding IS NULL) = (embedding_model IS NULL))
);
CREATE INDEX listings_active_geo_idx ON listings USING gist (location) WHERE status = 'active';
CREATE INDEX listings_active_h3_idx ON listings (h3_r7) WHERE status = 'active';
CREATE INDEX listings_title_trgm_idx ON listings USING gin (title gin_trgm_ops);
CREATE INDEX listings_seller_idx ON listings (seller_id, status, created_at DESC);
CREATE INDEX listings_category_idx ON listings (category_id, status, published_at DESC);
CREATE INDEX listings_attributes_idx ON listings USING gin (attributes jsonb_path_ops);
CREATE TRIGGER listings_updated_at BEFORE UPDATE ON listings
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER listings_bump_version BEFORE UPDATE ON listings
  FOR EACH ROW EXECUTE FUNCTION bump_version();
"""

DOWNGRADE = r"""
DROP TABLE listings;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
