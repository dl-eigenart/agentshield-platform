/**
 * Thin fetch wrapper around the AgentShield /v1/classify endpoint.
 * Kept dependency-free (uses global fetch, Node ≥ 18) so the MCP stays small.
 */

export interface ClassifyInput {
  text: string;
  metadata?: Record<string, unknown>;
}

export interface Verdict {
  is_injection: boolean;
  confidence: number;
  category: string | null;
  latency_ms: number | null;
  model: string | null;
  request_id: string | null;
}

export class ClassifyError extends Error {
  statusCode?: number;
  constructor(message: string, statusCode?: number) {
    super(message);
    this.name = "ClassifyError";
    this.statusCode = statusCode;
  }
}

const DEFAULT_BASE_URL = "https://api.agentshield.dev";
const DEFAULT_TIMEOUT_MS = 10_000;

function baseUrl(): string {
  return (process.env.AGENTSHIELD_BASE_URL ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
}

function apiKey(): string {
  const key = process.env.AGENTSHIELD_API_KEY;
  if (!key) {
    throw new ClassifyError(
      "AGENTSHIELD_API_KEY is not set. Sign up at https://agentshield.pro/signup (free tier, no credit card).",
      401,
    );
  }
  return key;
}

export async function classifyText(input: ClassifyInput): Promise<Verdict> {
  const url = `${baseUrl()}/v1/classify`;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey()}`,
        "Content-Type": "application/json",
        Accept: "application/json",
        "User-Agent": "agentshield-mcp/0.1.0",
      },
      body: JSON.stringify({
        text: input.text,
        ...(input.metadata ? { metadata: input.metadata } : {}),
      }),
      signal: controller.signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      throw new ClassifyError(`Request timed out after ${DEFAULT_TIMEOUT_MS} ms`);
    }
    throw new ClassifyError(
      `Network error calling ${url}: ${err instanceof Error ? err.message : String(err)}`,
    );
  } finally {
    clearTimeout(timeout);
  }

  if (!res.ok) {
    const body = await safeBody(res);
    throw new ClassifyError(
      extractMessage(body) ?? `HTTP ${res.status} ${res.statusText}`,
      res.status,
    );
  }

  let data: unknown;
  try {
    data = await res.json();
  } catch {
    throw new ClassifyError("Response was not valid JSON", res.status);
  }

  return normalize(data);
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

async function safeBody(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    try {
      return await res.text();
    } catch {
      return null;
    }
  }
}

function extractMessage(body: unknown): string | null {
  if (!body) return null;
  if (typeof body === "string") return body.trim() || null;
  if (typeof body === "object") {
    const b = body as Record<string, unknown>;
    for (const key of ["error", "message", "detail"]) {
      const v = b[key];
      if (typeof v === "string" && v) return v;
      if (v && typeof v === "object" && typeof (v as Record<string, unknown>).message === "string") {
        return (v as Record<string, string>).message;
      }
    }
  }
  return null;
}

function normalize(data: unknown): Verdict {
  const d = (data ?? {}) as Record<string, unknown>;
  return {
    is_injection: Boolean(d.is_injection ?? d.injection ?? false),
    confidence: toNumber(d.confidence) ?? 0,
    category: (d.category ?? d.label ?? null) as string | null,
    latency_ms: toNumber(d.latency_ms),
    model: (d.model ?? null) as string | null,
    request_id: (d.request_id ?? d.id ?? null) as string | null,
  };
}

function toNumber(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}
