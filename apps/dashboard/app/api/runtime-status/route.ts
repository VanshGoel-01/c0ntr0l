import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ")) {
    return NextResponse.json(
      { detail: "Project API key required" },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }

  const controlApiUrl = (process.env.CONTROL_API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
  try {
    const authentication = await fetch(`${controlApiUrl}/api/v1/workspace`, {
      cache: "no-store",
      headers: { Authorization: authorization },
      signal: AbortSignal.timeout(2000),
    });
    if (authentication.status === 401 || authentication.status === 403) {
      return NextResponse.json(
        { detail: "Invalid project API key" },
        { status: 401, headers: { "Cache-Control": "no-store" } },
      );
    }
    if (!authentication.ok) throw new Error("Control API rejected status check");
  } catch {
    return NextResponse.json(
      { detail: "Control API unavailable" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }

  const ollamaUrl = (process.env.OLLAMA_BASE_URL ?? "http://127.0.0.1:11434").replace(/\/+$/, "");
  const mockUrl = (process.env.MOCK_PROVIDER_BASE_URL ?? "http://127.0.0.1:8002").replace(/\/+$/, "");
  let ollama: { status: "connected" | "unavailable"; models: string[]; detail?: string };
  try {
    const response = await fetch(`${ollamaUrl}/api/tags`, { cache: "no-store", signal: AbortSignal.timeout(1200) });
    if (!response.ok) throw new Error(`Ollama returned ${response.status}`);
    const body = await response.json() as { models?: Array<{ name?: string }> };
    ollama = { status: "connected", models: (body.models ?? []).flatMap((model) => model.name ? [model.name] : []) };
  } catch {
    ollama = { status: "unavailable", models: [] };
  }

  let mock: { status: "connected" | "unavailable" };
  try {
    const response = await fetch(`${mockUrl}/health`, { cache: "no-store", signal: AbortSignal.timeout(1200) });
    mock = { status: response.ok ? "connected" : "unavailable" };
  } catch {
    mock = { status: "unavailable" };
  }

  return NextResponse.json({
    checkedAt: new Date().toISOString(),
    ollama,
    mock,
    gemini: { status: process.env.GEMINI_API_KEY ? "configured" : "not_configured" },
  }, { headers: { "Cache-Control": "no-store", "Vary": "Authorization", "X-Content-Type-Options": "nosniff" } });
}
