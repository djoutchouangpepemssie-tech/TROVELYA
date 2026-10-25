/** Icons drawn in the mock-up, shared by the demo screens. */

import type { CSSProperties } from "react";

export function VerifiedIcon({ size = 13, hidden = false }: { size?: number; hidden?: boolean }) {
  if (hidden) return null;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" role="img" aria-label="Vendeur vérifié">
      <path
        d="M12 2.8 4.6 5.8v6.1c0 4.6 3.1 7.8 7.4 9.3 4.3-1.5 7.4-4.7 7.4-9.3V5.8z"
        fill="#1D2BFF"
      />
      <path
        d="m8.6 12 2.4 2.4 4.6-4.8"
        fill="none"
        stroke="#FFFFFF"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function HeartIcon({ on, size = 17 }: { on: boolean; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.3a4.3 4.3 0 0 1 7.5 2.5C19.5 15.4 12 20 12 20z"
        style={on ? { fill: "#D93026", stroke: "#D93026" } : { fill: "none", stroke: "#0B0B0F" }}
        strokeWidth="1.9"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function BellIcon({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z" />
      <path d="M10 20.5a2 2 0 0 0 4 0" />
    </svg>
  );
}

/** Fill colours of the mock-up's badges by sale mode. */
export function badgeStyle(kind: "live" | "auc" | "buy"): CSSProperties {
  if (kind === "live") return { background: "#D93026", color: "#FFFFFF" };
  if (kind === "auc") return { background: "rgba(11,11,15,0.78)", color: "#FFFFFF" };
  return { background: "rgba(255,255,255,0.9)", color: "#0B0B0F" };
}

/** "18 500 €": French grouping with a plain space, as in the mock-up. */
export function euros(amount: number): string {
  return `${amount.toLocaleString("fr-FR").replace(/[\u202f\u00a0]/g, " ")} €`;
}
