import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Trophy, TrendingDown, DollarSign, Percent, Filter } from "lucide-react";
import { cn } from "@/lib/utils";

const API_BASE = "/api/v12";

function useTrades() {
  return useQuery({
    queryKey: ["trades"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/trades`);
      if (!res.ok) throw new Error("Failed to fetch trades");
      const json = await res.json();
      return json.data as any[];
    },
  });
}

export default function History() {
  const { data: trades, isLoading } = useTrades();
  const [filter, setFilter] = useState<"ALL" | "Ganador" | "Perdida">("ALL");

  const wins = trades?.filter((t) => t.actualOutcome === "Ganador").length ?? 0;
  const losses = trades?.filter((t) => t.actualOutcome === "Perdida").length ?? 0;
  const total = wins + losses;
  const wr = total > 0 ? ((wins / total) * 100).toFixed(1) : "0.0";

  const sharpWins = trades?.filter(
    (t) => t.actualOutcome === "Ganador" && t.alphaEdge === "SHARP"
  ).length ?? 0;
  const sharpTotal = trades?.filter((t) => t.alphaEdge === "SHARP").length ?? 0;
  const sharpWr = sharpTotal > 0 ? ((sharpWins / sharpTotal) * 100).toFixed(0) : "0";

  const filtered =
    filter === "ALL" ? trades : trades?.filter((t) => t.actualOutcome === filter);

  const sportIcon = (matchup: string) => {
    const m = matchup?.toLowerCase() || "";
    if (m.includes("tennis") || m.match(/vs .*(alcaraz|sinner|djokovic|medvedev|swiatek|sabalenka|gauff|fritz|rublev|zverev|navarro|draper|hurkacz|rybakina)/i)) return "🎾";
    if (m.includes("ufc") || m.includes("mma")) return "🥊";
    if (m.includes("soccer") || m.includes("ucl") || m.includes("madrid") || m.includes("barcelona") || m.includes("arsenal") || m.includes("liverpool") || m.includes("city") || m.includes("ajax") || m.includes("juventus") || m.includes("psg") || m.includes("dortmund") || m.includes("miami") || m.includes("lafc") || m.includes("flamengo") || m.includes("santos") || m.includes("epl") || m.includes("inter")) return "⚽";
    if (m.includes("wbc") || m.includes("venezuela") || m.includes("dominican") || m.includes("puerto rico") || m.includes("cuba") || m.includes("mets") || m.includes("padres") || m.includes("marlins") || m.includes("yankees") || m.includes("braves") || m.includes("cubs") || m.includes("pirates") || m.includes("phillies") || m.includes("dodgers") || m.includes("royals") || m.includes("white sox") || m.includes("blue jays") || m.includes("red sox") || m.includes("cardinals")) return "⚾";
    if (m.includes("nhl") || m.includes("rangers") || m.includes("devils")) return "🏒";
    return "🏀";
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-24">
      <div>
        <h2 className="text-3xl font-display font-bold flex items-center gap-3">
          <Trophy className="w-8 h-8 text-primary" /> Betting History
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">All tracked wagers — each parlay counts as 1 bet.</p>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="bg-green-500/10 border-green-500/30">
          <CardContent className="pt-5 pb-4 text-center">
            <Trophy className="w-5 h-5 text-green-400 mx-auto mb-1" />
            <p className="text-3xl font-display font-bold text-green-400">{wins}</p>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Wins</p>
          </CardContent>
        </Card>
        <Card className="bg-red-500/10 border-red-500/30">
          <CardContent className="pt-5 pb-4 text-center">
            <TrendingDown className="w-5 h-5 text-red-400 mx-auto mb-1" />
            <p className="text-3xl font-display font-bold text-red-400">{losses}</p>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Losses</p>
          </CardContent>
        </Card>
        <Card className="bg-primary/10 border-primary/30">
          <CardContent className="pt-5 pb-4 text-center">
            <Percent className="w-5 h-5 text-primary mx-auto mb-1" />
            <p className="text-3xl font-display font-bold text-primary">{wr}%</p>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Win Rate</p>
          </CardContent>
        </Card>
        <Card className="bg-yellow-500/10 border-yellow-500/30">
          <CardContent className="pt-5 pb-4 text-center">
            <DollarSign className="w-5 h-5 text-yellow-400 mx-auto mb-1" />
            <p className="text-3xl font-display font-bold text-yellow-400">{sharpWr}%</p>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">SHARP WR</p>
          </CardContent>
        </Card>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <Filter className="w-4 h-4 text-muted-foreground" />
        {(["ALL", "Ganador", "Perdida"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider border transition-all",
              filter === f
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border text-muted-foreground hover:border-primary/50"
            )}
          >
            {f === "ALL" ? `All (${total})` : f === "Ganador" ? `Wins (${wins})` : `Losses (${losses})`}
          </button>
        ))}
      </div>

      {/* Trade list */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-16 rounded-xl bg-card/50 animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered?.map((trade) => {
            const won = trade.actualOutcome === "Ganador";
            return (
              <Card
                key={trade.id}
                className={cn(
                  "border transition-colors",
                  won ? "border-green-500/20 bg-green-500/5" : "border-red-500/10 bg-card/50"
                )}
              >
                <CardContent className="py-3 px-4 flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-xl shrink-0">{sportIcon(trade.matchup)}</span>
                    <div className="min-w-0">
                      <p className="font-medium text-sm leading-tight truncate">{trade.matchup}</p>
                      {trade.selection && (
                        <p className="text-xs text-muted-foreground truncate">{trade.selection}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    {trade.alphaEdge === "SHARP" && (
                      <Badge className="bg-yellow-500/10 text-yellow-400 border-yellow-500/20 text-[10px] hidden sm:flex">
                        SHARP
                      </Badge>
                    )}
                    {trade.mathEv && (
                      <span className="text-xs text-green-400 font-mono hidden sm:block">+${trade.mathEv}</span>
                    )}
                    <Badge
                      className={cn(
                        "text-xs font-bold",
                        won
                          ? "bg-green-500/15 text-green-400 border-green-500/30"
                          : "bg-red-500/10 text-red-400 border-red-500/20"
                      )}
                    >
                      {won ? "WIN" : "LOSS"}
                    </Badge>
                    <span className="text-xs text-muted-foreground hidden sm:block">
                      {new Date(trade.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                    </span>
                  </div>
                </CardContent>
              </Card>
            );
          })}
          {filtered?.length === 0 && (
            <div className="py-12 text-center border border-dashed border-border rounded-xl">
              <p className="text-muted-foreground">No trades found.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
