"""Roles, named permissions and dual approval (sections 3.1, 3.2 and 7.3, P1-T01b).

Encoding of the section 3.2 matrix in `role_permissions`:
- allowed            → requires_approval = false, limit_minor = NULL
- 🔒 (dual approval)  → requires_approval = true
- "✅ ≤ 500 € · 🔒 > 500 €" → requires_approval = false, limit_minor = 50000 (cents); above the
  limit the action needs dual approval.
Object conditions ("if reported", "linked to a dispute", "levels 1-2") are enforced by the
policies of the phase that owns the object (P5 to P8).

Also seeds the [PARAM] values used by P1 (docs/plans/P1-identite-comptes.md, section 1).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24
"""

from trovelya.core.migrations.sql import execute_script

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE roles (key TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE permissions (key TEXT PRIMARY KEY, description TEXT NOT NULL);

CREATE TABLE role_permissions (
  role_key          TEXT REFERENCES roles,
  permission_key    TEXT REFERENCES permissions,
  requires_approval BOOLEAN NOT NULL DEFAULT false,
  limit_minor       BIGINT CHECK (limit_minor >= 0),
  PRIMARY KEY (role_key, permission_key)
);
CREATE INDEX role_permissions_permission_idx ON role_permissions (permission_key);

CREATE TABLE user_roles (
  user_id    UUID REFERENCES users,
  role_key   TEXT REFERENCES roles,
  granted_by UUID REFERENCES users,
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, role_key)
);
CREATE INDEX user_roles_role_idx ON user_roles (role_key);
CREATE INDEX user_roles_granted_by_idx ON user_roles (granted_by);

CREATE TABLE approval_requests (
  id             UUID PRIMARY KEY,
  permission_key TEXT NOT NULL REFERENCES permissions,
  requested_by   UUID NOT NULL REFERENCES users,
  payload        JSONB NOT NULL,
  reason         TEXT NOT NULL,
  status         TEXT NOT NULL CHECK (status IN ('pending','approved','rejected','expired')),
  decided_by     UUID REFERENCES users,
  decided_at     TIMESTAMPTZ,
  expires_at     TIMESTAMPTZ NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (decided_by IS NULL OR decided_by <> requested_by)
);
CREATE INDEX approval_requests_permission_idx ON approval_requests (permission_key);
CREATE INDEX approval_requests_requested_by_idx ON approval_requests (requested_by);
CREATE INDEX approval_requests_decided_by_idx ON approval_requests (decided_by);
CREATE INDEX approval_requests_pending_idx ON approval_requests (expires_at)
  WHERE status = 'pending';

INSERT INTO roles (key, description) VALUES
  ('anonymous', 'Visiteur non connecté'),
  ('member', 'Membre vérifié par e-mail ou fournisseur d''identité'),
  ('seller_individual', 'Vendeur particulier (prestataire de paiement validé)'),
  ('seller_business', 'Vendeur professionnel (entreprise vérifiée)'),
  ('staff_moderator', 'Modérateur'),
  ('staff_support', 'Agent support'),
  ('staff_trust', 'Analyste confiance'),
  ('staff_finance', 'Finance'),
  ('staff_admin', 'Administrateur'),
  ('staff_superadmin', 'Super-administrateur');

INSERT INTO permissions (key, description) VALUES
  ('listing.publish', 'Publier une annonce'),
  ('order.buy', 'Acheter'),
  ('listing.remove_any', 'Retirer une annonce d''autrui'),
  ('conversation.read_private', 'Lire une conversation privée'),
  ('dispute.resolve', 'Trancher un litige'),
  ('refund.create', 'Rembourser'),
  ('sanction.apply', 'Appliquer une sanction de niveau 1 à 3'),
  ('user.suspend', 'Suspendre un compte (niveau 4)'),
  ('payout.validate_manual', 'Valider un versement manuel'),
  ('settings.update', 'Modifier platform_settings'),
  ('staff_roles.manage', 'Gérer les rôles staff'),
  ('personal_data.export', 'Exporter des données personnelles');

INSERT INTO role_permissions (role_key, permission_key, requires_approval, limit_minor) VALUES
  ('seller_individual', 'listing.publish', false, NULL),
  ('seller_business', 'listing.publish', false, NULL),
  ('member', 'order.buy', false, NULL),
  ('seller_individual', 'order.buy', false, NULL),
  ('seller_business', 'order.buy', false, NULL),
  ('staff_moderator', 'listing.remove_any', false, NULL),
  ('staff_trust', 'listing.remove_any', false, NULL),
  ('staff_admin', 'listing.remove_any', false, NULL),
  ('staff_superadmin', 'listing.remove_any', false, NULL),
  ('staff_moderator', 'conversation.read_private', false, NULL),
  ('staff_support', 'conversation.read_private', false, NULL),
  ('staff_trust', 'conversation.read_private', false, NULL),
  ('staff_superadmin', 'conversation.read_private', false, NULL),
  ('staff_support', 'dispute.resolve', false, 50000),
  ('staff_admin', 'dispute.resolve', false, NULL),
  ('staff_superadmin', 'dispute.resolve', false, NULL),
  ('staff_support', 'refund.create', true, NULL),
  ('staff_finance', 'refund.create', false, 50000),
  ('staff_superadmin', 'refund.create', false, NULL),
  ('staff_moderator', 'sanction.apply', false, NULL),
  ('staff_trust', 'sanction.apply', false, NULL),
  ('staff_admin', 'sanction.apply', false, NULL),
  ('staff_superadmin', 'sanction.apply', false, NULL),
  ('staff_trust', 'user.suspend', true, NULL),
  ('staff_admin', 'user.suspend', true, NULL),
  ('staff_superadmin', 'user.suspend', true, NULL),
  ('staff_finance', 'payout.validate_manual', true, NULL),
  ('staff_superadmin', 'payout.validate_manual', false, NULL),
  ('staff_admin', 'settings.update', true, NULL),
  ('staff_superadmin', 'settings.update', false, NULL),
  ('staff_superadmin', 'staff_roles.manage', true, NULL),
  ('staff_admin', 'personal_data.export', true, NULL),
  ('staff_superadmin', 'personal_data.export', true, NULL);

INSERT INTO platform_settings (key, value, description) VALUES
  ('auth.magic_link_ttl_min', '15', 'Durée de validité d''un lien magique, en minutes'),
  ('auth.step_up_max_age_h', '12', 'Âge maximal de la preuve forte (action sensible), en heures'),
  ('retention.erasure_grace_days', '30', 'Délai de grâce avant effacement d''un compte, en jours'),
  ('retention.data_export_days', '7', 'Durée de conservation d''un export RGPD, en jours'),
  ('auth.min_signup_age', '15', 'Âge minimal d''inscription (8.18)'),
  ('auth.min_trade_age', '18', 'Âge minimal pour acheter, vendre et enchérir (8.18)');
"""

DOWNGRADE = r"""
DELETE FROM platform_settings WHERE key IN (
  'auth.magic_link_ttl_min', 'auth.step_up_max_age_h', 'retention.erasure_grace_days',
  'retention.data_export_days', 'auth.min_signup_age', 'auth.min_trade_age'
);
DROP TABLE approval_requests;
DROP TABLE user_roles;
DROP TABLE role_permissions;
DROP TABLE permissions;
DROP TABLE roles;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
