import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import globals from "globals";
import tseslint from "typescript-eslint";

/** Base ESLint flat config shared by every TypeScript package. */
export default tseslint.config(
  { ignores: ["dist/**", ".next/**", "coverage/**", "*.config.*"] },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      globals: { ...globals.node },
      parserOptions: { projectService: true },
    },
  },
  prettier,
);
