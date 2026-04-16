import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppLayout } from "./components/layout";
import Dashboard from "./pages/dashboard";
import Predictions from "./pages/predictions";
import SharpMoney from "./pages/sharp-money";
import Matchups from "./pages/matchups";
import Teams from "./pages/teams";
import Players from "./pages/players";
import Games from "./pages/games";
import History from "./pages/history";
import NotFound from "./pages/not-found";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 1000 * 60 * 5 } }
});

function Router() {
  return (
    <AppLayout>
      <Switch>
        <Route path="/" component={Dashboard} />
        <Route path="/predictions" component={Predictions} />
        <Route path="/sharp" component={SharpMoney} />
        <Route path="/matchups" component={Matchups} />
        <Route path="/teams" component={Teams} />
        <Route path="/players" component={Players} />
        <Route path="/games" component={Games} />
        <Route path="/history" component={History} />
        <Route component={NotFound} />
      </Switch>
    </AppLayout>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
