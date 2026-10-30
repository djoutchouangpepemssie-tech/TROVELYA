/**
 * The details of a listing being made (W09, step 2, P2-T09a2): what the AI proposed, changed
 * field by field by the member, checked as the API checks a draft (`schemas.py` Title,
 * Description, BrandName, Caption; `draft_rules.py` category, condition, brand, photos; the
 * attributes by `validateAttributes`), so each field says what is wrong before sending.
 */

import { type CategoryTree, rulesFor, validateAttributes } from "../attributes";

export const CONDITIONS = [
  "new_with_tags",
  "new_without_tags",
  "very_good",
  "good",
  "fair",
  "for_parts",
] as const;
export type ItemCondition = (typeof CONDITIONS)[number];

/** `POST /v1/listings/assist`, as the API cleaned it: never a value the catalogue refuses. */
export type Suggestion = {
  suggestion_id: string;
  title: string | null;
  category: { key: string; name: string } | null;
  brand: string | null;
  condition: ItemCondition | null;
  attributes: Record<string, unknown>;
  caption: string | null;
  price_range?: { low: { amount_minor: number }; high: { amount_minor: number } } | null;
};

/** What `GET /v1/categories` says, as far as step 2 needs. */
export type Catalogue = {
  categories: {
    key: string;
    name: string;
    parent_key: string | null;
    is_leaf: boolean;
    max_photos: number;
    brand_policy: "required" | "optional" | "none";
    allowed_conditions: ItemCondition[] | null;
    attributes: { key: string; required: boolean }[];
  }[];
  attributes: CategoryTree["attributes"];
};

export type Details = {
  title: string;
  category: string;
  brand: string;
  condition: ItemCondition | "";
  attributes: Record<string, unknown>;
  description: string;
  caption: string;
  keepCaption: boolean; // Q47: the caption is stored only if the seller keeps it
};

export function fromSuggestion(suggestion: Suggestion | null): Details {
  return {
    title: suggestion?.title ?? "",
    category: suggestion?.category?.key ?? "",
    brand: suggestion?.brand ?? "",
    condition: suggestion?.condition ?? "",
    attributes: { ...suggestion?.attributes },
    description: "",
    caption: suggestion?.caption ?? "",
    keepCaption: false,
  };
}

/** The fields still holding what the AI proposed (marked « Proposé par l'IA »). */
export function proposedFields(details: Details, suggestion: Suggestion | null): Set<string> {
  const same = new Set<string>();
  if (!suggestion) return same;
  const pairs: [string, unknown, unknown][] = [
    ["title", details.title, suggestion.title],
    ["category", details.category, suggestion.category?.key],
    ["brand", details.brand, suggestion.brand],
    ["condition", details.condition, suggestion.condition],
    ...Object.entries(suggestion.attributes).map(([key, value]): [string, unknown, unknown] => [
      `attributes.${key}`,
      details.attributes[key],
      value,
    ]),
    ["caption", details.caption, suggestion.caption],
  ];
  for (const [field, value, proposed] of pairs) {
    if (proposed != null && value === proposed) same.add(field);
  }
  return same;
}

/** The categories a listing may go in, under their parent's name, in the API's order. */
export function leaves(catalogue: Catalogue): { key: string; label: string }[] {
  const names = new Map(catalogue.categories.map((category) => [category.key, category.name]));
  return catalogue.categories
    .filter((category) => category.is_leaf)
    .map((category) => {
      const parent = category.parent_key ? names.get(category.parent_key) : undefined;
      return { key: category.key, label: parent ? `${parent} › ${category.name}` : category.name };
    });
}

const length = (text: string) => Array.from(text).length;
// Control characters but line breaks and tabs, as `_printable`.
const CONTROL = /\p{Cc}/u;

/** A text as the API's constrained strings: stripped, then its length, then its characters. */
function text(value: string, min: number, max: number, oneLine: boolean): string | null {
  const stripped = value.replace(/\r\n?/g, "\n").trim();
  if (length(stripped) < min) return min === 1 ? "required" : "too_short";
  if (length(stripped) > max) return "too_long";
  if (CONTROL.test(stripped.replace(/[\n\t]/g, ""))) return "invalid_characters";
  if (oneLine && /[\n\t]/.test(stripped)) return "one_line";
  return null;
}

export type Checked = {
  errors: Record<string, string>; // by field, `attributes.<key>` for an attribute
  attributes: Record<string, unknown>; // the values the API keeps
  brand: string | null; // none when the category takes no brand
};

/** Every error a draft of these details would get, for `photos` photos; `year` is Paris's. */
export function checkDetails(
  details: Details,
  catalogue: Catalogue,
  photos: number,
  year: number,
): Checked {
  const errors: Record<string, string> = {};
  const add = (field: string, code: string | null) => {
    if (code && !(field in errors)) errors[field] = code;
  };
  add("title", text(details.title, 5, 120, true));
  add("description", text(details.description, 20, 5000, false));
  if (details.keepCaption) add("caption", text(details.caption, 1, 300, true));
  const category = catalogue.categories.find(
    (candidate) => candidate.key === details.category && candidate.is_leaf,
  );
  if (!category) add("category", "required");
  else if (photos > category.max_photos) add("category", "too_many_photos");
  if (!details.condition) add("condition", "required");
  else if (category?.allowed_conditions && !category.allowed_conditions.includes(details.condition))
    add("condition", "not_allowed");

  let brand: string | null = details.brand.trim() || null;
  if (category?.brand_policy === "none") brand = null;
  else if (brand === null) add("brand", category?.brand_policy === "required" ? "required" : null);
  else if (length(brand) > 80) add("brand", "too_long");
  else if (!/[\p{L}\p{N}]/u.test(brand)) add("brand", "invalid");
  else add("brand", text(brand, 1, 80, true));

  if (!category) return { errors, attributes: {}, brand };
  // Only the category's own attributes are sent: those of a category left behind are dropped.
  const rules = rulesFor(catalogue, category.key);
  const own = Object.fromEntries(
    rules
      .filter((rule) => Object.hasOwn(details.attributes, rule.key))
      .map((rule) => [rule.key, details.attributes[rule.key]]),
  );
  const [attributes, issues] = validateAttributes(own, rules, year);
  for (const [key, code] of issues) add(`attributes.${key}`, code);
  return { errors, attributes, brand };
}
