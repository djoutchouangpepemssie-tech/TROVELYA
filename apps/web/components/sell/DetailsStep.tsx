"use client";

import { Button, Checkbox, Input } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { type ReactNode, useEffect, useId, useState } from "react";

import { apiCall } from "@/lib/api";
import { parisYear, rulesFor } from "@/lib/attributes";
import {
  type Catalogue,
  checkDetails,
  CONDITIONS,
  type Details,
  type DraftDetails,
  fromSuggestion,
  leaves,
  proposedFields,
  type Suggestion,
} from "@/lib/sell/details";
import type { SellPhoto } from "@/lib/sell/photos";

import { SellStep } from "./SellStep";

// `POST /v1/listings/assist` reads 1 to 4 photos: the first ones, the main photo first.
const ASSIST_PHOTOS = 4;

type AttributeView = Omit<Catalogue["attributes"][number], "values"> & {
  name: string;
  unit: string | null;
  values: { key: string; name: string }[] | null;
};
/** `GET /v1/categories`, with the names the form shows. */
type Tree = Omit<Catalogue, "attributes"> & { attributes: AttributeView[] };

export type DetailsDone = DraftDetails & { suggestion_id: string | null };

/** A native control (a long list of categories reads better on a phone) in the field's frame. */
function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string | undefined;
  error?: string | undefined;
  children: (props: {
    id: string;
    "aria-invalid"?: true;
    "aria-describedby"?: string;
  }) => ReactNode;
}) {
  const id = useId();
  const described = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean);
  return (
    <div className="trv-field">
      <label className="trv-field-label" htmlFor={id}>
        {label}
      </label>
      {children({
        id,
        ...(error ? { "aria-invalid": true as const } : {}),
        ...(described.length ? { "aria-describedby": described.join(" ") } : {}),
      })}
      {hint ? (
        <p className="trv-field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="trv-field-error" id={`${id}-error`} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/**
 * W09, step 2 (P2-T09a2): what the AI proposes from the photos fills the fields, each marked
 * « Proposé par l'IA » while it holds the proposal; the member changes any of them. Without
 * the AI (off, over the daily cap, failing) the fields start empty. Each field says what the
 * API would refuse once the member tries to go on; the first wrong one takes the focus.
 */
export function DetailsStep({
  photos,
  onDone,
}: {
  photos: SellPhoto[];
  onDone: (details: DetailsDone) => void;
}) {
  const t = useTranslations("Sell.details");
  const [tree, setTree] = useState<Tree | "failed" | null>(null);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [ai, setAi] = useState<"asking" | "done" | "limit" | "unavailable">("asking");
  const [details, setDetails] = useState<Details>(fromSuggestion(null));
  const [numbers, setNumbers] = useState<Record<string, string>>({});
  const [tried, setTried] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    void apiCall<Tree>("/v1/categories").then((result) => {
      if (live) setTree(result.ok ? result.data : "failed");
    });
    return () => {
      live = false;
    };
  }, [attempt]);

  useEffect(() => {
    let live = true;
    const media_ids = photos.slice(0, ASSIST_PHOTOS).flatMap((photo) => photo.media?.id ?? []);
    void apiCall<Suggestion>("/v1/listings/assist", {
      method: "POST",
      body: JSON.stringify({ media_ids }),
    }).then((result) => {
      if (!live) return;
      if (result.ok) {
        setSuggestion(result.data);
        setDetails(fromSuggestion(result.data));
        setAi("done");
      } else setAi(result.code === "ai_limit" ? "limit" : "unavailable");
    });
    return () => {
      live = false;
    };
  }, [photos]);

  if (tree === null || ai === "asking") {
    return (
      <SellStep step={2} title={t("title")} actions={null}>
        <p role="status" aria-busy="true">
          {t("asking")}
        </p>
      </SellStep>
    );
  }
  if (tree === "failed") {
    return (
      <SellStep
        step={2}
        title={t("title")}
        actions={
          <Button
            onClick={() => {
              setTree(null);
              setAttempt((count) => count + 1);
            }}
          >
            {t("retry")}
          </Button>
        }
      >
        <p role="alert">{t("catalogueFailed")}</p>
      </SellStep>
    );
  }

  const checked = checkDetails(details, tree, photos.length, parisYear());
  const proposed = proposedFields(details, suggestion);
  const category = tree.categories.find((candidate) => candidate.key === details.category);
  const definitions = new Map(tree.attributes.map((attribute) => [attribute.key, attribute]));
  const hint = (field: string) => (proposed.has(field) ? t("proposed") : undefined);
  const error = (field: string) => {
    const code = tried ? checked.errors[field] : undefined;
    return code ? t(`errors.${code}`) : undefined;
  };
  const change = (changes: Partial<Details>) => {
    setDetails((current) => ({ ...current, ...changes }));
  };
  const setAttribute = (key: string, value: unknown) => {
    setDetails((current) => {
      const attributes = Object.fromEntries(
        Object.entries(current.attributes).filter(([other]) => other !== key),
      );
      if (value !== undefined) attributes[key] = value;
      return { ...current, attributes };
    });
  };

  function next() {
    setTried(true);
    if (Object.keys(checked.errors).length === 0) {
      onDone({ ...checked.draft, suggestion_id: suggestion?.suggestion_id ?? null });
      return;
    }
    // After the errors render: the first field marked invalid takes the focus.
    requestAnimationFrame(() => {
      document.querySelector<HTMLElement>('main [aria-invalid="true"]')?.focus();
    });
  }

  return (
    <SellStep
      step={2}
      title={t("title")}
      intro={ai === "done" ? t("intro") : t(`ai.${ai}`)}
      actions={<Button onClick={next}>{t("next")}</Button>}
    >
      <div className="flex flex-col gap-5">
        <Input
          label={t("titleLabel")}
          value={details.title}
          onChange={(event) => {
            change({ title: event.target.value });
          }}
          {...(hint("title") ? { hint: t("proposed") } : {})}
          {...(error("title") ? { error: error("title") as string } : {})}
        />
        <Field label={t("category")} hint={hint("category")} error={error("category")}>
          {(props) => (
            <select
              {...props}
              className="trv-input w-full min-w-0"
              value={details.category}
              onChange={(event) => {
                change({ category: event.target.value });
              }}
            >
              <option value="">{t("choose")}</option>
              {leaves(tree).map((leaf) => (
                <option key={leaf.key} value={leaf.key}>
                  {leaf.label}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label={t("condition")} hint={hint("condition")} error={error("condition")}>
          {(props) => (
            <select
              {...props}
              className="trv-input w-full min-w-0"
              value={details.condition}
              onChange={(event) => {
                change({ condition: event.target.value as Details["condition"] });
              }}
            >
              <option value="">{t("choose")}</option>
              {(category?.allowed_conditions ?? CONDITIONS).map((condition) => (
                <option key={condition} value={condition}>
                  {t(`conditions.${condition}`)}
                </option>
              ))}
            </select>
          )}
        </Field>
        {category?.brand_policy === "none" ? null : (
          <Input
            label={category?.brand_policy === "required" ? t("brandRequired") : t("brand")}
            value={details.brand}
            autoComplete="off"
            onChange={(event) => {
              change({ brand: event.target.value });
            }}
            {...(hint("brand") ? { hint: t("proposed") } : {})}
            {...(error("brand") ? { error: error("brand") as string } : {})}
          />
        )}
        {(category ? rulesFor(tree, category.key) : []).map((rule) => {
          const definition = definitions.get(rule.key);
          if (!definition) return null;
          const field = `attributes.${rule.key}`;
          const label = `${definition.name}${definition.unit ? ` (${definition.unit})` : ""}${
            rule.required ? "" : ` ${t("optional")}`
          }`;
          const value = details.attributes[rule.key];
          if (rule.type === "bool") {
            return (
              <Checkbox
                key={rule.key}
                label={label}
                checked={value === true}
                onCheckedChange={(checked) => {
                  setAttribute(rule.key, checked);
                }}
              />
            );
          }
          return (
            <Field key={rule.key} label={label} hint={hint(field)} error={error(field)}>
              {(props) =>
                rule.type === "enum" ? (
                  <select
                    {...props}
                    className="trv-input w-full min-w-0"
                    value={typeof value === "string" ? value : ""}
                    onChange={(event) => {
                      setAttribute(rule.key, event.target.value || undefined);
                    }}
                  >
                    <option value="">{t("choose")}</option>
                    {(definition.values ?? []).map((option) => (
                      <option key={option.key} value={option.key}>
                        {option.name}
                      </option>
                    ))}
                  </select>
                ) : rule.type === "text" ? (
                  <input
                    {...props}
                    className="trv-input w-full min-w-0"
                    value={typeof value === "string" ? value : ""}
                    onChange={(event) => {
                      setAttribute(rule.key, event.target.value || undefined);
                    }}
                  />
                ) : (
                  <input
                    {...props}
                    className="trv-input w-full min-w-0"
                    inputMode={rule.type === "decimal" ? "decimal" : "numeric"}
                    value={
                      numbers[rule.key] ??
                      (typeof value === "number"
                        ? String(value)
                        : typeof value === "string"
                          ? value
                          : "")
                    }
                    onChange={(event) => {
                      const raw = event.target.value;
                      setNumbers((current) => ({ ...current, [rule.key]: raw }));
                      const number = Number(raw.replace(",", "."));
                      // A number the member is still typing is checked as it reads: `type`.
                      setAttribute(
                        rule.key,
                        raw.trim() === "" ? undefined : Number.isNaN(number) ? raw : number,
                      );
                    }}
                  />
                )
              }
            </Field>
          );
        })}
        <Field label={t("description")} hint={t("descriptionHint")} error={error("description")}>
          {(props) => (
            <textarea
              {...props}
              className="trv-input min-h-40 py-3"
              value={details.description}
              onChange={(event) => {
                change({ description: event.target.value });
              }}
            />
          )}
        </Field>
        {suggestion?.caption ? (
          <div className="flex flex-col gap-3">
            <Checkbox
              label={t("keepCaption")}
              checked={details.keepCaption}
              onCheckedChange={(keepCaption) => {
                change({ keepCaption });
              }}
            />
            {details.keepCaption ? (
              <Input
                label={t("caption")}
                value={details.caption}
                onChange={(event) => {
                  change({ caption: event.target.value });
                }}
                {...(hint("caption") ? { hint: t("proposed") } : {})}
                {...(error("caption") ? { error: error("caption") as string } : {})}
              />
            ) : null}
          </div>
        ) : null}
      </div>
    </SellStep>
  );
}
