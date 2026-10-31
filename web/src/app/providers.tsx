"use client";

// Makes TanStack Query available to every page. It keeps one shared cache of
// everything fetched from the API, so two components asking for the same
// environment share one request, and a change made anywhere updates both.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Retry network trouble and server errors, but never a 4xx: asking
        // again for an environment that does not exist will not make it exist.
        retry: (failureCount, error) => {
          const isClientError =
            error instanceof ApiError &&
            error.status >= 400 &&
            error.status < 500;
          return !isClientError && failureCount < 2;
        },
      },
    },
  });
}

// On the server every render gets a fresh client, so users never share data.
// In the browser one client lives for the whole visit, keeping its cache.
let browserQueryClient: QueryClient | undefined;

function getQueryClient() {
  if (typeof window === "undefined") return makeQueryClient();
  browserQueryClient ??= makeQueryClient();
  return browserQueryClient;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={getQueryClient()}>
      {children}
    </QueryClientProvider>
  );
}
