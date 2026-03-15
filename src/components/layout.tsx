import { ReactNode } from "react";
import { Link, useLocation } from "wouter";
import { SidebarProvider, Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarMenu, SidebarMenuItem, SidebarMenuButton, SidebarTrigger, SidebarHeader } from "@/components/ui/sidebar";
import { Activity, BarChart2, Crosshair, Swords, Users, Shield, Zap } from "lucide-react";

const navigation = [
  { name: "Dashboard",   href: "/",           icon: Activity  },
  { name: "Predictions", href: "/predictions", icon: Zap       },
  { name: "Sharp Money", href: "/sharp",       icon: Crosshair },
  { name: "Matchups",    href: "/matchups",    icon: Swords    },
  { name: "Teams",       href: "/teams",       icon: Shield    },
  { name: "Players",     href: "/players",     icon: Users     },
  { name: "Games",       href: "/games",       icon: BarChart2 },
];

export function AppLayout({ children }: { children: ReactNode }) {
  const [location] = useLocation();

  return (
    <SidebarProvider style={{ "--sidebar-width": "16rem" } as React.CSSProperties}>
      <div className="flex min-h-screen w-full bg-background dark text-foreground">
        <Sidebar className="border-r border-sidebar-border bg-sidebar relative overflow-hidden">
          <div className="bg-carbon-overlay" />
          <SidebarHeader className="p-6 relative z-10 border-b border-sidebar-border/50">
            <div className="flex items-center gap-3">
              <img src={`${import.meta.env.BASE_URL}images/v12-logo.png`} alt="V12" className="w-8 h-8 rounded-md shadow-[0_0_15px_rgba(0,255,255,0.5)]" />
              <div className="flex flex-col">
                <span className="font-display font-bold text-lg tracking-wider text-primary">V12 GOD-ENGINE</span>
                <span className="text-[10px] text-muted-foreground uppercase tracking-widest">Intelligence v5.0</span>
              </div>
            </div>
          </SidebarHeader>
          <SidebarContent className="relative z-10 p-2">
            <SidebarGroup>
              <SidebarGroupLabel className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Core Modules</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {navigation.map((item) => {
                    const isActive = location === item.href || (item.href !== "/" && location.startsWith(item.href));
                    return (
                      <SidebarMenuItem key={item.name}>
                        <SidebarMenuButton asChild isActive={isActive} className="hover-elevate active-elevate-2 py-5 transition-all">
                          <Link href={item.href} className="flex items-center gap-3 w-full">
                            <item.icon className={`w-5 h-5 ${isActive ? 'text-primary drop-shadow-[0_0_8px_rgba(0,255,255,0.5)]' : 'text-muted-foreground'}`} />
                            <span className={`font-medium ${isActive ? 'text-foreground' : 'text-muted-foreground'}`}>{item.name}</span>
                          </Link>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          </SidebarContent>
        </Sidebar>
        <div className="flex-1 flex flex-col relative min-w-0">
          <header className="h-16 flex items-center justify-between px-6 border-b border-border bg-background/80 backdrop-blur-md sticky top-0 z-50">
            <div className="flex items-center gap-4">
              <SidebarTrigger className="text-muted-foreground hover:text-foreground transition-colors" />
              <div className="h-4 w-px bg-border hidden sm:block" />
              <h1 className="text-xl font-display font-bold tracking-wide hidden sm:block">
                {navigation.find(n => n.href === location)?.name || "V12 Engine"}
              </h1>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-success/10 rounded-full border border-success/20 shadow-[0_0_10px_rgba(0,255,0,0.1)]">
              <div className="w-2 h-2 rounded-full bg-success animate-pulse" />
              <span className="text-xs font-bold text-success uppercase tracking-wider">System Online</span>
            </div>
          </header>
          <main className="flex-1 p-6 lg:p-8 overflow-y-auto bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-primary/5 via-background to-background">
            <div className="max-w-7xl mx-auto space-y-6">{children}</div>
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
