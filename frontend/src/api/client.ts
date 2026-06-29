export type ApiError = { detail?: string };

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export class ApiClient {
  private accessToken: string | null = localStorage.getItem("renkolab_access_token");
  private refreshToken: string | null = localStorage.getItem("renkolab_refresh_token");

  isAuthenticated(): boolean {
    return Boolean(this.accessToken);
  }

  async login(username: string, password: string): Promise<TokenPair> {
    const pair = await this.request<TokenPair>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
      authenticated: false,
    });
    this.setTokens(pair);
    return pair;
  }

  async logout(): Promise<void> {
    if (this.accessToken) {
      await this.request("/auth/logout", { method: "POST" });
    }
    this.setTokens(null);
  }

  async get<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: "GET" });
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
  }

  private setTokens(pair: TokenPair | null): void {
    this.accessToken = pair?.access_token ?? null;
    this.refreshToken = pair?.refresh_token ?? null;
    if (pair) {
      localStorage.setItem("renkolab_access_token", pair.access_token);
      localStorage.setItem("renkolab_refresh_token", pair.refresh_token);
    } else {
      localStorage.removeItem("renkolab_access_token");
      localStorage.removeItem("renkolab_refresh_token");
    }
  }

  private async request<T>(path: string, init: RequestInit & { authenticated?: boolean } = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Content-Type", "application/json");
    if (init.authenticated !== false && this.accessToken) {
      headers.set("Authorization", `Bearer ${this.accessToken}`);
    }
    const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
    if (!response.ok) {
      const payload = (await response.json().catch(() => ({}))) as ApiError;
      throw new Error(payload.detail ?? `${response.status} ${response.statusText}`);
    }
    const text = await response.text();
    return (text ? JSON.parse(text) : {}) as T;
  }
}

export const api = new ApiClient();
