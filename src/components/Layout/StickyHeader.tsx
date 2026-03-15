import React, { useEffect, useState } from 'react';
import { quotaService } from '../../services/QuotaService';
import { bankrollService } from '../../services/BankrollService';
import { twMerge } from 'tailwind-merge';

export const StickyHeader: React.FC = () => {
    const [budget, setBudget] = useState(0);
    const [bankroll, setBankroll] = useState(0);
    const [burned, setBurned] = useState(0);

    useEffect(() => {
        // Initialize defaults if needed
        quotaService.initializeBudget(300);

        // Initial fetch
        const fetchData = async () => {
            try {
                const quota = await quotaService.getStatus();
                setBudget(quota.totalBudget);
                setBurned(quota.totalBurned);
                const br = await bankrollService.getBankroll();
                setBankroll(br);
            } catch (err) {
                console.error("Failed to fetch header data", err);
            }
        };

        fetchData();

        // Poll for updates (simple reactivity mechanism)
        const interval = setInterval(fetchData, 2000);
        return () => clearInterval(interval);
    }, []);

    const remaining = budget - burned;

    return (
        <header className="fixed top-0 left-0 right-0 h-12 bg-black/95 backdrop-blur-md border-b border-yellow-900/40 shadow-[0_4px_30px_rgba(0,0,0,0.8)] text-white flex justify-between items-center px-6 z-50 font-mono text-xs select-none">
            <div className="flex items-center gap-6">
                <div className="flex items-center gap-2">
                    <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-yellow-500"></span>
                    </span>
                    <span className="font-black text-gray-400 tracking-[0.2em] text-[10px]">ORACLE_AUDIT_2026</span>
                </div>
                <div className="flex items-center gap-2 px-3 py-1 bg-yellow-950/20 border border-yellow-900/30 rounded-md shadow-inner">
                    <span className="text-gray-500 tracking-wider text-[10px]">BANKROLL:</span>
                    <span className="text-yellow-400 font-black drop-shadow-[0_0_8px_rgba(250,204,21,0.5)]">
                        ${bankroll.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                </div>
            </div>

            <div className="flex items-center gap-6">
                <div className="flex flex-col items-end leading-none">
                    <span className="text-[10px] text-gray-500 tracking-widest">SESSION_COST</span>
                    <span className="text-yellow-600 font-black drop-shadow-[0_0_5px_rgba(202,138,4,0.3)]">${burned.toFixed(4)}</span>
                </div>
                <div className={twMerge("flex flex-col items-end leading-none", remaining < 50 ? "text-yellow-500 animate-[pulse_0.5s_infinite]" : "text-yellow-200")}>
                    <span className="text-[10px] text-gray-500 tracking-widest">RESERVE_COMPUTE</span>
                    <span className="font-black drop-shadow-[0_0_8px_rgba(250,204,21,0.5)]">${remaining.toFixed(4)}</span>
                </div>
            </div>
        </header>
    );
};
