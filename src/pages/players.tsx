import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Users, Search, Zap, Brain, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

function usePlayerPropSearch(playerQuery: string) {
  return useQuery({
    queryKey: ["player-props", playerQuery],
    queryFn: async () => {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sport: "NBA",
          matchup: playerQuery,
          context: "[PLAYER_PROP_MODE]",
          sharpOdds: "1.909",
          softOdds: "1.87",
        }),
      });
      if (!res.ok) throw new Error("Analysis failed");
      return res.json();
    },
    enabled: false,
  });
}

const QUICK_PROPS = [
  "LeBron James Over 25.5 Points",
  "Stephen Curry Over 4.5 Three Pointers",
  "Nikola Jokic Triple Double",
  "Giannis Antetokounmpo Over 30.5 Points",
  "Luka Doncic Over 8.5 Assists",
  "Anthony Davis Over 13.5 Rebounds",
];

export default function Players() {
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");

  const { data: result, isFetching, refetch } = usePlayerPropSearch(activeQuery);

  const handleSearch = () => {
    if (!query.trim()) {
      toast.error("Enter a player name or prop (e.g. LeBron Over 25.5 Points)");
      return;
    }
    setActiveQuery(query);
    setTimeout(() => refetch(), 50);
  };

  const handleQuickProp = (prop: string) => {
    setQuery(prop);
    setActiveQuery(prop);
    setTimeout(() => refetch(), 50);
  };

  const cogData = result?.cognitiveData || result;

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div>
        <h2 className="text-3xl font-display font-bold flex items-center gap-3">
          <Users className="w-8 h-8 text-primary" /> Player Prop Engine
        </h2>
        <p className="text-muted-foreground mt-1">
          AI-powered player prop analysis. Enter any player + stat line for instant edge detection.
        </p>
      </div>

      <Card className="border-primary/30 bg-primary/5">
        <CardContent className="pt-6">
          <div className="flex gap-3">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. LeBron James Over 25.5 Points, Curry 4+ Threes..."
              className="flex-1 border-border/50"
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
            <Button
              onClick={handleSearch}
              disabled={isFetching}
              className="bg-primary hover:bg-primary/90 font-bold tracking-wider"
            >
              {isFetching ? (
                <Brain className="w-4 h-4 animate-pulse" />
              ) : (
                <Search className="w-4 h-4" />
              )}
              <span className="ml-2">ANALYZE</span>
            </Button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {QUICK_PROPS.map((prop) => (
              <button
                key={prop}
                onClick={() => handleQuickProp(prop)}
                className="text-xs px-3 py-1.5 rounded-full bg-card border border-border/50 text-muted-foreground hover:text-foreground hover:border-primary/40 transition-all"
              >
                {prop}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {isFetching && (
        <Card className="border-border/50 bg-card/30">
          <CardContent className="py-16 flex flex-col items-center gap-4">
            <Brain className="w-12 h-12 text-primary animate-pulse" />
            <p className="font-display font-bold text-primary tracking-widest animate-pulse">
              ANALYZING PROP MARKETS...
            </p>
          </CardContent>
        </Card>
      )}

      {cogData?.suggested_side && !isFetching && (
        <Card className="border-primary/40 bg-card overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500">
          <CardHeader className="bg-primary/10 border-b border-primary/20 pb-4">
            <div className="flex justify-between items-start">
              <CardTitle className="font-display text-primary flex items-center gap-2">
                <Zap className="w-5 h-5" /> Prop Analysis Result
              </CardTitle>
              {cogData.targetOdds && (
                <Badge className="bg-primary/20 text-primary border-primary/30 text-base py-1 px-3">
                  {cogData.targetOdds}
                </Badge>
              )}
            </div>
            <p className="text-foreground/80 font-medium mt-1">{cogData.matchup || activeQuery}</p>
          </CardHeader>
          <CardContent className="pt-6 space-y-6">
            <div className="flex items-start gap-4">
              <div className="bg-primary/10 p-3 rounded-xl border border-primary/20">
                <TrendingUp className="w-6 h-6 text-primary" />
              </div>
              <div>
                <h4 className="font-bold text-sm uppercase tracking-wider text-muted-foreground mb-1">
                  Suggested Play
                </h4>
                <p className="font-display text-xl whitespace-pre-wrap">{cogData.suggested_side}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 p-4 rounded-xl border border-border bg-background/50">
              <div>
                <span className="block text-xs uppercase text-muted-foreground mb-1">EV Edge</span>
                <span className={cn("font-mono font-bold", cogData.alphaEdge?.startsWith("+") ? "text-green-400" : "text-foreground")}>
                  {cogData.alphaEdge || "—"}
                </span>
              </div>
              <div>
                <span className="block text-xs uppercase text-muted-foreground mb-1">Vig Adj. EV</span>
                <span className="font-mono font-bold text-green-400">{cogData.vigAdjustedEv || "—"}</span>
              </div>
              <div>
                <span className="block text-xs uppercase text-muted-foreground mb-1">Confidence</span>
                <span className="font-mono font-bold text-primary">
                  {cogData.confidence_score ? (cogData.confidence_score * 100).toFixed(1) + "%" : "—"}
                </span>
              </div>
              <div>
                <span className="block text-xs uppercase text-muted-foreground mb-1">Dominance</span>
                <span className="font-mono font-bold text-primary">{cogData.ultronDominanceScore || "—"}/100</span>
              </div>
            </div>

            {cogData.rationale && (
              <div className="p-4 rounded-lg bg-muted/30 border border-border text-sm">
                <h4 className="font-bold mb-2">Engine Rationale:</h4>
                <p className="text-muted-foreground leading-relaxed">{cogData.rationale}</p>
              </div>
            )}

            {Array.isArray(cogData.omni_vector_generation) && cogData.omni_vector_generation.length > 0 && (
              <div className="space-y-2">
                <h4 className="font-bold text-sm uppercase tracking-wider text-muted-foreground">Omni-Vectors</h4>
                {cogData.omni_vector_generation.map((pick: any, i: number) => (
                  <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-background/50 border border-border/50">
                    <Badge variant="outline" className="shrink-0 text-xs">{pick.tier}</Badge>
                    <div>
                      <p className="font-bold">{pick.lock_text}</p>
                      <p className="text-sm text-muted-foreground">{pick.lock_data}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {!isFetching && !cogData?.suggested_side && (
        <div className="py-20 text-center border-2 border-dashed border-border rounded-xl">
          <Users className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-30" />
          <h3 className="text-lg font-bold text-muted-foreground">Enter a player prop above</h3>
          <p className="text-sm text-muted-foreground mt-1">
            The engine will analyze line value, recent form, and market edges.
          </p>
        </div>
      )}
    </div>
  );
}
