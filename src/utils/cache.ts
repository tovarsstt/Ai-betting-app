// ── TTL cache with disk persistence ──────────────────────────────────────────
// Backed by an in-memory Map that hydrates from disk on boot and writes through
// on every set. Why persistence: the Odds API free tier is ~500 req/month, and
// a purely in-memory cache is wiped on every server restart — so each restart
// re-fetched every sport from scratch and burned the whole month's quota in a
// day ("the app only works for a day"). Persisting the cache means a restart
// serves the last-known slate for free instead of re-billing the API.
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';

interface Entry {
  data: unknown;
  expires: number;
}

const CACHE_FILE = join(process.cwd(), 'data', '.cache.json');
const store = new Map<string, Entry>();

// Set/Map are not JSON-native (a Set stringifies to `{}`), yet cached values
// like the active-sport-keys Set rely on `.has()`. Tag them on write and
// reconstruct on read so they survive the disk round-trip intact.
function replacer(_key: string, value: unknown): unknown {
  if (value instanceof Set) return { __t: 'Set', v: [...value] };
  if (value instanceof Map) return { __t: 'Map', v: [...value] };
  return value;
}

function reviver(_key: string, value: unknown): unknown {
  if (value && typeof value === 'object' && '__t' in value) {
    const tagged = value as { __t: string; v: unknown[] };
    if (tagged.__t === 'Set') return new Set(tagged.v);
    if (tagged.__t === 'Map') return new Map(tagged.v as [unknown, unknown][]);
  }
  return value;
}

// ── Hydrate from disk on module load (expired entries dropped) ────────────────
(function hydrate(): void {
  try {
    if (!existsSync(CACHE_FILE)) return;
    const raw = JSON.parse(readFileSync(CACHE_FILE, 'utf8'), reviver) as Record<string, Entry>;
    const now = Date.now();
    for (const [key, entry] of Object.entries(raw)) {
      if (entry && typeof entry.expires === 'number' && entry.expires > now) {
        store.set(key, entry);
      }
    }
  } catch {
    // Corrupt/unreadable cache file must never crash boot — start cold.
  }
})();

// ── Debounced write-through to disk ──────────────────────────────────────────
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function flush(): void {
  try {
    mkdirSync(dirname(CACHE_FILE), { recursive: true });
    const obj: Record<string, Entry> = {};
    for (const [key, entry] of store) obj[key] = entry;
    writeFileSync(CACHE_FILE, JSON.stringify(obj, replacer));
  } catch {
    // A failed cache write is never fatal — the in-memory copy still serves.
  }
}

function scheduleFlush(): void {
  if (flushTimer) return;
  flushTimer = setTimeout(() => {
    flushTimer = null;
    flush();
  }, 500);
  // Do not keep the process alive just to flush the cache.
  if (typeof flushTimer.unref === 'function') flushTimer.unref();
}

// Flush the latest state on shutdown so an imminent restart loses nothing.
for (const sig of ['exit', 'SIGINT', 'SIGTERM'] as const) {
  process.once(sig, () => {
    if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
    flush();
    if (sig !== 'exit') process.exit(0);
  });
}

export function getCached(key: string): unknown {
  const entry = store.get(key);
  if (!entry) return null;
  if (entry.expires < Date.now()) { store.delete(key); scheduleFlush(); return null; }
  return entry.data;
}

export function setCache(key: string, data: unknown, ttlMs = 15 * 60 * 1000): void {
  store.set(key, { data, expires: Date.now() + ttlMs });
  scheduleFlush();
}

// Last-known value ignoring expiry — for graceful degradation when a live fetch
// fails or the Odds API quota is exhausted. Serving a slightly stale slate beats
// showing an empty/broken board.
export function getStale(key: string): unknown {
  return store.get(key)?.data ?? null;
}
