import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RefreshCw, Shield, Zap, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useMutation } from "@tanstack/react-query";

const SPORTS = ["NBA", "WNBA", "NFL", "SOCCER", "TENNIS"];

interface ArbOpp {
  game: string; market: string;
  legs: { name: string; odds: number; book: string }[];
  totalImpliedProb: number; expectedReturn: number;
}

const LEG_ACCENTS = ["text-emerald-400", "text-amber-400", "text-stone-300"];

export default function ArbitragePage() {
  const [sport, setSport] = useState("NBA");

  const { mutate, data, isPending, error } = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/arbitrage?sport=${sport}`);
      if (!res.ok) throw new Error("Failed");
      return res.json() as Promise<{ opportunities: ArbOpp[]; scanned: number }>;
    },
  });

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-4xl font-black tracking-tighter uppercase italic">
          Arbitrage <span className="text-primary">Scanner</span>
        </h1>
        <p className="text-muted-foreground text-sm mt-1">Cross-book market discrepancies — guaranteed profit opportunities.</p>
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
          <Shield className="w-10 h-10 text-primary animate-bounce" />
          <p className="text-sm font-black tracking-widest uppercase">Scanning across books...</p>
        </div>
      )}

      {data && (
        <div className="space-y-6 animate-in slide-in-from-bottom-8 duration-700">
          <div className="flex items-center gap-3">
            <Badge variant="outline" className="text-xs font-mono">{data.scanned} events scanned</Badge>
            <Badge className={cn("text-xs font-black", data.opportunities.length > 0 ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-white/5 text-muted-foreground border-white/10")}>
              {data.opportunities.length} opportunities found
            </Badge>
          </div>

          {data.opportunities.length === 0 ? (
            <Card className="glass-card p-8 text-center">
              <Shield className="w-12 h-12 text-muted-foreground/30 mx-auto mb-3" />
              <p className="text-muted-foreground text-sm">No arbitrage opportunities detected right now. Markets are efficiently priced.</p>
              <p className="text-[10px] text-muted-foreground/50 mt-2">Arb windows typically last 30-90 seconds. Keep scanning.</p>
            </Card>
          ) : (
            data.opportunities.map((opp, i) => (
              <Card key={i} className="glass-card cave-border-profit hover-elevate overflow-hidden">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-black">{opp.game}</h3>
                    <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-sm font-black">
                      +{(opp.expectedReturn * 100).toFixed(2)}% ROI
                    </Badge>
                  </div>
                  <div className={cn("grid gap-4", opp.legs.length > 2 ? "grid-cols-3" : "grid-cols-2")}>
                    {opp.legs.map((leg, j) => (
                      <div key={j} className="p-4 rounded-xl bg-white/5 border border-white/10">
                        <div className={cn("text-[10px] font-black uppercase tracking-widest mb-1", LEG_ACCENTS[j % LEG_ACCENTS.length])}>{leg.name}</div>
                        <div className="text-2xl font-black">{leg.odds > 0 ? "+" : ""}{leg.odds}</div>
                        <div className="text-xs text-muted-foreground mt-1">{leg.book}</div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-3 text-[10px] text-muted-foreground font-mono">
                    Combined implied probability: {(opp.totalImpliedProb * 100).toFixed(2)}% (under 100% = arbitrage)
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}
    </div>
  );
}
