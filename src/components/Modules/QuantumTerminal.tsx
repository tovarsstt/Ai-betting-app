import React, { useState, useRef, useEffect } from 'react';
import { Terminal, Cpu, Zap, ChevronRight, Loader2 } from 'lucide-react';

interface QuantumToolResult {
  tool: string;
  output: string;
  success: boolean;
  timestamp: string;
}

interface QuantumSession {
  goal: string;
  logs: QuantumToolResult[];
  final_verdict: string;
  hash: string;
}

export const QuantumTerminal: React.FC = () => {
    const [goal, setGoal] = useState("");
    const [missionData, setMissionData] = useState<QuantumSession | null>(null);
    const [isEngaged, setIsEngaged] = useState(false);
    const logContainerRef = useRef<HTMLDivElement>(null);

    const engageQuantumMission = async () => {
        if (!goal) return;
        setIsEngaged(true);
        setMissionData(null);
        try {
            const res = await fetch('/api/quantum-mission', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ goal })
            });
            const data = await res.json();
            setMissionData(data);
        } catch (err) {
            console.error("Quantum Error:", err);
        } finally {
            setIsEngaged(false);
        }
    };

    useEffect(() => {
        if (logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
    }, [missionData]);

    return (
        <div className="w-full h-full bg-[#0A0D14] border border-purple-500/20 rounded-2xl overflow-hidden flex flex-col font-mono shadow-[0_0_50px_rgba(168,85,247,0.1)] transition-all duration-500 hover:border-purple-500/40">
            {/* Header / Sigma Status */}
            <div className="bg-gradient-to-r from-purple-900/40 to-blue-900/20 p-4 border-b border-purple-500/20 flex items-center justify-between backdrop-blur-md">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center border border-purple-500/40 animate-pulse">
                        <Cpu size={16} className="text-purple-400" />
                    </div>
                    <div>
                        <h2 className="text-[11px] font-black text-white tracking-[0.2em] uppercase">Quantum Coordination Layer</h2>
                        <div className="flex items-center gap-2 mt-0.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping"></span>
                            <span className="text-[8px] text-emerald-400 font-bold uppercase tracking-widest">Σ_CORE_ACTIVE :: CLAUDE_CODE_SKILLS</span>
                        </div>
                    </div>
                </div>
                <div className="text-[10px] text-purple-400/60 font-black">
                    V16.0_STABLE
                </div>
            </div>

            {/* Terminal Viewport */}
            <div className="flex-1 p-6 overflow-hidden flex flex-col gap-6">
                
                {/* Input Matrix */}
                <div className="relative group">
                    <div className="absolute -inset-1 bg-gradient-to-r from-purple-600 to-blue-600 rounded-xl blur opacity-10 group-hover:opacity-20 transition duration-1000"></div>
                    <div className="relative bg-black/60 border border-white/5 rounded-xl p-4 flex items-center gap-4 transition-all hover:bg-black/80">
                        <ChevronRight size={20} className="text-purple-500" />
                        <input 
                            value={goal}
                            onChange={(e) => setGoal(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && engageQuantumMission()}
                            placeholder="INITIALIZE QUANTUM MISSION (e.g. Scan logs for betting edges)"
                            className="bg-transparent border-none outline-none text-white text-xs w-full placeholder:text-gray-700 tracking-wide font-medium"
                            disabled={isEngaged}
                        />
                        <button 
                            onClick={engageQuantumMission}
                            disabled={isEngaged || !goal}
                            className={`px-4 py-2 rounded-lg font-black text-[10px] tracking-widest uppercase transition-all ${
                                isEngaged ? 'bg-gray-800 text-gray-500' : 'bg-purple-600 hover:bg-purple-500 text-white shadow-[0_0_20px_rgba(168,85,247,0.4)]'
                            }`}
                        >
                            {isEngaged ? (
                                <Loader2 size={12} className="animate-spin" />
                            ) : (
                                "Engage"
                            )}
                        </button>
                    </div>
                </div>

                {/* Execution Stream */}
                <div 
                    ref={logContainerRef}
                    className="flex-1 bg-black/40 border border-white/5 rounded-xl p-4 font-mono text-[10px] space-y-4 overflow-y-auto scrollbar-hide"
                >
                    {!missionData && !isEngaged && (
                        <div className="h-full flex flex-col items-center justify-center opacity-30 text-gray-500 gap-2">
                             <Terminal size={40} strokeWidth={1} />
                             <span className="tracking-[0.3em] uppercase">Awaiting Quantum Scripting...</span>
                        </div>
                    )}

                    {isEngaged && (
                        <div className="flex items-center gap-3 text-purple-400 animate-pulse font-bold tracking-widest uppercase italic">
                            <Loader2 size={12} className="animate-spin" />
                            Coordinating Savant Agents...
                        </div>
                    )}

                    {missionData?.logs.map((log, i) => (
                        <div key={i} className="animate-in slide-in-from-left-4 duration-500">
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-blue-500 font-bold">[{new Date(log.timestamp).toLocaleTimeString()}]</span>
                                <span className={`px-1.5 py-0.5 rounded text-[8px] font-black uppercase tracking-widest ${
                                    log.success ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'
                                }`}>
                                    {log.tool}
                                </span>
                            </div>
                            <pre className="text-gray-400 pl-4 border-l border-white/5 py-1 max-w-full overflow-hidden whitespace-pre-wrap leading-relaxed">
                                {log.output}
                            </pre>
                        </div>
                    ))}
                </div>

                {/* Mission Summary / Audit Receipt */}
                {missionData && (
                    <div className="bg-purple-500/5 border border-purple-500/20 p-5 rounded-xl animate-in fade-in slide-in-from-bottom-4 duration-700">
                        <div className="flex justify-between items-start mb-3">
                            <div className="flex items-center gap-2">
                                <Zap size={14} className="text-yellow-400" />
                                <span className="text-[10px] font-black text-white uppercase tracking-widest">Post-Mission Audit</span>
                            </div>
                            <span className="font-mono text-[9px] text-purple-400/60 uppercase">{missionData.hash}</span>
                        </div>
                        <p className="text-xs text-purple-200 leading-relaxed font-bold italic">
                            "{missionData.final_verdict}"
                        </p>
                    </div>
                )}
            </div>
            
            {/* Footer Matrix */}
            <div className="bg-black/80 px-6 py-2 border-t border-purple-500/10 flex justify-between items-center opacity-60">
                <div className="flex gap-4">
                    <div className="flex items-center gap-1.5">
                        <span className="w-1 h-1 rounded-full bg-blue-500"></span>
                        <span className="text-[7px] text-gray-500 uppercase font-black tracking-widest">BASH_ENABLED</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <span className="w-1 h-1 rounded-full bg-purple-500"></span>
                        <span className="text-[7px] text-gray-500 uppercase font-black tracking-widest">CLAUDE_CODE_V1</span>
                    </div>
                </div>
                <span className="text-[7px] text-gray-700 font-mono tracking-tighter">COORDINATION_ENGINE // STAKED_LIQUIDITY</span>
            </div>
        </div>
    );
};
