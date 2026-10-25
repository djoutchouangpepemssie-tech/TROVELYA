/** Temporary mock-up demo: the mock-up's photos and where its screens live in this site. */

export const IMG = {
  watch: "/demo/montre.jpg",
  vinyl: "/demo/vinyle.jpg",
  book: "/demo/fleurs-du-mal.jpg",
  lamp: "/demo/lampe-opaline.jpg",
  lens: "/demo/objectif.jpg",
  vase: "/demo/vase.jpg",
  liveVinyls: "/demo/live-vinyles.jpg",
  map: "/demo/carte.jpg",
} as const;

export type ImageKey = keyof typeof IMG;

/** Mock-up screens reproduced in the demo, by their mock-up file name. */
const SCREENS: Record<string, string> = {
  WebHome: "",
  WebCatalog: "/catalogue",
  WebProduct: "/annonce",
  WebLive: "/live",
  WebStudio: "/atelier",
  // Screens not reproduced yet open the closest one that is.
  Auction: "/annonce",
  Search: "/catalogue",
  VisualSearch: "/catalogue",
  Request: "/catalogue",
  Shop: "/annonce",
  Checkout: "/annonce",
  Agent: "/annonce",
  Live: "/live",
  Order: "/atelier",
  Sell: "/atelier",
  Studio: "/atelier",
  Boost: "/atelier",
};

/** Href of a mock-up screen inside the demo, or null when it has no counterpart yet. */
export function demoHref(screen: string): string | null {
  const path = SCREENS[screen];
  return path === undefined ? null : `/fr/demo${path}`;
}
