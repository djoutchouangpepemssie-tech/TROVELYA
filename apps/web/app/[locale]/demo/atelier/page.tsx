import type { Metadata } from "next";

import { Studio } from "./Studio";

export const metadata: Metadata = {
  title: "Atelier marchand · Démonstration · TROVÉLYA",
};

export default function StudioPage() {
  return <Studio />;
}
