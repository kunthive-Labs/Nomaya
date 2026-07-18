// Server-side proxy to the Nomaya FastAPI service. Keeps NOMAYA_API_TOKEN out
// of the browser bundle and makes dashboard requests same-origin.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const UPSTREAM = process.env.NOMAYA_API_URL || "http://127.0.0.1:8000";

async function forward(req: NextRequest, path: string[]): Promise<NextResponse> {
  const url = `${UPSTREAM}/api/${path.join("/")}${req.nextUrl.search}`;
  const headers: Record<string, string> = {};
  if (process.env.NOMAYA_API_TOKEN) {
    headers["Authorization"] = `Bearer ${process.env.NOMAYA_API_TOKEN}`;
  }

  const init: RequestInit = { method: req.method, headers, cache: "no-store" };
  if (req.method !== "GET" && req.method !== "HEAD") {
    headers["Content-Type"] = req.headers.get("content-type") || "application/json";
    init.body = await req.text();
  }

  try {
    const res = await fetch(url, init);
    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("content-type") || "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: `Nomaya API unreachable at ${UPSTREAM}` }, { status: 502 });
  }
}

export async function GET(req: NextRequest, { params }: { params: { path: string[] } }) {
  return forward(req, params.path);
}

export async function POST(req: NextRequest, { params }: { params: { path: string[] } }) {
  return forward(req, params.path);
}

export async function DELETE(req: NextRequest, { params }: { params: { path: string[] } }) {
  return forward(req, params.path);
}
