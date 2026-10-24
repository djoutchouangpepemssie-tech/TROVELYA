import * as Sentry from "@sentry/nextjs";

import { sentryOptions } from "./lib/sentry";

// Errors and traces only: no session replay (section 16.4).
Sentry.init(sentryOptions());

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
