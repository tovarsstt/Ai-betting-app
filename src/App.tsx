import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppLayout } from "./components/layout";
import GameBreakdown from "./pages/game-breakdown";
import ParlaysPage from "./pages/parlays";
import AlphaSheetsPage from "./pages/alpha-sheets";
import SharpScannerPage from "./pages/sharp-scanner";
import ArbitragePage from "./pages/arbitrage";
import TrackRecordPage from "./pages/track-record";
import UpsetRadarPage from "./pages/upset-radar";
import NotFound from "./pages/not-found";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 1000 * 60 * 5 } }
});

function Router() {
  return (
    <AppLayout>
      <Switch>
        <Route path="/" component={GameBreakdown} />
        <Route path="/parlays" component={ParlaysPage} />
        <Route path="/alpha-sheets" component={AlphaSheetsPage} />
        <Route path="/sharp-scanner" component={SharpScannerPage} />
        <Route path="/arbitrage" component={ArbitragePage} />
        <Route path="/track-record" component={TrackRecordPage} />
        <Route path="/upset-radar" component={UpsetRadarPage} />
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
