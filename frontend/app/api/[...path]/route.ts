import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ path: string[] }> };

const DEFAULT_MAX_REQUEST_BYTES = 44 * 1024 * 1024;

function requestLimit() {
  const configured = Number(process.env.MAX_REQUEST_BYTES);
  return Number.isSafeInteger(configured) && configured > 0 ? configured : DEFAULT_MAX_REQUEST_BYTES;
}

async function proxy(request: NextRequest, context: RouteContext) {
  const backend = process.env.BACKEND_API_URL?.trim().replace(/\/$/, "");
  if (!backend) {
    return NextResponse.json(
      { detail: "BACKEND_API_URL is not configured on the frontend server" },
      { status: 503 },
    );
  }

  const { path } = await context.params;
  const safePath = path.map(encodeURIComponent).join("/");
  const upstreamUrl = new URL(`${backend}/api/${safePath}`);
  upstreamUrl.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of ["accept", "content-type", "x-api-key"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const hasBody = !["GET", "HEAD"].includes(request.method);
  const maximum = requestLimit();
  const declaredLength = Number(request.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > maximum) {
    return NextResponse.json({ detail: "Request body exceeds configured limit" }, { status: 413 });
  }
  let exceededLimit = false;
  let received = 0;
  const limitedBody = hasBody && request.body
    ? request.body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
        transform(chunk, controller) {
          received += chunk.byteLength;
          if (received > maximum) {
            exceededLimit = true;
            controller.error(new Error("request body too large"));
            return;
          }
          controller.enqueue(chunk);
        },
      }))
    : undefined;
  let response: Response;
  try {
    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      body: limitedBody,
      cache: "no-store",
      redirect: "manual",
    };
    if (limitedBody) init.duplex = "half";
    response = await fetch(upstreamUrl, init);
  } catch {
    if (exceededLimit) {
      return NextResponse.json({ detail: "Request body exceeds configured limit" }, { status: 413 });
    }
    return NextResponse.json({ detail: "Simulation backend is unavailable" }, { status: 502 });
  }

  const responseHeaders = new Headers();
  for (const name of ["content-type", "retry-after", "cache-control"]) {
    const value = response.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new NextResponse(response.body, {
    status: response.status,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const DELETE = proxy;
