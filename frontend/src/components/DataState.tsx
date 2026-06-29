import React from "react";

export function DataState({ error, loading }: { error?: string | null; loading?: boolean }) {
  if (loading) return <p className="muted">Loading live platform data…</p>;
  if (error) return <p className="error">{error}</p>;
  return null;
}
