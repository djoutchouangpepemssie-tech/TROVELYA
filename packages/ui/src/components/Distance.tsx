export type RoundedDistance = { kind: "under-1-km" } | { kind: "km"; km: number };

const METERS_PER_KM = 1000;

/**
 * Public distance rounding (section 8.11): never the exact distance.
 * < 1 km → "less than 1 km"; < 10 km → nearest km; < 100 km → nearest 5 km;
 * ≥ 100 km → nearest 10 km.
 */
export function roundDistance(meters: number): RoundedDistance {
  if (!Number.isFinite(meters) || meters < 0) {
    throw new RangeError(`invalid distance: ${String(meters)}`);
  }
  if (meters < METERS_PER_KM) return { kind: "under-1-km" };
  const km = meters / METERS_PER_KM;
  const step = km < 10 ? 1 : km < 100 ? 5 : 10;
  return { kind: "km", km: Math.round(km / step) * step };
}

export type DistanceLabels = { underOneKm: string; km: (km: number) => string };

export function Distance({ meters, labels }: { meters: number; labels: DistanceLabels }) {
  const rounded = roundDistance(meters);
  return (
    <span className="trv-distance">
      {rounded.kind === "under-1-km" ? labels.underOneKm : labels.km(rounded.km)}
    </span>
  );
}
