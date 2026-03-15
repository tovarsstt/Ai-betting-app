import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

export default function NotFound() {
  return (
    <div className="flex h-[80vh] w-full items-center justify-center">
      <Card className="w-full max-w-md backdrop-blur-md bg-background/50 border-white/10 shadow-[0_0_15px_rgba(255,255,255,0.05)] text-center">
        <CardHeader>
          <CardTitle className="text-4xl text-white font-display uppercase tracking-widest">
            404
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-zinc-400">Page not found in the matrix.</p>
        </CardContent>
      </Card>
    </div>
  );
}
