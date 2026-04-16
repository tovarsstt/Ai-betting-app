import { useListTrades } from "../hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Activity, TrendingUp, TrendingDown, Trophy, XCircle, DollarSign, Target } from "lucide-react";
import { format } from "date-fns";

export default function History() {
  const { data: trades, isLoading } = useListTrades();

  const wins = trades?.filter(t => t.actualOutcome === "WIN") || [];
  const losses = trades?.filter(t => t.actualOutcome === "LOSS") || [];
  const totalBets = trades?.length || 0;
  const winRate = totalBets > 0 ? (wins.length / totalBets * 100) : 0;

  if (isLoading) return (
    <div className="flex items-center justify-center h-64"><Activity className="w-8 h-8 text-primary animate-spin" /></div>
  );

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col gap-2">
        <h2 className="text-3xl font-display font-bold flex items-center gap-3">
          <DollarSign className="w-8 h-8 text-primary" /> Betting History
        </h2>
        <p className="text-muted-foreground">Track record powered by V12 God-Engine analytics.</p>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="bg-gradient-to-br from-card to-primary/5 border-primary/20">
          <CardContent className="p-4 text-center">
            <div className="text-3xl font-display font-bold text-primary">{totalBets}</div>
            <div className="text-xs text-muted-foreground mt-1">Total Bets</div>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-card to-success/5 border-success/20">
          <CardContent className="p-4 text-center">
            <div className="text-3xl font-display font-bold text-success">{wins.length}</div>
            <div className="text-xs text-muted-foreground mt-1">Wins</div>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-card to-destructive/5 border-destructive/20">
          <CardContent className="p-4 text-center">
            <div className="text-3xl font-display font-bold text-destructive">{losses.length}</div>
            <div className="text-xs text-muted-foreground mt-1">Losses</div>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-card to-accent/5 border-accent/20">
          <CardContent className="p-4 text-center">
            <div className="text-3xl font-display font-bold text-accent">{winRate.toFixed(0)}%</div>
            <div className="text-xs text-muted-foreground mt-1">Win Rate</div>
          </CardContent>
        </Card>
      </div>

      {/* Trade log */}
      <div className="space-y-4">
        {trades?.map((trade) => {
          const isWin = trade.actualOutcome === "WIN";
          return (
            <Card key={trade.id} className={cn(
              "overflow-hidden transition-all duration-300 hover:-translate-y-0.5 backdrop-blur",
              isWin && "border-success/30 bg-gradient-to-r from-card to-success/5",
              !isWin && "border-destructive/30 bg-gradient-to-r from-card to-destructive/5"
            )}>
              {/* Accent line */}
              <div className={cn("h-1 w-full", isWin ? "bg-gradient-to-r from-success to-success/20" : "bg-gradient-to-r from-destructive to-destructive/20")} />
              <CardContent className="p-5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-3 flex-wrap">
                      <Badge className={cn("font-bold text-xs px-3 py-1",
                        isWin ? "bg-success/20 text-success border border-success/30" : "bg-destructive/20 text-destructive border border-destructive/30"
                      )}>
                        {isWin ? <Trophy className="w-3 h-3 mr-1 inline" /> : <XCircle className="w-3 h-3 mr-1 inline" />}
                        {trade.actualOutcome}
                      </Badge>
                      <Badge variant="outline" className={cn("text-[10px] font-mono",
                        trade.alphaEdge === "SHARP" && "text-success border-success/30",
                        trade.alphaEdge === "FADE" && "text-destructive border-destructive/30",
                        trade.alphaEdge === "NEUTRAL" && "text-muted-foreground"
                      )}>
                        {trade.alphaEdge}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {trade.timestamp ? format(new Date(trade.timestamp), "MMM d, yyyy • h:mm a") : "—"}
                      </span>
                    </div>
                    <div className="font-display font-bold text-lg">{trade.matchup}</div>
                    <div className="text-sm text-muted-foreground">
                      <span className="text-foreground font-medium">{trade.selection}</span>
                    </div>
                    {trade.prospectTheoryRead && (
                      <div className="text-xs text-muted-foreground italic mt-1">{trade.prospectTheoryRead}</div>
                    )}
                  </div>
                  <div className="flex sm:flex-col items-center sm:items-end gap-3 sm:gap-1">
                    <div className="flex items-center gap-1.5">
                      <Target className="w-3.5 h-3.5 text-primary" />
                      <span className="text-xs text-muted-foreground">Kelly:</span>
                      <span className="text-sm font-bold text-primary">{trade.kellySizing}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {(trade.mathEv || 0) >= 0
                        ? <TrendingUp className="w-3.5 h-3.5 text-success" />
                        : <TrendingDown className="w-3.5 h-3.5 text-destructive" />
                      }
                      <span className="text-xs text-muted-foreground">EV:</span>
                      <span className={cn("text-sm font-bold", (trade.mathEv || 0) >= 0 ? "text-success" : "text-destructive")}>
                        {((trade.mathEv || 0) * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
        {(!trades || trades.length === 0) && (
          <div className="py-20 text-center border-2 border-dashed border-border rounded-xl">
            <DollarSign className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-50" />
            <h3 className="text-lg font-bold">No betting history yet</h3>
            <p className="text-muted-foreground">Your trades will appear here as they're recorded.</p>
          </div>
        )}
      </div>
    </div>
  );
}
