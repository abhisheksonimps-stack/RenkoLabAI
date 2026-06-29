import React, { useEffect, useState } from "react";
import { api } from "./api/client";
import { DataState } from "./components/DataState";
import { Panel } from "./components/Panel";

type DashboardState = {
  health?: Record<string, unknown>;
  runtime?: Record<string, unknown>;
  portfolio?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  strategies?: { strategies: string[] };
  orders?: unknown[];
  positions?: unknown[];
  analytics?: Record<string, unknown>;
};

function App() {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("change-me-now");
  const [authenticated, setAuthenticated] = useState(api.isAuthenticated());
  const [data, setData] = useState<DashboardState>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function login(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    await api.login(username, password);
    setAuthenticated(true);
    await refresh();
  }

  async function logout() {
    await api.logout();
    setAuthenticated(false);
    setData({});
  }

  async function refresh() {
    if (!api.isAuthenticated()) return;
    setLoading(true);
    setError(null);
    try {
      const [health, runtime, portfolio, metrics, strategies, orders, positions, analytics] = await Promise.all([
        api.get<Record<string, unknown>>("/production/health"),
        api.get<Record<string, unknown>>("/runtime/status"),
        api.get<Record<string, unknown>>("/portfolio/snapshot"),
        api.get<Record<string, unknown>>("/production/metrics"),
        api.get<{ strategies: string[] }>("/strategies"),
        api.get<unknown[]>("/orders"),
        api.get<unknown[]>("/positions"),
        api.get<Record<string, unknown>>("/production-analytics/snapshot"),
      ]);
      setData({ health, runtime, portfolio, metrics, strategies, orders, positions, analytics });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 10_000);
    return () => window.clearInterval(id);
  }, [authenticated]);

  if (!authenticated) {
    return (
      <main className="login-shell">
        <form className="login-card" onSubmit={login}>
          <h1>RenkoLab AI</h1>
          <p>Production trading console</p>
          <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username" />
          <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" type="password" />
          <button type="submit">Login</button>
          <DataState error={error} />
        </form>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header>
        <div>
          <h1>RenkoLab AI</h1>
          <p>Institutional live trading platform</p>
        </div>
        <nav>
          <button onClick={refresh}>Refresh</button>
          <button onClick={() => api.post("/runtime/stop").then(refresh)}>Stop Runtime</button>
          <button onClick={logout}>Logout</button>
        </nav>
      </header>
      <DataState loading={loading} error={error} />
      <div className="grid">
        <Panel title="Dashboard">{renderJson(data.health)}</Panel>
        <Panel title="Runtime Controls">{renderJson(data.runtime)}</Panel>
        <Panel title="Live Renko Charts"><p className="muted">Charts render after live ticks update analytics and portfolio snapshots.</p>{renderJson(data.analytics)}</Panel>
        <Panel title="Portfolio">{renderJson(data.portfolio)}</Panel>
        <Panel title="Orders">{renderJson(data.orders)}</Panel>
        <Panel title="Positions">{renderJson(data.positions)}</Panel>
        <Panel title="Strategies">{renderJson(data.strategies)}</Panel>
        <Panel title="Backtesting"><p className="muted">Submit backtests through the production API endpoint /api/v1/backtesting/run.</p></Panel>
        <Panel title="Analytics">{renderJson(data.analytics)}</Panel>
        <Panel title="Health Dashboard">{renderJson(data.health)}</Panel>
        <Panel title="Metrics">{renderJson(data.metrics)}</Panel>
      </div>
    </main>
  );
}

function renderJson(value: unknown) {
  if (value === undefined) return <p className="muted">No production data available yet.</p>;
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}

export default App;
