import { useState, useRef } from "react";
import { Download, X, Twitter } from "lucide-react";
import html2canvas from "html2canvas";

export interface ShareData {
  hash?: string;
  selection?: string;
  odds?: number | string;
  game_name?: string;
  value_gap?: string;
  recommended_unit?: string;
  logic_bullets?: string[];
}

export function ShareModal({ data, onClose }: { data: ShareData; onClose: () => void }) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [theme, setTheme] = useState<"dark" | "clean">("dark");

  const handleDownload = async () => {
    if (!cardRef.current) return;
    setIsExporting(true);
    await new Promise((r) => setTimeout(r, 100));
    try {
      const canvas = await html2canvas(cardRef.current, {
        scale: 3,
        backgroundColor: theme === "dark" ? "#070b0d" : "#ffffff",
        useCORS: true,
      });
      const link = document.createElement("a");
      link.href = canvas.toDataURL("image/png");
      link.download = `PICK_${data.hash || "WIN"}.png`;
      link.click();
    } finally {
      setIsExporting(false);
    }
  };

  const handleTwitter = () => {
    const text = `🔥 TODAY'S PICK: ${data.selection} @ ${data.odds}\n📊 Edge: ${data.value_gap}\n🎯 ${data.game_name}\n\n@cavemanlocks`;
    window.open(`https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}`, "_blank");
  };

  return (
    <div className="fixed inset-0 z-[100] bg-black/95 backdrop-blur-xl flex items-center justify-center p-4 overflow-y-auto">
      <div className="max-w-sm w-full flex flex-col gap-5 pt-16 pb-10">
        <div
          ref={cardRef}
          className={`relative rounded-3xl overflow-hidden border-2 shadow-2xl transition-all duration-300 ${
            theme === "dark" ? "bg-[#070b0d] border-[#3b82f6]/40" : "bg-white border-gray-200"
          }`}
        >
          {theme === "dark" ? (
            <div className="p-7">
              <div className="flex justify-between items-center mb-6">
                <div>
                  <div className="text-[9px] font-black text-[#3b82f6] uppercase tracking-[0.3em] mb-0.5">AI PICK • VERIFIED</div>
                  <div className="text-xl font-black text-white italic tracking-tighter leading-none">Caveman Locks</div>
                </div>
                <div className="text-right">
                  <div className="text-[9px] font-black text-white/30 uppercase tracking-widest">EDGE</div>
                  <div className="text-lg font-black text-[#00ffc3]">{data.value_gap}</div>
                </div>
              </div>
              <div className="bg-[#0f212e] border-l-4 border-[#3b82f6] p-5 rounded-r-xl mb-5">
                <div className="text-[9px] text-[#3b82f6] font-bold uppercase tracking-widest mb-2">TARGET ACQUIRED</div>
                <div className="text-3xl font-black text-white italic tracking-tighter leading-tight break-words">
                  {data.selection?.toUpperCase()}{data.odds !== undefined && <span className="text-[#3b82f6]"> @{data.odds}</span>}
                </div>
                <div className="text-sm text-[#b1bad3] mt-2 font-medium">{data.game_name}</div>
              </div>
              <div className="flex gap-3 mb-5">
                <div className="flex-1 bg-white/5 border border-white/10 p-3 rounded-xl text-center">
                  <div className="text-[8px] text-white/30 font-bold uppercase tracking-widest mb-0.5">UNIT SIZE</div>
                  <div className="text-sm font-black text-white">{data.recommended_unit}</div>
                </div>
                <div className="flex-1 bg-white/5 border border-white/10 p-3 rounded-xl text-center">
                  <div className="text-[8px] text-white/30 font-bold uppercase tracking-widest mb-0.5">HASH</div>
                  <div className="text-[10px] font-mono font-black text-white/60 truncate">{data.hash?.slice(0, 10)}</div>
                </div>
              </div>
              {data.logic_bullets?.slice(0, 2).map((b, i) => (
                <div key={i} className="flex gap-2 text-[10px] text-white/70 mb-2">
                  <span className="text-[#3b82f6] font-bold shrink-0">[{i + 1}]</span>
                  <span className="leading-relaxed">{b}</span>
                </div>
              ))}
              <div className="mt-5 pt-4 border-t border-white/10 flex justify-between items-center">
                <span className="text-[9px] font-black text-white/20 uppercase tracking-[0.3em]">@cavemanlocks</span>
                <span className="text-[9px] font-black text-white/20 uppercase tracking-[0.3em]">AI Sports Edge</span>
              </div>
            </div>
          ) : (
            <div className="p-7">
              <div className="flex justify-between items-center mb-5">
                <div>
                  <div className="text-[9px] font-black text-[#002f6c] uppercase tracking-[0.3em] mb-0.5">AI PICK • VERIFIED</div>
                  <div className="text-xl font-black text-[#002f6c] italic tracking-tighter">Caveman Locks</div>
                </div>
                <div className="bg-[#fbef5a] px-3 py-1 rounded-lg">
                  <div className="text-[9px] font-black text-[#002f6c] uppercase">EDGE</div>
                  <div className="text-base font-black text-[#002f6c]">{data.value_gap}</div>
                </div>
              </div>
              <div className="bg-[#002f6c] p-5 rounded-2xl mb-5">
                <div className="text-[9px] text-[#fbef5a] font-bold uppercase tracking-widest mb-1">TODAY'S PICK</div>
                <div className="text-2xl font-black text-white italic tracking-tighter break-words">
                  {data.selection?.toUpperCase()}{data.odds !== undefined && <span className="text-[#fbef5a]"> @{data.odds}</span>}
                </div>
                <div className="text-xs text-white/60 mt-2">{data.game_name}</div>
              </div>
              {data.logic_bullets?.slice(0, 2).map((b, i) => (
                <div key={i} className="flex gap-2 text-[10px] text-gray-600 mb-2">
                  <span className="text-[#002f6c] font-bold shrink-0">[{i + 1}]</span>
                  <span className="leading-relaxed">{b}</span>
                </div>
              ))}
              <div className="mt-5 pt-4 border-t border-gray-100 flex justify-between items-center">
                <span className="text-[9px] font-black text-gray-300 uppercase tracking-[0.3em]">@cavemanlocks</span>
                <span className="text-[9px] font-black text-[#002f6c] uppercase tracking-[0.3em]">{data.recommended_unit}</span>
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex bg-white/5 rounded-2xl p-1 border border-white/10">
            <button
              onClick={() => setTheme("dark")}
              className={`flex-1 py-2 text-[10px] font-black uppercase tracking-widest rounded-xl transition-all ${theme === "dark" ? "bg-[#3b82f6] text-white" : "text-white/50"}`}
            >
              Dark
            </button>
            <button
              onClick={() => setTheme("clean")}
              className={`flex-1 py-2 text-[10px] font-black uppercase tracking-widest rounded-xl transition-all ${theme === "clean" ? "bg-white text-black" : "text-white/50"}`}
            >
              Clean
            </button>
          </div>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="p-4 bg-white/5 border border-white/10 text-white rounded-2xl hover:bg-white/10 transition-all active:scale-95"
            >
              <X size={18} />
            </button>
            <button
              onClick={handleTwitter}
              className="flex-1 py-4 bg-[#1d9bf0] text-white rounded-2xl font-black text-sm tracking-widest uppercase flex items-center justify-center gap-2 hover:bg-[#1a8cd8] transition-all active:scale-95"
            >
              <Twitter size={16} strokeWidth={3} /> Post on X
            </button>
            <button
              onClick={handleDownload}
              disabled={isExporting}
              className="flex-1 py-4 bg-[#fbef5a] text-[#002f6c] rounded-2xl font-black text-sm tracking-widest uppercase flex items-center justify-center gap-2 hover:bg-yellow-300 transition-all active:scale-95 disabled:opacity-50"
            >
              <Download size={16} strokeWidth={3} /> Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
