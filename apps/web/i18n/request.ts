import { locale as rootLocale } from "next/root-params";
import { hasLocale } from "next-intl";
import { getRequestConfig } from "next-intl/server";

import { routing } from "./routing";

export default getRequestConfig(async ({ locale }) => {
  // An explicit locale (getTranslations({ locale })) wins; otherwise the [locale] root param.
  const requested = locale ?? (await rootLocale());
  const resolved = hasLocale(routing.locales, requested) ? requested : routing.defaultLocale;
  const messages = (await import(`../messages/${resolved}.json`)) as {
    default: Record<string, unknown>;
  };
  return { locale: resolved, messages: messages.default };
});
