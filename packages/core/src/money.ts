/**
 * Money on the client: integer minor units + ISO 4217 currency, mirror of shared/money.py.
 * Display only: amounts are always computed by the API (section 5.9).
 */
export interface Money {
  amountMinor: number;
  currency: string;
}

/** Throws unless `value` is a safe integer (no float, NaN, Infinity or precision loss). */
export function assertMinor(value: number): asserts value is number {
  if (!Number.isSafeInteger(value)) {
    throw new TypeError(`amountMinor must be a safe integer, got ${String(value)}`);
  }
}

export function formatMoney(money: Money, locale: string): string {
  assertMinor(money.amountMinor);
  const format = new Intl.NumberFormat(locale, { style: "currency", currency: money.currency });
  const digits = format.resolvedOptions().maximumFractionDigits ?? 2;
  return format.format(money.amountMinor / 10 ** digits);
}
