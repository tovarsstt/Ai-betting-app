import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Swords, Zap, TrendingUp, Target, ChevronUp,
  GitMerge, Star, RefreshCw, Trophy, Flame,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useMutation } from "@tanstack/react-query";

const SPORTS = ["NBA", "WNBA", "MLB", "NFL", "NHL", "SOCCER", "TENNIS", "UFC"];

interface MarketPick { pick: string; odds: string; win_prob: number; rationale: string; niche_stat: string; is_alt?: boolean; }
interface PropPick { player: string; market: string; pick: string; odds: string; win_prob: number; rationale: string; niche_stat: string; }
interface SGPLeg { pick: string; odds: string; why: string; }
interface SGPBlock { legs: SGPLeg[]; combined_odds: string; why: string; ev: string; }
interface ParlayLeg { pick: string; odds: string; why: string; game?: string; }
interface ParlayBlock { legs: ParlayLeg[]; combined_odds: string; why: string; ev: string; }
interface PickOfDay { selection: string; odds: string; why: string; ev: string; units: string; game: string; sport: string; }
interface FullBreakdownResult {
  game: string; game_summary: string;
  spread_pick: MarketPick; ml_pick: MarketPick; total_pick: MarketPick;
  top_props: PropPick[]; sgp: SGPBlock;
  pick_of_day: PickOfDay; parlay_of_day: ParlayBlock;
  hash: string;
}

function winProbBadge(p: number) {
  if (p >= 0.72) return "bg-emerald-500/20 text-emerald-400 border-emerald-500/40";
  if (p >= 0.64) return "bg-blue-500/20 text-blue-400 border-blue-500/40";
  return "bg-amber-500/20 text-amber-400 border-amber-500/40";
}
function winProbBar(p: number) {
  if (p >= 0.72) return "from-emerald-500 to-emerald-400";
  if (p >= 0.64) return "from-blue-500 to-blue-400";
  return "from-amber-500 to-amber-400";
}

type Accent = "purple" | "emerald" | "blue";
const ACCENT_MAP: Record<Accent, { border: string; bg: string; header: string; title: string; badge: string; niche: string }> = {
  purple: { border: "border-purple-500/30", bg: "bg-purple-500/5", header: "bg-purple-500/10 border-purple-500/20", title: "text-purple-400", badge: "bg-purple-500/20 text-purple-400 border-purple-500/30", niche: "bg-purple-500/5 border-purple-500/20 text-purple-300" },
  emerald: { border: "border-emerald-500/30", bg: "bg-emerald-500/5", header: "bg-emerald-500/10 border-emerald-500/20", title: "text-emerald-400", badge: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30", niche: "bg-emerald-500/5 border-emerald-500/20 text-emerald-300" },
  blue: { border: "border-blue-500/30", bg: "bg-blue-500/5", header: "bg-blue-500/10 border-blue-500/20", title: "text-blue-400", badge: "bg-blue-500/20 text-blue-400 border-blue-500/30", niche: "bg-blue-500/5 border-blue-500/20 text-blue-300" },
};

function WinBar({ prob }: { prob: number }) {
  return (
    <div className="mt-3 space-y-1">
      <div className="flex justify-between items-center text-[10px] font-mono">
        <span className="text-muted-foreground">WIN PROB</span>
        <span className={cn("font-black", prob >= 0.72 ? "text-emerald-400" : prob >= 0.64 ? "text-blue-400" : "text-amber-400")}>
          {Math.round(prob * 100)}%
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-muted/30 overflow-hidden">
        <div className={cn("h-full rounded-full bg-gradient-to-r", winProbBar(prob))} style={{ width: `${Math.round(prob * 100)}%` }} />
      </div>
    </div>
  );
}

function MarketCard({ label, icon: Icon, data, accent, rank }: { label: string; icon: React.ElementType; data: MarketPick; accent: Accent; rank: number }) {
  const cls = ACCENT_MAP[accent];
  return (
    <Card className={cn("border overflow-hidden shadow-lg", cls.border, cls.bg)}>
      {rank === 0 && (
        <div className="flex items-center gap-1.5 px-4 pt-3">
          <Flame className="w-3 h-3 text-amber-400" />
          <span className="text-[9px] font-black uppercase tracking-[0.2em] text-amber-400">Best Bet</span>
        </div>
      )}
      <CardHeader className={cn("border-b pb-3", cls.header, rank === 0 ? "mt-2" : "")}>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className={cn("text-[10px] font-black uppercase tracking-widest flex items-center gap-1.5", cls.title)}>
            <Icon className="w-3.5 h-3.5 shrink-0" /> {label}
          </CardTitle>
          <Badge className={cn("text-xs font-black py-0.5 px-2 shrink-0 border", cls.badge)}>
            {Math.round(data.win_prob * 100)}%
          </Badge>
        </div>
        <p className="font-black text-lg text-foreground mt-1 leading-tight">
          {data.pick} <span className="text-muted-foreground font-mono text-sm font-normal">{data.odds}</span>
        </p>
        {data.is_alt && (
          <div className="inline-flex items-center gap-1 mt-1.5 px-2 py-0.5 rounded-full bg-orange-500/15 border border-orange-500/30">
            <TrendingUp className="w-3 h-3 text-orange-400" />
            <span className="text-[9px] font-black uppercase tracking-widest text-orange-400">Alt Line · Better Value</span>
          </div>
        )}
        <WinBar prob={data.win_prob} />
      </CardHeader>
      <CardContent className="pt-3 space-y-2.5">
        <p className="text-xs text-muted-foreground leading-relaxed">{data.rationale}</p>
        <div className={cn("flex items-start gap-2 p-2 rounded-lg border text-[10px] font-mono", cls.niche)}>
          <ChevronUp className="w-3 h-3 shrink-0 mt-0.5 opacity-70" />
          <span className="leading-relaxed opacity-90">{data.niche_stat}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function PropRow({ prop, rank }: { prop: PropPick; rank: number }) {
  const isTop = rank <= 2;
  return (
    <div className={cn("flex items-start gap-3 p-3.5 rounded-xl border transition-all", isTop ? "border-primary/30 bg-primary/5 hover:border-primary/50" : "border-border/50 bg-muted/10 hover:border-border")}>
      <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center font-black text-xs shrink-0", !isTop && "text-muted-foreground bg-muted/30 border border-border")}
        style={isTop ? { background: "linear-gradient(135deg,#7c3aed,#2563eb)", color: "white" } : {}}>
        {rank}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2 flex-wrap">
          <div>
            <span className="font-black text-sm text-foreground">{prop.player}</span>
            <span className="text-[10px] font-bold text-muted-foreground ml-2 uppercase tracking-wider">{prop.market}</span>
          </div>
          <Badge className={cn("text-[10px] font-black shrink-0 border", winProbBadge(prop.win_prob))}>
            {Math.round(prop.win_prob * 100)}%
          </Badge>
        </div>
        <p className="font-bold text-primary text-sm mt-0.5">
          {prop.pick} <span className="text-muted-foreground font-mono text-xs font-normal">{prop.odds}</span>
        </p>
        <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{prop.rationale}</p>
        {prop.niche_stat && <p className="text-[10px] font-mono text-muted-foreground/50 mt-1 italic">{prop.niche_stat}</p>}
      </div>
    </div>
  );
}

function SGPCard({ sgp }: { sgp: SGPBlock }) {
  return (
    <Card className="border-yellow-500/30 bg-yellow-500/5 overflow-hidden shadow-lg shadow-yellow-500/10">
      <CardHeader className="bg-yellow-500/10 border-b border-yellow-500/20 pb-3">
        <CardTitle className="text-[10px] font-black uppercase tracking-widest text-yellow-400 flex items-center gap-1.5">
          <GitMerge className="w-3.5 h-3.5" /> Same-Game Parlay
        </CardTitle>
        <div className="flex items-center gap-3 mt-1.5 flex-wrap">
          <span className="font-black text-2xl text-foreground">{sgp.combined_odds}</span>
          <Badge className="text-xs font-black bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">{sgp.ev} EV</Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-4 space-y-2">
        {sgp.legs.map((leg, i) => (
          <div key={i} className="flex items-start gap-2.5 p-2.5 rounded-lg bg-muted/20 border border-border/40">
            <span className="w-5 h-5 rounded-full bg-yellow-500/20 border border-yellow-500/30 flex items-center justify-center text-[9px] font-black text-yellow-400 shrink-0 mt-0.5">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold text-sm text-foreground">{leg.pick}</span>
                <span className="font-mono text-xs text-muted-foreground">{leg.odds}</span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">{leg.why}</p>
            </div>
          </div>
        ))}
        <p className="text-xs text-muted-foreground/70 italic pt-1 border-t border-border/30">{sgp.why}</p>
      </CardContent>
    </Card>
  );
}

function ParlayOfDayCard({ parlay }: { parlay: ParlayBlock }) {
  return (
    <Card className="border-violet-500/30 bg-violet-500/5 overflow-hidden shadow-lg shadow-violet-500/10">
      <CardHeader className="bg-violet-500/10 border-b border-violet-500/20 pb-3">
        <CardTitle className="text-[10px] font-black uppercase tracking-widest text-violet-400 flex items-center gap-1.5">
          <Trophy className="w-3.5 h-3.5" /> Parlay of the Day
          <span className="text-[8px] text-muted-foreground font-normal normal-case tracking-normal ml-1">cross-sport</span>
        </CardTitle>
        <div className="flex items-center gap-3 mt-1.5 flex-wrap">
          <span className="font-black text-2xl text-foreground">{parlay.combined_odds}</span>
          <Badge className="text-xs font-black bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">{parlay.ev} EV</Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-4 space-y-2">
        {parlay.legs.map((leg, i) => (
          <div key={i} className="flex items-start gap-2.5 p-2.5 rounded-lg bg-muted/20 border border-border/40">
            <span className="w-5 h-5 rounded-full bg-violet-500/20 border border-violet-500/30 flex items-center justify-center text-[9px] font-black text-violet-400 shrink-0 mt-0.5">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold text-sm text-foreground">{leg.pick}</span>
                <span className="font-mono text-xs text-muted-foreground">{leg.odds}</span>
                {leg.game && <span className="text-[9px] text-muted-foreground/50 uppercase tracking-wider">{leg.game}</span>}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">{leg.why}</p>
            </div>
          </div>
        ))}
        <p className="text-xs text-muted-foreground/70 italic pt-1 border-t border-border/30">{parlay.why}</p>
      </CardContent>
    </Card>
  );
}

function PickOfDayCard({ pick }: { pick: PickOfDay }) {
  return (
    <Card className="border-yellow-500/40 overflow-hidden shadow-xl shadow-yellow-500/10 relative"
      style={{ background: "linear-gradient(135deg,rgba(234,179,8,0.07) 0%,rgba(234,179,8,0.02) 100%)" }}>
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-yellow-500/60 to-transparent" />
      <CardHeader className="bg-yellow-500/10 border-b border-yellow-500/20 pb-4">
        <CardTitle className="text-[10px] font-black uppercase tracking-widest text-yellow-400 flex items-center gap-1.5">
          <Star className="w-3.5 h-3.5 fill-yellow-400" /> Pick of the Day
          <span className="text-[8px] text-muted-foreground font-normal normal-case tracking-normal ml-1">highest edge tonight</span>
        </CardTitle>
        <p className="font-black text-xl text-foreground mt-2 leading-tight">{pick.selection}</p>
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          <span className="font-black text-yellow-400 text-xl">{pick.odds}</span>
          {pick.ev && <Badge className="text-xs font-black bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">{pick.ev} EV</Badge>}
          {pick.units && <Badge className="text-xs font-black bg-blue-500/20 text-blue-400 border border-blue-500/30">{pick.units}</Badge>}
          {pick.sport && <Badge className="text-xs font-bold bg-muted text-muted-foreground border border-border">{pick.sport}</Badge>}
        </div>
      </CardHeader>
      <CardContent className="pt-3">
        <p className="text-xs text-muted-foreground leading-relaxed">{pick.why}</p>
        {pick.game && <p className="text-[10px] text-muted-foreground/40 uppercase tracking-wider mt-2">{pick.game}</p>}
      </CardContent>
    </Card>
  );
}

function useFullBreakdown() {
  return useMutation<FullBreakdownResult, Error, { matchup: string; sport: string }>({
    mutationFn: async ({ matchup, sport }) => {
      const res = await fetch("/api/full-breakdown", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matchup, sport }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({})) as { message?: string };
        throw new Error(body.message || `Error ${res.status}`);
      }
      return res.json();
    },
  });
}

export default function GameBreakdown() {
  const mutation = useFullBreakdown();
  const [matchupText, setMatchupText] = useState("");
  const [sport, setSport] = useState("NBA");
  const [result, setResult] = useState<FullBreakdownResult | null>(null);

  const handleAnalyze = () => {
    if (!matchupText.trim()) { toast.error("Enter a game first"); return; }
    setResult(null);
    toast.loading("Running full breakdown…", { id: "fb" });
    mutation.mutate({ sport, matchup: matchupText.trim() }, {
      onSuccess: (data) => { toast.success("Breakdown ready", { id: "fb" }); setResult(data); setMatchupText(""); },
      onError: (err) => toast.error(err.message || "Engine error", { id: "fb" }),
    });
  };

  const markets = result
    ? ([
        { type: "Spread",    data: result.spread_pick, accent: "purple"  as Accent, icon: Target     },
        { type: "Moneyline", data: result.ml_pick,     accent: "emerald" as Accent, icon: TrendingUp },
        { type: "Total",     data: result.total_pick,  accent: "blue"    as Accent, icon: TrendingUp },
      ]).sort((a, b) => b.data.win_prob - a.data.win_prob)
    : [];

  const cleanProps = result?.top_props?.filter(p => p.player).sort((a, b) => b.win_prob - a.win_prob) ?? [];

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-32">

      {/* Hero */}
      <div className="relative">
        <div className="absolute -inset-x-6 -top-6 h-28 pointer-events-none opacity-25"
          style={{ background: "radial-gradient(ellipse at 50% 0%,rgba(124,58,237,0.5) 0%,transparent 70%)" }} />
        <div className="relative flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl flex items-center justify-center shadow-lg shadow-primary/30 shrink-0"
            style={{ background: "linear-gradient(135deg,#7c3aed,#2563eb)" }}>
            <Swords className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-black tracking-tight"
              style={{ background: "linear-gradient(90deg,#a78bfa,#60a5fa)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              Game Breakdown
            </h1>
            <p className="text-[10px] text-muted-foreground uppercase tracking-widest">Pick of Day · Parlay · SGP · Markets · Props</p>
          </div>
        </div>
      </div>

      {/* Input */}
      <Card className="border-primary/25 relative overflow-hidden shadow-xl shadow-primary/10"
        style={{ background: "linear-gradient(135deg,rgba(124,58,237,0.06) 0%,rgba(37,99,235,0.03) 100%)" }}>
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />
        {mutation.isPending && (
          <div className="absolute inset-0 bg-background/85 backdrop-blur-sm z-10 flex flex-col items-center justify-center gap-4">
            <div className="relative">
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center shadow-xl shadow-primary/40"
                style={{ background: "linear-gradient(135deg,#7c3aed,#2563eb)" }}>
                <Swords className="w-7 h-7 text-white animate-pulse" />
              </div>
              <div className="absolute inset-0 rounded-2xl animate-ping opacity-20"
                style={{ background: "linear-gradient(135deg,#7c3aed,#2563eb)" }} />
            </div>
            <div className="text-center">
              <p className="font-black text-sm tracking-widest text-primary">RUNNING FULL BREAKDOWN</p>
              <p className="text-xs text-muted-foreground mt-1">Live odds · Injuries · Sharp signals · AI</p>
            </div>
          </div>
        )}
        <CardContent className="pt-5 pb-5 space-y-4">
          <div>
            <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-2.5">Sport</p>
            <div className="flex flex-wrap gap-1.5">
              {SPORTS.map((s) => (
                <button key={s} onClick={() => setSport(s)}
                  className={cn("px-3 py-1 rounded-full text-[11px] font-black border transition-all",
                    sport === s ? "text-white border-transparent shadow-md shadow-primary/30" : "bg-background/50 border-border/50 text-muted-foreground hover:border-primary/40 hover:text-foreground"
                  )}
                  style={sport === s ? { background: "linear-gradient(135deg,#7c3aed,#2563eb)" } : {}}>
                  {s}
                </button>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <Input value={matchupText} onChange={(e) => setMatchupText(e.target.value)}
              placeholder="e.g. Timberwolves vs OKC, Sinner vs Alcaraz, Fever vs Sky…"
              className="flex-1 bg-background/60 border-border/60 h-10"
              onKeyDown={(e) => e.key === "Enter" && handleAnalyze()} />
            <Button onClick={handleAnalyze} disabled={mutation.isPending}
              className="font-black tracking-wide shrink-0 h-10 px-5 shadow-lg shadow-primary/20 text-white border-0"
              style={{ background: "linear-gradient(135deg,#7c3aed,#2563eb)" }}>
              {mutation.isPending
                ? <><RefreshCw className="w-3.5 h-3.5 mr-1.5 animate-spin" />Running</>
                : <><Zap className="w-3.5 h-3.5 mr-1.5" />BREAKDOWN</>}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {result && (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-3 duration-500">

          {/* Game summary */}
          <div className="flex items-start gap-3 p-4 rounded-xl border border-primary/20 bg-primary/5">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
              style={{ background: "linear-gradient(135deg,rgba(124,58,237,0.2),rgba(37,99,235,0.15))", border: "1px solid rgba(124,58,237,0.3)" }}>
              <Swords className="w-4 h-4 text-primary" />
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-black uppercase tracking-widest text-primary mb-1">{result.game}</p>
              <p className="text-sm text-muted-foreground leading-relaxed">{result.game_summary}</p>
            </div>
          </div>

          {/* Pick of Day + Parlay */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {result.pick_of_day?.selection && <PickOfDayCard pick={result.pick_of_day} />}
            {result.parlay_of_day?.legs?.length > 0 && <ParlayOfDayCard parlay={result.parlay_of_day} />}
          </div>

          {/* Divider */}
          <div className="flex items-center gap-3">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent to-border/40" />
            <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground/40 px-2">This Game</span>
            <div className="h-px flex-1 bg-gradient-to-l from-transparent to-border/40" />
          </div>

          {/* Markets */}
          <div>
            <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-3">Main Markets — Ranked by Win Prob</p>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {markets.map((m, i) => (
                <MarketCard key={m.type} label={m.type} icon={m.icon} data={m.data} accent={m.accent} rank={i} />
              ))}
            </div>
          </div>

          {/* Props */}
          {cleanProps.length > 0 && (
            <div>
              <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-3">Top Props — Ranked by Win Prob</p>
              <div className="space-y-2">
                {cleanProps.map((prop, i) => <PropRow key={i} prop={prop} rank={i + 1} />)}
              </div>
            </div>
          )}

          {/* SGP */}
          {result.sgp?.legs?.length > 0 && (
            <div>
              <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-3">Best SGP — Correlated Legs</p>
              <SGPCard sgp={result.sgp} />
            </div>
          )}

          {/* Footer */}
          <div className="flex items-center justify-between pt-2 border-t border-border/20">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[9px] text-muted-foreground/40 uppercase tracking-widest">Live Analysis</span>
            </div>
            <p className="text-[9px] font-mono text-muted-foreground/30">{result.hash}</p>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!result && !mutation.isPending && (
        <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center opacity-15"
            style={{ background: "linear-gradient(135deg,#7c3aed,#2563eb)" }}>
            <Swords className="w-8 h-8 text-white" />
          </div>
          <div>
            <p className="text-sm font-bold text-muted-foreground/40">Enter any game above</p>
            <p className="text-xs text-muted-foreground/25 mt-0.5">Pick of day · SGP · Markets · Props · Parlay</p>
          </div>
        </div>
      )}
    </div>
  );
}
