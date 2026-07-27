/**
 * Cliente HTTP del dashboard de solo lectura.
 *
 * Consume la API real desplegada (`arcus.entrypoints.dashboard_api`), que lee
 * directamente de DynamoDB (historial de revisiones) y S3 (grafo de contexto).
 * No hay datos simulados: si la API no responde, se propaga el error para que
 * la UI lo muestre en vez de rellenar con datos falsos.
 */

import type { Finding, RepoGraph, ReviewRun } from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

export class ApiConfigError extends Error {}

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

function assertConfigured(): void {
  if (!API_BASE_URL) {
    throw new ApiConfigError(
      "VITE_API_BASE_URL no está configurado. Define la URL de la API del dashboard en dashboard/.env.",
    );
  }
}

async function getJson<T>(path: string, query?: Record<string, string>): Promise<T> {
  assertConfigured();
  const url = new URL(`${API_BASE_URL}${path}`);
  for (const [key, value] of Object.entries(query ?? {})) {
    url.searchParams.set(key, value);
  }

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method: "GET",
      headers: { "x-api-key": API_KEY },
    });
  } catch {
    throw new ApiRequestError(
      `No se pudo contactar la API de Arcus en ${url.origin}. Verifica la conexión y VITE_API_BASE_URL.`,
      0,
    );
  }

  if (!response.ok) {
    let message = `La API respondió ${response.status} para ${path}.`;
    try {
      const body = (await response.json()) as { message?: string };
      if (body.message) message = body.message;
    } catch {
      // Cuerpo no-JSON o vacío: se conserva el mensaje genérico.
    }
    throw new ApiRequestError(message, response.status);
  }

  return (await response.json()) as T;
}

export interface ReviewRunWithFindings extends ReviewRun {
  findings: Finding[];
}

interface ReposResponse {
  repos: string[];
}

interface ReviewsResponse {
  runs: ReviewRunWithFindings[];
}

/** Lista los repositorios que tienen al menos una revisión persistida. */
export async function fetchRepos(): Promise<string[]> {
  const data = await getJson<ReposResponse>("/repos");
  return data.repos;
}

/** Lista las revisiones de un repositorio (más reciente primero). */
export async function fetchReviews(repo: string): Promise<ReviewRunWithFindings[]> {
  const data = await getJson<ReviewsResponse>("/reviews", { repo });
  return data.runs;
}

/** Obtiene el grafo de contexto persistido de un repositorio. */
export async function fetchGraph(repo: string): Promise<RepoGraph> {
  return await getJson<RepoGraph>("/graph", { repo });
}
