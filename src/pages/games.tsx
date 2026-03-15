import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export default function Games() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-display font-medium text-white tracking-widest uppercase">
          <span className="text-zinc-600 mr-2">/</span>
          Live Games Viewer
        </h1>
      </div>
      <div><p className="text-zinc-400">Awaiting match ingestion...</p></div>
    </div>
  );
}
