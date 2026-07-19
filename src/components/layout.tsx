import type { ReactNode } from "react";
import { Link, useLocation } from "wouter";
import {
  SidebarProvider, Sidebar, SidebarContent, SidebarGroup,
  SidebarGroupContent, SidebarMenu, SidebarMenuItem,
  SidebarMenuButton, SidebarTrigger, SidebarHeader
} from "@/components/ui/sidebar";
import { Swords, TrendingUp, BarChart3, Zap, Shield, Trophy, Radar, Crosshair } from "lucide-react";

const navigation = [
  { name: "Game Breakdown", href: "/", icon: Swords },
  { name: "Pick Report", href: "/pick-report", icon: Crosshair },
  { name: "Parlays", href: "/parlays", icon: TrendingUp },
  { name: "Alpha Sheets", href: "/alpha-sheets", icon: BarChart3 },
  { name: "Sharp Scanner", href: "/sharp-scanner", icon: Zap },
  { name: "Arbitrage", href: "/arbitrage", icon: Shield },
  { name: "Upset Radar", href: "/upset-radar", icon: Radar },
  { name: "Track Record", href: "/track-record", icon: Trophy },
];

export function AppLayout({ children }: { children: ReactNode }) {
  const [location] = useLocation();

  return (
    <SidebarProvider style={{ "--sidebar-width": "15rem" } as React.CSSProperties}>
      <div className="flex min-h-screen w-full bg-background dark text-foreground">

        {/* ── Sidebar ── */}
        <Sidebar className="border-r border-sidebar-border bg-sidebar">
          <SidebarHeader className="p-5 border-b border-sidebar-border/50">
            <Link href="/" className="flex items-center gap-3 cursor-pointer">
              <img src="/brand/caveman-locks-icon.svg" alt="Caveman Locks" className="w-9 h-9 shrink-0" />
              <div className="flex flex-col min-w-0">
                <span
                  className="font-display font-bold text-base truncate"
                  style={{ color: "#C8860A" }}
                >
                  Caveman Locks
                </span>
                <span className="text-[10px] text-muted-foreground uppercase tracking-widest">CTE Certified Picks</span>
              </div>
            </Link>
          </SidebarHeader>

          <SidebarContent className="p-2 pt-3">
            <SidebarGroup>
              <SidebarGroupContent>
                <SidebarMenu>
                  {navigation.map((item) => {
                    const isActive = location === item.href || (item.href !== "/" && location.startsWith(item.href));
                    return (
                      <SidebarMenuItem key={item.name}>
                        <SidebarMenuButton
                          render={<Link href={item.href} />}
                          isActive={isActive}
                          className="py-5 transition-all rounded-lg flex items-center gap-3 w-full hover:bg-primary/5"
                        >
                          <item.icon className={`w-5 h-5 transition-colors ${isActive ? "text-primary" : "text-muted-foreground"}`} />
                          <span className={`font-medium text-sm ${isActive ? "text-foreground" : "text-muted-foreground"}`}>
                            {item.name}
                          </span>
                          {isActive && (
                            <div
                              className="ml-auto w-1.5 h-1.5 rounded-full"
                              style={{ background: "#C8860A" }}
                            />
                          )}
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          </SidebarContent>

          <div className="mt-auto p-4 border-t border-sidebar-border/30">
            <p className="text-[10px] text-muted-foreground/40 text-center uppercase tracking-widest">cte locks v17.0</p>
          </div>
        </Sidebar>

        {/* ── Main ── */}
        <div className="flex-1 flex flex-col relative min-w-0">
          <header className="h-14 flex items-center justify-between px-5 border-b border-border/50 bg-background/80 backdrop-blur-md sticky top-0 z-50">
            <div className="flex items-center gap-3">
              <SidebarTrigger className="text-muted-foreground hover:text-foreground transition-colors" />
              <div className="h-4 w-px bg-border hidden sm:block" />
              <h1 className="text-lg font-display font-bold tracking-wide hidden sm:block">
                {navigation.find(n => n.href === location)?.name || "CTE LOCKS"}
              </h1>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-[#C8860A]/30 bg-[#C8860A]/10">
              <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: "#C8860A" }} />
              <span className="text-xs font-bold uppercase tracking-wider" style={{ color: "#C8860A" }}>Live</span>
            </div>
          </header>

          <main
            className="flex-1 p-4 md:p-6 lg:p-8 overflow-y-auto"
            style={{ background: "radial-gradient(ellipse at top right, rgba(200,134,10,0.06) 0%, transparent 55%), radial-gradient(ellipse at bottom left, rgba(139,94,6,0.05) 0%, transparent 55%)" }}
          >
            <div className="max-w-7xl mx-auto">{children}</div>
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
