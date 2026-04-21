import type { ReactNode } from "react";
import { Link, useLocation } from "wouter";
import { SidebarProvider, Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent, SidebarMenu, SidebarMenuItem, SidebarMenuButton, SidebarTrigger, SidebarHeader } from "@/components/ui/sidebar";
import { Activity, Crosshair, Swords, Trophy, Zap } from "lucide-react";

const navigation = [
  { name: "Dashboard",   href: "/",            icon: Activity  },
  { name: "Picks",       href: "/predictions",  icon: Zap       },
  { name: "Sharp Money", href: "/sharp",        icon: Crosshair },
  { name: "Matchups",    href: "/matchups",     icon: Swords    },
  { name: "History",     href: "/history",      icon: Trophy    },
];

export function AppLayout({ children }: { children: ReactNode }) {
  const [location] = useLocation();

  return (
    <SidebarProvider style={{ "--sidebar-width": "15rem" } as React.CSSProperties}>
      <div className="flex min-h-screen w-full bg-background dark text-foreground">

        {/* ── Sidebar ── */}
        <Sidebar className="border-r border-sidebar-border bg-sidebar">
          <SidebarHeader className="p-5 border-b border-sidebar-border/50">
            <div className="flex items-center gap-3">
              <div
                className="w-9 h-9 rounded-xl flex items-center justify-center shadow-lg shrink-0"
                style={{ background: "linear-gradient(135deg, #7c3aed 0%, #2563eb 100%)" }}
              >
                <span className="text-white font-black text-base select-none">W</span>
              </div>
              <div className="flex flex-col min-w-0">
                <span
                  className="font-display font-bold text-base truncate"
                  style={{ background: "linear-gradient(90deg,#a78bfa,#60a5fa)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}
                >
                  WinWithTovy
                </span>
                <span className="text-[10px] text-muted-foreground uppercase tracking-widest">AI Sports Edge</span>
              </div>
            </div>
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
                              style={{ background: "linear-gradient(135deg,#7c3aed,#2563eb)" }}
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
            <p className="text-[10px] text-muted-foreground/40 text-center uppercase tracking-widest">@winwithtovy</p>
          </div>
        </Sidebar>

        {/* ── Main ── */}
        <div className="flex-1 flex flex-col relative min-w-0">
          <header className="h-14 flex items-center justify-between px-5 border-b border-border/50 bg-background/80 backdrop-blur-md sticky top-0 z-50">
            <div className="flex items-center gap-3">
              <SidebarTrigger className="text-muted-foreground hover:text-foreground transition-colors" />
              <div className="h-4 w-px bg-border hidden sm:block" />
              <h1 className="text-lg font-display font-bold tracking-wide hidden sm:block">
                {navigation.find((n) => n.href === location)?.name ?? "Dashboard"}
              </h1>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-primary/20 bg-primary/10">
              <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
              <span className="text-xs font-bold text-primary uppercase tracking-wider">Live</span>
            </div>
          </header>

          <main
            className="flex-1 p-6 lg:p-8 overflow-y-auto"
            style={{ background: "radial-gradient(ellipse at top right, rgba(124,58,237,0.07) 0%, transparent 55%), radial-gradient(ellipse at bottom left, rgba(37,99,235,0.05) 0%, transparent 55%)" }}
          >
            <div className="max-w-7xl mx-auto space-y-6">{children}</div>
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
