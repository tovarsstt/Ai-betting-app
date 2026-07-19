import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Crosshair, RefreshCw } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

/* ─── Pick Report — the full kill-test, every engine, one tap.
   Design: verdict dominates (ochre, display type); engine numbers recede
   (bone 60%, tabular); sharp corners + 1px charcoal borders, no shadows. ─── */

const SPORTS = ["tennis", "soccer", "mlb"] as const;
type Sport = (typeof SPORTS)[number];
const SURFACES = ["Hard", "Clay", "Grass"] as const;

interface SplitMarket {
  points: number; serve: number; blend: number; worst: number;
  floor_odds: number | null; blend_floor_odds: number | null;
}
interface TennisReport {
  home_cover_prob: number | null;
  serve_model_home_prob?: number;
  model_split?: string;
  split_robust_markets?: Record<string, SplitMarket>;
  method?: string; context?: Record<string, number>;
  ranks_stale?: string; model_note?: string;
  bet_signal?: string;
}
interface SoccerReport {
  status?: string;
  lambda_home?: number; lambda_away?: number;
  markets?: {
    "1x2": { home: number; draw: number; away: number };
    double_chance: { "1X": number; X2: number; "12": number };
    totals: Record<string, { over: number; under: number }>;
    btts: { yes: number; no: number };
    expected_total_goals: number;
    correct_score: { score: string; prob: number; fair_decimal_odds: number }[];
  };
}
interface MlbReport {
  expected_runs?: { home: number; away: number; total: number };
  total?: { line: number; p_over: number; p_under: number; p_push: number };
  context?: { probable_starters?: Record<string, { name?: string; ra9?: number; starts?: number }> };
}
interface KillTestPayload {
  success: boolean;
  data?: { sport: Sport; home: string; away: string; surface?: string;
           report: TennisReport & SoccerReport & MlbReport };
  error?: string;
}

const pct = (p: number | null | undefined) => (p == null ? "—" : `${(p * 100).toFixed(1)}%`);

/* floor rule: given a prob, min price for +5% EV */
const floor = (p: number) => (p > 0 ? (1.05 / p).toFixed(2) : "—");

function Row({ label, prob, note, hot }: { label: string; prob: number; note?: string; hot?: boolean }) {
  return (
    <div className={cn("flex items-baseline justify-between border-b border-white/5 py-2",
      hot && "cave-border-ochre px-3 -mx-1 border-b-0 my-1")}>
      <span className={cn("font-display uppercase tracking-wide", hot ? "text-primary text-lg" : "text-sm text-foreground/80")}>
        {label}
      </span>
      <span className="font-mono tabular-nums text-right">
        <span className={cn(hot ? "text-primary text-lg font-bold" : "text-foreground")}>{pct(prob)}</span>
        <span className="ml-3 text-xs text-foreground/50">bet ≥ {floor(prob)}</span>
        {note && <span className="ml-2 text-xs text-foreground/40">{note}</span>}
      </span>
    </div>
  );
}

export default function PickReportPage() {
  const [sport, setSport] = useState<Sport>("tennis");
  const [home, setHome] = useState("");
  const [away, setAway] = useState("");
  const [surface, setSurface] = useState<string>("Hard");
  const [priceHome, setPriceHome] = useState("");
  const [priceAway, setPriceAway] = useState("");

  const m = useMutation({
    mutationFn: async (): Promise<KillTestPayload> => {
      const res = await fetch("/api/kill-test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sport, home: home.trim(), away: away.trim(),
          surface: sport === "tennis" ? surface : undefined,
          priceHome: priceHome ? Number(priceHome) : undefined,
          priceAway: priceAway ? Number(priceAway) : undefined,
        }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.error ?? `${res.status}`);
      return res.json();
    },
  });

  const r = m.data?.data?.report;
  const split = r?.split_robust_markets;

  return (
    <div className="mx-auto max-w-xl px-4 pb-16">
      {/* input block — dense, one column, thumb-reachable */}
      <div className="border border-white/10 bg-card/60 p-4 mt-4">
        <div className="flex gap-2">
          {SPORTS.map((s) => (
            <button key={s} onClick={() => setSport(s)}
              className={cn("flex-1 py-2 font-display uppercase tracking-widest text-sm border",
                sport === s ? "border-primary text-primary" : "border-white/10 text-foreground/50")}>
              {s}
            </button>
          ))}
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2">
          <Input placeholder={sport === "mlb" ? "Home team" : "Player / team A"} value={home}
            onChange={(e) => setHome(e.target.value)} className="rounded-none border-white/15 bg-transparent" />
          <Input placeholder={sport === "mlb" ? "Away team" : "Player / team B"} value={away}
            onChange={(e) => setAway(e.target.value)} className="rounded-none border-white/15 bg-transparent" />
          <div className="flex gap-2">
            <Input placeholder="Odds A (opt.)" inputMode="decimal" value={priceHome}
              onChange={(e) => setPriceHome(e.target.value)} className="rounded-none border-white/15 bg-transparent" />
            <Input placeholder="Odds B (opt.)" inputMode="decimal" value={priceAway}
              onChange={(e) => setPriceAway(e.target.value)} className="rounded-none border-white/15 bg-transparent" />
          </div>
          {sport === "tennis" && (
            <div className="flex gap-2">
              {SURFACES.map((s) => (
                <button key={s} onClick={() => setSurface(s)}
                  className={cn("flex-1 py-1.5 text-xs font-display uppercase tracking-widest border",
                    surface === s ? "border-primary/60 text-primary" : "border-white/10 text-foreground/40")}>
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>
        <Button onClick={() => m.mutate()} disabled={m.isPending || !home.trim() || !away.trim()}
          className="mt-3 w-full rounded-none font-display uppercase tracking-widest text-base">
          {m.isPending
            ? <span className="flex items-center gap-2"><RefreshCw className="h-4 w-4 animate-spin" />Firing every engine…</span>
            : <span className="flex items-center gap-2"><Crosshair className="h-4 w-4" />Kill-test this pick</span>}
        </Button>
      </div>

      {m.isError && (
        <p className="mt-4 text-sm text-red-400/80 font-mono">{(m.error as Error).message}</p>
      )}

      {/* ── TENNIS report ── */}
      {r && m.data?.data?.sport === "tennis" && (
        <div className="mt-6">
          {r.bet_signal === "NO_DATA" ? (
            <p className="text-sm text-foreground/60 font-mono">{r.model_note ?? "no data — cave does not estimate"}</p>
          ) : (
            <>
              <div className="flex justify-between text-xs font-mono text-foreground/50 uppercase">
                <span>points engine: {pct(r.home_cover_prob)}</span>
                <span>serve engine: {pct(r.serve_model_home_prob)}</span>
              </div>
              {r.ranks_stale && <p className="mt-2 text-xs text-yellow-500/80 font-mono">{r.ranks_stale}</p>}
              {split ? (
                <div className="mt-4">
                  <h2 className="text-primary text-xl">Engines split — routed markets</h2>
                  <p className="text-xs text-foreground/50 mt-1">
                    Bet only where the book price beats the floor. Stricter floor = safe even if the
                    wrong engine is right. Blend floor = balanced call.
                  </p>
                  <div className="mt-3 font-mono text-sm">
                    <div className="grid grid-cols-4 gap-1 text-[10px] uppercase text-foreground/40 border-b border-white/10 pb-1">
                      <span>market</span><span className="text-right">blend P</span>
                      <span className="text-right">safe floor</span><span className="text-right">blend floor</span>
                    </div>
                    {Object.entries(split).map(([k, v]) => (
                      <div key={k} className="grid grid-cols-4 gap-1 py-2 border-b border-white/5 tabular-nums">
                        <span className="uppercase text-xs">{k.replace(/_/g, " ")}</span>
                        <span className="text-right text-primary">{pct(v.blend)}</span>
                        <span className="text-right">{v.floor_odds ?? "—"}</span>
                        <span className="text-right">{v.blend_floor_odds ?? "—"}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                r.home_cover_prob != null && (
                  <div className="mt-4">
                    <h2 className="text-xl">Engines agree — pick ladder</h2>
                    <Row label={`${m.data.data.home} ML`} prob={r.home_cover_prob}
                      hot={r.home_cover_prob >= 0.58} />
                    <Row label={`${m.data.data.away} ML`} prob={1 - r.home_cover_prob}
                      hot={1 - r.home_cover_prob >= 0.58} />
                  </div>
                )
              )}
            </>
          )}
        </div>
      )}

      {/* ── SOCCER report ── */}
      {r?.markets && m.data?.data?.sport === "soccer" && (
        <div className="mt-6">
          <div className="text-xs font-mono text-foreground/50 uppercase">
            xG {r.lambda_home?.toFixed(2)} vs {r.lambda_away?.toFixed(2)} · total {r.markets.expected_total_goals}
          </div>
          <h2 className="mt-3 text-xl">Full board</h2>
          <Row label={`${m.data.data.home} win`} prob={r.markets["1x2"].home} hot={r.markets["1x2"].home >= 0.5} />
          <Row label="Draw" prob={r.markets["1x2"].draw} hot={r.markets["1x2"].draw >= 0.34} />
          <Row label={`${m.data.data.away} win`} prob={r.markets["1x2"].away} hot={r.markets["1x2"].away >= 0.5} />
          <Row label="DC 1X" prob={r.markets.double_chance["1X"]} />
          <Row label="DC X2" prob={r.markets.double_chance.X2} />
          <Row label="Under 2.5" prob={r.markets.totals["2.5"].under} hot={r.markets.totals["2.5"].under >= 0.62} />
          <Row label="BTTS No" prob={r.markets.btts.no} />
          <p className="mt-3 text-xs font-mono text-foreground/50">
            top scores: {r.markets.correct_score.slice(0, 3).map((s) => `${s.score} ${pct(s.prob)}`).join(" · ")}
          </p>
        </div>
      )}

      {/* ── MLB report ── */}
      {r?.expected_runs && m.data?.data?.sport === "mlb" && (
        <div className="mt-6">
          <h2 className="text-xl">Run model</h2>
          <div className="font-mono text-sm mt-2 tabular-nums">
            expected runs — home {r.expected_runs.home} · away {r.expected_runs.away} · total {r.expected_runs.total}
          </div>
          {r.total && (
            <Row label={`Under ${r.total.line}`} prob={r.total.p_under}
              note={r.total.p_push ? `push ${pct(r.total.p_push)}` : undefined}
              hot={r.total.p_under >= 0.58} />
          )}
          {Object.entries(r.context?.probable_starters ?? {}).map(([side, p]) =>
            p && typeof p === "object" && (p.starts ?? 99) < 8 ? (
              <p key={side} className="mt-2 text-xs text-yellow-500/80 font-mono">
                {side} starter {p.name} — ra9 {p.ra9} on only {p.starts} starts. Small sample, haircut the edge.
              </p>
            ) : null,
          )}
        </div>
      )}
    </div>
  );
}
