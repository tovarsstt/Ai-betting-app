import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BarChart2, Cpu, RefreshCw, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

const SPORTS_TABS = ["NBA", "NFL", "MLB", "SOCCER", "TENNIS"];

function useTodayGames(sport: string) {
  return useQuery({
    queryKey: ["today-games", sport],
    queryFn: async () => {
      const res = await fetch(`/api/v12/today-games?sport=${sport}`);
      if (!res.ok) throw new Error("Failed to fetch games");
      const json = await res.json();
      return json.data || [];
    },
    staleTime: 1000 * 60 * 5,
  });
}

export default function Games() {
  const [sport, setSport] = useState("NBA");
  const { data: games, isLoading, refetch, isFetching } = useTodayGames(sport);

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-3xl font-display font-bold flex items-center gap-3">
            <BarChart2 className="w-8 h-8 text-primary" /> Live Games Viewer
          </h2>
          <p className="text-muted-foreground mt-1">
            Upcoming and live games with quick-analyze links.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          disabled={isFetching}
          className="border-border/50"
        >
          <RefreshCw className={cn("w-4 h-4 mr-2", isFetching && "animate-spin")} />
          Refresh
        </Button>
      </div>

      <div className="flex gap-2 flex-wrap">
        {SPORTS_TABS.map((s) => (
          <button
            key={s}
            onClick={() => setSport(s)}
            className={cn(
              "px-4 py-2 rounded-lg text-sm font-bold transition-all border",
              sport === s
                ? "bg-primary text-primary-foreground border-primary shadow-[0_0_10px_rgba(0,255,255,0.2)]"
                : "bg-card border-border/50 text-muted-foreground hover:text-foreground hover:border-primary/40"
            )}
          >
            {s}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-36 rounded-xl bg-card/50 animate-pulse" />
          ))}
        </div>
      ) : games && games.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {games.map((game: any) => (
            <Card
              key={game.id}
              className="border-border/50 bg-card/60 backdrop-blur hover:border-primary/40 transition-all duration-300 hover:-translate-y-0.5"
            >
              <CardHeader className="pb-2">
                <div className="flex justify-between items-center">
                  <Badge variant="outline" className="text-xs border-border/60 text-muted-foreground">
                    {game.sport || sport}
                  </Badge>
                  <span className="text-xs text-muted-foreground font-mono">
                    {game.date ? new Date(game.date).toLocaleDateString() : "Today"}
                  </span>
                </div>
              </CardHeader>
              <CardContent className="pb-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-center flex-1">
                    <p className="font-display font-bold text-lg truncate">{game.awayTeam || game.away_team}</p>
                    {game.awayScore != null && (
                      <p className="text-2xl font-black text-primary">{game.awayScore}</p>
                    )}
                  </div>
                  <div className="px-4 text-muted-foreground font-bold text-sm">VS</div>
                  <div className="text-center flex-1">
                    <p className="font-display font-bold text-lg truncate">{game.homeTeam || game.home_team}</p>
                    {game.homeScore != null && (
                      <p className="text-2xl font-black text-primary">{game.homeScore}</p>
                    )}
                  </div>
                </div>
                {game.status && (
                  <div className="flex justify-center">
                    <Badge
                      className={cn(
                        "text-xs font-bold",
                        game.status === "Final"
                          ? "bg-muted text-muted-foreground"
                          : "bg-success/20 text-success border-success/30"
                      )}
                    >
                      {game.status}
                    </Badge>
                  </div>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full border-primary/30 text-primary hover:bg-primary/10"
                  onClick={() => {
                    const matchup = `${game.awayTeam || game.away_team} vs ${game.homeTeam || game.home_team}`;
                    const params = new URLSearchParams({ prefill: matchup, sport });
                    window.location.href = `/matchups?${params.toString()}`;
                  }}
                >
                  <Cpu className="w-3 h-3 mr-1.5" />
                  Analyze in Engine
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="py-20 text-center border-2 border-dashed border-border rounded-xl">
          <Zap className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-30" />
          <h3 className="text-lg font-bold text-muted-foreground">No games found for {sport}</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Add a BALLDONTLIE_API_KEY to .env to enable live game fetching.
          </p>
        </div>
      )}
    </div>
  );
}
