import React, { useRef, useState, useEffect } from 'react';
import { Download, Sliders, Type, Maximize, Palette, Settings } from 'lucide-react';
import html2canvas from 'html2canvas';

// Quick static map for NBA teams to their ESPN abbreviatons for dynamic logos
const TEAM_MAP: Record<string, string> = {
    'lakers': 'lal', 'clippers': 'lac', 'warriors': 'gsw', 'suns': 'phx', 'kings': 'sac',
    'mavericks': 'dal', 'rockets': 'hou', 'grizzlies': 'mem', 'pelicans': 'nop', 'spurs': 'sas',
    'nuggets': 'den', 'timberwolves': 'min', 'thunder': 'okc', 'trail blazers': 'por', 'blazers': 'por', 'jazz': 'uta',
    'celtics': 'bos', 'nets': 'bkn', 'knicks': 'nyk', '76ers': 'phi', 'sixers': 'phi', 'raptors': 'tor',
    'bulls': 'chi', 'cavaliers': 'cle', 'cavs': 'cle', 'pistons': 'det', 'pacers': 'ind', 'bucks': 'mil',
    'hawks': 'atl', 'hornets': 'cha', 'heat': 'mia', 'magic': 'orl', 'wizards': 'wsh'
};

const getDynamicImage = (text: string) => {
    const lower = text.toLowerCase();
    let rawUrl = null;

    for (const [key, abbr] of Object.entries(TEAM_MAP)) {
        if (lower.includes(key)) {
            rawUrl = `https://a.espncdn.com/i/teamlogos/nba/500/${abbr}.png`;
            break;
        }
    }

    // Fallback if it looks like a player prop or unknown
    if (!rawUrl && (lower.includes('over') || lower.includes('under') || lower.includes('points') || lower.includes('rebounds') || lower.includes('assists'))) {
        rawUrl = 'https://a.espncdn.com/combiner/i?img=/i/headshots/nba/players/full/1966.png'; // LeBron face placeholder for player props
    }

    // Proxy the image to avoid html2canvas Tainting / CORS issues
    if (rawUrl) {
        return `http://localhost:3001/api/proxy-image?url=${encodeURIComponent(rawUrl)}`;
    }
    return null;
};

interface SocialShareCardProps {
    data: {
        matchup?: string;
        suggested_side?: string;
        confidence_score?: number;
        omni_vector_generation?: Array<{
            lock_type: string;
            tier: string;
            lock_text: string;
            lock_data: string;
            headshot_url?: string;
        }>;
        rationale?: string;
        vigAdjustedEv?: string | number;
    };
    specificPick?: {
        lock_type: string;
        tier: string;
        lock_text: string;
        lock_data: string;
        headshot_url?: string;
    };
    theme?: 'antigravity' | 'minimal' | 'default';
    onClose: () => void;
}

export const SocialShareCard: React.FC<SocialShareCardProps> = ({ data, specificPick, theme = 'antigravity', onClose }) => {
    const cardRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const displayPick = specificPick || (Array.isArray(data.omni_vector_generation) ? data.omni_vector_generation[0] : null);

    // Core Data States
    const [dynamicImgUrl, setDynamicImgUrl] = useState<string | null>(null);

    // Customization States for Total Freedom
    const [textSizeMultiplier, setTextSizeMultiplier] = useState(1);
    const [paddingMultiplier, setPaddingMultiplier] = useState(1);
    const [logoScale, setLogoScale] = useState(1);
    const [accentColor, setAccentColor] = useState('#3B82F6'); // Default Blue
    const [showControls, setShowControls] = useState(false);

    // Derived styles based on modifiers
    const pdScale = `${paddingMultiplier * 2}rem`; // Native base is usually p-8 (2rem)
    const imgTransform = `scale(${logoScale})`;


    useEffect(() => {
        if (displayPick) {
            // Priority 1: Direct ESPN headshot mapped from Python
            if (displayPick.headshot_url) {
                const proxyUrl = `http://localhost:3001/api/proxy-image?url=${encodeURIComponent(displayPick.headshot_url)}`;
                setDynamicImgUrl(proxyUrl);
            } else {
                // Priority 2: Fuzzy match from text
                const initialImg = getDynamicImage(displayPick.lock_text) || getDynamicImage(data.matchup || "");
                setDynamicImgUrl(initialImg);
            }
        }
    }, [displayPick, data.matchup]);

    const handleTextBlur = (e: React.FocusEvent<HTMLElement>) => {
        const text = e.currentTarget.innerText;
        if (!dynamicImgUrl?.startsWith('data:image')) {
            const newImg = getDynamicImage(text);
            if (newImg) setDynamicImgUrl(newImg);
        }
    };

    const handleImageClick = () => fileInputRef.current?.click();

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            const reader = new FileReader();
            reader.onloadend = () => {
                setDynamicImgUrl(reader.result as string);
            };
            reader.readAsDataURL(file);
        }
    };

    const handleDownload = async () => {
        if (!cardRef.current) return;

        // Hide controls temporarily for pristine screenshot
        setShowControls(false);

        // Yield render pipeline to React before heavy canvas blocking
        await new Promise(r => setTimeout(r, 50));

        window.getSelection()?.removeAllRanges();
        const editableElements = cardRef.current.querySelectorAll('[contenteditable]');
        editableElements.forEach(el => {
            el.setAttribute('data-temp-editable', 'true');
            el.removeAttribute('contenteditable');
        });

        try {
            const canvas = await html2canvas(cardRef.current, {
                scale: 3,
                backgroundColor: theme === 'minimal' ? '#ffffff' : '#000000',
                useCORS: true,
                allowTaint: true,
                logging: false,
            });
            const image = canvas.toDataURL('image/png', 1.0);
            const link = document.createElement('a');
            link.download = `BetAI-${theme}-${Date.now()}.png`;
            link.href = image;
            link.click();
        } catch (err) {
            console.error('Failed to generate image:', err);
            alert('Export failed due to cross-origin constraints. Try again without the image.');
        } finally {
            editableElements.forEach(el => {
                el.setAttribute('contenteditable', 'true');
                el.removeAttribute('data-temp-editable');
            });
        }
    };

    if (!displayPick) return null;
    const confidencePct = Math.max(70, Math.round((data.confidence_score || 0.7) * 100));

    // --- ANTIGRAVITY (SOCIAL) THEME --- //
    const renderAntigravityTheme = () => (
        <div ref={cardRef} className="w-full aspect-[4/5] bg-[#0A0D14] relative flex flex-col overflow-hidden font-sans border border-blue-900/30">
            <div className="absolute inset-0 opacity-[0.15]" style={{ backgroundImage: `radial-gradient(${accentColor} 1px, transparent 1px)`, backgroundSize: '24px 24px' }}></div>
            <div className="absolute inset-0 bg-gradient-to-t from-black via-[#0A0D14]/80 to-transparent"></div>

            <div className="flex-1 flex flex-col items-center justify-center relative z-10 text-center mt-4 transition-all" style={{ padding: pdScale }}>

                <input type="file" accept="image/*" className="hidden" ref={fileInputRef} onChange={handleFileChange} />

                <div
                    onClick={handleImageClick}
                    className="cursor-pointer group relative h-40 mb-6 flex items-center justify-center w-full transition-transform"
                    title="Click to upload custom image"
                >
                    <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity z-20 rounded-full flex items-center justify-center text-white text-xs font-bold border-2 border-dashed border-white/50">
                        CHANGE MEDIA
                    </div>
                    {dynamicImgUrl ? (
                        <>
                            <div className="absolute inset-x-10 bottom-0 top-10 blur-3xl rounded-full opacity-30" style={{ backgroundColor: accentColor }}></div>
                            <img
                                src={dynamicImgUrl}
                                alt="Dynamic Logo"
                                crossOrigin="anonymous"
                                className="h-full object-contain filter relative z-10 transition-transform"
                                style={{ transform: imgTransform, filter: `drop-shadow(0 0 25px ${accentColor}80)` }}
                            />
                        </>
                    ) : (
                        <div className="w-24 h-24 rounded-full flex items-center justify-center shadow-[0_0_40px_rgba(59,130,246,0.5)]" style={{ background: `linear-gradient(to bottom right, ${accentColor}, #000)` }}>
                            <span className="text-white text-3xl font-black">AI</span>
                        </div>
                    )}
                </div>

                <div
                    className="font-mono tracking-[0.4em] uppercase mb-4 py-1.5 px-4 border rounded-full outline-none backdrop-blur-md transition-all"
                    contentEditable suppressContentEditableWarning onBlur={handleTextBlur}
                    style={{ fontSize: `calc(10px * ${textSizeMultiplier})`, borderColor: `${accentColor}40`, backgroundColor: `${accentColor}20`, color: accentColor }}
                >
                    {data.matchup}
                </div>

                <h1
                    className="font-black text-white uppercase leading-[0.95] tracking-tighter drop-shadow-xl outline-none w-full px-2 transition-all"
                    contentEditable suppressContentEditableWarning onBlur={handleTextBlur}
                    style={{ fontSize: `calc(2.75rem * ${textSizeMultiplier})` }}
                >
                    {displayPick.lock_text}
                </h1>

                <div
                    className="mt-6 px-8 py-3 text-white font-black tracking-tight rounded-xl outline-none border border-white/10 transition-all"
                    contentEditable suppressContentEditableWarning
                    style={{ fontSize: `calc(1.875rem * ${textSizeMultiplier})`, background: `linear-gradient(to right, ${accentColor}, #000)`, boxShadow: `0 0 30px ${accentColor}60` }}
                >
                    {displayPick.lock_data}
                </div>
            </div>

            {/* Discord CTA Footer */}
            <div className="h-20 w-full relative z-10 flex items-center justify-between px-8" style={{ backgroundColor: '#5865F2', boxShadow: `0 -10px 30px rgba(88,101,242,0.3)` }}>
                <div className="flex items-center gap-4">
                    <svg className="w-8 h-8 text-white flex-shrink-0" viewBox="0 0 127.14 96.36" fill="currentColor"><path d="M107.7 8.07A105.15 105.15 0 0081.47 0a72.06 72.06 0 00-3.36 6.83 97.68 97.68 0 00-29.08 0 72.37 72.37 0 00-3.36-6.83 105.15 105.15 0 00-26.23 8.07C2.6 32.26-3.12 55.8 1.6 79.1a105.73 105.73 0 0032.2 16.27 77.7 77.7 0 006.89-11.3 68.42 68.42 0 01-10.85-5.18c.91-.66 1.8-1.34 2.66-2a75.57 75.57 0 0064.32 0c.87.71 1.76 1.39 2.66 2a68.68 68.68 0 01-10.87 5.19 77 77 0 006.89 11.29 105.73 105.73 0 0032.2-16.27c5.21-26.68-.64-50.62-17.6-71.03zm-64.84 57.7c-6.19 0-11.28-5.69-11.28-12.72 0-7 4.96-12.72 11.28-12.72 6.37 0 11.39 5.79 11.28 12.72 0 7-4.96 12.72-11.28 12.72zm41.42 0c-6.19 0-11.28-5.69-11.28-12.72 0-7 4.96-12.72 11.28-12.72 6.37 0 11.39 5.79 11.28 12.72 0 7-4.96 12.72-11.28 12.72z" /></svg>
                    <span
                        className="text-white font-black uppercase tracking-widest text-xl outline-none min-w-[100px]"
                        contentEditable suppressContentEditableWarning
                    >
                        95%+ LOCKS
                    </span>
                </div>
                <div
                    className="text-white font-mono text-xs tracking-widest uppercase bg-black/20 px-3 py-1.5 rounded text-white/90 outline-none whitespace-nowrap"
                    contentEditable suppressContentEditableWarning
                >
                    LINK IN BIO
                </div>
            </div>
        </div>
    );

    // --- MINIMAL (CLEAN) THEME --- //
    const renderMinimalTheme = () => (
        <div ref={cardRef} className="w-full aspect-[4/5] bg-white relative flex flex-col overflow-hidden font-sans border-8 border-gray-100">
            <div className="pb-4 flex justify-between items-start" style={{ padding: `${paddingMultiplier * 1.5}rem` }}>
                <div>
                    <div className="text-gray-400 font-mono tracking-[0.2em] uppercase mb-1 outline-none transition-all" style={{ fontSize: `calc(10px * ${textSizeMultiplier})` }} contentEditable suppressContentEditableWarning>Insider Report</div>
                    <div className="text-black font-black tracking-tighter uppercase outline-none transition-all" style={{ fontSize: `calc(1.5rem * ${textSizeMultiplier})` }} contentEditable suppressContentEditableWarning>Algorithm Edge</div>
                </div>
                <div className="px-3 py-1 bg-black text-white font-bold uppercase tracking-widest rounded-sm outline-none transition-all" style={{ fontSize: `calc(10px * ${textSizeMultiplier})` }} contentEditable suppressContentEditableWarning>
                    Verified
                </div>
            </div>

            <div className="flex-1 flex flex-col justify-center border-y border-gray-100 my-4 bg-gray-50/50" style={{ padding: `${paddingMultiplier * 2}rem` }}>
                <div
                    className="text-gray-400 font-bold uppercase tracking-[0.15em] mb-4 outline-none transition-all"
                    style={{ fontSize: `calc(0.875rem * ${textSizeMultiplier})` }}
                    contentEditable suppressContentEditableWarning onBlur={handleTextBlur}
                >
                    {data.matchup}
                </div>

                <h1
                    className="font-black text-black leading-[1.05] tracking-tighter uppercase outline-none transition-all"
                    style={{ fontSize: `calc(3rem * ${textSizeMultiplier})` }}
                    contentEditable suppressContentEditableWarning onBlur={handleTextBlur}
                >
                    {displayPick.lock_text}
                </h1>

                <div className="mt-8 flex items-center gap-4 border-l-4 pl-4 py-1" style={{ borderColor: accentColor }}>
                    <span className="text-gray-400 font-bold uppercase tracking-widest outline-none transition-all" style={{ fontSize: `calc(10px * ${textSizeMultiplier})` }} contentEditable suppressContentEditableWarning>Suggested Play</span>
                    <span
                        className="font-black outline-none transition-all"
                        style={{ fontSize: `calc(1.5rem * ${textSizeMultiplier})`, color: accentColor }}
                        contentEditable suppressContentEditableWarning
                    >
                        {displayPick.lock_data}
                    </span>
                </div>
            </div>

            <div className="pt-2 flex justify-between items-end" style={{ padding: `${paddingMultiplier * 1.5}rem` }}>
                <div className="flex flex-col gap-1">
                    <span className="text-gray-400 font-mono text-[10px] uppercase tracking-widest mb-1 outline-none" contentEditable suppressContentEditableWarning>Math Probability</span>
                    <span className="text-black font-black text-3xl tracking-tighter outline-none" contentEditable suppressContentEditableWarning>{confidencePct}.4%</span>
                </div>
                <div className="flex flex-col items-end gap-2 text-gray-300">
                    <svg className="w-8 h-8 text-gray-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" /></svg>
                    <span className="font-mono text-[9px] uppercase tracking-widest outline-none" contentEditable suppressContentEditableWarning>{new Date().toLocaleDateString()}</span>
                </div>
            </div>
        </div>
    );

    // --- DEFAULT THEME --- //
    const renderDefaultTheme = () => (
        <div ref={cardRef} className="w-full aspect-[4/5] bg-gray-900 border border-gray-800 relative flex flex-col overflow-hidden justify-between" style={{ padding: pdScale }}>
            <div className="text-center mt-12">
                <div className="font-bold tracking-widest uppercase mb-6 outline-none transition-all" style={{ fontSize: `calc(0.75rem * ${textSizeMultiplier})`, color: accentColor }} contentEditable suppressContentEditableWarning onBlur={handleTextBlur}>{data.matchup}</div>
                <h1 className="font-black text-white uppercase leading-tight outline-none transition-all" style={{ fontSize: `calc(2.25rem * ${textSizeMultiplier})` }} contentEditable suppressContentEditableWarning onBlur={handleTextBlur}>{displayPick.lock_text}</h1>
                <div className="mt-8 font-black tracking-tight outline-none transition-all text-white" style={{ fontSize: `calc(1.875rem * ${textSizeMultiplier})` }} contentEditable suppressContentEditableWarning>{displayPick.lock_data}</div>
            </div>

            <div className="absolute inset-x-8 bottom-8 py-3 px-6 bg-black/40 rounded-lg flex justify-between items-center text-gray-400 font-mono tracking-widest uppercase" style={{ fontSize: `calc(10px * ${textSizeMultiplier})` }}>
                <span className="outline-none" contentEditable suppressContentEditableWarning>AI Confidence: {confidencePct}%</span>
                <span className="outline-none" contentEditable suppressContentEditableWarning>{new Date().toLocaleDateString()}</span>
            </div>
        </div>
    );

    // Color choices for palette
    const bgColors = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#FFFFFF"];

    return (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/95 p-4 animate-in fade-in duration-200">
            {/* Master Studio Controls Column */}
            {showControls && (
                <div className="absolute left-6 top-1/2 -translate-y-1/2 bg-gray-900 border border-gray-800 p-6 rounded-2xl shadow-2xl flex flex-col gap-6 w-64 animate-in slide-in-from-left-8 text-white z-50">
                    <h3 className="font-black tracking-widest text-xs border-b border-gray-800 pb-2 flex items-center gap-2">
                        <Settings size={14} /> STUDIO FREEDOM
                    </h3>

                    <div className="space-y-4">
                        <div className="flex flex-col gap-2">
                            <label className="text-[10px] text-gray-400 font-mono uppercase flex justify-between">
                                <span className="flex items-center gap-1"><Type size={10} /> Font Scale</span>
                                <span>{textSizeMultiplier.toFixed(1)}x</span>
                            </label>
                            <input type="range" min="0.5" max="1.5" step="0.1" value={textSizeMultiplier} onChange={(e) => setTextSizeMultiplier(Number(e.target.value))} className="accent-blue-500 bg-gray-800 h-1 rounded appearance-none" />
                        </div>

                        <div className="flex flex-col gap-2">
                            <label className="text-[10px] text-gray-400 font-mono uppercase flex justify-between">
                                <span className="flex items-center gap-1"><Maximize size={10} /> Logo Matrix</span>
                                <span>{logoScale.toFixed(1)}x</span>
                            </label>
                            <input type="range" min="0.5" max="2.0" step="0.1" value={logoScale} onChange={(e) => setLogoScale(Number(e.target.value))} className="accent-emerald-500 bg-gray-800 h-1 rounded appearance-none" />
                        </div>

                        <div className="flex flex-col gap-2">
                            <label className="text-[10px] text-gray-400 font-mono uppercase flex justify-between">
                                <span className="flex items-center gap-1"><Sliders size={10} /> Internal Padding</span>
                                <span>{paddingMultiplier.toFixed(1)}x</span>
                            </label>
                            <input type="range" min="0.5" max="2.0" step="0.1" value={paddingMultiplier} onChange={(e) => setPaddingMultiplier(Number(e.target.value))} className="accent-purple-500 bg-gray-800 h-1 rounded appearance-none" />
                        </div>
                    </div>

                    <div className="border-t border-gray-800 pt-4">
                        <label className="text-[10px] text-gray-400 font-mono uppercase mb-2 flex items-center gap-1"><Palette size={10} /> Brand Accent</label>
                        <div className="flex flex-wrap gap-2 mt-2">
                            {bgColors.map(color => (
                                <button
                                    key={color}
                                    onClick={() => setAccentColor(color)}
                                    className={`w-6 h-6 rounded-full transition-transform hover:scale-125 ${accentColor === color ? 'ring-2 ring-white scale-110 shadow-[0_0_15px_rgba(255,255,255,0.5)]' : 'ring-1 ring-gray-700'}`}
                                    style={{ backgroundColor: color }}
                                />
                            ))}
                        </div>
                    </div>
                </div>
            )}

            <div className="flex flex-col gap-5 max-w-[400px] w-full relative">

                {/* TOOLTIP / HINT */}
                <div className="absolute -top-10 left-0 right-0 flex justify-between items-center sm:-mx-16">
                    <div className="bg-white/10 text-white/70 text-[10px] font-mono px-4 py-1.5 rounded-full backdrop-blur-md flex items-center gap-2 border border-white/5">
                        <span className="text-xs animate-bounce">✏️</span> Click ANY text to edit, or logo to upload.
                    </div>

                    <button
                        onClick={() => setShowControls(!showControls)}
                        className={`flex items-center gap-2 px-3 py-1.5 rounded-full font-bold text-[10px] tracking-widest uppercase transition-colors border ${showControls ? 'bg-blue-600 text-white border-blue-500 shadow-[0_0_15px_rgba(59,130,246,0.3)]' : 'bg-gray-800 text-gray-400 border-gray-700 hover:bg-gray-700'}`}
                    >
                        <Sliders size={12} /> Studio
                    </button>
                </div>

                <div className={`relative rounded-2xl overflow-hidden shadow-[0_0_50px_rgba(0,0,0,0.8)]`}>
                    {theme === 'antigravity' && renderAntigravityTheme()}
                    {theme === 'minimal' && renderMinimalTheme()}
                    {theme === 'default' && renderDefaultTheme()}
                </div>

                <div className="flex gap-3">
                    <button
                        onClick={onClose}
                        className="flex-[1] py-3.5 bg-white/5 border border-white/10 text-white rounded-xl font-bold text-[11px] tracking-widest uppercase hover:bg-white/10 transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleDownload}
                        className="flex-[2] py-3.5 hover:bg-[#4752C4] text-white rounded-xl font-black text-[11px] tracking-widest uppercase flex items-center justify-center gap-2 transition-all shadow-lg"
                        style={{ backgroundColor: showControls ? accentColor : '#5865F2' }}
                    >
                        <Download size={16} strokeWidth={3} /> Save HQ Image
                    </button>
                </div>
            </div>
        </div>
    );
};
