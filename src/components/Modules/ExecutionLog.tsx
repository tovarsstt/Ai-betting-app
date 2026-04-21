import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const PHASE_MESSAGES: Record<number, string[]> = {
  0: [
    ">> INITIALIZING QUANT ASSASSIN...",
    ">> CALCULATING ODDS DISCREPANCIES...",
    ">> MAPPING STAKE.COM LIQUIDITY...",
    ">> ALPHA VARIANCE σ=2.4 DETECTED."
  ],
  1: [
    ">> DEPLOYING MIROFISH SIMULATION...",
    ">> RUNNING SOCIAL AGENT DEBATE (n=10)...",
    ">> EXTRACTING NARRATIVE CONFLUENCE...",
    ">> NARRATIVE ALPHA_LOCKED."
  ],
  2: [
    ">> OMQX CONVERGENCE PROTOCOL ACTIVE...",
    ">> DETECTING VARIANCE DELTA...",
    ">> INSTITUTIONAL GROUND TRUTH CHECK...",
    ">> RECONCILER_STATUS: READY."
  ],
  3: [
    ">> FINAL AUDIT IN PROGRESS...",
    ">> SYNTHESIZING SWARM CONSENSUS...",
    ">> GENERATING BAANGGG_PLAYLOAD...",
    ">> READY FOR EXECUTION."
  ]
};

export const ExecutionLog = ({ phase }: { phase: number }) => {
  const [logs, setLogs] = useState<string[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const messages = PHASE_MESSAGES[phase] || [];
    let index = 0;
    
    // Reset logs when phase changes to show new agent activity
    setLogs([]);

    const interval = setInterval(() => {
      if (index < messages.length) {
        setLogs(prev => [...prev.slice(-3), messages[index]]);
        index++;
      } else {
        clearInterval(interval);
      }
    }, 600);

    return () => clearInterval(interval);
  }, [phase]);

  return (
    <div 
      ref={containerRef}
      className="bg-black/95 border border-white/10 rounded-2xl p-6 font-mono text-[10px] text-gray-400 h-32 overflow-hidden shadow-2xl relative"
    >
      <div className="absolute top-2 right-4 text-[8px] font-black text-white/20 uppercase tracking-widest">
        Agent_Stream_v4.2
      </div>
      <AnimatePresence mode="popLayout">
        {logs.map((log, i) => (
          <motion.div
            key={log + i}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            className="mb-2 flex items-center gap-3"
          >
            <span className="text-blue-500 font-bold">»</span>
            <span className="font-bold tracking-tight text-white/80">{log}</span>
          </motion.div>
        ))}
      </AnimatePresence>
      <div className="w-1.5 h-3 bg-blue-500 animate-pulse inline-block ml-1 mt-1" />
    </div>
  );
};
