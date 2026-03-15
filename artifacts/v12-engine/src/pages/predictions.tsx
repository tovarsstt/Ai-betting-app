import { useState } from "react";
import { useListPredictions } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatPercentage, cn } from "@/lib/utils";
import { format } from "date-fns";
import { Brain, Zap, Skull, CheckCircle2, ChevronRight, Filter } from "lucide-react";

export default function Predictions() {
  const { data: predictions, isLoading } = useListPredictions();
  const [filter, setFilter] = useState<string>("ALL");

  const filteredPredictions = predictions?.filter(p => filter === "ALL" || p.signal === filter) || [];

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-3xl font-display font-bold flex items-center gap-3"><Brain className="w-8 h-8 text-primary" /> Model Predictions</h2>
          <p className="text-muted-foreground mt-1">V12 Machine Learning Output & Analysis</p>
        </div>
        <div className="flex bg-card border border-border rounded-lg p-1">
          {["ALL", "SHARP", "FADE", "NEUTRAL"].map((f) => (
            <button key={f} onClick={() => setFilter(f)} className={cn("px-4 py-2 text-sm font-medium rounded-md transition-all hover-elevate", filter === f ? "bg-primary text-primary-foreground shadow-md" : "text-muted-foreground hover:text-foreground")}>{f}</button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          {[1,2,3,4,5,6].map(i => <div key={i} className="h-[300px] rounded-xl bg-card/50 animate-pulse" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          {filteredPredictions.map((pred) => (
            <Card key={pred.id} className={cn("flex flex-col overflow-hidden transition-all duration-300 hover:-translate-y-1 bg-card/60 backdrop-blur",
              pred.signal === "SHARP"   && "border-success/30 hover:border-success/80 hover:shadow-[0_0_20px_rgba(0,255,0,0.15)]",
              pred.signal === "FADE"    && "border-destructive/30 hover:border-destructive/80 hover:shadow-[0_0_20px_rgba(255,0,0,0.15)]",
              pred.signal === "NEUTRAL" && "border-border hover:border-primary/50"
            )}>
              <CardHeader className="pb-3 border-b border-border/50">
                <div className="flex justify-between items-start">
                  <div className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-2">{pred.sport} • {format(new Date(pred.gameDate), "MMM d, yyyy")}</div>
                  <Badge variant="outline" className={cn("font-bold px-2 py-0.5",
                    pred.signal === "SHARP" && "bg-success/20 text-success border-success/50",
                    pred.signal === "FADE"  && "bg-destructive/20 text-destructive border-destructive/50"
                  )}>
                    {pred.signal === "SHARP" && <Zap className="w-3 h-3 mr-1 inline" />}
                    {pred.signal === "FADE"  && <Skull className="w-3 h-3 mr-1 inline" />}
                    {pred.signal}
                  </Badge>
                </div>
                <CardTitle className="text-xl font-display flex flex-col gap-1">
                  <span>{pred.awayTeam}</span>
                  <span className="text-muted-foreground text-sm">@</span>
                  <span>{pred.homeTeam}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="flex-1 pt-4 pb-2 space-y-4">
                <div className="flex justify-between items-center p-3 rounded-lg bg-background/50 border border-border/50">
                  <span className="text-sm text-muted-foreground">Predicted Winner</span>
                  <span className="font-bold text-foreground flex items-center gap-1"><CheckCircle2 className="w-4 h-4 text-primary" />{pred.predictedWinner}</span>
                </div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><p className="text-muted-foreground">EV Edge</p><p className={cn("font-bold text-lg", pred.evEdge && pred.evEdge > 0 ? "text-success" : "text-foreground")}>{formatPercentage(pred.evEdge)}</p></div>
                  <div><p className="text-muted-foreground">Kelly Stake</p><p className="font-bold text-lg text-primary">{formatPercentage(pred.kellyStake)}</p></div>
                  <div><p className="text-muted-foreground">Tilt Tensor</p><p className="font-medium">{pred.tiltTensor?.toFixed(2) || "—"}</p></div>
                  <div><p className="text-muted-foreground">Circadian Friction</p><p className="font-medium text-destructive">{pred.circadianFrictionHome?.toFixed(2) || "—"}</p></div>
                </div>
              </CardContent>
              <CardFooter className="pt-2 border-t border-border/50 bg-black/20">
                <Button variant="ghost" className="w-full justify-between hover-elevate">View Full Analysis <ChevronRight className="w-4 h-4 text-muted-foreground" /></Button>
              </CardFooter>
            </Card>
          ))}
          {filteredPredictions.length === 0 && (
            <div className="col-span-full py-20 text-center border-2 border-dashed border-border rounded-xl">
              <Filter className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-bold">No predictions found</h3>
              <p className="text-muted-foreground">Change filters or ingest new games to generate models.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
