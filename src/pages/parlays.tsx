import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { RefreshCw, Trophy, GitMerge, TrendingUp, Target, Zap, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useMutation } from "@tanstack/react-query";

const SPORTS = ["NBA", "WNBA", "NFL", "MLB", "SOCCER", "TENNIS", "F1", "ALL"];

interface ParlayLeg { pick: string; odds: string; why: string; game?: string; }
interface ParlayBlock { legs: ParlayLeg[]; combined_odds: string; why: string; ev: string; game?: string; }
interface ParlaysResult {
  sport: string;
  best_pick: { selection: string; odds: string; why: string; ev: string; units: string; game: string; };
  sgp: ParlayBlock;
  multi_parlay: ParlayBlock;
  ev_parlay: ParlayBlock;
  correlation_parlay: ParlayBlock;
  hash: string;
  timestamp: string;
}

function ParlayCard({ title, icon: Icon, block, color }: { title: string; icon: React.ElementType; block: ParlayBlock; color: string }) {
  return (
    <Card className="glass-card hover-elevate overflow-hidden">
      <CardHeader className="pb-3 border-b border-white/5 bg-white/[0.02]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className={cn("w-4 h-4", color)} />
            <span className="text-[10px] font-black uppercase tracking-[0.15em] text-muted-foreground">{title}</span>
          </div>
          <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-[9px] font-black">{block.ev}</Badge>
        </div>
        <div className="mt-3 flex items-center gap-4">
          <div className="text-3xl font-black text-primary">{block.combined_odds}</div>
          {block.game && <span className="text-[10px] font-mono text-muted-foreground">{block.game}</span>}
        </div>
      </CardHeader>
      <CardContent className="p-0 divide-y divide-white/5">
        {block.legs.map((leg, i) => (
          <div key={i} className="p-4 hover:bg-white/[0.02] transition-colors">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-bold">{leg.pick}</span>
              <span className="text-xs font-mono text-muted-foreground">{leg.odds}</span>
            </div>
            {leg.game && <p className="text-[10px] text-muted-foreground mb-1">{leg.game}</p>}
            <p className="text-[10px] text-muted-foreground/70 italic">{leg.why}</p>
          </div>
        ))}
      </CardContent>
      <div className="px-4 py-3 border-t border-white/5 bg-white/[0.01]">
        <p className="text-[10px] text-muted-foreground italic">{block.why}</p>
      </div>
    </Card>
  );
}

export default function ParlaysPage() {
  const [sport, setSport] = useState("NBA");
  const [game, setGame] = useState("");

  const { mutate, data, isPending, error } = useMutation({
    mutationFn: async () => {
      const params = new URLSearchParams({ sport });
      if (game) params.set("game", game);
      const res = await fetch(`/api/parlays?${params}`);
      if (!res.ok) throw new Error("Failed");
      return res.json() as Promise<ParlaysResult>;
    },
  });

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-4xl font-black tracking-tighter uppercase italic">
          Parlay <span className="text-primary">Engine</span>
        </h1>
        <p className="text-muted-foreground text-sm mt-1">SGP, Cross-Sport, EV Stack, and Correlation parlays.</p>
      </header>

      <div className="glass p-4 rounded-2xl flex flex-col md:flex-row gap-3">
        <div className="flex flex-nowrap gap-2 overflow-x-auto scrollbar-none">
          {SPORTS.map(s => (
            <button key={s} onClick={() => setSport(s)}
              className={cn("px-3 py-1.5 rounded-xl text-[10px] font-black tracking-widest uppercase transition-all",
                sport === s ? "bg-primary text-primary-foreground" : "hover:bg-white/5 text-muted-foreground"
              )}>
              {s}
            </button>
          ))}
        </div>
        <Input placeholder="Optional: specific game (e.g. Lakers vs Celtics)" value={game} onChange={e => setGame(e.target.value)}
          className="flex-1 h-10 bg-white/5 border-white/10 text-sm font-bold rounded-xl" />
        <Button onClick={() => mutate()} disabled={isPending}
          className="h-10 px-6 rounded-xl bg-primary text-primary-foreground font-black tracking-widest">
          {isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <>BUILD<Zap className="ml-2 w-3 h-3 fill-current" /></>}
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
          <RefreshCw className="w-10 h-10 text-primary animate-spin" />
          <p className="text-sm font-black tracking-widest uppercase">Building optimal parlays...</p>
        </div>
      )}

      {data && (
        <div className="space-y-8 animate-in slide-in-from-bottom-8 duration-700">
          {/* Best Pick */}
          <Card className="glass-card cave-border-profit overflow-hidden">
            <CardHeader className="bg-emerald-500/5 border-b border-emerald-500/20 px-6 py-4">
              <CardTitle className="text-xs font-black uppercase tracking-[0.3em] text-emerald-400 flex items-center gap-2">
                <Trophy className="w-4 h-4" /> Best Single Bet Tonight
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <h3 className="text-2xl font-black tracking-tight">{data.best_pick.selection}</h3>
                  <p className="text-sm text-muted-foreground mt-1">{data.best_pick.game}</p>
                  <p className="text-xs text-muted-foreground/70 italic mt-2">{data.best_pick.why}</p>
                </div>
                <div className="flex items-center gap-4 shrink-0">
                  <div className="text-center">
                    <div className="text-3xl font-black text-primary">{data.best_pick.odds}</div>
                    <div className="text-[9px] font-mono text-muted-foreground uppercase">Odds</div>
                  </div>
                  <div className="text-center">
                    <div className="text-xl font-black text-emerald-400">{data.best_pick.ev}</div>
                    <div className="text-[9px] font-mono text-muted-foreground uppercase">EV</div>
                  </div>
                  <Badge className="bg-primary/10 text-primary font-black text-xs">{data.best_pick.units}</Badge>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Parlay Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ParlayCard title="Same Game Parlay (SGP)" icon={GitMerge} block={data.sgp} color="text-primary" />
            <ParlayCard title="Cross-Sport Parlay" icon={TrendingUp} block={data.multi_parlay} color="text-amber-400" />
            <ParlayCard title="EV Stack Parlay" icon={Target} block={data.ev_parlay} color="text-emerald-400" />
            <ParlayCard title="Correlation Parlay" icon={Zap} block={data.correlation_parlay} color="text-amber-400" />
          </div>

          <div className="flex justify-center pt-4 opacity-20 hover:opacity-100 transition-opacity">
            <div className="flex items-center gap-4 text-[10px] font-mono tracking-widest uppercase">
              <span>Hash: {data.hash}</span>
              <span className="w-1 h-1 rounded-full bg-muted-foreground" />
              <span>{data.timestamp}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
