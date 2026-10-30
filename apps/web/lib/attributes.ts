/**
 * Attribute values of a listing checked as the API checks them (apps/api, catalog service
 * `attributes.py`, section 7.5), so the form says what is wrong before sending (W09, P2-T09a2).
 * The API stays the judge: same codes, same order, same bounds; every error reported at once.
 *
 * Codes: `required`, `unknown`, `type`, `not_in_list`, `too_small`, `too_large`, `step` (exact
 * decimal arithmetic: 0.1 + 0.2 is not a multiple of 0.1), `too_long`, `empty`,
 * `invalid_characters`. `int` and `year` fit in a signed 32-bit integer, a `year` is at most next
 * year (plan P2, Q21). A number too large for JavaScript (Infinity) is too large, as the API says.
 */

export type AttributeType = "enum" | "bool" | "text" | "int" | "year" | "decimal";

export type AttributeRule = {
  key: string;
  type: AttributeType;
  required?: boolean;
  values?: readonly string[]; // the keys of an `enum`
  min?: number;
  max?: number;
  step?: number;
  maxLength?: number;
};

export type AttributeIssue = [key: string, code: string];

const INT32_MIN = -(2 ** 31);
const INT32_MAX = 2 ** 31 - 1;

/** A number as an exact decimal: digits and the power of ten they are scaled by. */
function exact(value: number): { digits: bigint; scale: number } {
  const [mantissa = "0", exponent = "0"] = value.toString().toLowerCase().split("e");
  const [whole = "0", fraction = ""] = mantissa.split(".");
  const scale = fraction.length - Number(exponent);
  const digits = BigInt(whole + fraction);
  return scale >= 0 ? { digits, scale } : { digits: digits * 10n ** BigInt(-scale), scale: 0 };
}

function isMultiple(value: number, start: number, step: number): boolean {
  const [v, s, d] = [exact(value), exact(start), exact(step)];
  const scale = Math.max(v.scale, s.scale, d.scale);
  const at = (n: { digits: bigint; scale: number }) => n.digits * 10n ** BigInt(scale - n.scale);
  return (at(v) - at(s)) % at(d) === 0n;
}

function bounds(value: number, rule: { min?: number; max?: number; step?: number }) {
  if (rule.min !== undefined && value < rule.min) return "too_small";
  if (rule.max !== undefined && value > rule.max) return "too_large";
  if (rule.step !== undefined && !isMultiple(value, rule.min ?? 0, rule.step)) return "step";
  return null;
}

function cleanText(value: string): string | null {
  if (/[\p{Cc}\p{Cs}]/u.test(value)) return null;
  return value.replace(/\p{Cf}/gu, "").trim();
}

function infinite(value: unknown): string | null {
  if (value === Infinity) return "too_large";
  if (value === -Infinity) return "too_small";
  return null;
}

function check(rule: AttributeRule, value: unknown, year: number): [unknown, string | null] {
  switch (rule.type) {
    case "enum":
      if (typeof value !== "string") return [null, "type"];
      return [value, (rule.values ?? []).includes(value) ? null : "not_in_list"];
    case "bool":
      return [value, typeof value === "boolean" ? null : "type"];
    case "text": {
      if (typeof value !== "string") return [null, "type"];
      const text = cleanText(value);
      if (text === null) return [null, "invalid_characters"];
      if (!text) return [null, "empty"];
      if (Array.from(text).length > (rule.maxLength ?? Infinity)) return [null, "too_long"];
      return [text, null];
    }
    case "int":
    case "year": {
      const huge = infinite(value);
      if (huge) return [value, huge];
      if (typeof value !== "number" || !Number.isInteger(value)) return [null, "type"];
      if (value < INT32_MIN) return [value, "too_small"];
      if (value > INT32_MAX) return [value, "too_large"];
      const max = rule.type === "year" ? Math.min(rule.max ?? Infinity, year + 1) : rule.max;
      return [value, bounds(value, { ...rule, ...(max === undefined ? {} : { max }) })];
    }
    case "decimal": {
      const huge = infinite(value);
      if (huge) return [value, huge];
      if (typeof value !== "number" || !Number.isFinite(value)) return [null, "type"];
      return [value, bounds(value, rule)];
    }
  }
}

/** Accepted values (in the category's order) and every error found; `year` is this year. */
export function validateAttributes(
  values: Record<string, unknown>,
  rules: readonly AttributeRule[],
  year: number,
): [Record<string, unknown>, AttributeIssue[]] {
  const accepted: Record<string, unknown> = {};
  const known = new Set(rules.map((rule) => rule.key));
  const errors: AttributeIssue[] = Object.keys(values)
    .filter((key) => !known.has(key))
    .map((key) => [key, "unknown"]);
  for (const rule of rules) {
    const value = values[rule.key];
    if (value === null || value === undefined) {
      if (rule.required) errors.push([rule.key, "required"]);
      continue;
    }
    const [stored, error] = check(rule, value, year);
    if (error) errors.push([rule.key, error]);
    else accepted[rule.key] = stored;
  }
  return [accepted, errors];
}
