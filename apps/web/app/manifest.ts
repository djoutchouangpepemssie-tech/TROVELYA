import type { MetadataRoute } from "next";

import messages from "@/messages/fr.json";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: messages.Metadata.title,
    short_name: messages.Home.brand,
    description: messages.Metadata.description,
    start_url: "/fr",
    scope: "/",
    display: "standalone",
    background_color: "#FFFFFF",
    theme_color: "#1D2BFF",
    lang: "fr",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
