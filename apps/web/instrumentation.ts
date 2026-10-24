import * as Sentry from "@sentry/nextjs";

import { sentryOptions } from "./lib/sentry";

export function register(): void {
  // Same options for the Node.js and Edge runtimes.
  Sentry.init(sentryOptions());
}

export const onRequestError = Sentry.captureRequestError;
