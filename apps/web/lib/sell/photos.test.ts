import { describe, expect, it } from "vitest";

import { MAX_PHOTOS, photos, type PhotoAction, type SellPhoto } from "./photos";

const media = {
  id: "m1",
  purpose: "listing",
  status: "ready",
  variants: [],
  rejection_reason: null,
};

function run(...actions: PhotoAction[]): SellPhoto[] {
  return actions.reduce<SellPhoto[]>(photos, []);
}

describe("the photos of a listing being made (W09, step 1)", () => {
  it("adds photos as being sent, up to the most a listing takes", () => {
    const added = run({ type: "add", photos: [{ key: "a", name: "a.jpg", preview: "blob:a" }] });
    expect(added).toEqual([{ key: "a", name: "a.jpg", preview: "blob:a", status: "sending" }]);
    const many = Array.from({ length: MAX_PHOTOS + 3 }, (_, i) => ({
      key: String(i),
      name: `${String(i)}.jpg`,
      preview: `blob:${String(i)}`,
    }));
    expect(run({ type: "add", photos: many })).toHaveLength(MAX_PHOTOS);
  });

  it("follows each photo: sent, processed, ready or refused", () => {
    const start: PhotoAction = { type: "add", photos: [{ key: "a", name: "a", preview: "p" }] };
    expect(run(start, { type: "processing", key: "a" })[0]?.status).toBe("processing");
    const ready = run(start, { type: "ready", key: "a", media })[0];
    expect([ready?.status, ready?.media?.id]).toEqual(["ready", "m1"]);
    const failed = run(start, { type: "failed", key: "a", reason: "type" })[0];
    expect([failed?.status, failed?.failure]).toEqual(["failed", "type"]);
  });

  it("moves a photo up or down, never past either end, and removes it", () => {
    const start: PhotoAction = {
      type: "add",
      photos: ["a", "b", "c"].map((key) => ({ key, name: key, preview: key })),
    };
    const order = (list: SellPhoto[]) => list.map((photo) => photo.key).join("");
    expect(order(run(start, { type: "move", key: "c", by: -1 }))).toBe("acb");
    expect(order(run(start, { type: "move", key: "a", by: -1 }))).toBe("abc");
    expect(order(run(start, { type: "move", key: "c", by: 1 }))).toBe("abc");
    expect(order(run(start, { type: "remove", key: "b" }))).toBe("ac");
    expect(order(run(start, { type: "ready", key: "zz", media }))).toBe("abc"); // gone already
  });
});
