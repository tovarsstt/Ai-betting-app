// ── Parsing utilities ────────────────────────────────────────────────────────

export const parseJSON = (raw: string): unknown => {
  const clean = raw.replace(/```json|```/g, "").trim();
  try { return JSON.parse(clean); } catch { /* fall through */ }
  const match = clean.match(/\{[\s\S]*\}|\[[\s\S]*\]/);
  if (match) { try { return JSON.parse(match[0]); } catch { /* fall through */ } }
  throw new Error("JSON_PARSE_FAILED");
};

// ── parseOddsForTeams — extract home/away + spread from live odds text ────────
export function parseOddsForTeams(oddsText: string): { home: string; away: string; spread: number; homeOdds: number; awayOdds: number; drawOdds?: number } | null {
  try {
    // Robust match for "Away @ Home" followed by a separator and time.
    // MUST be multiline (m): odds text starts with a "LIVE ODDS — SPORT:"
    // header line, so a string-start anchor never matched the first game.
    const atMatch = oddsText.match(/^([A-Z][A-Za-z0-9 '\.]+?)\s+@\s+([A-Z][A-Za-z0-9 '\.]+?)\s+(?:[—–-]|at)\s+/m);
    if (!atMatch) return null;

    const away = atMatch[1].trim();
    const home = atMatch[2].trim();

    // Improved name-based extractor
    const extractByName = (teamName: string, line: string, pattern: string): string | null => {
      const words = teamName.split(' ');
      // Try full name first, then longest word
      const candidates = [teamName, ...words.sort((a,b) => b.length - a.length)];
      for (const cand of candidates) {
        if (cand.length < 3) continue;
        const kw = cand.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const re = new RegExp(kw + '[^|]*?' + pattern, 'i');
        const m = line.match(re);
        if (m) return m[1];
      }
      return null;
    };

    const spreadLine = oddsText.match(/Spread:[^\n]*/)?.[0] ?? '';
    const homeSpreadStr = spreadLine ? extractByName(home, spreadLine, '([+-]\\d+\\.?\\d*)\\s*\\(') : null;
    const allSpreads = [...spreadLine.matchAll(/([+-]\d+\.?\d*)\s*\(/g)].map(m => parseFloat(m[1]));
    const spread = homeSpreadStr ? parseFloat(homeSpreadStr) : (allSpreads[1] ?? allSpreads[0] ?? 0);

    const mlSection = oddsText.match(/Moneyline:[^\n]*/);
    // No moneyline → no data. Fabricating -110/-110 fed fake coin-flip odds
    // into the math layer disguised as real market data.
    if (!mlSection) return null;
    const oddsMatches = [...mlSection[0].matchAll(/([+-]\d{2,4})/g)].map(m => parseInt(m[1]));
    const homeOdds = parseInt(extractByName(home, mlSection[0], '([+-]\\d{2,4})') ?? '') || oddsMatches[1];
    const awayOdds = parseInt(extractByName(away, mlSection[0], '([+-]\\d{2,4})') ?? '') || oddsMatches[0];
    if (!Number.isFinite(homeOdds) || !Number.isFinite(awayOdds)) return null;

    // Soccer 3-way: capture the Draw price when present (optional, non-breaking)
    const drawMatch = mlSection[0].match(/draw[^|]*?([+-]\d{2,4})/i);
    const drawOdds = drawMatch ? parseInt(drawMatch[1]) : undefined;

    return { home, away, spread, homeOdds, awayOdds, ...(Number.isFinite(drawOdds) ? { drawOdds } : {}) };
  } catch (err) {
    console.error("[Parser] Odds parsing failed:", err);
    return null;
  }
}

// Extract matchup strings from live odds context (pattern: "Away @ Home —")
export function parseMatchupsFromOdds(oddsCtx: string): string[] {
  // Match "Team Name @ Other Team —" per line (no newlines, digits allowed for 76ers etc.)
  const matches = [...oddsCtx.matchAll(/([A-Z][a-zA-Z0-9 '\.]+?)\s+@\s+([A-Z][a-zA-Z0-9 '\.]+?)\s+[—–-]/g)];
  return matches.map(m => `${m[1].trim()} vs ${m[2].trim()}`);
}
