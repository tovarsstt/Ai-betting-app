// ── In-memory cache — TTL-based, no disk I/O ─────────────────────────────────
const store = new Map<string, { data: unknown; expires: number }>();

export function getCached(key: string): unknown {
  const entry = store.get(key);
  if (!entry) return null;
  if (entry.expires < Date.now()) { store.delete(key); return null; }
  return entry.data;
}

export function setCache(key: string, data: unknown, ttlMs = 15 * 60 * 1000) {
  store.set(key, { data, expires: Date.now() + ttlMs });
}
