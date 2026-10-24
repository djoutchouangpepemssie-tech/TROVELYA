import { describe, expect, it } from "vitest";

import tokens from "../tokens.json" with { type: "json" };
import { buildThemeCss, buildTokensCss } from "./build";

describe("buildTokensCss", () => {
  const css = buildTokensCss(tokens);

  it("defines the light brand colour on :root", () => {
    expect(css).toMatch(/:root \{[^}]*--trv-color-brand: #1D2BFF;/);
  });

  it("switches to dark colours with the system preference unless light is forced", () => {
    expect(css).toMatch(
      /@media \(prefers-color-scheme: dark\) \{\s*:root:not\(\[data-theme="light"\]\) \{[^}]*--trv-color-brand: #4D5BFF;/,
    );
  });

  it("supports a forced dark theme", () => {
    expect(css).toMatch(/:root\[data-theme="dark"\] \{[^}]*--trv-color-surface: #0B0B0F;/);
  });

  it("exposes radii, spacing, motion and fonts", () => {
    expect(css).toContain("--trv-radius-pill: 999px;");
    expect(css).toContain("--trv-space-4: 16px;");
    expect(css).toContain("--trv-motion-base: 200ms;");
    expect(css).toContain("--trv-easing-standard: cubic-bezier(.2,.8,.2,1);");
    expect(css).toContain("--trv-font-mono:");
  });
});

describe("buildThemeCss", () => {
  it("maps tokens to Tailwind theme variables", () => {
    const css = buildThemeCss(tokens);
    expect(css).toContain("@theme inline {");
    expect(css).toContain("--color-brand: var(--trv-color-brand);");
    expect(css).toContain("--radius-lg: var(--trv-radius-lg);");
    expect(css).toContain("--font-sans: var(--trv-font-sans);");
    expect(css).toContain("--shadow-2: var(--trv-shadow-2);");
  });
});

// WCAG 2.2 AA: body text needs a contrast ratio of at least 4.5:1 (section 6.3).
function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r = 0, g = 0, b = 0] = channels.map((c) =>
    c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (high + 0.05) / (low + 0.05);
}

describe("text colour contrast", () => {
  const color = tokens.color as Record<string, { light: string; dark: string }>;
  const cases = (["light", "dark"] as const).flatMap((mode) =>
    ["ink", "ink-2", "ink-3"].flatMap((text) =>
      ["surface", "surface-2"].map((background) => ({ mode, text, background })),
    ),
  );

  it.each(cases)("$text on $background ($mode) is at least 4.5:1", ({ mode, text, background }) => {
    const foreground = color[text]?.[mode] ?? "";
    const back = color[background]?.[mode] ?? "";
    expect(contrast(foreground, back)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("text on coloured fills", () => {
  const color = tokens.color as Record<string, { light: string; dark: string }>;
  const fills = ["danger", "live", "success", "warning"].flatMap((fill) =>
    (["light", "dark"] as const).map((mode) => ({ fill, mode })),
  );

  // @trovelya/ui writes #0B0B0F on these fills: white would be below 4.5:1.
  it.each(fills)("ink text on $fill ($mode) is at least 4.5:1", ({ fill, mode }) => {
    expect(contrast("#0B0B0F", color[fill]?.[mode] ?? "")).toBeGreaterThanOrEqual(4.5);
  });

  it("brand fill keeps white text readable", () => {
    expect(contrast("#FFFFFF", color.brand?.light ?? "")).toBeGreaterThanOrEqual(4.5);
  });
});
