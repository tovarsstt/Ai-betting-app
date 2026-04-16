import { db } from './index.ts';
import { predictions, evSignals, trades } from './schema.ts';
import { v4 as uuidv4 } from 'uuid';

async function seed() {
  console.log("Seeding database with WinWithTovy betting history...");

  // === USER'S REAL BETTING HISTORY (April 15, 2026) ===
  const realTrades = [
    {
      id: uuidv4(),
      matchup: "LAC Clippers vs GS Warriors",
      mathEv: -0.12,
      dissonanceScore: 0.65,
      prospectTheoryRead: "Player prop parlay - high correlation risk",
      selection: "Kawhi O10.5 A+R / Curry O3.5 3PM / Gui Santos O14.5 PRA",
      alphaEdge: "FADE",
      kellySizing: "1.5%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-04-15T20:15:00"),
    },
    {
      id: uuidv4(),
      matchup: "ATL Braves vs MIA Marlins + SD Padres vs SEA Mariners + Athletics vs TEX Rangers + LAD Dodgers vs NY Mets",
      mathEv: 0.08,
      dissonanceScore: 0.30,
      prospectTheoryRead: "MLB moneyline parlay - all favorites with edge",
      selection: "Braves ML / Mariners ML / Athletics ML / Dodgers ML",
      alphaEdge: "SHARP",
      kellySizing: "2.5%",
      actualOutcome: "WIN",
      timestamp: new Date("2026-04-15T20:33:00"),
    },
    {
      id: uuidv4(),
      matchup: "PHI 76ers vs ORL Magic",
      mathEv: 0.15,
      dissonanceScore: 0.22,
      prospectTheoryRead: "Drummond props + 76ers ML combo - strong value",
      selection: "Drummond O7.5 Pts + 76ers ML",
      alphaEdge: "SHARP",
      kellySizing: "2.0%",
      actualOutcome: "WIN",
      timestamp: new Date("2026-04-15T19:31:00"),
    },
    {
      id: uuidv4(),
      matchup: "Arsenal vs Sporting CP + Bayern Munich vs Real Madrid",
      mathEv: 0.04,
      dissonanceScore: 0.55,
      prospectTheoryRead: "UCL Asian Handicap parlay - high variance",
      selection: "Sporting CP +1.5 AH / Real Madrid +1.5 AH",
      alphaEdge: "NEUTRAL",
      kellySizing: "2.2%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-04-15T14:15:00"),
    },
    {
      id: uuidv4(),
      matchup: "Bayern Munich vs Real Madrid",
      mathEv: 0.22,
      dissonanceScore: 0.70,
      prospectTheoryRead: "Single longshot ML - high risk/reward",
      selection: "Real Madrid ML @4.95",
      alphaEdge: "FADE",
      kellySizing: "2.5%",
      actualOutcome: "LOSS",
      timestamp: new Date("2026-04-15T14:14:00"),
    },
  ];

  // === PREDICTIONS (the engine's analysis for today's games) ===
  const predictionData = [
    {
      id: uuidv4(), matchup: "LAC Clippers vs GS Warriors", sport: "NBA", status: "completed",
      awayTeam: "LA Clippers", homeTeam: "Golden State Warriors",
      predictedWinner: "Golden State Warriors", evEdge: 0.045, kellyStake: 0.025,
      tiltTensor: -0.32, circadianFrictionHome: 0.15, circadianFrictionAway: 0.42,
      signal: "SHARP", gameDate: new Date("2026-04-15T21:00:00"),
    },
    {
      id: uuidv4(), matchup: "PHI 76ers vs ORL Magic", sport: "NBA", status: "completed",
      awayTeam: "Orlando Magic", homeTeam: "Philadelphia 76ers",
      predictedWinner: "Philadelphia 76ers", evEdge: 0.082, kellyStake: 0.035,
      tiltTensor: 0.18, circadianFrictionHome: 0.10, circadianFrictionAway: 0.55,
      signal: "SHARP", gameDate: new Date("2026-04-15T18:30:00"),
    },
    {
      id: uuidv4(), matchup: "ATL Braves vs MIA Marlins", sport: "MLB", status: "completed",
      awayTeam: "Miami Marlins", homeTeam: "Atlanta Braves",
      predictedWinner: "Atlanta Braves", evEdge: 0.065, kellyStake: 0.030,
      tiltTensor: 0.05, circadianFrictionHome: 0.08, circadianFrictionAway: 0.35,
      signal: "SHARP", gameDate: new Date("2026-04-15T18:15:00"),
    },
    {
      id: uuidv4(), matchup: "SD Padres vs SEA Mariners", sport: "MLB", status: "completed",
      awayTeam: "San Diego Padres", homeTeam: "Seattle Mariners",
      predictedWinner: "Seattle Mariners", evEdge: 0.038, kellyStake: 0.020,
      tiltTensor: -0.12, circadianFrictionHome: 0.20, circadianFrictionAway: 0.28,
      signal: "NEUTRAL", gameDate: new Date("2026-04-15T20:40:00"),
    },
    {
      id: uuidv4(), matchup: "LAD Dodgers vs NY Mets", sport: "MLB", status: "completed",
      awayTeam: "New York Mets", homeTeam: "Los Angeles Dodgers",
      predictedWinner: "Los Angeles Dodgers", evEdge: 0.072, kellyStake: 0.032,
      tiltTensor: 0.25, circadianFrictionHome: 0.05, circadianFrictionAway: 0.48,
      signal: "SHARP", gameDate: new Date("2026-04-15T21:10:00"),
    },
    {
      id: uuidv4(), matchup: "Athletics vs TEX Rangers", sport: "MLB", status: "completed",
      awayTeam: "Texas Rangers", homeTeam: "Athletics",
      predictedWinner: "Athletics", evEdge: 0.041, kellyStake: 0.022,
      tiltTensor: -0.08, circadianFrictionHome: 0.18, circadianFrictionAway: 0.30,
      signal: "NEUTRAL", gameDate: new Date("2026-04-15T20:40:00"),
    },
    {
      id: uuidv4(), matchup: "Bayern Munich vs Real Madrid", sport: "UCL", status: "completed",
      awayTeam: "Real Madrid CF", homeTeam: "Bayern Munich",
      predictedWinner: "Bayern Munich", evEdge: -0.05, kellyStake: 0.010,
      tiltTensor: -0.65, circadianFrictionHome: 0.12, circadianFrictionAway: 0.58,
      signal: "FADE", gameDate: new Date("2026-04-15T14:00:00"),
    },
    {
      id: uuidv4(), matchup: "Arsenal vs Sporting CP", sport: "UCL", status: "completed",
      awayTeam: "Sporting CP", homeTeam: "Arsenal FC",
      predictedWinner: "Arsenal FC", evEdge: 0.032, kellyStake: 0.018,
      tiltTensor: 0.10, circadianFrictionHome: 0.08, circadianFrictionAway: 0.40,
      signal: "NEUTRAL", gameDate: new Date("2026-04-15T14:00:00"),
    },
    {
      id: uuidv4(), matchup: "BOS Celtics vs MIL Bucks", sport: "NBA", status: "pending",
      awayTeam: "Milwaukee Bucks", homeTeam: "Boston Celtics",
      predictedWinner: "Boston Celtics", evEdge: 0.055, kellyStake: 0.028,
      tiltTensor: 0.22, circadianFrictionHome: 0.07, circadianFrictionAway: 0.38,
      signal: "SHARP", gameDate: new Date("2026-04-16T19:30:00"),
    },
    {
      id: uuidv4(), matchup: "DEN Nuggets vs DAL Mavericks", sport: "NBA", status: "pending",
      awayTeam: "Dallas Mavericks", homeTeam: "Denver Nuggets",
      predictedWinner: "Denver Nuggets", evEdge: 0.048, kellyStake: 0.024,
      tiltTensor: -0.15, circadianFrictionHome: 0.12, circadianFrictionAway: 0.45,
      signal: "SHARP", gameDate: new Date("2026-04-16T21:00:00"),
    },
  ];

  // === EV SIGNALS (derived from predictions) ===
  const evSignalData = predictionData.map((pred) => ({
    id: uuidv4(),
    predictionId: pred.id,
    homeTeam: pred.homeTeam,
    awayTeam: pred.awayTeam,
    sport: pred.sport,
    betSide: pred.predictedWinner,
    signal: pred.signal!,
    evEdgePct: pred.evEdge!,
    makerPrice: pred.evEdge! > 0 ? 1.5 + Math.random() * 1.5 : 3.5 + Math.random() * 2,
    kellyFraction: pred.kellyStake!,
  }));

  // Insert all data
  await db.insert(predictions).values(predictionData);
  console.log(`  Inserted ${predictionData.length} predictions`);

  await db.insert(evSignals).values(evSignalData);
  console.log(`  Inserted ${evSignalData.length} EV signals`);

  await db.insert(trades).values(realTrades);
  console.log(`  Inserted ${realTrades.length} trades (real betting history)`);

  console.log("Seed complete!");
  process.exit(0);
}

seed().catch((err) => {
  console.error("Seed failed:", err);
  process.exit(1);
});
