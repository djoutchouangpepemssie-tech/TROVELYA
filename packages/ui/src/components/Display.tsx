import { Avatar as AvatarPrimitive } from "radix-ui";
import type { HTMLAttributes, ReactNode } from "react";

export type BadgeTone = "neutral" | "brand" | "success" | "warning" | "danger" | "live";

export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: ReactNode }) {
  return (
    <span className="trv-badge" data-tone={tone}>
      {children}
    </span>
  );
}

/** Image with initials as fallback; `name` is the accessible text. */
export function Avatar({
  src,
  name,
  initials,
  size = 40,
}: {
  src?: string;
  name: string;
  initials: string;
  size?: number;
}) {
  return (
    <AvatarPrimitive.Root className="trv-avatar" style={{ width: size, height: size }}>
      {src ? <AvatarPrimitive.Image src={src} alt={name} /> : null}
      <AvatarPrimitive.Fallback aria-label={name}>{initials}</AvatarPrimitive.Fallback>
    </AvatarPrimitive.Root>
  );
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={["trv-card", className].filter(Boolean).join(" ")} {...props} />;
}

/** Loading placeholder (section 6.3: skeletons, never full-screen spinners). */
export function Skeleton({
  width = "100%",
  height = 16,
}: {
  width?: number | string;
  height?: number | string;
}) {
  return <span className="trv-skeleton" aria-hidden="true" style={{ width, height }} />;
}

/** Empty states always offer a way forward (section 6.3). */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="trv-empty-state">
      <p className="trv-empty-state-title">{title}</p>
      <p className="trv-empty-state-description">{description}</p>
      {action}
    </div>
  );
}

export type SquircleFamily =
  "blue" | "sky" | "teal" | "red" | "orange" | "gold" | "green" | "night" | "ink";

/** 60 px gradient squircle holding a menu icon, with an optional counter (section 6.2). */
export function Squircle({
  family,
  icon,
  count,
  countLabel,
}: {
  family: SquircleFamily;
  icon: ReactNode;
  count?: number;
  countLabel?: string;
}) {
  return (
    <span className="trv-squircle" data-family={family}>
      {icon}
      {count ? (
        <span className="trv-squircle-count" aria-label={countLabel}>
          {count > 99 ? "99+" : count}
        </span>
      ) : null}
    </span>
  );
}

/** Floating "Liquid Glass" surface; opaque when backdrop-filter or transparency is unwanted. */
export function LiquidGlass({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={["trv-glass", className].filter(Boolean).join(" ")} {...props} />;
}
