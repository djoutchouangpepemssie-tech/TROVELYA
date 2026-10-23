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
