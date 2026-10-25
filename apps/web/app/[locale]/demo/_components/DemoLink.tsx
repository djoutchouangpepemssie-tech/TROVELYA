import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import { demoHref } from "./data";

type Props = {
  /** Mock-up screen the link points to (its file name, e.g. "WebCatalog"). */
  to: string;
  className?: string;
  style?: CSSProperties;
  "aria-label"?: string;
  children: ReactNode;
};

/** A mock-up link: inside the demo when the screen exists, plain text otherwise (no dead link). */
export function DemoLink({ to, children, ...rest }: Props) {
  const href = demoHref(to);
  if (href === null) {
    // An icon-only item keeps its name for screen readers (a label needs a role on a span).
    const role = rest["aria-label"] ? "img" : undefined;
    return (
      <span role={role} {...rest} className={`demo-nolink ${rest.className ?? ""}`.trim()}>
        {children}
      </span>
    );
  }
  return (
    <Link href={href} {...rest}>
      {children}
    </Link>
  );
}
