import { useListPredictions, useListEvSignals } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatPercentage, cn } from "@/lib/utils";
import { Activity, Target, TrendingUp, Zap, Skull, ShieldAlert } from "lucide-react";
import { format } from "date-fns";

export default function Dashboard() {
  const { data: predictions, isLoading: loadingPreds } = useListPredictions();
  const { data: evSignals, isLoading: loadingEv } = useListEvSignals();

  const sharpPredictions = predictions?.filter(p => p.signal === "SHARP") || [];
  const fadePredictions  = predictions?.filter(p => p.signal === "FADE")  || [];
  const avgEvEdge = evSignals?.reduce((acc, curr) => acc + (curr.evEdgePct || 0), 0) / (evSignals?.length || 1);

  if (loadingPreds || loadingEv) return (
    <div className="flex items-center justify-center h-64"><Activity className="w-8 h-8 text-primary animate-spin" /></div>
  );

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col gap-2">
        <h2 className="text-3xl font-display font-bold">Intelligence Overview</h2>
        <p className="text-muted-foreground">V12 God-Engine real-time analytics and system status.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-card/50 backdrop-blur border-border/50 hover:border-primary/50 transition-colors">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Active Signals</span>
              <Target className="w-5 h-5 text-primary" />
            </div>
            <div className="text-4xl font-display font-bold">{evSignals?.length || 0}</div>
            <div className="mt-2 text-xs text-primary">+12% from yesterday</div>
          </CardContent>
        </Card>

        <Card className="bg-card/50 backdrop-blur border-border/50 hover:border-success/50 transition-colors">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Sharp Plays</span>
              <Zap className="w-5 h-5 text-success" />
            </div>
            <div className="text-4xl font-display font-bold text-success">{sharpPredictions.length}</div>
            <div className="mt-2 text-xs text-muted-foreground">Identified actionable edges</div>
          </CardContent>
        </Card>

        <Card className="bg-card/50 backdrop-blur border-border/50 hover:border-destructive/50 transition-colors">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Fade Warnings</span>
              <Skull className="w-5 h-5 text-destructive" />
            </div>
            <div className="text-4xl font-display font-bold text-destructive">{fadePredictions.length}</div>
            <div className="mt-2 text-xs text-muted-foreground">High-risk traps avoided</div>
          </CardContent>
        </Card>

        <Card className="bg-card/50 backdrop-blur border-border/50 hover:border-accent/50 transition-colors">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Avg EV Edge</span>
              <TrendingUp className="w-5 h-5 text-accent" />
            </div>
            <div className="text-4xl font-display font-bold text-accent">{formatPercentage(avgEvEdge || 0)}</div>
            <div className="mt-2 text-xs text-muted-foreground">Across all monitored markets</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 border-border/50 bg-card/30 backdrop-blur flex flex-col">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="font-display text-xl flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-primary" /> Highest Edge Markets
            </CardTitle>
            <CardDescription>Top EV opportunities detected by ASA v5.0 filter</CardDescription>
          </CardHeader>
          <CardContent className="p-0 flex-1">
            <div className="divide-y divide-border/50">
              {evSignals?.slice(0, 5).map((signal) => (
                <div key={signal.id} className="p-4 flex items-center justify-between hover:bg-muted/20 transition-colors">
                  <div>
                    <div className="font-bold flex items-center gap-2">
                      {signal.homeTeam} vs {signal.awayTeam}
                      <Badge className={cn("ml-2 font-bold tracking-widest",
                        signal.signal === "SHARP" && "bg-success text-success-foreground",
                        signal.signal === "FADE"  && "bg-destructive text-destructive-foreground",
                        signal.signal === "NEUTRAL" && "bg-muted text-muted-foreground"
                      )}>{signal.signal}</Badge>
                    </div>
                    <div className="text-sm text-muted-foreground mt-1 flex items-center gap-3">
                      <span>{signal.sport}</span><span>•</span>
                      <span>Bet: <strong className="text-foreground">{signal.betSide}</strong></span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-display font-bold text-success">{formatPercentage(signal.evEdgePct)} EV</div>
                    <div className="text-xs text-muted-foreground">Kelly: {(signal.kellyFraction || 0).toFixed(2)}</div>
                  </div>
                </div>
              ))}
              {(!evSignals || evSignals.length === 0) && (
                <div className="p-8 text-center text-muted-foreground">No EV signals detected.</div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/50 bg-card/30 backdrop-blur">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="font-display text-xl flex items-center gap-2">
              <Activity className="w-5 h-5 text-primary" /> Engine Activity
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-4">
            {predictions?.slice(0, 5).map((pred) => (
              <div key={pred.id} className="flex gap-3">
                <div className="mt-1 w-2 h-2 rounded-full bg-primary shrink-0" />
                <div>
                  <p className="text-sm">Analyzed <span className="font-semibold text-foreground">{pred.homeTeam} vs {pred.awayTeam}</span></p>
                  <p className="text-xs text-muted-foreground mt-1">Predicted: <span className="text-primary">{pred.predictedWinner}</span> • {format(new Date(pred.createdAt), "HH:mm:ss")}</p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
