import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RefreshCw, Zap, TrendingUp, ArrowUpRight, ArrowDownRight, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useMutation } from "@tanstack/react-query";

const SPORTS = ["NBA", "WNBA", "NFL", "SOCCER", "TENNIS"];

interface SteamMove {
  game: string; bet: string; opening_line: string; current_line: string;
  move: string; direction: string; why: string; ev: string;
}
interface EVPlay { game: string; bet: string; odds: string; ev: string; why: string; }
interface SharpResult {
  sport: string;
  steam_moves: SteamMove[];
  rlm: SteamMove[];
  best_ev_plays: EVPlay[];
  hash?: string;
}

export default function SharpScannerPage() {
  const [sport, setSport] = useState("NBA");

  const { mutate, data, isPending, error } = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/sharp-scanner?sport=${sport}`);
      if (!res.ok) throw new Error("Failed");
      return res.json() as Promise<SharpResult>;
    },
  });

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-4xl font-black tracking-tighter uppercase italic">
          Sharp <span className="text-primary">Scanner</span>
        </h1>
        <p className="text-muted-foreground text-sm mt-1">Steam moves, reverse line movement, and CLV opportunities.</p>
      </header>

      <div className="glass p-4 rounded-2xl flex flex-nowrap items-center gap-3 overflow-x-auto scrollbar-none">
        {SPORTS.map(s => (
          <button key={s} onClick={() => setSport(s)}
            className={cn("px-3 py-1.5 rounded-xl text-[10px] font-black tracking-widest uppercase transition-all",
              sport === s ? "bg-primary text-primary-foreground" : "hover:bg-white/5 text-muted-foreground"
            )}>
            {s}
          </button>
        ))}
        <Button onClick={() => mutate()} disabled={isPending}
          className="ml-auto h-10 px-6 rounded-xl bg-primary text-primary-foreground font-black tracking-widest">
          {isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <>SCAN <Zap className="ml-2 w-3 h-3 fill-current" /></>}
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
          <Zap className="w-10 h-10 text-primary animate-bounce" />
          <p className="text-sm font-black tracking-widest uppercase">Scanning sharp action...</p>
        </div>
      )}

      {data && (
        <div className="space-y-8 animate-in slide-in-from-bottom-8 duration-700">
          {/* Steam Moves */}
          <div className="space-y-4">
            <h2 className="text-lg font-black uppercase tracking-widest flex items-center gap-2">
              <ArrowUpRight className="w-5 h-5 text-emerald-400" /> Steam Moves
            </h2>
            {data.steam_moves?.length ? data.steam_moves.map((m, i) => (
              <Card key={i} className="glass-card cave-border-profit hover-elevate">
                <CardContent className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div className="flex-1">
                    <h4 className="text-base font-black">{m.bet}</h4>
                    <p className="text-xs text-muted-foreground">{m.game}</p>
                    <p className="text-[10px] text-muted-foreground/70 italic mt-1">{m.why}</p>
                  </div>
                  <div className="flex items-center gap-4 shrink-0">
                    <div className="text-center">
                      <div className="text-xs font-mono text-muted-foreground">{m.opening_line}</div>
                      <div className="text-[9px] uppercase text-muted-foreground/50">Open</div>
                    </div>
                    <ArrowUpRight className="w-4 h-4 text-emerald-400" />
                    <div className="text-center">
                      <div className="text-xs font-mono font-bold">{m.current_line}</div>
                      <div className="text-[9px] uppercase text-muted-foreground/50">Current</div>
                    </div>
                    <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-[9px] font-black">{m.ev}</Badge>
                  </div>
                </CardContent>
              </Card>
            )) : <p className="text-sm text-muted-foreground italic">No steam moves detected.</p>}
          </div>

          {/* RLM */}
          <div className="space-y-4">
            <h2 className="text-lg font-black uppercase tracking-widest flex items-center gap-2">
              <ArrowDownRight className="w-5 h-5 text-amber-400" /> Reverse Line Movement
            </h2>
            {data.rlm?.length ? data.rlm.map((m, i) => (
              <Card key={i} className="glass-card cave-border-bone hover-elevate">
                <CardContent className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div className="flex-1">
                    <h4 className="text-base font-black">{m.bet}</h4>
                    <p className="text-xs text-muted-foreground">{m.game}</p>
                    <p className="text-[10px] text-muted-foreground/70 italic mt-1">{m.why}</p>
                  </div>
                  <div className="flex items-center gap-4 shrink-0">
                    <div className="text-center">
                      <div className="text-xs font-mono text-muted-foreground">{m.opening_line}</div>
                      <div className="text-[9px] uppercase text-muted-foreground/50">Open</div>
                    </div>
                    <ArrowDownRight className="w-4 h-4 text-amber-400" />
                    <div className="text-center">
                      <div className="text-xs font-mono font-bold">{m.current_line}</div>
                      <div className="text-[9px] uppercase text-muted-foreground/50">Current</div>
                    </div>
                    <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/20 text-[9px] font-black">{m.ev}</Badge>
                  </div>
                </CardContent>
              </Card>
            )) : <p className="text-sm text-muted-foreground italic">No RLM signals detected.</p>}
          </div>

          {/* Best EV Plays */}
          <div className="space-y-4">
            <h2 className="text-lg font-black uppercase tracking-widest flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-primary" /> Best EV Plays
            </h2>
            {data.best_ev_plays?.length ? data.best_ev_plays.map((p, i) => (
              <Card key={i} className="glass-card cave-border-ochre hover-elevate">
                <CardContent className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div className="flex-1">
                    <h4 className="text-base font-black">{p.bet}</h4>
                    <p className="text-xs text-muted-foreground">{p.game}</p>
                    <p className="text-[10px] text-muted-foreground/70 italic mt-1">{p.why}</p>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <div className="text-lg font-black text-primary">{p.odds}</div>
                    <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 font-black">{p.ev}</Badge>
                  </div>
                </CardContent>
              </Card>
            )) : <p className="text-sm text-muted-foreground italic">No high-EV plays found.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
