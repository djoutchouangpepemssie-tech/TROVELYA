/**
 * Legal documents (section 14.10): Markdown files in `content/legal/<locale>/`, each with the
 * version recorded when it is accepted (`consents.policy_version`). Provisional until a lawyer
 * validates them before the public launch.
 */

export const LEGAL_DOCUMENTS = ["cgu", "confidentialite", "cookies", "mentions"] as const;
export type LegalDocument = (typeof LEGAL_DOCUMENTS)[number];

export const POLICY_VERSIONS: Record<LegalDocument, string> = {
  cgu: "provisoire-2026-10",
  confidentialite: "provisoire-2026-10",
  cookies: "provisoire-2026-10",
  mentions: "provisoire-2026-10",
};

/** Version of the terms accepted at sign-up (purpose `terms`). */
export const TERMS_VERSION = POLICY_VERSIONS.cgu;
/** Version shown with the cookie choices (`analytics`, `personalised_ads`…). */
export const COOKIE_POLICY_VERSION = POLICY_VERSIONS.cookies;
/** Version shown with the precise location consent. */
export const PRIVACY_POLICY_VERSION = POLICY_VERSIONS.confidentialite;

export function isLegalDocument(value: string): value is LegalDocument {
  return (LEGAL_DOCUMENTS as readonly string[]).includes(value);
}
