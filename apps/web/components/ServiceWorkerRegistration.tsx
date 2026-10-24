"use client";

import { useEffect } from "react";

/** Registers the minimal service worker that makes the site installable (PWA). */
export function ServiceWorkerRegistration() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker.register("/sw.js", { scope: "/" });
    }
  }, []);
  return null;
}
