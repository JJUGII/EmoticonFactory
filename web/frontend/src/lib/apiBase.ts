/** Resolve API origin: Vercel same-origin proxy or explicit NEXT_PUBLIC_API_URL. */

function envApiUrl(): string | undefined {
  const v = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "");
  return v || undefined;
}

function isLocalhostHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1";
}

function isLocalhostUrl(url: string): boolean {
  try {
    return isLocalhostHost(new URL(url).hostname);
  } catch {
    return false;
  }
}

/**
 * Browser on Vercel: use relative `/api` (Next rewrites → backend).
 * Local dev on PC: http://localhost:8000 unless NEXT_PUBLIC_API_URL set.
 */
export function getApiBase(): string {
  const env = envApiUrl();

  if (typeof window !== "undefined") {
    const pageLocal = isLocalhostHost(window.location.hostname);
    if (env && !(isLocalhostUrl(env) && !pageLocal)) {
      return env;
    }
    return "";
  }

  return env || "http://localhost:8000";
}

/** ngrok free interstitial — required on API requests (not for typing URL in browser). */
export function isNgrokBackend(base?: string): boolean {
  const b = (base ?? getApiBase()).toLowerCase();
  return b.includes("ngrok-free.app") || b.includes("ngrok-free.dev") || b.includes("ngrok.io");
}

export function ngrokRequestHeaders(
  extra?: Record<string, string>
): Record<string, string> {
  if (!isNgrokBackend()) {
    return extra ?? {};
  }
  return {
    "ngrok-skip-browser-warning": "1",
    ...(extra ?? {}),
  };
}
