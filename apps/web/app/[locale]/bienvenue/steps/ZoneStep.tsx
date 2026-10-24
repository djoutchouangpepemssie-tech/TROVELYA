"use client";

import { Button, Card, Input, Select } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { onboardingApi, type Place } from "../api";
import { StepLayout } from "../StepLayout";

const RADII_KM = [1, 2, 5, 10, 25, 50, 100] as const;
const DEFAULT_RADIUS_KM = 5; // E1: local first, 5 km by default
const TOP_SIZES = ["XS", "S", "M", "L", "XL", "XXL"] as const;
const MIN_QUERY = 3;
const DEBOUNCE_MS = 300; // the geocoder allows 30 requests per minute and per member

type ZoneStepProps = {
  error: string | null;
  onError: (message: string | null) => void;
  onSkip: () => void;
  onSave: (sizes: Record<string, string>) => Promise<void>;
};

function validShoeSize(value: string): boolean {
  if (!/^\d{2}(\.5)?$/.test(value)) return false;
  const size = Number(value);
  return size >= 16 && size <= 50;
}

export function ZoneStep({ error, onError, onSkip, onSave }: ZoneStepProps) {
  const t = useTranslations("Onboarding");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Place[] | null>(null);
  const [place, setPlace] = useState<Place | null>(null);
  const [radius, setRadius] = useState<number>(DEFAULT_RADIUS_KM);
  const [locationError, setLocationError] = useState(false);
  const [top, setTop] = useState<string | undefined>(undefined);
  const [shoe, setShoe] = useState("");
  const [shoeError, setShoeError] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    const q = query.trim();
    if (place || q.length < MIN_QUERY) {
      setResults(null);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      void onboardingApi.searchPlaces(q).then((result) => {
        if (cancelled) return;
        if (result.ok) {
          setResults(result.data.data);
          onError(null);
        } else {
          onError(t("error"));
        }
      });
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, place, onError, t]);

  function locateMe() {
    setLocationError(false);
    if (!("geolocation" in navigator)) {
      setLocationError(true);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        void onboardingApi
          .reversePlace(position.coords.latitude, position.coords.longitude)
          .then((result) => {
            if (result.ok) setPlace(result.data);
            else setLocationError(true);
          });
      },
      () => {
        setLocationError(true);
      },
      { maximumAge: 600_000, timeout: 10_000 },
    );
  }

  async function submit() {
    const shoeSize = shoe.trim().replace(",", ".");
    if (shoeSize && !validShoeSize(shoeSize)) {
      setShoeError(true);
      return;
    }
    setShoeError(false);
    setSending(true);
    try {
      if (place) {
        const created = await onboardingApi.createZone({
          label: t("zone.zoneLabel"),
          place_name: place.place_name,
          lat: place.lat,
          lon: place.lon,
          radius_km: radius,
        });
        if (!created.ok) {
          onError(t("error"));
          return;
        }
      }
      const sizes: Record<string, string> = {};
      if (top) sizes.top = top;
      if (shoeSize) sizes.shoe_eu = shoeSize;
      await onSave(sizes);
    } finally {
      setSending(false);
    }
  }

  return (
    <StepLayout
      step={3}
      title={t("zone.title")}
      intro={t("zone.intro")}
      error={error}
      actions={
        <>
          <Button size="lg" disabled={sending} onClick={() => void submit()}>
            {t("continue")}
          </Button>
          <Button variant="ghost" onClick={onSkip}>
            {t("skip")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-6">
        {place ? (
          <Card className="flex items-center justify-between gap-3 p-4">
            <div>
              <p className="font-semibold">
                {t("zone.summary", { place: place.place_name, radius })}
              </p>
              <p className="text-sm text-ink-2">{t("zone.summaryHint")}</p>
            </div>
            <Button
              variant="ghost"
              onClick={() => {
                setPlace(null);
                setQuery("");
              }}
            >
              {t("zone.change")}
            </Button>
          </Card>
        ) : (
          <div className="flex flex-col gap-3">
            <Input
              label={t("zone.search")}
              hint={t("zone.searchHint")}
              type="search"
              autoComplete="off"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
              }}
            />
            {results !== null && (
              <div aria-live="polite">
                {results.length === 0 ? (
                  <p className="text-sm text-ink-2">{t("zone.noResult")}</p>
                ) : (
                  <ul aria-label={t("zone.results")} className="flex flex-col gap-1">
                    {results.map((result) => (
                      <li key={`${result.label}-${String(result.lat)}-${String(result.lon)}`}>
                        <Button
                          variant="ghost"
                          className="w-full justify-start"
                          onClick={() => {
                            setPlace(result);
                            setResults(null);
                          }}
                        >
                          {result.place_name} · {result.postal_code}
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            <div>
              <Button variant="secondary" onClick={locateMe}>
                {t("zone.useLocation")}
              </Button>
              {locationError && (
                <p role="alert" className="mt-2 text-sm text-danger">
                  {t("zone.locationDenied")}
                </p>
              )}
            </div>
          </div>
        )}

        <Select
          label={t("zone.radius")}
          placeholder={t("zone.radiusOption", { km: DEFAULT_RADIUS_KM })}
          options={RADII_KM.map((km) => ({
            value: String(km),
            label: t("zone.radiusOption", { km }),
          }))}
          value={String(radius)}
          onValueChange={(value) => {
            setRadius(Number(value));
          }}
        />

        <fieldset className="flex flex-col gap-4">
          <legend className="mb-2 font-semibold">{t("zone.sizes")}</legend>
          <Select
            label={t("zone.topSize")}
            placeholder={t("zone.topSizePlaceholder")}
            options={TOP_SIZES.map((size) => ({ value: size, label: size }))}
            {...(top === undefined ? {} : { value: top })}
            onValueChange={setTop}
          />
          <Input
            label={t("zone.shoeSize")}
            inputMode="decimal"
            value={shoe}
            onChange={(event) => {
              setShoe(event.target.value);
            }}
            {...(shoeError ? { error: t("zone.shoeSizeInvalid") } : {})}
          />
        </fieldset>
      </div>
    </StepLayout>
  );
}
