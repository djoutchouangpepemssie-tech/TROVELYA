/**
 * Attribute values of a listing checked as the API checks them (apps/api, catalog service
 * `attributes.py`, section 7.5), so the form says what is wrong before sending (W09, P2-T09a2).
 * The API stays the judge: same codes, same order, same bounds; every error reported at once.
 *
 * Codes: `required`, `unknown`, `type`, `not_in_list`, `too_small`, `too_large`, `step` (exact
 * decimal arithmetic: 0.1 + 0.2 is not a multiple of 0.1), `too_long`, `empty`,
 * `invalid_characters`. `int` and `year` fit in a signed 32-bit integer, a `year` is at most next
 * year (plan P2, Q21). A number too large for JavaScript (Infinity) is too large, as the API says.
 * The values are those the form sends through `JSON.stringify` (an integer, never `30.0`).
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

/** What `GET /v1/categories` says of the attributes (only what the check needs). */
export type CategoryTree = {
  categories: { key: string; attributes: { key: string; required: boolean }[] }[];
  attributes: {
    key: string;
    type: AttributeType;
    values: { key: string }[] | null;
    min?: number | null;
    max?: number | null;
    step?: number | null;
    max_length?: number | null;
  }[];
};

/** The rules of a category, in its order, from the tree the API serves; none for an unknown
 * category. A bound the API leaves out comes as `null`: it is no bound. */
export function rulesFor(tree: CategoryTree, categoryKey: string): AttributeRule[] {
  const definitions = new Map(tree.attributes.map((attribute) => [attribute.key, attribute]));
  const category = tree.categories.find((candidate) => candidate.key === categoryKey);
  return (category?.attributes ?? []).flatMap(({ key, required }) => {
    const definition = definitions.get(key);
    if (!definition) return [];
    const rule: AttributeRule = { key, type: definition.type, required };
    if (definition.values) rule.values = definition.values.map((value) => value.key);
    if (definition.min != null) rule.min = definition.min;
    if (definition.max != null) rule.max = definition.max;
    if (definition.step != null) rule.step = definition.step;
    if (definition.max_length != null) rule.maxLength = definition.max_length;
    return [rule];
  });
}

/** The year the API checks against: Paris's, not the browser's (the night of 31 December). */
export function parisYear(now: Date = new Date()): number {
  const year = new Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris", year: "numeric" });
  return Number(year.format(now));
}

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
  if (rule.min != null && value < rule.min) return "too_small";
  if (rule.max != null && value > rule.max) return "too_large";
  if (rule.step != null && !isMultiple(value, rule.min ?? 0, rule.step)) return "step";
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
    default: {
      // A type the seed does not know: a bug, not the member's mistake (as the API says).
      const unknown: never = rule.type;
      throw new Error(`attribute ${rule.key}: unknown type ${String(unknown)}`);
    }
  }
}

/** Accepted values (in the category's order) and every error found; `year` is Paris's
 * (`parisYear`). */
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
    const value = Object.hasOwn(values, rule.key) ? values[rule.key] : undefined;
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
