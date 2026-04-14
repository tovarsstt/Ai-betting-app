import React, { useRef } from 'react';
import { Download } from 'lucide-react';
import html2canvas from 'html2canvas';

interface ParlayShareCardProps {
    data: {
        matchup?: string;
        suggested_side?: string;
        confidence_score?: number;
        omni_vector_generation?: any;
        rationale?: string;
        vigAdjustedEv?: string | number;
    };
    onClose: () => void;
}

export const ParlayShareCard: React.FC<ParlayShareCardProps> = ({ data, onClose }) => {
    const cardRef = useRef<HTMLDivElement>(null);

    const handleDownload = async () => {
        if (!cardRef.current) return;

        // Temporarily disable contentEditable and clear selection, otherwise html2canvas will crash
        window.getSelection()?.removeAllRanges();
        const editableElements = cardRef.current.querySelectorAll('[contenteditable]');
        editableElements.forEach(el => {
            el.setAttribute('data-temp-editable', 'true');
            el.removeAttribute('contenteditable');
        });

        try {
            const canvas = await html2canvas(cardRef.current, {
                scale: 3,
                backgroundColor: '#000000',
                useCORS: true,
                logging: false,
            });
            const image = canvas.toDataURL('image/png', 1.0);
            const link = document.createElement('a');
            link.download = `BetAI-Parlay-${Date.now()}.png`;
            link.href = image;
            link.click();
        } catch (err) {
            console.error('Failed to generate image:', err);
            alert('Export failed. Please check the console.');
        } finally {
            // Restore contentEditable
            editableElements.forEach(el => {
                el.setAttribute('contenteditable', 'true');
                el.removeAttribute('data-temp-editable');
            });
        }
    };

    if (!data.omni_vector_generation || !data.suggested_side || !data.matchup) return null;

    const edgeValue = Math.round(((data.confidence_score ?? 0.7) as number) * 100);
    const confidencePct = Math.max(70, edgeValue - 5);

    const omniVectorGenerationArray = Array.isArray(data.omni_vector_generation)
        ? data.omni_vector_generation
        : (data.omni_vector_generation ? [data.omni_vector_generation] : []);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-md p-4 animate-in fade-in duration-300">
            <div className="flex flex-col gap-6 max-w-[400px] w-full">

                {/* VISUAL CARD FOR SCREENSHOT */}
                <div
                    ref={cardRef}
                    className="w-full aspect-[4/5] bg-black relative overflow-hidden flex flex-col items-center justify-center p-8 shadow-2xl"
                >
                    {/* BACKGROUND: Gradient fallback (no local path dependency) */}
                    <div className="absolute inset-0 bg-gradient-to-br from-gray-900 via-slate-800 to-black brightness-90 contrast-110" style={{ backgroundImage: 'radial-gradient(ellipse at 20% 50%, rgba(59,130,246,0.15) 0%, transparent 60%), radial-gradient(ellipse at 80% 20%, rgba(139,92,246,0.1) 0%, transparent 50%)' }}></div>
                    <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-black/60"></div>

                    {/* Edit Hint */}
                    <div data-html2canvas-ignore="true" className="absolute top-4 left-1/2 -translate-x-1/2 z-50 bg-white/20 text-white/80 text-[10px] px-3 py-1 rounded-full backdrop-blur-sm pointer-events-none">
                        ✏️ Click text to edit before exporting
                    </div>

                    {/* SOCIAL OVERLAY BOX (TWEET STYLE) */}
                    <div className="z-10 w-full bg-white rounded-[32px] p-8 shadow-[0_20px_50px_rgba(0,0,0,0.5)] flex flex-col gap-6">
                        {/* Profile Header */}
                        <div className="flex items-center gap-4">
                            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-yellow-400 to-orange-500 flex items-center justify-center border-4 border-white shadow-md overflow-hidden">
                                <span className="text-2xl font-black text-white">DG</span>
                            </div>
                            <div className="flex flex-col">
                                <div className="flex items-center gap-1.5">
                                    <span className="font-extrabold text-black text-xl tracking-tight">DanGamble.AI</span>
                                    <svg viewBox="0 0 24 24" className="w-6 h-6 text-[#1D9BF0] fill-current" aria-hidden="true">
                                        <path d="M22.25 12c0-1.43-.88-2.67-2.19-3.34.46-1.39.2-2.97-.81-3.99s-2.6-1.27-3.99-.81c-.67-1.31-1.91-2.19-3.34-2.19s-2.67.88-3.33 2.19c-1.4-.46-2.98-.2-4 .81s-1.27 2.6-.81 3.99c-1.31.67-2.19 1.91-2.19 3.34s.88 2.67 2.19 3.34c-.46 1.39-.2 2.97.81 3.99s2.6 1.27 3.99.81c.67 1.31 1.91 2.19 3.34 2.19s2.67-.88 3.33-2.19c1.4.46 2.98.2 4-.81s1.27-2.6.81-3.99c1.31-.67 2.19-1.91 2.19-3.34zm-11.71 4.2L6.8 12.46l1.41-1.42 2.26 2.26 4.8-5.23 1.47 1.36-6.2 6.77z"></path>
                                    </svg>
                                </div>
                                <span className="text-gray-500 font-medium text-base">@DanGambleAI · Now</span>
                            </div>
                        </div>

                        {/* Tweet Text Content */}
                        <div className="text-gray-900 text-2xl font-black leading-tight tracking-tight outline-none hover:bg-gray-100 transition-colors px-2 py-1 -mx-2 rounded" contentEditable suppressContentEditableWarning>
                            {data.matchup.includes('VS') ? `Locking in today's elite slate. The data is screaming on these edges. 🧠🔥` : `Mandatory generation active. The God-Engine is seeing absolute value here. 💹`}
                        </div>

                        {/* Parlay Picks List */}
                        <div className="flex flex-col gap-4 py-2">
                            {omniVectorGenerationArray.length > 0 ? (
                                omniVectorGenerationArray.map((pick: any, idx: number) => (
                                    <div key={idx} className="flex items-start gap-4">
                                        <span className="text-2xl pt-1">✅</span>
                                        <div className="flex flex-col">
                                            <span className="font-black text-black text-2xl tracking-tighter uppercase leading-tight outline-none hover:bg-gray-100 transition-colors px-2 rounded -ml-2" contentEditable suppressContentEditableWarning>
                                                {pick.display_label || (pick.lock_text.includes(']') ? pick.lock_text.split(']')[1].trim() : pick.lock_text)}
                                            </span>
                                            <span className="text-[#1D9BF0] font-black text-xs uppercase tracking-[0.2em] mt-0.5">
                                                {pick.lock_type} · {pick.tier}
                                            </span>
                                        </div>
                                    </div>
                                ))
                            ) : (
                                <div className="text-gray-400 italic">No picks detected in current payload.</div>
                            )}
                        </div>

                        {/* Footer Interaction Bar */}
                        <div className="mt-2 pt-6 border-t border-gray-100 flex justify-between items-center">
                            <div className="flex gap-8 text-gray-500">
                                <div className="flex items-center gap-2">
                                    <span className="font-black text-black">C: {confidencePct}%</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="font-black text-black">EV: {data.vigAdjustedEv || '+8.2%'}</span>
                                </div>
                            </div>
                            <div className="px-5 py-2 rounded-full bg-black text-white font-black text-sm uppercase tracking-widest">
                                TAIL THE GOAT 🐐
                            </div>
                        </div>
                    </div>
                </div>

                {/* INFLUENCER SCRIPT BOX - UI ONLY, NOT IN IMAGE */}
                <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-sm font-mono text-gray-300">
                    <div className="text-xs text-yellow-500 mb-2 font-bold tracking-widest uppercase border-b border-gray-800 pb-2">Omni Vector Generation (Copy to Clipboard)</div>
                    {omniVectorGenerationArray.length > 0 ? omniVectorGenerationArray.map((pick: any, idx: number) => (
                        <div key={idx} className="mb-2">
                            <span className="text-white font-bold">{pick.lock_type} ({pick.tier}):</span> {pick.lock_text} - <span className="text-gray-400 text-xs">{pick.lock_data}</span>
                        </div>
                    )) : null}
                </div>

                {/* ACTIONS */}
                <div className="flex gap-3">
                    <button
                        onClick={onClose}
                        className="flex-[1] py-4 bg-gray-900 hover:bg-gray-800 text-white rounded-xl font-bold tracking-widest uppercase transition-colors"
                    >
                        Close
                    </button>
                    <button
                        onClick={handleDownload}
                        className="flex-[2] py-4 bg-purple-600 hover:bg-purple-500 text-white rounded-xl font-black tracking-widest uppercase flex items-center justify-center gap-2 transition-all shadow-[0_0_20px_rgba(168,85,247,0.4)]"
                    >
                        <Download size={20} />
                        Export Parlay
                    </button>
                </div>
            </div>
        </div>
    );
};
