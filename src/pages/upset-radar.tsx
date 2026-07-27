import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Radar, RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

const OCHRE = "#C8860A";
const SPORTS = ["ALL", "SOCCER", "NBA", "WNBA", "MLB", "NHL", "TENNIS"];

interface UpsetCandidate {
  sport: string;
  game: string;
  commence_time: string;
  underdog: string;
  favorite: string;
  upset_prob_pct: number;
  fair_odds: number;
  best_odds: number;
  best_book: string;
  ev_pct: number;
}

interface UpsetPayload {
  upsets: UpsetCandidate[];
  scanned: number;
  computed_at: string;
}

function fmtOdds(odds: number): string {
  return odds > 0 ? `+${odds}` : `${odds}`;
}

export default function UpsetRadarPage() {
  const [sport, setSport] = useState("ALL");

  const q = useQuery({
    queryKey: ["upset-radar", sport],
    queryFn: async (): Promise<UpsetPayload> => {
      const res = await fetch(`/api/upset-radar?sport=${sport}`);
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    staleTime: 10 * 60 * 1000,
  });

  const upsets = q.data?.upsets ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-display font-black uppercase tracking-wide flex items-center gap-3">
            <Radar className="w-6 h-6" style={{ color: OCHRE }} />
            Upset Radar
          </h2>
          <p className="text-xs text-muted-foreground uppercase tracking-widest mt-1">
            Pure market math — live dogs the soft books overpay. No AI involved.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => q.refetch()} disabled={q.isFetching}>
          <RefreshCw className={`w-4 h-4 ${q.isFetching ? "animate-spin" : ""}`} />
        </Button>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {SPORTS.map(s => (
          <button key={s} onClick={() => setSport(s)}
            className="px-3 py-1.5 text-[11px] font-black uppercase tracking-widest transition-colors"
            style={sport === s
              ? { background: OCHRE, color: "#1A1A1A" }
              : { background: "rgba(255,255,255,0.04)", color: "#9ca3af", border: "1px solid rgba(255,255,255,0.08)" }}>
            {s}
          </button>
        ))}
      </div>

      {q.isLoading && (
        <p className="text-sm text-muted-foreground uppercase tracking-widest py-8 text-center">
          Scanning slates for live dogs...
        </p>
      )}
      {q.isError && (
        <p className="text-sm text-red-400">Radar offline — check the server (port 3001).</p>
      )}

      <div className="space-y-2">
        {upsets.map((u, i) => {
          const positive = u.ev_pct > 0;
          return (
            <div key={`${u.game}-${i}`} className="flex flex-wrap items-center gap-4 border border-white/10 bg-white/[0.02] px-4 py-3.5">
              <span className="text-[10px] font-mono text-muted-foreground w-14">{u.sport}</span>
              <div className="flex-1 min-w-48">
                <div className="font-bold text-sm">
                  {u.underdog} <span className="text-muted-foreground font-normal">beats</span> {u.favorite}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {u.game} · {new Date(u.commence_time).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                </div>
              </div>
              <div className="text-right">
                <div className="text-xl font-black tabular-nums" style={{ color: OCHRE }}>
                  {u.upset_prob_pct}%
                </div>
                <div className="text-[9px] uppercase tracking-widest text-muted-foreground">upset prob</div>
              </div>
              <div className="text-right">
                <div className="text-sm font-black font-mono">{fmtOdds(u.best_odds)}</div>
                <div className="text-[9px] uppercase tracking-widest text-muted-foreground">
                  {u.best_book} · fair {fmtOdds(u.fair_odds)}
                </div>
              </div>
              <span className="text-[10px] font-black font-mono px-2 py-1"
                style={{
                  color: positive ? "#22c55e" : "#9ca3af",
                  background: positive ? "rgba(34,197,94,0.1)" : "rgba(255,255,255,0.04)",
                  border: `1px solid ${positive ? "rgba(34,197,94,0.3)" : "rgba(255,255,255,0.08)"}`,
                }}>
                EV {u.ev_pct > 0 ? "+" : ""}{u.ev_pct}%
              </span>
            </div>
          );
        })}
        {q.isSuccess && !upsets.length && (
          <p className="text-sm text-muted-foreground py-8 text-center uppercase tracking-widest">
            No live dogs on radar right now. Favorites rule today.
          </p>
        )}
      </div>

      {q.isSuccess && (
        <p className="text-[10px] text-muted-foreground/60 font-mono">
          {q.data?.scanned} games scanned · Pinnacle devig = upset probability · positive EV = best book pays above fair · 21+ entertainment only
        </p>
      )}
    </div>
  );
}
