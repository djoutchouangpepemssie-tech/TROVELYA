import nextPlugin from "@next/eslint-plugin-next";
import base from "@trovelya/config-eslint";

// No hard-coded interface text (section 4.2): every string shown to users comes from
// messages/*.json through next-intl.
const noLiteralText = {
  files: ["app/**/*.tsx", "components/**/*.tsx"],
  rules: {
    "no-restricted-syntax": [
      "error",
      {
        selector: "JSXText[value=/[A-Za-zÀ-ÿ]/]",
        message: "Interface text must come from messages/*.json (next-intl).",
      },
      {
        selector:
          "JSXAttribute[name.name=/^(alt|title|placeholder|aria-label)$/] > Literal[value=/[A-Za-zÀ-ÿ]/]",
        message: "Interface text must come from messages/*.json (next-intl).",
      },
    ],
  },
};

export default [
  {
    ignores: [".next/**", "next-env.d.ts", "public/**", "playwright-report/**", "test-results/**"],
  },
  ...base,
  {
    plugins: { "@next/next": nextPlugin },
    rules: {
      ...nextPlugin.configs.recommended.rules,
      ...nextPlugin.configs["core-web-vitals"].rules,
    },
  },
  noLiteralText,
  // Temporary mock-up demo (app/[locale]/demo/README.md): its text is the mock-up's fictitious
  // copy, kept next to the screens so the whole demo is removed by deleting one folder.
  {
    files: ["app/[[]locale]/demo/**/*.tsx"],
    rules: { "no-restricted-syntax": "off", "@next/next/no-img-element": "off" },
  },
];
