"""Category tree, attributes and brands (section 7.5, P2-T01a).

Additions to the spec, recorded in docs/plans/P2-catalogue-annonces.md (P2-T01a):
- `categories.allowed_conditions`: the item conditions a category accepts (NULL = all), e.g.
  sealed cosmetics only (8.19).
- `categories.brand_policy`: whether a listing of the category names a brand.
- `attribute_definitions.constraints`: bounds of a value (min, max, step, max_length).
- The `path` (ltree) is the category key itself, so the tree is readable and stable: a key is
  never reused, a category leaves the tree by `is_active = false`.
- `enum_values` maps each value key to its labels ({"noir": {"fr": "Noir"}}), like `names`.
- The listing types (`listing_status`, `item_condition`) are created here: categories use
  `item_condition` already; the listing tables follow in P2-T03a.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-26
"""

from trovelya.core.migrations.sql import execute_script

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TYPE listing_status AS ENUM
  ('draft','pending_review','active','reserved','sold','withdrawn','removed','expired');
CREATE TYPE item_condition AS ENUM
  ('new_with_tags','new_without_tags','very_good','good','fair','for_parts');

CREATE TABLE categories (
  id                     UUID PRIMARY KEY,
  parent_id              UUID REFERENCES categories(id),
  key                    TEXT NOT NULL UNIQUE CHECK (key ~ '^[a-z0-9_]+(\.[a-z0-9_]+)*$'),
  path                   LTREE NOT NULL,
  names                  JSONB NOT NULL CHECK (jsonb_typeof(names) = 'object'),
  icon                   TEXT,
  position               SMALLINT NOT NULL DEFAULT 0,
  is_active              BOOLEAN NOT NULL DEFAULT true,
  requires_verification_video_above_minor BIGINT
    CHECK (requires_verification_video_above_minor >= 0),
  is_restricted          BOOLEAN NOT NULL DEFAULT false,
  vertical               TEXT NOT NULL DEFAULT 'goods'
    CHECK (vertical IN ('goods','real_estate','vehicles','services')),
  transaction_model      TEXT NOT NULL DEFAULT 'protected_purchase'
    CHECK (transaction_model IN ('protected_purchase','contact','mixed')),
  shipping_allowed       BOOLEAN NOT NULL DEFAULT true,
  protected_payment_cap_minor BIGINT CHECK (protected_payment_cap_minor > 0),
  listing_fee_minor      BIGINT CHECK (listing_fee_minor >= 0),
  max_photos             SMALLINT NOT NULL DEFAULT 12 CHECK (max_photos BETWEEN 1 AND 50),
  vat_category           TEXT NOT NULL DEFAULT 'standard',
  allowed_conditions     item_condition[] CHECK (cardinality(allowed_conditions) > 0),
  brand_policy           TEXT NOT NULL DEFAULT 'optional'
    CHECK (brand_policy IN ('required','optional','none')),
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT categories_path_matches_key CHECK (path::text = key),
  CONSTRAINT categories_root_has_no_parent CHECK ((parent_id IS NULL) = (nlevel(path) = 1))
);
CREATE INDEX categories_path_gist ON categories USING gist (path);
CREATE INDEX categories_parent_idx ON categories (parent_id);
CREATE TRIGGER categories_updated_at BEFORE UPDATE ON categories
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE attribute_definitions (
  id          UUID PRIMARY KEY,
  key         TEXT NOT NULL UNIQUE CHECK (key ~ '^[a-z][a-z0-9_]*$'),
  names       JSONB NOT NULL CHECK (jsonb_typeof(names) = 'object'),
  data_type   TEXT NOT NULL CHECK (data_type IN ('text','int','decimal','enum','bool','year')),
  enum_values JSONB,
  unit        TEXT,
  constraints JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(constraints) = 'object'),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT attribute_definitions_enum_values_check CHECK (
    (data_type = 'enum') = (
      enum_values IS NOT NULL AND jsonb_typeof(enum_values) = 'object'
      AND enum_values <> '{}'::jsonb
    )
  )
);
CREATE TRIGGER attribute_definitions_updated_at BEFORE UPDATE ON attribute_definitions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE category_attributes (
  category_id   UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  attribute_id  UUID NOT NULL REFERENCES attribute_definitions(id),
  is_required   BOOLEAN NOT NULL DEFAULT false,
  is_filterable BOOLEAN NOT NULL DEFAULT true,
  position      SMALLINT NOT NULL DEFAULT 0,
  PRIMARY KEY (category_id, attribute_id)
);
CREATE INDEX category_attributes_attribute_idx ON category_attributes (attribute_id);

CREATE TABLE brands (
  id          UUID PRIMARY KEY,
  name        CITEXT NOT NULL UNIQUE CHECK (char_length(name) BETWEEN 1 AND 80),
  slug        TEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  shop_id     UUID,
  is_verified BOOLEAN NOT NULL DEFAULT false,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX brands_name_trgm_idx ON brands USING gin ((name::text) gin_trgm_ops);
"""

DOWNGRADE = r"""
DROP TABLE brands;
DROP TABLE category_attributes;
DROP TABLE attribute_definitions;
DROP TABLE categories;
DROP TYPE item_condition;
DROP TYPE listing_status;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
