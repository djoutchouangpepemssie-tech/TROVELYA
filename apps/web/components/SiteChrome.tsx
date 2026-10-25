"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

// The temporary mock-up demo (app/[locale]/demo) brings its own header and footer.
const DEMO = /^\/[a-z]{2}\/demo(\/|$)/;

/** The site header, footer and tabs, left out of the mock-up demo pages. */
export function SiteChrome({ children }: { children: ReactNode }) {
  return DEMO.test(usePathname()) ? null : children;
}
