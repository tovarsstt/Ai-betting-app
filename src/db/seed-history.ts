import { db } from './index.ts';
import { trades } from './schema.ts';
import { v4 as uuidv4 } from 'uuid';

async function seedHistory() {
  console.log("Seeding additional betting history...");

  const historicalTrades = [
    // === APRIL 2, 2026 ===
    {
      id: uuidv4(),
      matchup: "DET Pistons vs MIN Timberwolves + CHA Hornets vs PHX Suns + OKC Thunder vs LA Lakers + GS Warriors vs CLE Cavaliers + LA Clippers vs SA Spurs",
      mathEv: 0.09,
      dissonanceScore: 0.25,
      prospectTheoryRead: "5-leg NBA spread/ML parlay - all favorites covered",
      selection: "Pistons -1.5 / Hornets -1.5 / Thunder ML / Cavaliers ML / Spurs +3.5",
      alphaEdge: "SHARP",
      kellySizing: "1.0%",
      actualOutcome: "WIN",
      timestamp: new Date("2026-04-02T17:49:00"),
    },
    {
      id: uuidv4(),
      matchup: "DET Pistons vs MIN Wolves + CHA Hornets vs PHX Suns + OKC Thunder vs LA Lakers + GS Warriors vs CLE Cavaliers",
      mathEv: -0.35,
      dissonanceScore: 0.80,
      prospectTheoryRead: "8-leg player props parlay - extreme correlation risk @12.43 odds",
      selection: "A.Thompson O1.5 STL / Duren O18.5 PTS / G.Allen O1.5 3PM / Diabate O7.5 REB / Doncic O26.5 PTS / Holmgren U19.5 PTS / Merrill O1.5 3PM / Mobley O22.5 PRA",
      alphaEdge: "FADE",
      kellySizing: "0.5%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-04-02T17:55:00"),
    },
    {
      id: uuidv4(),
      matchup: "DET Pistons vs MIN Wolves + CHA Hornets vs PHX Suns + ARI Diamondbacks vs ATL Braves + LA Clippers vs SA Spurs",
      mathEv: -0.10,
      dissonanceScore: 0.55,
      prospectTheoryRead: "Mixed NBA/MLB parlay with Baldwin TB prop",
      selection: "Pistons -1.5 / Hornets -1.5 / Drake Baldwin O1.5 TB / Spurs +3.5",
      alphaEdge: "NEUTRAL",
      kellySizing: "1.0%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-04-02T17:56:00"),
    },

    // === MARCH 28, 2026 ===
    {
      id: uuidv4(),
      matchup: "STL Cardinals vs TB Rays + CHI Cubs vs WSH Nationals + TOR Blue Jays vs Athletics + NY Mets vs PIT Pirates + MIL Brewers vs CHI White Sox + SF Giants vs NY Yankees",
      mathEv: -0.85,
      dissonanceScore: 0.95,
      prospectTheoryRead: "Massive 12+ leg MLB hits parlay @412.47 odds - lottery ticket",
      selection: "Aranda/Caminero/Crow-Armstrong/Amaya/Clement/Kirk/Lindor/Soto/Turang/Bellinger/Wells/Caballero hits & TB props",
      alphaEdge: "FADE",
      kellySizing: "0.5%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-03-28T11:01:00"),
    },
    {
      id: uuidv4(),
      matchup: "STL Cardinals vs TB Rays + SF Giants vs NY Yankees + LA Dodgers vs ARI Diamondbacks",
      mathEv: -0.15,
      dissonanceScore: 0.50,
      prospectTheoryRead: "3-leg MLB hits parlay - simple O0.5 hits",
      selection: "Caminero O0.5 hits / Caballero O0.5 hits / Tucker O0.5 hits",
      alphaEdge: "NEUTRAL",
      kellySizing: "2.0%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-03-28T11:03:00"),
    },
    {
      id: uuidv4(),
      matchup: "SF Giants vs NY Yankees",
      mathEv: -0.08,
      dissonanceScore: 0.60,
      prospectTheoryRead: "Yankees player props single-game parlay",
      selection: "Judge O0.5 hits / Caballero O0.5 TB / Wells O0.5 hits @4.30",
      alphaEdge: "NEUTRAL",
      kellySizing: "2.5%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-03-28T18:38:00"),
    },
    {
      id: uuidv4(),
      matchup: "CHA Hornets vs PHI 76ers + Illinois vs Iowa + SF Giants vs NY Yankees + ATL Hawks vs SAC Kings",
      mathEv: 0.02,
      dissonanceScore: 0.40,
      prospectTheoryRead: "4-leg ML parlay - NBA/NCAAB/MLB mix",
      selection: "Hornets ML / Illinois ML / Yankees ML / Hawks ML",
      alphaEdge: "NEUTRAL",
      kellySizing: "2.5%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-03-28T19:08:00"),
    },
    {
      id: uuidv4(),
      matchup: "CHA Hornets vs PHI 76ers + MEM Grizzlies vs CHI Bulls + Mexico vs Portugal + Adesanya vs Pyfer (UFC)",
      mathEv: -0.05,
      dissonanceScore: 0.65,
      prospectTheoryRead: "4-leg mixed sports parlay - NBA/Soccer/UFC",
      selection: "Hornets +2.5 / Bulls -1.5 / Portugal ML / Adesanya ML",
      alphaEdge: "NEUTRAL",
      kellySizing: "2.5%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-03-28T19:07:00"),
    },
    {
      id: uuidv4(),
      matchup: "Bahamondes vs Musayev + Adesanya vs Pyfer (UFC 313)",
      mathEv: 0.05,
      dissonanceScore: 0.35,
      prospectTheoryRead: "UFC 2-leg favorites parlay",
      selection: "Bahamondes ML / Adesanya ML @2.24",
      alphaEdge: "NEUTRAL",
      kellySizing: "2.1%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-03-28T18:38:00"),
    },
    {
      id: uuidv4(),
      matchup: "Sabalenka vs Gauff + MIL Bucks vs SA Spurs + Lehecka vs Sinner",
      mathEv: -0.02,
      dissonanceScore: 0.45,
      prospectTheoryRead: "Tennis/NBA mixed - Gauff games + Wemby blocks + Sinner ML",
      selection: "Gauff O8.5 games / Wembanyama O2.5 BLK / Sinner ML",
      alphaEdge: "NEUTRAL",
      kellySizing: "2.5%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-03-28T07:36:00"),
    },

    // === MARCH 27, 2026 ===
    {
      id: uuidv4(),
      matchup: "LA Dodgers vs ARI Diamondbacks + LA Lakers vs BKN Nets",
      mathEv: 0.06,
      dissonanceScore: 0.40,
      prospectTheoryRead: "2-leg LA props parlay - Betts hits + LeBron points",
      selection: "Mookie Betts O0.5 hits / LeBron O18.5 PTS",
      alphaEdge: "SHARP",
      kellySizing: "2.5%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-03-27T21:54:00"),
    },

    // === MARCH 25-26, 2026 ===
    {
      id: uuidv4(),
      matchup: "Tennis (Miami Open) + NCAAB (March Madness) - 14 legs",
      mathEv: -0.90,
      dissonanceScore: 0.95,
      prospectTheoryRead: "14-leg mega parlay @377 odds - Lehecka/Sabalenka/Paul/Sinner/Gauff/Zverev + NCAAB spreads",
      selection: "Lehecka ML / Sabalenka ML / Paul ML / Sinner ML / Gauff ML / Zverev ML / Texas +8.5 / Nebraska ML / Arizona -6.5 / Houston ML / St Johns +7.5 / Michigan ML / UConn -1.5 / Iowa St ML",
      alphaEdge: "FADE",
      kellySizing: "0.5%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-03-25T12:32:00"),
    },

    // === MARCH 18, 2026 ===
    {
      id: uuidv4(),
      matchup: "UCL: Barcelona vs Newcastle + Tottenham vs Atletico + Liverpool vs Galatasaray + Bayern vs Atalanta",
      mathEv: 0.03,
      dissonanceScore: 0.50,
      prospectTheoryRead: "UCL 4-leg parlay - DC + Asian totals/handicap",
      selection: "Barcelona DC / Spurs-Atletico O2.5 / Galatasaray +2.25 AH / Bayern-Atalanta O2.5",
      alphaEdge: "NEUTRAL",
      kellySizing: "6.5%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-03-18T00:32:00"),
    },
    {
      id: uuidv4(),
      matchup: "UCL: Barcelona vs Newcastle + Tottenham vs Atletico + Bayern vs Atalanta + Liverpool vs Galatasaray",
      mathEv: -0.20,
      dissonanceScore: 0.70,
      prospectTheoryRead: "UCL 4-leg longshot parlay @15.94 - Atletico ML + Galatasaray DC risky legs",
      selection: "Barcelona DC / Atletico ML / Bayern-Atalanta O2.5 / Galatasaray DC @15.94",
      alphaEdge: "FADE",
      kellySizing: "0.5%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-03-18T00:34:00"),
    },

    // === MARCH 17, 2026 ===
    {
      id: uuidv4(),
      matchup: "SAC Kings vs SA Spurs + DEN Nuggets vs PHI 76ers",
      mathEv: 0.04,
      dissonanceScore: 0.45,
      prospectTheoryRead: "NBA team totals parlay - both overs",
      selection: "Spurs O134.5 team total / Nuggets O129.5 team total",
      alphaEdge: "NEUTRAL",
      kellySizing: "3.4%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-03-17T22:28:00"),
    },
    {
      id: uuidv4(),
      matchup: "USA vs Venezuela (WBC)",
      mathEv: 0.18,
      dissonanceScore: 0.30,
      prospectTheoryRead: "WBC underdog ML - Venezuela value play",
      selection: "Venezuela ML @2.95",
      alphaEdge: "SHARP",
      kellySizing: "2.0%",
      actualOutcome: "WIN",
      timestamp: new Date("2026-03-17T18:24:00"),
    },
  ];

  await db.insert(trades).values(historicalTrades);
  console.log(`  Inserted ${historicalTrades.length} historical trades`);
  console.log("Historical seed complete!");
  process.exit(0);
}

seedHistory().catch((err) => {
  console.error("Historical seed failed:", err);
  process.exit(1);
});
