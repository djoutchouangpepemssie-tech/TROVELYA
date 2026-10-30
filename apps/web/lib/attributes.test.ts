import { describe, expect, it } from "vitest";

import {
  type AttributeRule,
  type CategoryTree,
  parisYear,
  rulesFor,
  validateAttributes,
} from "./attributes";

// The cases of the API's own test (apps/api/tests/unit/catalog/test_attributes.py), so the form
// and the API never disagree.
const RULES: AttributeRule[] = [
  { key: "color", type: "enum", required: true, values: ["noir", "blanc"] },
  { key: "shoe_eu", type: "decimal", min: 15, max: 52, step: 0.5 },
  { key: "width_cm", type: "int", min: 1, max: 2000 },
  { key: "isbn", type: "text", maxLength: 17 },
  { key: "edition_year", type: "year", min: 1450 },
  { key: "first_edition", type: "bool" },
];
const YEAR = 2026;
const INT32_MAX = 2 ** 31 - 1;

const check = (values: Record<string, unknown>, rules = RULES) =>
  validateAttributes(values, rules, YEAR);

describe("attributes checked as the API checks them", () => {
  it("keeps valid values in the category's order, text trimmed", () => {
    const [values, errors] = check({
      first_edition: true,
      isbn: "  978-2-07-036024-5 ",
      color: "noir",
      shoe_eu: 42.5,
      width_cm: 30,
      edition_year: 1957,
    });
    expect(errors).toEqual([]);
    expect(Object.entries(values)).toEqual([
      ["color", "noir"],
      ["shoe_eu", 42.5],
      ["width_cm", 30],
      ["isbn", "978-2-07-036024-5"],
      ["edition_year", 1957],
      ["first_edition", true],
    ]);
  });

  it("lets optional attributes be absent or null", () => {
    expect(check({ color: "blanc", isbn: null })).toEqual([{ color: "blanc" }, []]);
  });

  it.each([
    [{ color: null }, ["color", "required"]],
    [{ color: "violet" }, ["color", "not_in_list"]],
    [{ color: 3 }, ["color", "type"]],
    [{ shoe_eu: 14.5 }, ["shoe_eu", "too_small"]],
    [{ shoe_eu: 52.5 }, ["shoe_eu", "too_large"]],
    [{ shoe_eu: 42.3 }, ["shoe_eu", "step"]],
    [{ shoe_eu: "42" }, ["shoe_eu", "type"]],
    [{ shoe_eu: NaN }, ["shoe_eu", "type"]],
    [{ width_cm: 0 }, ["width_cm", "too_small"]],
    [{ width_cm: 2001 }, ["width_cm", "too_large"]],
    [{ width_cm: 12.5 }, ["width_cm", "type"]],
    [{ width_cm: true }, ["width_cm", "type"]],
    [{ isbn: "9".repeat(18) }, ["isbn", "too_long"]],
    [{ isbn: "   " }, ["isbn", "empty"]],
    [{ isbn: 978 }, ["isbn", "type"]],
    [{ edition_year: 1449 }, ["edition_year", "too_small"]],
    [{ edition_year: "1957" }, ["edition_year", "type"]],
    [{ first_edition: "oui" }, ["first_edition", "type"]],
    [{ first_edition: 1 }, ["first_edition", "type"]],
    [{ size_eu: 42 }, ["size_eu", "unknown"]],
    [{ width_cm: Infinity }, ["width_cm", "too_large"]], // 10**400 in the API's test
    [{ shoe_eu: Infinity }, ["shoe_eu", "too_large"]],
    [{ isbn: "978\x00" }, ["isbn", "invalid_characters"]],
    [{ isbn: "978\n2" }, ["isbn", "invalid_characters"]],
    [{ isbn: " ​ " }, ["isbn", "empty"]],
    [{ isbn: "978\ud800" }, ["isbn", "invalid_characters"]],
  ])("%o is refused with %o", (given, error) => {
    expect(check({ color: "noir", ...given })[1]).toContainEqual(error);
  });

  it("reports every error at once", () => {
    expect(check({ shoe_eu: 99, brand_new: 1 })[1].sort()).toEqual([
      ["brand_new", "unknown"],
      ["color", "required"],
      ["shoe_eu", "too_large"],
    ]);
  });

  it.each([{ shoe_eu: 15 }, { shoe_eu: 52 }, { width_cm: 1 }, { width_cm: 2000 }])(
    "includes the bounds: %o",
    (given) => {
      expect(check({ color: "noir", ...given })[1]).toEqual([]);
    },
  );

  it("counts the step from the minimum, or from zero", () => {
    const odd: AttributeRule[] = [{ key: "odd", type: "int", min: 1, step: 2 }];
    expect(check({ odd: 3 }, odd)[1]).toEqual([]);
    expect(check({ odd: 4 }, odd)[1]).toEqual([["odd", "step"]]);
    const dozens: AttributeRule[] = [{ key: "dozens", type: "int", step: 12 }];
    expect(check({ dozens: 24 }, dozens)[1]).toEqual([]);
    expect(check({ dozens: 25 }, dozens)[1]).toEqual([["dozens", "step"]]);
  });

  it("drops invisible characters from text", () => {
    expect(check({ color: "noir", isbn: "978​-2" })[0].isbn).toBe("978-2");
  });

  it("ends years next year, and keeps a lower maximum of the seed", () => {
    expect(check({ color: "noir", edition_year: YEAR + 1 })[1]).toEqual([]);
    expect(check({ color: "noir", edition_year: YEAR + 2 })[1]).toEqual([
      ["edition_year", "too_large"],
    ]);
    expect(validateAttributes({ color: "noir", edition_year: 2028 }, RULES, 2027)[1]).toEqual([]);
    expect(check({ color: "noir", edition_year: 1e30 })[1]).toEqual([
      ["edition_year", "too_large"],
    ]);
    const vintage: AttributeRule[] = [{ key: "vintage", type: "year", min: 1900, max: 2000 }];
    expect(check({ vintage: 2001 }, vintage)[1]).toEqual([["vintage", "too_large"]]);
  });

  it.each([
    [INT32_MAX, null],
    [INT32_MAX + 1, "too_large"],
    [-(2 ** 31), null],
    [-(2 ** 31) - 1, "too_small"],
  ])("fits integers in 32 bits: %d", (value, error) => {
    const count: AttributeRule[] = [{ key: "count", type: "int" }];
    expect(check({ count: value }, count)[1]).toEqual(error ? [["count", error]] : []);
  });
});

describe("the rules of a category, from GET /v1/categories", () => {
  const tree: CategoryTree = {
    categories: [
      {
        key: "mode.femme.robes",
        attributes: [
          { key: "clothing_size", required: true },
          { key: "length_cm", required: false },
          { key: "label", required: false },
        ],
      },
    ],
    attributes: [
      { key: "label", type: "text", values: null, max_length: 3, min: null, max: null },
      { key: "length_cm", type: "int", values: null, min: 1, max: 300, step: null },
      { key: "clothing_size", type: "enum", values: [{ key: "m" }, { key: "l" }] },
    ],
  };

  it("joins each attribute's definition, a null bound being no bound", () => {
    const rules = rulesFor(tree, "mode.femme.robes");
    expect(rules.map((rule) => rule.key)).toEqual(["clothing_size", "length_cm", "label"]);
    expect(validateAttributes({ clothing_size: "m", length_cm: 5 }, rules, YEAR)).toEqual([
      { clothing_size: "m", length_cm: 5 },
      [],
    ]);
    expect(validateAttributes({ label: "abcdef" }, rules, YEAR)[1]).toEqual([
      ["clothing_size", "required"],
      ["label", "too_long"],
    ]);
    expect(rulesFor(tree, "inconnue")).toEqual([]);
  });

  it("never takes a key of an object's prototype for a value", () => {
    const rules: AttributeRule[] = [{ key: "constructor", type: "text", required: true }];
    expect(validateAttributes({}, rules, YEAR)[1]).toEqual([["constructor", "required"]]);
  });

  it("takes an unknown type for a bug", () => {
    const rules = [{ key: "odd", type: "colour" }] as unknown as AttributeRule[];
    expect(() => validateAttributes({ odd: 1 }, rules, YEAR)).toThrow("unknown type");
  });

  it("counts the year in Paris", () => {
    expect(parisYear(new Date("2026-12-31T23:30:00Z"))).toBe(2027);
  });
});
