import { useState } from "react";
import { useListMatchups, useIngestMatchup } from "../hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Swords, Info, Cpu, Zap, Target } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

function StatBar({ label, val1, val2, max, reverse = false }: { label: string; val1: number; val2: number; max: number; reverse?: boolean }) {
  const p1 = (val1 / max) * 100;
  const p2 = (val2 / max) * 100;
  const winner1 = reverse ? val1 < val2 : val1 > val2;
  const winner2 = reverse ? val2 < val1 : val2 > val1;
  return (
    <div className="space-y-1.5 mt-4">
      <div className="flex justify-between text-xs font-medium text-muted-foreground">
        <span className={cn(winner1 && "text-foreground font-bold")}>{val1.toFixed(1)}</span>
        <span className="uppercase tracking-wider">{label}</span>
        <span className={cn(winner2 && "text-foreground font-bold")}>{val2.toFixed(1)}</span>
      </div>
      <div className="flex items-center gap-2">
        <Progress value={p1} className={cn("h-2 rotate-180", winner1 ? "[&>div]:bg-primary" : "[&>div]:bg-muted")} />
        <Progress value={p2} className={cn("h-2", winner2 ? "[&>div]:bg-primary" : "[&>div]:bg-muted")} />
      </div>
    </div>
  );
}

export default function Matchups() {
  const { data: matchups, isLoading } = useListMatchups();
  const ingestMutation = useIngestMatchup();
  
  const [matchupText, setMatchupText] = useState("");
  const [sport, setSport] = useState("NBA");
  const [simResults, setSimResults] = useState<any>(null);

  const handleSimulate = () => {
    if (!matchupText) {
      toast.error("Please enter a matchup (e.g. Warriors vs Lakers)");
      return;
    }
    
    setSimResults(null);
    toast.loading("Initializing V12 Engine Simulation...", { id: "sim" });

    ingestMutation.mutate({
      sport,
      matchup: matchupText,
      trueProbability: 0.55, 
      marketDecimalOdds: 1.90
    }, {
      onSuccess: (data) => {
        toast.success(`Simulation Complete! Omni-Vectors Deployed.`, { id: "sim" });
        setSimResults(data);
        setMatchupText("");
      },
      onError: (err: any) => {
        toast.error(err.message || "Engine failure during simulation.", { id: "sim" });
      }
    });
  };

  const renderSimResultCard = (title: string, data: any) => {
    if (!data) return null;
    
    // Support both the wrapped structure and the flat structure from recent V13 refactors
    const cog = data.cognitiveData || data;
    
    // Check if we actually have data (if we have suggested_side it's likely valid)
    if (!cog.suggested_side) return null;
    
    return (
      <Card className="border-primary/30 bg-card overflow-hidden mt-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
        <CardHeader className="bg-primary/10 border-b border-primary/20 pb-4">
          <div className="flex justify-between items-start">
            <div>
              <CardTitle className="font-display flex items-center gap-2 text-primary">
                <Target className="w-5 h-5" /> {title}
              </CardTitle>
              <CardDescription className="text-foreground/80 mt-1 font-medium">{cog.matchup}</CardDescription>
            </div>
            {cog.targetOdds && <Badge className="bg-primary/20 text-primary border-primary/30 text-lg py-1">{cog.targetOdds}</Badge>}
          </div>
        </CardHeader>
        <CardContent className="pt-6 space-y-6">
          
          <div className="space-y-4">
             <div className="flex items-start gap-4">
                <div className="bg-primary/10 p-3 rounded-xl border border-primary/20">
                  <Swords className="w-6 h-6 text-primary" />
                </div>
                <div>
                  <h4 className="font-bold text-sm uppercase tracking-wider text-muted-foreground mb-1">Suggested Play</h4>
                  <p className="font-display text-xl whitespace-pre-wrap">{cog.suggested_side}</p>
                </div>
             </div>
          </div>
          
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 p-4 rounded-xl border border-border bg-background/50">
             <div>
                <span className="block text-xs uppercase text-muted-foreground mb-1">EV Edge</span>
                <span className="font-mono font-bold text-green-400">{cog.alphaEdge}</span>
             </div>
             <div>
                <span className="block text-xs uppercase text-muted-foreground mb-1">Vig Adj. EV</span>
                <span className="font-mono font-bold text-green-400">{cog.vigAdjustedEv}</span>
             </div>
             <div>
                <span className="block text-xs uppercase text-muted-foreground mb-1">Confidence</span>
                <span className="font-mono font-bold text-primary">{cog.confidence_score ? (cog.confidence_score * 100).toFixed(1) + "%" : "N/A"}</span>
             </div>
             <div>
                <span className="block text-xs uppercase text-muted-foreground mb-1">Dominance</span>
                <span className="font-mono font-bold text-primary">{cog.ultronDominanceScore}/100</span>
             </div>
          </div>
          
          <div className="p-4 rounded-lg bg-muted/30 border border-border text-sm">
             <h4 className="font-bold mb-2">Engine Rationale:</h4>
             <p className="text-muted-foreground leading-relaxed">{cog.rationale}</p>
          </div>

        </CardContent>
      </Card>
    );
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-24">
      <div>
        <h2 className="text-3xl font-display font-bold flex items-center gap-3"><Cpu className="w-8 h-8 text-primary" /> Custom Engine Target</h2>
        <p className="text-muted-foreground mt-1">Deploy the V12 God-Engine sequentially for Standard Picks, SGP, and Slate Parlays.</p>
      </div>

      <Card className="border-primary/50 bg-primary/5 shadow-lg shadow-primary/10 relative overflow-hidden">
        {ingestMutation.isPending && (
          <div className="absolute inset-0 bg-background/50 backdrop-blur-sm z-10 flex flex-col items-center justify-center">
            <Cpu className="w-12 h-12 text-primary animate-pulse mb-4" />
            <h3 className="font-display font-bold text-xl tracking-widest text-primary">GENERATING OMNI-VECTORS...</h3>
          </div>
        )}
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-4 items-end">
            <div className="w-full sm:w-1/4 space-y-2">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Sport / League</label>
              <Input 
                value={sport}
                onChange={(e) => setSport(e.target.value)}
                placeholder="NBA, TENNIS, SOCCER..."
                className="font-bold border-border/50"
              />
            </div>
            <div className="w-full sm:w-1/2 space-y-2">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Target Matchup</label>
              <Input 
                value={matchupText}
                onChange={(e) => setMatchupText(e.target.value)}
                placeholder="e.g. Warriors vs Lakers, Sabalenka vs Osaka..."
                className="border-border/50"
                onKeyDown={(e) => e.key === 'Enter' && handleSimulate()}
              />
            </div>
            <Button 
              onClick={handleSimulate} 
              disabled={ingestMutation.isPending}
              className="w-full sm:w-1/4 font-bold tracking-widest bg-primary hover:bg-primary/90 text-primary-foreground h-10"
            >
              <Zap className="w-4 h-4 mr-2" /> ENGAGE
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* SIMULATION RESULTS */}
      {simResults && (
        <div className="space-y-8">
           <div className="flex items-center gap-4 py-4 border-b border-border">
              <Zap className="w-6 h-6 text-yellow-500" />
              <h3 className="text-2xl font-display font-bold">V12 Omni-Vector Payload</h3>
           </div>
           
           {renderSimResultCard("Standard Lock Execution", simResults.standard)}
           {renderSimResultCard("Correlated SGP Generation", simResults.sgp)}
           {renderSimResultCard("Slate Parlay Accumulation", simResults.slate)}
        </div>
      )}

      {/* HISTORICAL MATCHUPS LIST */}
      <div className="pt-12">
        <h2 className="text-2xl font-display font-bold flex items-center gap-3 mb-6"><Swords className="w-6 h-6 text-muted-foreground" /> Tracked Head-to-Head Ratings</h2>
        {isLoading ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">{[1,2].map(i => <div key={i} className="h-96 rounded-xl bg-card/50 animate-pulse" />)}</div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {matchups?.map((match: any) => (
              <Card key={match.id} className="bg-card/50 backdrop-blur border-border/50 hover:border-primary/30 transition-colors overflow-hidden">
                <CardHeader className="bg-black/20 border-b border-border/50 pb-4">
                  <div className="flex justify-between items-center mb-2">
                    <Badge variant="outline" className="border-border text-muted-foreground">{match.sport}</Badge>
                    {match.matchupEdge && <Badge className="bg-primary text-primary-foreground font-bold tracking-widest">EDGE: {match.matchupEdge}</Badge>}
                  </div>
                  <div className="flex justify-between items-center">
                    <CardTitle className="text-2xl font-display w-[40%] text-right truncate pr-4">{match.awayTeam}</CardTitle>
                    <span className="text-muted-foreground text-sm font-bold bg-background/50 px-2 py-1 rounded">VS</span>
                    <CardTitle className="text-2xl font-display w-[40%] pl-4 truncate">{match.homeTeam}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="pt-6">
                  <StatBar label="Offensive Rtg"  val1={match.awayOffenseRating||0}   val2={match.homeOffenseRating||0}   max={130} />
                  <StatBar label="Defensive Rtg"  val1={match.awayDefenseRating||0}   val2={match.homeDefenseRating||0}   max={130} reverse />
                  <StatBar label="Pace"           val1={match.awayPace||0}            val2={match.homePace||0}            max={110} />
                  <StatBar label="Turnovers"      val1={match.awayTurnoversPerGame||0} val2={match.homeTurnoversPerGame||0} max={20} reverse />
                  <StatBar label="Shot Quality"   val1={match.awayShotQuality||0}     val2={match.homeShotQuality||0}     max={1.5} />
                  <StatBar label="Rebounding"     val1={match.awayReboundingRating||0} val2={match.homeReboundingRating||0} max={60} />
                  
                  {match.matchupNotes && (
                    <div className="mt-6 p-4 rounded-lg bg-primary/5 border border-primary/20 flex gap-3 text-sm">
                      <Info className="w-5 h-5 text-primary shrink-0" />
                      <p className="text-muted-foreground leading-relaxed">{match.matchupNotes}</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
            {(!matchups || matchups.length === 0) && (
               <div className="col-span-full py-12 text-center border border-dashed border-border rounded-xl">
                 <Swords className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-50" />
                 <h3 className="text-lg font-bold">No Historical Matchups Tracked</h3>
                 <p className="text-muted-foreground">Data will populate here automatically during cron cycles.</p>
               </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
