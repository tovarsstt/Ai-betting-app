import { useState } from "react";
import { useListTeams, useGetTeamPerformance } from "../hooks/useApi";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Shield, TrendingUp, TrendingDown, Minus, Filter } from "lucide-react";
import { cn } from "@/lib/utils";

// Inclusive list of standard and emerging sports monitored by the v12 God-Engine
const SPORTS = ["ALL", "NBA", "NFL", "MLB", "NHL", "SOCCER", "NCAAB", "CFB", "WNBA", "UFC", "TENNIS", "F1"];

function TeamRow({ team }: { team: any }) {
  const { data: perf, isLoading } = useGetTeamPerformance(team.id);

  if (isLoading) {
    return (
      <TableRow>
        <TableCell colSpan={8} className="text-center text-muted-foreground py-4">
          Loading {team.name} data...
        </TableCell>
      </TableRow>
    );
  }
  
  if (!perf) return null;

  return (
    <TableRow className="border-border/50 hover:bg-muted/10 transition-colors">
      <TableCell className="font-bold">
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <span>{team.name}</span>
            <span className="text-[10px] font-bold tracking-wider px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground uppercase">
              {team.sport}
            </span>
          </div>
          <span className="text-xs text-muted-foreground font-normal mt-0.5">
            {team.conference} {team.division && `• ${team.division}`}
          </span>
        </div>
      </TableCell>
      <TableCell className="text-center font-display text-lg font-bold">
        {perf.wins}-{perf.losses}{perf.draws ? `-${perf.draws}` : ''}
      </TableCell>
      <TableCell className="text-center font-mono">{perf.atsRecord || "—"}</TableCell>
      <TableCell className="text-center font-mono">{perf.overUnderRecord || "—"}</TableCell>
      <TableCell className="text-center text-primary font-bold">{(perf.offensiveRating || 0).toFixed(1)}</TableCell>
      <TableCell className="text-center text-accent font-bold">{(perf.defensiveRating || 0).toFixed(1)}</TableCell>
      <TableCell className="text-center text-muted-foreground">{(perf.pace || 0).toFixed(1)}</TableCell>
      <TableCell className="text-right font-medium">
        <div className="flex items-center justify-end gap-1.5">
          <span>{perf.streakType}{perf.streakCount}</span>
          {perf.streakType === "W" ? (
            <TrendingUp className="w-4 h-4 text-success" />
          ) : perf.streakType === "L" ? (
            <TrendingDown className="w-4 h-4 text-destructive" />
          ) : (
            <Minus className="w-4 h-4 text-muted-foreground" />
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}

export default function Teams() {
  const { data: teams, isLoading } = useListTeams();
  const [filter, setFilter] = useState("ALL");

  const filteredTeams = teams?.filter((t: any) => filter === "ALL" || t.sport === filter) || [];

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-6">
        <div>
          <h2 className="text-3xl font-display font-bold flex items-center gap-3">
            <Shield className="w-8 h-8 text-primary" /> 
            Team Intelligence
          </h2>
          <p className="text-muted-foreground mt-1">Long-term performance: ATS, O/U, ratings, pace, streak data across all leagues.</p>
        </div>
        
        <div className="flex flex-wrap gap-2 max-w-full justify-start xl:justify-end">
          {SPORTS.map((s) => (
            <Badge 
              key={s} 
              variant={filter === s ? "default" : "outline"}
              className={cn(
                "cursor-pointer hover:bg-primary/80 hover:text-primary-foreground transition-all duration-300", 
                filter === s ? "bg-primary text-primary-foreground font-bold shadow-[0_0_10px_rgba(0,255,255,0.4)]" : "text-muted-foreground border-border/60"
              )}
              onClick={() => setFilter(s)}
            >
              {s}
            </Badge>
          ))}
        </div>
      </div>

      <Card className="bg-card/50 backdrop-blur border-border/50">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader className="bg-black/40">
              <TableRow className="border-border/50">
                <TableHead className="w-[250px]">Team</TableHead>
                <TableHead className="text-center whitespace-nowrap">W-L</TableHead>
                <TableHead className="text-center whitespace-nowrap">ATS</TableHead>
                <TableHead className="text-center whitespace-nowrap">O/U</TableHead>
                <TableHead className="text-center whitespace-nowrap">Off Rtg</TableHead>
                <TableHead className="text-center whitespace-nowrap">Def Rtg</TableHead>
                <TableHead className="text-center whitespace-nowrap">Pace / Temp</TableHead>
                <TableHead className="text-right whitespace-nowrap">Streak</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-16">
                    <div className="flex flex-col items-center gap-3 text-muted-foreground">
                      <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                      Loading global team intelligence...
                    </div>
                  </TableCell>
                </TableRow>
              ) : filteredTeams.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-16 text-muted-foreground">
                    <Filter className="w-10 h-10 mx-auto mb-3 opacity-30" />
                    <p className="text-lg font-medium">No teams found</p>
                    <p className="text-sm">There are no tracked teams matching the '{filter}' filter.</p>
                  </TableCell>
                </TableRow>
              ) : (
                filteredTeams.map((team: any) => (
                  <TeamRow key={team.id} team={team} />
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}
