import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { DesignSystemShowcase } from "@/components/DesignSystemShowcase";
import { isProduction } from "@/lib/environment";

// Internal page (plan P0, E4): never indexed, never served in production.
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function DesignSystemPage() {
  if (isProduction()) {
    notFound();
  }
  return <DesignSystemShowcase />;
}
