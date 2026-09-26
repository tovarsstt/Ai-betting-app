import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RefreshCw, BarChart3, Zap, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useMutation } from "@tanstack/react-query";

const SPORTS = ["NBA", "WNBA", "NFL", "MLB", "SOCCER", "TENNIS", "F1"];

interface AlphaItem {
  rank: number;
  team_logo: string;
  player_name: string;
  metric_label: string;
  metric_value: string;   // "Over 27.5 -115"
  rationale: string;      // sourced only
  implied_prob: number;   // math-computed
  ai_score: number;       // math-computed
  status_color: string;   // derived from ai_score
  espn_id: string;
}

interface AlphaSheet {
  title: string;
  subtitle: string;
  data: AlphaItem[];
  timestamp: string;
}

// Sport emoji mapping
const SPORT_EMOJI: Record<string, string> = {
  NBA: "🏀", WNBA: "🏀", NFL: "🏈", MLB: "⚾",
  NHL: "🏒", SOCCER: "⚽", TENNIS: "🎾", F1: "🏎️",
};

// Confidence tier from implied_prob (market probability)
function getConfTier(imp: number): { label: string; color: string; glow: string } {
  if (imp >= 70) return { label: "HAMMER",      color: "#C8860A", glow: "rgba(200,134,10,0.35)" };
  if (imp >= 60) return { label: "STRONG",       color: "#22c55e", glow: "rgba(34,197,94,0.35)" };
  if (imp >= 52) return { label: "SOLID",        color: "#3b82f6", glow: "rgba(59,130,246,0.3)" };
  return              { label: "SPECULATIVE",   color: "#f59e0b", glow: "rgba(245,158,11,0.3)" };
}

function ConfidenceBar({ implied_prob, ai_score, status_color }: {
  implied_prob: number;
  ai_score: number;
  status_color: string;
}) {
  const tier = getConfTier(implied_prob);
  const pct = Math.min(99, Math.max(1, Math.round(implied_prob)));
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span
          className="text-[9px] font-black uppercase tracking-widest px-1.5 py-0.5 rounded"
          style={{ color: tier.color, background: `${tier.color}18`, border: `1px solid ${tier.color}35` }}
        >
          {tier.label}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[9px] font-mono text-muted-foreground">{pct}% MKT</span>
          <span
            className="text-[9px] font-black font-mono px-1.5 py-0.5 rounded"
            style={{ color: status_color, background: `${status_color}18` }}
          >
            {ai_score.toFixed(1)}
          </span>
        </div>
      </div>
      <div className="relative h-1.5 rounded-full bg-white/5 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: tier.color, boxShadow: `0 0 8px ${tier.glow}` }}
        />
      </div>
    </div>
  );
}

export default function AlphaSheetsPage() {
  const [sport, setSport] = useState("NBA");

  const { mutate, data, isPending, error } = useMutation({
    mutationFn: async () => {
      const res = await fetch("/api/alpha-sheets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sport }),
      });
      if (!res.ok) throw new Error("Failed");
      return res.json() as Promise<AlphaSheet>;
    },
  });

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-4xl font-black tracking-tighter uppercase italic">
          Alpha <span className="text-primary">Sheets</span>
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Real prop edges — market math only, no hallucinations.
        </p>
      </header>

      {/* Sport selector */}
      <div className="glass p-4 rounded-2xl flex flex-nowrap items-center gap-3 overflow-x-auto scrollbar-none">
        {SPORTS.map(s => (
          <button key={s} onClick={() => setSport(s)}
            className={cn(
              "px-3 py-1.5 rounded-xl text-[10px] font-black tracking-widest uppercase transition-all whitespace-nowrap",
              sport === s
                ? "bg-primary text-primary-foreground"
                : "hover:bg-white/5 text-muted-foreground"
            )}>
            {SPORT_EMOJI[s]} {s}
          </button>
        ))}
        <Button onClick={() => mutate()} disabled={isPending}
          className="ml-auto h-10 px-6 rounded-xl bg-primary text-primary-foreground font-black tracking-widest shrink-0">
          {isPending
            ? <RefreshCw className="w-4 h-4 animate-spin" />
            : <><span>GENERATE</span><Zap className="ml-2 w-3 h-3 fill-current" /></>}
        </Button>
      </div>

      {error && (
        <div className="border border-red-500/30 bg-red-500/5 p-4 rounded-xl flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
          <p className="text-sm text-red-300 font-medium">{(error as Error).message}</p>
        </div>
      )}

      {isPending && (
        <div className="py-12 flex flex-col items-center space-y-3 animate-pulse">
          <BarChart3 className="w-10 h-10 text-primary animate-bounce" />
          <p className="text-sm font-black tracking-widest uppercase">Scanning {sport} data...</p>
        </div>
      )}

      {data && (
        <div className="space-y-6 animate-in slide-in-from-bottom-8 duration-700">
          <div className="text-center space-y-1">
            <h2 className="text-2xl font-black tracking-tighter uppercase">{data.title}</h2>
            <p className="text-xs text-muted-foreground">{data.subtitle}</p>
          </div>

          {data.data.length === 0 ? (
            <Card className="glass-card p-8 text-center">
              <p className="text-muted-foreground text-sm">
                No qualifying props found for {sport} today.
              </p>
            </Card>
          ) : (
            <div className="space-y-3">
              {data.data.map((item, i) => (
                <Card key={i} className="glass-card hover-elevate overflow-hidden">
                  <CardContent className="p-4 space-y-3">
                    {/* Top row */}
                    <div className="flex items-center gap-4">
                      {/* Rank badge */}
                      <div
                        className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center font-black text-lg shrink-0"
                        style={{ borderColor: item.status_color, borderWidth: 2 }}
                      >
                        {item.rank}
                      </div>

                      {/* Player + label */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="font-black text-base truncate">{item.player_name}</span>
                          {item.team_logo && (
                            <Badge className="text-[8px] font-mono bg-white/5 border-white/10 shrink-0">
                              {item.team_logo}
                            </Badge>
                          )}
                        </div>
                        <div className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                          {item.metric_label}
                        </div>
                      </div>

                      {/* Pick + odds */}
                      <div className="text-right shrink-0">
                        <div className="text-sm font-black text-primary">{item.metric_value}</div>
                        <div className="text-[10px] text-muted-foreground font-mono mt-0.5">
                          {SPORT_EMOJI[sport]} {sport}
                        </div>
                      </div>
                    </div>

                    {/* Confidence bar — math-computed */}
                    <ConfidenceBar
                      implied_prob={item.implied_prob ?? 50}
                      ai_score={item.ai_score ?? 5}
                      status_color={item.status_color ?? "#C8860A"}
                    />

                    {/* Sourced rationale */}
                    {item.rationale && (
                      <p className="text-[10px] text-muted-foreground leading-relaxed font-medium border-l-2 border-white/10 pl-3">
                        {item.rationale}
                      </p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
