import "./demo.css";

import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

// Temporary mock-up demo (README.md): fictitious data, never indexed, never in production.
export const metadata: Metadata = {
  title: "Démonstration de la maquette · TROVÉLYA",
  robots: { index: false, follow: false },
};

export default function DemoLayout({ children }: { children: ReactNode }) {
  if (process.env.VERCEL_ENV === "production") notFound();
  return (
    <div className="trv-demo">
      <aside className="trv-demo-strip" aria-label="Démonstration">
        <strong>Démonstration · données fictives</strong>
        <span>Les produits, vendeurs et prix de ces pages ne sont pas réels.</span>
        <Link href="/fr/legal/cookies">Gestion des cookies</Link>
        <Link href="/fr">Quitter la démonstration</Link>
      </aside>
      {children}
    </div>
  );
}
