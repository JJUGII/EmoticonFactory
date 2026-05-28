import { NextRequest, NextResponse } from "next/server";

/**
 * Vercel rewrites to ngrok need ngrok-skip-browser-warning or API gets HTML interstitial.
 */
export async function middleware(request: NextRequest) {
  const backend = (process.env.API_URL || "").trim().replace(/\/$/, "");
  if (!backend) {
    return NextResponse.next();
  }
  const isNgrok =
    backend.includes("ngrok-free.app") ||
    backend.includes("ngrok-free.dev") ||
    backend.includes("ngrok.io");
  if (!isNgrok) {
    return NextResponse.next();
  }

  const target = `${backend}${request.nextUrl.pathname}${request.nextUrl.search}`;
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.set("ngrok-skip-browser-warning", "1");

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    redirect: "manual",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
    init.duplex = "half";
  }

  try {
    const res = await fetch(target, init);
    return new NextResponse(res.body, {
      status: res.status,
      statusText: res.statusText,
      headers: res.headers,
    });
  } catch (err) {
    console.error("[ngrok proxy]", err);
    return NextResponse.json(
      { detail: "Backend unreachable via ngrok" },
      { status: 502 }
    );
  }
}

export const config = {
  matcher: "/api/:path*",
};
