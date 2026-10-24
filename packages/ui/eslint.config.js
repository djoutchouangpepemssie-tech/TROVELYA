import base from "@trovelya/config-eslint";

// Components never hold interface text: every label comes from the app through props.
export default [
  ...base,
  {
    files: ["src/**/*.tsx"],
    ignores: ["src/**/*.test.tsx"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXText[value=/[A-Za-zÀ-ÿ]/]",
          message: "Interface text must be passed in by the app (next-intl messages).",
        },
      ],
    },
  },
];
