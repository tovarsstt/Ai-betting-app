import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Swords, Zap, Target, ChevronRight,
  GitMerge, Star, RefreshCw, Trophy,
  ShieldAlert, Activity, BarChart3, Binary,
  AlertTriangle, TrendingUp, DollarSign, Radar,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useMutation, useQuery } from "@tanstack/react-query";

const SPORTS = ["NBA", "WNBA", "NFL", "MLB", "NHL", "SOCCER", "TENNIS", "F1"];

/* ─── Types matching actual server responses ─── */
interface SGPLeg {
  label: string;
  value: string;
  rationale: string;
  espn_id?: string;
}

interface SwarmAgent {
  primary_single?: string;
  primary_odds?: string;
  bet_structure?: string;       // math-computed
  implied_prob?: number;        // math-computed
  sgp_blueprint?: SGPLeg[];
  omni_report?: string;
  // legacy fields (may still arrive from cache) — display-only, not used for math
  value_gap?: string;
  confidence_score?: number;
}

interface AnalyzeResult {
  quant?: SwarmAgent;
  simulation?: SwarmAgent;
  primary_single?: string;
  primary_odds?: string;
  bet_structure?: string;       // math-computed
  implied_prob?: number;        // math-computed
  sgp_blueprint?: SGPLeg[];
  omni_report?: string;
  swarm_report?: {
    quant?: SwarmAgent;
    simulation?: SwarmAgent;
    audit_verdict?: string;
  };
  hash?: string;
  timestamp?: string;
}

interface ProphetResult {
  selection: string;
  odds: string;
  game_name: string;
  recommended_unit: string;
  logic_bullets: string[];
  correlated_insight?: string;
  // Math-computed server fields — never hallucinated
  implied_prob: number | null;
  devigged_prob: number | null;
  payout_100: number | null;
  edge_pct: number | null;
  bet_structure: string | null;
  upset_alert?: string | null;
  hash?: string;
  // legacy fields (may still arrive from cache)
  value_gap?: string;
  win_prob?: number | null;
  kelly_stake?: string;
}

interface LineGap {
  game: string;
  market: string;
  outcome: string;
  pinnacle_odds: number;
  book: string;
  book_odds: number;
  pinnacle_implied: number;
  book_implied: number;
  gap_pct: number;
  best_line: number;
  best_book: string;
  signal: string;
  commence_time: string;
}
interface LineGapsResult {
  gaps: LineGap[];
  scanned: number;
  compared?: number;   // games actually priced by Pinnacle AND a soft book
  best_gap?: number;   // tightest = largest fair-prob gap found (even below the 3pt bar)
  sport: string;
  computed_at: string;
}

/* ─── Lock tier config ─── */
const LOCK_TIERS = [
  { min: 72, label: "HAMMER",       color: "#C8860A", glow: "rgba(200,134,10,0.45)"  },
  { min: 65, label: "STRONG VALUE", color: "#22c55e", glow: "rgba(34,197,94,0.4)"   },
  { min: 55, label: "MODERATE",     color: "#3b82f6", glow: "rgba(59,130,246,0.4)"  },
  { min:  0, label: "SPECULATIVE",  color: "#f59e0b", glow: "rgba(245,158,11,0.35)" },
] as const;

function getTier(pct: number) {
  return LOCK_TIERS.find(t => pct >= t.min) ?? LOCK_TIERS[LOCK_TIERS.length - 1];
}

/* ─── Bet Structure Badge ─── */
const BET_STRUCTURE_CONFIG: Record<string, { label: string; sublabel: string; color: string; bg: string; border: string }> = {
  'SINGLE':            { label: 'SINGLE',          sublabel: 'Plus-money · take standalone',    color: '#22c55e', bg: 'rgba(34,197,94,0.08)',   border: 'rgba(34,197,94,0.25)'  },
  'SINGLE + PARLAY':   { label: 'SINGLE + PARLAY',  sublabel: 'Good both ways · sweet spot',     color: '#C8860A', bg: 'rgba(200,134,10,0.08)',  border: 'rgba(200,134,10,0.28)' },
  'PARLAY PREFERRED':  { label: 'PARLAY PREFERRED', sublabel: 'Better in a parlay · can single', color: '#3b82f6', bg: 'rgba(59,130,246,0.08)',  border: 'rgba(59,130,246,0.25)' },
  'PARLAY ONLY':       { label: 'PARLAY ONLY',      sublabel: 'Heavy fav · bad single juice',    color: '#a855f7', bg: 'rgba(168,85,247,0.08)',  border: 'rgba(168,85,247,0.25)' },
};

function BetStructureBadge({ structure }: { structure?: string | null }) {
  if (!structure) return null;
  const cfg = BET_STRUCTURE_CONFIG[structure] ?? BET_STRUCTURE_CONFIG['SINGLE + PARLAY'];
  return (
    <div
      className="inline-flex flex-col gap-0.5 px-3 py-1.5 rounded-lg"
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}
    >
      <span className="text-[10px] font-black uppercase tracking-[0.18em]" style={{ color: cfg.color }}>
        {cfg.label}
      </span>
      <span className="text-[8px] font-mono text-muted-foreground">{cfg.sublabel}</span>
    </div>
  );
}

/* ─── Lock Meter — driven by math-computed impliedProb only ─── */
function LockMeter({
  impliedProb, edgePct,
}: {
  impliedProb?: number | null;
  edgePct?: number | null;
  // winProb intentionally removed — AI must not supply this
}) {
  if (impliedProb == null) return null;
  // Use market implied prob as the meter source of truth
  const pct = Math.min(99, Math.max(1, Math.round(impliedProb)));
  const tier = getTier(pct);

  return (
    <div className="space-y-2.5">
      {/* Tier label row */}
      <div className="flex items-center justify-between">
        <span className="text-[9px] font-black uppercase tracking-[0.25em] text-muted-foreground">
          Market Confidence
        </span>
        <span
          className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded"
          style={{ color: tier.color, background: `${tier.color}18`, border: `1px solid ${tier.color}35` }}
        >
          {tier.label}
        </span>
      </div>

      {/* Bar */}
      <div className="relative h-3 rounded-full bg-white/5 overflow-hidden border border-white/5">
        <div
          className="h-full rounded-full transition-all duration-1000 ease-out"
          style={{
            width: `${pct}%`,
            background: tier.color,
            boxShadow: `0 0 14px ${tier.glow}`,
          }}
        />
      </div>

      {/* Probability row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl font-black tabular-nums" style={{ color: tier.color }}>
            {pct}%
          </span>
          <span className="text-[9px] font-mono text-muted-foreground uppercase">mkt prob</span>
        </div>
        <div className="flex items-center gap-3">
          {edgePct != null && (
            <span
              className="text-[9px] font-black font-mono px-1.5 py-0.5 rounded"
              style={{
                color: edgePct > 0 ? "#22c55e" : "#f87171",
                background: edgePct > 0 ? "rgba(34,197,94,0.1)" : "rgba(248,113,113,0.1)",
              }}
            >
              EDGE {edgePct > 0 ? "+" : ""}{edgePct.toFixed(1)}%
            </span>
          )}
        </div>
      </div>
    </div>
  );
}


/* ─── Payout Calculator ─── */
function WagerCalculator({ odds, payout100 }: { odds: string; payout100?: number | null }) {
  const [stake, setStake] = useState(100);

  // Parse American odds from string like "-115" or "+130"
  const oddsNum = parseInt(odds.replace(/[^-\d]/g, ""), 10);
  if (isNaN(oddsNum) || oddsNum === 0) return null;

  const dec = oddsNum > 0 ? oddsNum / 100 + 1 : 100 / Math.abs(oddsNum) + 1;
  const profit  = stake * (dec - 1);
  const total   = stake * dec;
  const breakEven = oddsNum > 0
    ? (100 / (oddsNum + 100)) * 100
    : (Math.abs(oddsNum) / (Math.abs(oddsNum) + 100)) * 100;

  const profitDisplay = profit >= 1000
    ? `$${(profit / 1000).toFixed(1)}k`
    : `$${profit.toFixed(0)}`;
  const totalDisplay = total >= 1000
    ? `$${(total / 1000).toFixed(1)}k`
    : `$${total.toFixed(0)}`;

  return (
    <div className="p-4 rounded-xl bg-white/[0.025] border border-white/[0.06] space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[9px] font-black uppercase tracking-[0.25em] text-muted-foreground">
          <DollarSign className="w-3 h-3" /> Payout Calculator
        </div>
        {payout100 != null && (
          <span className="text-[9px] font-mono text-muted-foreground">
            Per $100: +${payout100.toFixed(0)} net
          </span>
        )}
      </div>

      {/* Stake input */}
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground font-black text-sm">$</span>
        <input
          type="number"
          min={1}
          value={stake}
          onChange={(e) => setStake(Math.max(1, Number(e.target.value)))}
          className="w-28 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm font-black text-right focus:outline-none focus:border-primary/50 focus:bg-white/8 transition-colors"
        />
        <span className="text-[9px] text-muted-foreground font-mono">wager</span>
      </div>

      {/* Output grid */}
      <div className="grid grid-cols-3 gap-2">
        <div className="text-center p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/15">
          <div className="text-xl font-black text-emerald-400">{profitDisplay}</div>
          <div className="text-[8px] font-mono text-muted-foreground uppercase mt-0.5">Net Win</div>
        </div>
        <div className="text-center p-2.5 rounded-lg bg-primary/5 border border-primary/15">
          <div className="text-xl font-black text-primary">{totalDisplay}</div>
          <div className="text-[8px] font-mono text-muted-foreground uppercase mt-0.5">Return</div>
        </div>
        <div className="text-center p-2.5 rounded-lg bg-white/[0.025] border border-white/[0.06]">
          <div className="text-xl font-black">{breakEven.toFixed(1)}%</div>
          <div className="text-[8px] font-mono text-muted-foreground uppercase mt-0.5">Break-even</div>
        </div>
      </div>
    </div>
  );
}

/* ─── Sharp Panel — pure math, no AI ─── */
function SharpPanel({ sport }: { sport: string }) {
  const { data, isLoading, refetch } = useQuery<LineGapsResult>({
    queryKey: ["line-gaps", sport],
    queryFn: async () => {
      const res = await fetch(`/api/line-gaps?sport=${sport}`);
      if (!res.ok) throw new Error("Line gaps unavailable");
      return res.json();
    },
    staleTime: 5 * 60 * 1000, // 5 min
    retry: 1,
  });

  const formatTime = (iso: string) => {
    try {
      return new Date(iso).toLocaleTimeString("en-US", {
        hour: "2-digit", minute: "2-digit", timeZone: "America/New_York",
      }) + " ET";
    } catch { return ""; }
  };

  const formatOdds = (n: number) => n > 0 ? `+${n}` : `${n}`;

  return (
    <Card className="glass-card overflow-hidden border border-[#C8860A]/20">
      <CardHeader className="px-5 py-3 border-b border-[#C8860A]/15 bg-[#C8860A]/5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Radar className="w-3.5 h-3.5 text-[#C8860A]" />
            <span className="text-[10px] font-black uppercase tracking-[0.25em] text-[#C8860A]">
              Sharp Scanner — Pure Math
            </span>
            <span className="text-[9px] font-mono text-muted-foreground">
              Pinnacle vs DK/FD · no AI
            </span>
          </div>
          <div className="flex items-center gap-2">
            {data && (
              <span className="text-[9px] font-mono text-muted-foreground">
                {data.scanned} scanned · {data.compared ?? 0} priced both books
              </span>
            )}
            <button
              onClick={() => refetch()}
              className="p-1 rounded hover:bg-white/5 transition-colors"
              title="Refresh"
            >
              <RefreshCw className={cn("w-3 h-3 text-muted-foreground", isLoading && "animate-spin")} />
            </button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        {isLoading && (
          <div className="flex items-center justify-center gap-2 py-6 text-xs text-muted-foreground">
            <RefreshCw className="w-3 h-3 animate-spin" />
            Fetching live odds...
          </div>
        )}

        {!isLoading && (!data?.gaps?.length) && (
          <div className="py-6 text-center text-[11px] text-muted-foreground font-mono">
            {data
              ? (data.compared
                  ? `No ≥3pt edge across ${data.compared} games priced by both books — tightest gap ${data.best_gap ?? 0}pts. Market efficient right now.`
                  : "No games priced by both Pinnacle and a soft book right now.")
              : "Odds API key required"}
          </div>
        )}

        {data?.gaps?.map((gap, i) => {
          const isStrong = gap.signal === "STRONG_SHARP";
          const accentColor = isStrong ? "#C8860A" : "#22c55e";
          return (
            <div
              key={i}
              className={cn(
                "px-5 py-3 border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] transition-colors",
                isStrong && "bg-[#C8860A]/[0.03]"
              )}
            >
              {/* Game + time */}
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <div>
                  <span className="text-[11px] font-bold">{gap.game}</span>
                  <span className="text-[9px] font-mono text-muted-foreground ml-2">
                    {formatTime(gap.commence_time)}
                  </span>
                </div>
                <span
                  className="text-[9px] font-black uppercase px-1.5 py-0.5 rounded shrink-0"
                  style={{
                    color: accentColor,
                    background: `${accentColor}18`,
                    border: `1px solid ${accentColor}35`,
                  }}
                >
                  {isStrong ? "STRONG" : "SHARP"}
                </span>
              </div>

              {/* Market + outcome */}
              <div className="text-[10px] text-muted-foreground font-mono mb-2">
                {gap.market.toUpperCase()} · {gap.outcome}
              </div>

              {/* Odds comparison */}
              <div className="flex items-center gap-4">
                <div>
                  <div className="text-[9px] font-mono text-muted-foreground uppercase">Pinnacle</div>
                  <div className="text-sm font-black tabular-nums">{formatOdds(gap.pinnacle_odds)}</div>
                  <div className="text-[9px] font-mono text-muted-foreground">{gap.pinnacle_implied}%</div>
                </div>
                <div className="flex flex-col items-center gap-0.5 px-2">
                  <ChevronRight className="w-3 h-3 text-muted-foreground/50" />
                  <span
                    className="text-[10px] font-black tabular-nums"
                    style={{ color: accentColor }}
                  >
                    +{gap.gap_pct}%
                  </span>
                </div>
                <div>
                  <div className="text-[9px] font-mono text-muted-foreground uppercase">{gap.best_book}</div>
                  <div className="text-sm font-black tabular-nums" style={{ color: accentColor }}>
                    {formatOdds(gap.book_odds)}
                  </div>
                  <div className="text-[9px] font-mono text-muted-foreground">{gap.book_implied}%</div>
                </div>
                <div className="ml-auto text-right">
                  <div className="text-[9px] font-mono text-muted-foreground uppercase">Best Play</div>
                  <div className="text-[11px] font-black" style={{ color: accentColor }}>
                    {gap.outcome} @ {gap.best_book}
                  </div>
                  <div className="text-[9px] font-mono text-muted-foreground">
                    {formatOdds(gap.best_line)} · fair {gap.book_implied}%
                  </div>
                </div>
              </div>
            </div>
          );
        })}

        {data?.computed_at && (
          <div className="px-5 py-2 text-[9px] font-mono text-muted-foreground/50 border-t border-white/[0.03]">
            Updated {new Date(data.computed_at).toLocaleTimeString()} · Pinnacle vs soft fair-prob gap ≥3 pts (devigged)
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ─── Agent Card ─── */
function AgentCard({ title, icon: Icon, agent, color }: {
  title: string;
  icon: React.ElementType;
  agent: SwarmAgent;
  color: "emerald" | "blue" | "purple";
}) {
  const borderClass = { emerald: "cave-border-profit", blue: "cave-border-bone", purple: "cave-border-ochre" }[color];
  const iconColor   = { emerald: "text-emerald-400",    blue: "text-amber-400",   purple: "text-primary"   }[color];

  return (
    <Card className={cn("glass-card hover-elevate overflow-hidden", borderClass)}>
      <CardHeader className="pb-3 border-b border-white/5 bg-white/[0.02]">
        <div className="flex items-center gap-2 mb-3">
          <div className={cn("p-1.5 rounded-md bg-white/5", iconColor)}>
            <Icon className="w-4 h-4" />
          </div>
          <span className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground">{title}</span>
        </div>
        <h3 className="text-lg font-black tracking-tight leading-snug">{agent.primary_single || "Analyzing..."}</h3>
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          {agent.bet_structure && <BetStructureBadge structure={agent.bet_structure} />}
          {agent.primary_odds && (
            <span className="text-base font-black text-primary tabular-nums">{agent.primary_odds}</span>
          )}
          {agent.implied_prob != null && (
            <Badge className="bg-white/5 text-muted-foreground border-white/10 text-[9px] font-black">
              {agent.implied_prob}% MKT
            </Badge>
          )}
        </div>
        {agent.implied_prob != null && (
          <div className="mt-3"><LockMeter impliedProb={agent.implied_prob} /></div>
        )}
      </CardHeader>
      <CardContent className="pt-4 space-y-3">
        {agent.omni_report && (
          <p className="text-xs text-muted-foreground leading-relaxed font-medium italic border-l-2 border-white/10 pl-3">
            "{agent.omni_report}"
          </p>
        )}
        {agent.sgp_blueprint && agent.sgp_blueprint.length > 0 && (
          <div className="space-y-2 mt-3">
            <div className="text-[9px] font-black uppercase tracking-widest text-muted-foreground flex items-center gap-1">
              <GitMerge className="w-3 h-3" /> SGP Blueprint
            </div>
            {agent.sgp_blueprint.map((leg, i) => (
              <div key={i} className="p-3 rounded-lg bg-white/[0.03] border border-white/5 hover:border-primary/20 transition-colors">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[9px] font-black text-primary uppercase">{leg.label}</span>
                </div>
                <div className="text-sm font-bold">{leg.value}</div>
                <div className="text-[10px] text-muted-foreground mt-1 italic">{leg.rationale}</div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ─── Main Page ─── */
export default function GameBreakdown() {
  const [matchup, setMatchup] = useState("");
  const [sport, setSport]     = useState("NBA");

  const { mutate: analyze, data: swarmData, isPending: swarmPending, error: swarmError } = useMutation({
    mutationFn: async () => {
      const res = await fetch("/api/analyze-unified", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matchup, sport }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ message: "Server error" }));
        throw new Error(err.message || err.error || "Analysis failed");
      }
      return res.json() as Promise<AnalyzeResult>;
    },
  });

  const { mutate: getProphet, data: prophetData, isPending: prophetPending } = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/prophet?sport=${sport}`);
      if (!res.ok) throw new Error("Prophet failed");
      return res.json() as Promise<ProphetResult>;
    },
  });

  const isLoading  = swarmPending || prophetPending;
  const quant      = swarmData?.swarm_report?.quant      || swarmData?.quant;
  const simulation = swarmData?.swarm_report?.simulation || swarmData?.simulation;

  return (
    <div className="min-h-screen bg-background bg-grid">
      <div className="max-w-7xl mx-auto space-y-10">

        {/* ── Header ── */}
        <header className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Badge className="bg-primary/10 text-primary border-primary/20 font-black tracking-widest text-[10px]">
                V17.0 SYSTEM_PURIFIED
              </Badge>
              <div className="h-1 w-1 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[9px] font-mono text-emerald-500 uppercase font-bold">Engine Live</span>
            </div>
            <h1 className="text-5xl md:text-7xl font-black tracking-tighter uppercase italic">
              CTE <span className="text-primary">LOCKS</span>
            </h1>
            <p className="text-muted-foreground text-sm font-medium tracking-tight max-w-md">
              Institutional-grade market extraction. High-conviction predictive modeling.
              <span className="text-primary ml-1">Brutally honest.</span>
            </p>
          </div>

          <div className="flex flex-nowrap items-center gap-2 bg-white/5 p-1.5 rounded-2xl border border-white/10 backdrop-blur-sm overflow-x-auto scrollbar-none">
            {SPORTS.map((s) => (
              <button
                key={s}
                onClick={() => setSport(s)}
                className={cn(
                  "px-3 py-1.5 rounded-xl text-[10px] font-black transition-all tracking-widest uppercase",
                  sport === s
                    ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20"
                    : "hover:bg-white/5 text-muted-foreground"
                )}
              >
                {s}
              </button>
            ))}
          </div>
        </header>

        {/* ── Sharp Panel — always visible, auto-loads ── */}
        <SharpPanel sport={sport} />

        {/* ── Search ── */}
        <div className="glass p-5 rounded-2xl shadow-2xl relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-r from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
          <div className="relative z-10 flex flex-col md:flex-row gap-3">
            <div className="relative flex-1">
              <Swords className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
              <Input
                placeholder="ENTER MATCHUP (e.g. Lakers vs Celtics)"
                value={matchup}
                onChange={(e) => setMatchup(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && matchup && analyze()}
                className="pl-12 h-12 bg-white/5 border-white/10 text-base font-bold placeholder:text-muted-foreground/30 rounded-xl focus-visible:ring-primary/50"
              />
            </div>
            <Button
              onClick={() => analyze()}
              disabled={isLoading || !matchup}
              className="h-12 px-6 rounded-xl bg-primary text-primary-foreground font-black tracking-widest hover:scale-[1.02] active:scale-[0.98] transition-all disabled:opacity-50"
            >
              {swarmPending ? <RefreshCw className="w-5 h-5 animate-spin" /> : <>ANALYZE <Zap className="ml-2 w-4 h-4 fill-current" /></>}
            </Button>
            <Button
              onClick={() => getProphet()}
              disabled={isLoading}
              variant="outline"
              className="h-12 px-6 rounded-xl border-primary/30 text-primary font-black tracking-widest hover:bg-primary/10 transition-all"
            >
              {prophetPending ? <RefreshCw className="w-5 h-5 animate-spin" /> : <>PROPHET <Star className="ml-2 w-4 h-4" /></>}
            </Button>
          </div>
        </div>

        {/* ── Error ── */}
        {swarmError && (
          <div className="border border-red-500/30 bg-red-500/5 p-4 rounded-xl flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
            <p className="text-sm text-red-300 font-medium">{(swarmError as Error).message}</p>
          </div>
        )}

        {/* ── Loading ── */}
        {isLoading && (
          <div className="py-16 flex flex-col items-center justify-center space-y-5 animate-in fade-in zoom-in duration-500">
            <div className="relative w-20 h-20">
              <div className="absolute inset-0 rounded-full border-4 border-primary/20" />
              <div className="absolute inset-0 rounded-full border-4 border-t-primary animate-spin" />
              <Binary className="absolute inset-0 m-auto w-7 h-7 text-primary animate-pulse" />
            </div>
            <div className="text-center space-y-1">
              <p className="text-lg font-black tracking-widest uppercase italic animate-pulse">Scanning Market Sigmas...</p>
              <p className="text-xs font-mono text-muted-foreground">Ingesting live odds from Pinnacle & DraftKings</p>
            </div>
          </div>
        )}

        {/* ── Prophet Result ── */}
        {prophetData && !swarmData && (
          <div className="animate-in slide-in-from-bottom-8 duration-700">
            <Card className="glass-card cave-border-profit overflow-hidden">
              <CardHeader className="bg-emerald-500/5 border-b border-emerald-500/20 px-6 py-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-xs font-black uppercase tracking-[0.3em] text-emerald-400 flex items-center gap-2">
                    <Trophy className="w-4 h-4" /> Prophet — Pick of the Day
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    {prophetData.implied_prob != null && (
                      <Badge className="bg-white/5 text-muted-foreground border-white/10 text-[9px] font-black">
                        {prophetData.implied_prob}% MKT
                      </Badge>
                    )}
                    <Badge variant="outline" className="text-[9px] font-mono text-muted-foreground">
                      {prophetData.recommended_unit}
                    </Badge>
                  </div>
                </div>
              </CardHeader>

              <CardContent className="p-6 space-y-5">
                {/* Selection + game */}
                <div className="space-y-2">
                  <h3 className="text-2xl font-black tracking-tight">{prophetData.selection}</h3>
                  <div className="flex items-center gap-2 flex-wrap">
                    <BetStructureBadge structure={prophetData.bet_structure} />
                    <p className="text-sm text-muted-foreground font-medium">{prophetData.game_name}</p>
                  </div>
                </div>

                {/* Quality rule: winning > value. Fires when market favors the other side ≥55% */}
                {prophetData.upset_alert && (
                  <div className="flex items-start gap-2.5 px-4 py-3 rounded-lg border"
                    style={{ background: "rgba(248,113,113,0.08)", borderColor: "rgba(248,113,113,0.35)" }}>
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" style={{ color: "#f87171" }} />
                    <p className="text-xs font-bold leading-relaxed" style={{ color: "#f87171" }}>
                      {prophetData.upset_alert}
                    </p>
                  </div>
                )}

                {/* Odds row */}
                <div className="flex items-center gap-6">
                  <div className="text-center">
                    <div className="text-4xl font-black text-primary tabular-nums">{prophetData.odds}</div>
                    <div className="text-[9px] font-mono text-muted-foreground uppercase mt-0.5">Odds</div>
                  </div>
                  {prophetData.devigged_prob != null && (
                    <div className="text-center">
                      <div className="text-2xl font-black tabular-nums" style={{ color: "#C8860A" }}>
                        {prophetData.devigged_prob.toFixed(1)}%
                      </div>
                      <div className="text-[9px] font-mono text-muted-foreground uppercase mt-0.5">True Prob</div>
                    </div>
                  )}
                </div>

                {/* Lock Meter — math-computed only */}
                <LockMeter
                  impliedProb={prophetData.implied_prob}
                  edgePct={prophetData.edge_pct}
                />

                {/* Payout Calculator */}
                <WagerCalculator
                  odds={prophetData.odds}
                  payout100={prophetData.payout_100}
                />

                {/* Logic bullets */}
                {prophetData.logic_bullets?.length > 0 && (
                  <div className="space-y-2 pt-1">
                    <div className="text-[9px] font-black uppercase tracking-[0.25em] text-muted-foreground flex items-center gap-1">
                      <TrendingUp className="w-3 h-3" /> Edge Rationale
                    </div>
                    {prophetData.logic_bullets.map((b, i) => (
                      <div key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                        <ChevronRight className="w-3 h-3 shrink-0 mt-0.5 text-primary" />
                        <span>{b}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Correlated insight */}
                {prophetData.correlated_insight && (
                  <div className="p-3 rounded-lg bg-primary/5 border border-primary/10 text-xs text-primary italic">
                    <GitMerge className="w-3 h-3 inline mr-1" />
                    {prophetData.correlated_insight}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* ── Swarm Results ── */}
        {swarmData && (
          <div className="space-y-8 animate-in slide-in-from-bottom-8 duration-700">

            {/* Final Verdict */}
            <Card className="glass-card cave-border-ochre overflow-hidden animate-scan">
              <CardHeader className="bg-primary/5 border-b border-primary/20 px-6 py-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-xs font-black uppercase tracking-[0.3em] text-primary flex items-center gap-2">
                    <ShieldAlert className="w-4 h-4" /> Final Verdict
                  </CardTitle>
                  {swarmData.implied_prob != null && (
                    <Badge className="bg-white/5 text-muted-foreground border-white/10 text-[9px] font-black">
                      {swarmData.implied_prob}% MKT
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="p-6 space-y-4">
                <div className="space-y-2">
                  <h3 className="text-2xl font-black tracking-tight">{swarmData.primary_single || "Analysis Complete"}</h3>
                  <div className="flex items-center gap-2 flex-wrap">
                    <BetStructureBadge structure={swarmData.bet_structure} />
                    {swarmData.primary_odds && (
                      <span className="text-xl font-black text-primary tabular-nums">{swarmData.primary_odds}</span>
                    )}
                  </div>
                </div>
                {swarmData.implied_prob != null && (
                  <LockMeter impliedProb={swarmData.implied_prob} />
                )}
                {swarmData.omni_report && (
                  <p className="text-sm text-muted-foreground leading-relaxed font-medium italic border-l-2 border-primary/30 pl-4">
                    "{swarmData.omni_report}"
                  </p>
                )}
                {swarmData.sgp_blueprint && swarmData.sgp_blueprint.length > 0 && (
                  <div className="grid gap-2 mt-4">
                    <div className="text-[9px] font-black uppercase tracking-widest text-primary flex items-center gap-1">
                      <GitMerge className="w-3 h-3" /> Recommended SGP
                    </div>
                    {swarmData.sgp_blueprint.map((leg, i) => (
                      <div key={i} className="p-3 rounded-lg bg-primary/5 border border-primary/10 hover:border-primary/30 transition-colors">
                        <div className="text-[9px] font-black text-primary uppercase mb-0.5">{leg.label}</div>
                        <div className="text-sm font-bold">{leg.value}</div>
                        <div className="text-[10px] text-muted-foreground mt-0.5 italic">{leg.rationale}</div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Agent Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {quant      && <AgentCard title="Quant Agent — Pure EV"          icon={BarChart3} agent={quant}      color="emerald" />}
              {simulation && <AgentCard title="Simulation Agent — Situational" icon={Activity}  agent={simulation} color="blue"    />}
            </div>

            {/* Audit Verdict */}
            {swarmData.swarm_report?.audit_verdict && (
              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5 text-xs text-muted-foreground italic flex items-start gap-3">
                <Target className="w-4 h-4 shrink-0 text-primary mt-0.5" />
                <div>
                  <span className="text-[9px] font-black text-primary uppercase tracking-widest block mb-1">Audit Verdict</span>
                  {swarmData.swarm_report.audit_verdict}
                </div>
              </div>
            )}

            {/* Footer Hash */}
            <div className="flex justify-center pt-8 pb-4 opacity-20 hover:opacity-100 transition-opacity">
              <div className="flex items-center gap-4 text-[10px] font-mono tracking-widest uppercase">
                <span>System: CTE_LOCKS_V17</span>
                <span className="w-1 h-1 rounded-full bg-muted-foreground" />
                <span>Hash: {swarmData.hash}</span>
                <span className="w-1 h-1 rounded-full bg-muted-foreground" />
                <span>Status: SYSTEM_PURIFIED</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
