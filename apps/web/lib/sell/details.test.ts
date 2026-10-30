import { describe, expect, it } from "vitest";

import {
  type Catalogue,
  checkDetails,
  type Details,
  fromSuggestion,
  leaves,
  proposedFields,
  type Suggestion,
} from "./details";

const YEAR = 2026;

const catalogue: Catalogue = {
  categories: [
    {
      key: "mode",
      name: "Mode",
      parent_key: null,
      is_leaf: false,
      max_photos: 12,
      brand_policy: "optional",
      allowed_conditions: null,
      attributes: [],
    },
    {
      key: "mode.robes",
      name: "Robes",
      parent_key: "mode",
      is_leaf: true,
      max_photos: 12,
      brand_policy: "optional",
      allowed_conditions: null,
      attributes: [{ key: "clothing_size", required: true }],
    },
    {
      key: "mode.neuf",
      name: "Neuf",
      parent_key: "mode",
      is_leaf: true,
      max_photos: 2,
      brand_policy: "required",
      allowed_conditions: ["new_with_tags"],
      attributes: [],
    },
    {
      key: "mode.vrac",
      name: "Vrac",
      parent_key: "mode",
      is_leaf: true,
      max_photos: 12,
      brand_policy: "none",
      allowed_conditions: null,
      attributes: [],
    },
  ],
  attributes: [{ key: "clothing_size", type: "enum", values: [{ key: "m" }, { key: "l" }] }],
};

const suggestion: Suggestion = {
  suggestion_id: "s1",
  title: "Robe d'été fleurie",
  category: { key: "mode.robes", name: "Robes" },
  brand: "Sézane",
  condition: "very_good",
  attributes: { clothing_size: "m" },
  caption: "Robe fleurie posée à plat",
};

const good: Details = {
  title: "Robe d'été fleurie",
  category: "mode.robes",
  brand: "Sézane",
  condition: "very_good",
  attributes: { clothing_size: "m" },
  description: "Portée deux fois, aucune tache, taille un peu grand.",
  caption: "",
  keepCaption: false,
};

describe("the details of step 2", () => {
  it("start from the suggestion, the caption kept only if the seller says so (Q47)", () => {
    expect(fromSuggestion(suggestion)).toEqual({
      ...good,
      description: "",
      caption: "Robe fleurie posée à plat",
    });
    expect(fromSuggestion(null)).toEqual({
      title: "",
      category: "",
      brand: "",
      condition: "",
      attributes: {},
      description: "",
      caption: "",
      keepCaption: false,
    });
  });

  it("say which fields still hold what the AI proposed", () => {
    const start = fromSuggestion(suggestion);
    expect([...proposedFields(start, suggestion)]).toEqual([
      "title",
      "category",
      "brand",
      "condition",
      "attributes.clothing_size",
      "caption",
    ]);
    const edited = { ...start, title: "Robe longue", attributes: { clothing_size: "l" } };
    expect([...proposedFields(edited, suggestion)]).toEqual([
      "category",
      "brand",
      "condition",
      "caption",
    ]);
    expect(proposedFields(start, null).size).toBe(0);
  });

  it("list the leaves under their parent's name", () => {
    expect(leaves(catalogue)).toEqual([
      { key: "mode.robes", label: "Mode › Robes" },
      { key: "mode.neuf", label: "Mode › Neuf" },
      { key: "mode.vrac", label: "Mode › Vrac" },
    ]);
  });

  it("accept details the API takes, with the attributes it keeps and the brand cleaned", () => {
    expect(checkDetails({ ...good, brand: "  Sézane " }, catalogue, 1, YEAR)).toEqual({
      errors: {},
      attributes: { clothing_size: "m" },
      brand: "Sézane",
    });
  });

  it("report every field the API would refuse, as it counts", () => {
    const bad: Details = {
      title: " Robe ",
      category: "",
      brand: "",
      condition: "",
      attributes: {},
      description: "Trop court",
      caption: "",
      keepCaption: true,
    };
    expect(checkDetails(bad, catalogue, 1, YEAR).errors).toEqual({
      title: "too_short",
      category: "required",
      condition: "required",
      description: "too_short",
      caption: "required",
    });
    const long = { ...good, title: "é".repeat(121), description: `${"a".repeat(30)}\u0000` };
    expect(checkDetails(long, catalogue, 1, YEAR).errors).toEqual({
      title: "too_long",
      description: "invalid_characters",
    });
    const lines = { ...good, title: "Robe\nfleurie", caption: "a\tb", keepCaption: true };
    expect(checkDetails(lines, catalogue, 1, YEAR).errors).toEqual({
      title: "one_line",
      caption: "one_line",
    });
  });

  it("apply the category's rules: leaf, conditions, brand, photos, attributes", () => {
    expect(checkDetails({ ...good, category: "mode" }, catalogue, 1, YEAR).errors).toEqual({
      category: "required",
    });
    const strict = { ...good, category: "mode.neuf", brand: "" };
    expect(checkDetails(strict, catalogue, 3, YEAR).errors).toEqual({
      category: "too_many_photos",
      condition: "not_allowed",
      brand: "required",
    });
    expect(checkDetails({ ...good, brand: "!!!" }, catalogue, 1, YEAR).errors).toEqual({
      brand: "invalid",
    });
    const none = checkDetails({ ...good, category: "mode.vrac" }, catalogue, 1, YEAR);
    expect(none).toEqual({ errors: {}, attributes: {}, brand: null });
    const missing = { ...good, attributes: { clothing_size: "xxl" } };
    expect(checkDetails(missing, catalogue, 1, YEAR).errors).toEqual({
      "attributes.clothing_size": "not_in_list",
    });
  });
});
