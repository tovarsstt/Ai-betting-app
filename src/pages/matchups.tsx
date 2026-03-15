import { useState } from "react";
import { useListMatchups, useIngestMatchup } from "../hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Swords, Info, Cpu, Zap } from "lucide-react";
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

  const handleSimulate = () => {
    if (!matchupText) {
      toast.error("Please enter a matchup (e.g. Warriors vs Lakers)");
      return;
    }
    
    toast.loading("Initializing V12 Engine Simulation...", { id: "sim" });

    // Mocking the probability and odds for manual testing
    ingestMutation.mutate({
      sport,
      matchup: matchupText,
      trueProbability: 0.55, 
      marketDecimalOdds: 1.90
    }, {
      onSuccess: (data) => {
        toast.success(`Simulation Complete: ${data.analysis.signal} Edge Identified!`, { id: "sim" });
        setMatchupText("");
      },
      onError: () => {
        toast.error("Engine failure during simulation.", { id: "sim" });
      }
    });
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div>
        <h2 className="text-3xl font-display font-bold flex items-center gap-3"><Swords className="w-8 h-8 text-primary" /> Head-to-Head Matchups</h2>
        <p className="text-muted-foreground mt-1">Deep statistical analysis and manual V12 Engine intelligence targeting.</p>
      </div>

      <Card className="border-primary/50 bg-primary/5 shadow-lg shadow-primary/10">
        <CardHeader>
          <CardTitle className="font-display flex items-center gap-2">
            <Cpu className="w-5 h-5 text-primary" /> Custom AI Simulation
          </CardTitle>
          <CardDescription>Manually trigger the God-Engine to analyze a specific game context.</CardDescription>
        </CardHeader>
        <CardContent>
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
              className="w-full sm:w-1/4 font-bold tracking-widest bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              {ingestMutation.isPending ? "SIMULATING..." : <><Zap className="w-4 h-4 mr-2" /> SIMULATE</>}
            </Button>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">{[1,2].map(i => <div key={i} className="h-96 rounded-xl bg-card/50 animate-pulse" />)}</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {matchups?.map((match) => (
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
               <Cpu className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-50" />
               <h3 className="text-lg font-bold">Awaiting Data Ingestion</h3>
               <p className="text-muted-foreground">Use the simulation tool above to analyze a specific matchup.</p>
             </div>
          )}
        </div>
      )}
    </div>
  );
}
