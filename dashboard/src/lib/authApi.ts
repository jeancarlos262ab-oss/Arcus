/**
 * Cliente de autenticación del dashboard: login real con GitHub OAuth.
 *
 * Todas las rutas viven en `arcus.entrypoints.auth_api` y dependen de una
 * cookie de sesión HttpOnly (`credentials: "include"`), nunca de la API key
 * compartida de solo lectura. Cada usuario ve únicamente sus propios datos.
 */

import { ApiConfigError, ApiRequestError } from "./api";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

function assertConfigured(): void {
  if (!API_BASE_URL) {
    throw new ApiConfigError(
      "VITE_API_BASE_URL no está configurado. Define la URL de la API del dashboard en dashboard/.env.",
    );
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  assertConfigured();
  const url = `${API_BASE_URL}${path}`;

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      credentials: "include",
      headers: { "content-type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiRequestError(
      `No se pudo contactar la API de Arcus en ${API_BASE_URL}.`,
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

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface AuthMe {
  github_user_id: number;
  login: string;
}

export interface MyRepo {
  full_name: string;
  private: boolean;
  /** true si la GitHub App de Arcus ya está instalada en este repo. */
  app_installed: boolean;
}

/** URL que inicia el flujo real de GitHub OAuth (redirige el navegador entero). */
export function getLoginUrl(): string {
  assertConfigured();
  return `${API_BASE_URL}/auth/login`;
}

/** Identidad del usuario logueado, o null si no hay sesión válida. */
export async function fetchMe(): Promise<AuthMe | null> {
  try {
    return await request<AuthMe>("/me");
  } catch (err) {
    if (err instanceof ApiRequestError && err.status === 401) return null;
    throw err;
  }
}

/** Repositorios de GitHub que el usuario logueado puede ver (suyos o colaborador). */
export async function fetchMyRepos(): Promise<MyRepo[]> {
  const data = await request<{ repos: MyRepo[] }>("/me/repos");
  return data.repos;
}

/** Repositorios que el usuario logueado eligió ver en el dashboard. */
export async function fetchMyWatchlist(): Promise<string[]> {
  const data = await request<{ repos: string[] }>("/me/watchlist");
  return data.repos;
}

/** Reemplaza la selección guardada del usuario logueado. */
export async function saveMyWatchlist(repos: string[]): Promise<string[]> {
  const data = await request<{ repos: string[] }>("/me/watchlist", {
    method: "PUT",
    body: JSON.stringify({ repos }),
  });
  return data.repos;
}

/** Cierra la sesión del dashboard. No revoca la autorización en GitHub. */
export async function logout(): Promise<void> {
  await request<void>("/auth/logout", { method: "POST" });
}
