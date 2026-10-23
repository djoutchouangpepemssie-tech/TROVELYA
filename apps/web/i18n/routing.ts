import { defineRouting } from "next-intl/routing";

// French first (section 4.2); the 23 other EU languages arrive in P18.
export const routing = defineRouting({
  locales: ["fr"],
  defaultLocale: "fr",
  localePrefix: "always",
});
