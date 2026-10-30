/**
 * The photos of a listing being made (W09, step 1, P2-T09a1): each one sent, then processed,
 * then ready to use, or refused; the member orders them (the first is the main photo) and
 * takes some away. A pure reducer: the screen keeps the uploads and their previews.
 */

import type { Media, UploadFailure } from "@/lib/media";

// A listing of goods takes 12 photos at most (section 7.5, [PARAM] listings.max_photos_by_vertical);
// the category chosen at step 2 may take fewer.
export const MAX_PHOTOS = 12;

export type SellPhoto = {
  key: string;
  name: string;
  preview: string; // the local file's address, until the processed photo is shown
  status: "sending" | "processing" | "ready" | "failed";
  media?: Media;
  failure?: UploadFailure;
};

export type PhotoAction =
  | { type: "add"; photos: Pick<SellPhoto, "key" | "name" | "preview">[] }
  | { type: "processing"; key: string }
  | { type: "ready"; key: string; media: Media }
  | { type: "failed"; key: string; reason: UploadFailure }
  | { type: "move"; key: string; by: -1 | 1 }
  | { type: "remove"; key: string };

function update(list: SellPhoto[], key: string, changes: Partial<SellPhoto>): SellPhoto[] {
  return list.map((photo) => (photo.key === key ? { ...photo, ...changes } : photo));
}

export function photos(list: SellPhoto[], action: PhotoAction): SellPhoto[] {
  switch (action.type) {
    case "add": {
      const room = Math.max(0, MAX_PHOTOS - list.length);
      const added = action.photos.slice(0, room).map((photo) => ({
        ...photo,
        status: "sending" as const,
      }));
      return [...list, ...added];
    }
    case "processing":
      return update(list, action.key, { status: "processing" });
    case "ready":
      return update(list, action.key, { status: "ready", media: action.media });
    case "failed":
      return update(list, action.key, { status: "failed", failure: action.reason });
    case "move": {
      const from = list.findIndex((photo) => photo.key === action.key);
      const to = from + action.by;
      if (from < 0 || to < 0 || to >= list.length) return list;
      const moved = [...list];
      [moved[from], moved[to]] = [moved[to] as SellPhoto, moved[from] as SellPhoto];
      return moved;
    }
    case "remove":
      return list.filter((photo) => photo.key !== action.key);
  }
}
