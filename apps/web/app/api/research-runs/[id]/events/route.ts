import type { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/lib/api";

interface RouteContext {
  params: Promise<{ id: string }>;
}

const SSE_HEADERS: Readonly<Record<string, string>> = {
  "content-type": "text/event-stream",
  "cache-control": "no-cache",
  "x-accel-buffering": "no",
};

const UPSTREAM_UNAVAILABLE_CODE = "sse_upstream_unavailable";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: NextRequest,
  context: RouteContext,
): Promise<Response> {
  const { id } = await context.params;
  const upstreamUrl = `${getApiBaseUrl()}/api/research-runs/${encodeURIComponent(id)}/events`;

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      signal: request.signal,
      cache: "no-store",
      headers: { accept: "text/event-stream" },
    });
  } catch (error) {
    const detail =
      error instanceof Error
        ? error.message
        : "Failed to reach research run event stream";
    return Response.json(
      { code: UPSTREAM_UNAVAILABLE_CODE, detail },
      { status: 502 },
    );
  }

  if (!upstream.ok) {
    const passthroughHeaders = new Headers();
    const contentType = upstream.headers.get("content-type");
    if (contentType !== null) {
      passthroughHeaders.set("content-type", contentType);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: passthroughHeaders,
    });
  }

  return new Response(upstream.body, { headers: SSE_HEADERS });
}
