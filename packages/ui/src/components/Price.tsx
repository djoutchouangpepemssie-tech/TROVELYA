import { formatMoney } from "@trovelya/core";

/** Amount in integer minor units, shown in the monospace font (section 6.2). */
export function Price({
  amountMinor,
  currency,
  locale,
}: {
  amountMinor: number;
  currency: string;
  locale: string;
}) {
  return <span className="trv-price">{formatMoney({ amountMinor, currency }, locale)}</span>;
}
