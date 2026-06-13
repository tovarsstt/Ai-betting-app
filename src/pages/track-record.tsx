import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Trophy, Plus, RefreshCw, Clapperboard } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

const OCHRE = "#C8860A";

interface LedgerPick {
  id: string;
  created_at: string;
  sport: string;
  game: string;
  selection: string;
  odds: number;
  stake_units: number;
  closing_odds: number | null;
  result: "W" | "L" | "P" | "PENDING";
}

interface LedgerStats {
  total: number;
  pending: number;
  wins: number;
  losses: number;
  pushes: number;
  win_rate_pct: number | null;
  units_profit: number;
  roi_pct: number | null;
  avg_clv_pct: number | null;
  clv_beat_rate_pct: number | null;
  max_drawdown_units: number;
  profit_factor: number | null;
  current_streak: string;
  by_sport: Record<string, { wins: number; losses: number; units_profit: number }>;
}

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json() as Promise<T>;
}

function fmtOdds(odds: number): string {
  return odds > 0 ? `+${odds}` : `${odds}`;
}

function StatBlock({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="border border-white/10 bg-white/[0.02] px-5 py-4">
      <div className="text-3xl font-black tabular-nums" style={accent ? { color: OCHRE } : undefined}>
        {value}
      </div>
      <div className="text-[10px] font-black uppercase tracking-[0.25em] text-muted-foreground mt-1">
        {label}
      </div>
    </div>
  );
}

const RESULT_STYLE: Record<string, { color: string; label: string }> = {
  W: { color: "#22c55e", label: "WIN" },
  L: { color: "#f87171", label: "LOSS" },
  P: { color: "#9ca3af", label: "PUSH" },
  PENDING: { color: OCHRE, label: "PENDING" },
};

export default function TrackRecordPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState({ sport: "NBA", game: "", selection: "", odds: "", units: "1" });
  const [closingByPick, setClosingByPick] = useState<Record<string, string>>({});

  const statsQ = useQuery({
    queryKey: ["ledger-stats"],
    queryFn: () => fetchJSON<{ stats: LedgerStats }>("/api/ledger/stats"),
  });
  const picksQ = useQuery({
    queryKey: ["ledger-picks"],
    queryFn: () => fetchJSON<{ picks: LedgerPick[] }>("/api/ledger/picks"),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["ledger-stats"] });
    qc.invalidateQueries({ queryKey: ["ledger-picks"] });
  };

  const addMut = useMutation({
    mutationFn: () =>
      fetchJSON("/api/ledger/pick", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sport: form.sport,
          game: form.game,
          selection: form.selection,
          odds: Number(form.odds),
          stake_units: Number(form.units) || 1,
          source: "manual",
        }),
      }),
    onSuccess: () => {
      setForm({ ...form, game: "", selection: "", odds: "" });
      invalidate();
    },
  });

  const settleMut = useMutation({
    mutationFn: ({ id, result }: { id: string; result: "W" | "L" | "P" }) => {
      const closing = Number(closingByPick[id]);
      return fetchJSON("/api/ledger/settle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, result, closing_odds: Number.isFinite(closing) && closing !== 0 ? closing : undefined }),
      });
    },
    onSuccess: invalidate,
  });

  const stats = statsQ.data?.stats;
  const picks = picksQ.data?.picks ?? [];
  const canSubmit = form.game && form.selection && Math.abs(Number(form.odds)) >= 100;

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-display font-black uppercase tracking-wide flex items-center gap-3">
            <Trophy className="w-6 h-6" style={{ color: OCHRE }} />
            Track Record
          </h2>
          <p className="text-xs text-muted-foreground uppercase tracking-widest mt-1">
            Every pick logged. No deleting losers.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={invalidate} disabled={statsQ.isFetching}>
          <RefreshCw className={`w-4 h-4 ${statsQ.isFetching ? "animate-spin" : ""}`} />
        </Button>
      </div>

      {/* ── Stats grid ── */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatBlock label="Record" value={`${stats.wins}-${stats.losses}${stats.pushes ? `-${stats.pushes}` : ""}`} accent />
          <StatBlock label="Units" value={`${stats.units_profit >= 0 ? "+" : ""}${stats.units_profit}U`} />
          <StatBlock label="ROI" value={stats.roi_pct != null ? `${stats.roi_pct}%` : "—"} />
          <StatBlock label="Win Rate" value={stats.win_rate_pct != null ? `${stats.win_rate_pct}%` : "—"} />
          <StatBlock label="Avg CLV" value={stats.avg_clv_pct != null ? `${stats.avg_clv_pct >= 0 ? "+" : ""}${stats.avg_clv_pct}%` : "—"} accent />
          <StatBlock label="CLV Beat Rate" value={stats.clv_beat_rate_pct != null ? `${stats.clv_beat_rate_pct}%` : "—"} />
          <StatBlock label="Max Drawdown" value={`-${stats.max_drawdown_units}U`} />
          <StatBlock label="Profit Factor" value={stats.profit_factor != null ? `${stats.profit_factor}` : "—"} />
          <StatBlock label="Streak" value={stats.current_streak || "—"} />
        </div>
      )}

      {/* ── TikTok record card generator ── */}
      {stats && (
        <div className="flex flex-wrap items-center gap-2">
          {(["en", "es"] as const).map(lang => {
            const params = new URLSearchParams({
              mode: "record",
              lang,
              wins: String(stats.wins),
              losses: String(stats.losses),
              units: `${stats.units_profit >= 0 ? "+" : ""}${stats.units_profit}`,
              roi: String(stats.roi_pct ?? 0),
              clv: `${(stats.avg_clv_pct ?? 0) >= 0 ? "+" : ""}${stats.avg_clv_pct ?? 0}`,
              streak: stats.current_streak,
              record: `${stats.wins}-${stats.losses}`,
            });
            return (
              <Button key={lang} variant="outline" size="sm" className="font-black uppercase tracking-wider"
                onClick={() => window.open(`/templates/tiktok-pick.html?${params}`, "_blank")}>
                <Clapperboard className="w-4 h-4 mr-1.5" style={{ color: OCHRE }} />
                TikTok Card {lang.toUpperCase()}
              </Button>
            );
          })}
        </div>
      )}
      {statsQ.isError && (
        <p className="text-sm text-red-400">Ledger API offline — start the server (port 3001).</p>
      )}

      {/* ── Log new pick ── */}
      <Card className="border-white/10 bg-white/[0.02]">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-black uppercase tracking-[0.25em] text-muted-foreground">
            Log Pick
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Input className="w-24" placeholder="Sport" value={form.sport}
            onChange={e => setForm({ ...form, sport: e.target.value })} />
          <Input className="flex-1 min-w-44" placeholder="Game — e.g. Celtics vs Knicks" value={form.game}
            onChange={e => setForm({ ...form, game: e.target.value })} />
          <Input className="flex-1 min-w-44" placeholder="Pick — e.g. Celtics -4.5" value={form.selection}
            onChange={e => setForm({ ...form, selection: e.target.value })} />
          <Input className="w-24" placeholder="-110" value={form.odds}
            onChange={e => setForm({ ...form, odds: e.target.value })} />
          <Input className="w-16" placeholder="1U" value={form.units}
            onChange={e => setForm({ ...form, units: e.target.value })} />
          <Button
            disabled={!canSubmit || addMut.isPending}
            onClick={() => addMut.mutate()}
            style={{ background: OCHRE, color: "#1A1A1A" }}
            className="font-black uppercase tracking-wider"
          >
            <Plus className="w-4 h-4 mr-1" /> Log
          </Button>
        </CardContent>
      </Card>

      {/* ── Picks list ── */}
      <div className="space-y-2">
        {picks.map(p => {
          const rs = RESULT_STYLE[p.result];
          return (
            <div key={p.id} className="flex flex-wrap items-center gap-3 border border-white/10 bg-white/[0.02] px-4 py-3">
              <span className="text-[10px] font-black px-2 py-0.5 uppercase tracking-widest"
                style={{ color: rs.color, background: `${rs.color}18`, border: `1px solid ${rs.color}35` }}>
                {rs.label}
              </span>
              <span className="text-[10px] font-mono text-muted-foreground w-12">{p.sport}</span>
              <div className="flex-1 min-w-40">
                <div className="font-bold text-sm">{p.selection} <span className="font-mono" style={{ color: OCHRE }}>{fmtOdds(p.odds)}</span></div>
                <div className="text-[11px] text-muted-foreground">{p.game} · {p.stake_units}U · {new Date(p.created_at).toLocaleDateString()}</div>
              </div>
              {p.result === "PENDING" ? (
                <div className="flex items-center gap-1.5">
                  <Input className="w-24 h-8 text-xs" placeholder="Close odds"
                    value={closingByPick[p.id] ?? ""}
                    onChange={e => setClosingByPick({ ...closingByPick, [p.id]: e.target.value })} />
                  {(["W", "L", "P"] as const).map(r => (
                    <Button key={r} size="sm" variant="outline" className="h-8 px-3 font-black"
                      disabled={settleMut.isPending}
                      onClick={() => settleMut.mutate({ id: p.id, result: r })}>
                      {r}
                    </Button>
                  ))}
                </div>
              ) : (
                p.closing_odds != null && (
                  <span className="text-[11px] font-mono text-muted-foreground">close {fmtOdds(p.closing_odds)}</span>
                )
              )}
            </div>
          );
        })}
        {!picks.length && picksQ.isSuccess && (
          <p className="text-sm text-muted-foreground py-6 text-center uppercase tracking-widest">
            No picks logged yet. Cave is empty. Log first pick above.
          </p>
        )}
      </div>
    </div>
  );
}
