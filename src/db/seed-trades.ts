import { db } from './index.js';
import { trades } from './schema.js';

const allTrades = [
  // === APR 15, 2026 ===
  { id: 't001', timestamp: new Date('2026-04-15'), matchup: 'Mets vs Braves', selection: 'Mets ML', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '2u' },
  { id: 't002', timestamp: new Date('2026-04-15'), matchup: 'Padres vs Dodgers', selection: 'Padres ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't003', timestamp: new Date('2026-04-15'), matchup: 'NBA 5-Leg Parlay', selection: 'Multi-team spread parlay', actualOutcome: 'Perdida', alphaEdge: 'SHARP', kellySizing: '1u' },
  { id: 't004', timestamp: new Date('2026-04-15'), matchup: 'UFC Fight Night', selection: 'Favorite ML', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '1.5u' },
  { id: 't005', timestamp: new Date('2026-04-15'), matchup: 'Marlins vs Cubs', selection: 'Cubs -1.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },

  // === APR 14, 2026 ===
  { id: 't006', timestamp: new Date('2026-04-14'), matchup: 'Celtics vs Heat', selection: 'Celtics -5.5', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '2u' },
  { id: 't007', timestamp: new Date('2026-04-14'), matchup: 'Knicks vs Pacers', selection: 'Over 224.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't008', timestamp: new Date('2026-04-14'), matchup: 'Real Madrid vs Arsenal', selection: 'Real Madrid ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },

  // === APR 13, 2026 ===
  { id: 't009', timestamp: new Date('2026-04-13'), matchup: 'Warriors vs Lakers', selection: 'Warriors ML', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '2u' },
  { id: 't010', timestamp: new Date('2026-04-13'), matchup: 'Inter Miami vs LAFC', selection: 'LAFC +0.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },

  // === APR 10-12, 2026 ===
  { id: 't011', timestamp: new Date('2026-04-12'), matchup: 'Rangers vs Devils', selection: 'Rangers ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't012', timestamp: new Date('2026-04-11'), matchup: 'Suns vs Nuggets', selection: 'Under 228', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't013', timestamp: new Date('2026-04-10'), matchup: 'Barcelona vs Atletico', selection: 'Barcelona ML', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '2u' },

  // === APR 7-9, 2026 ===
  { id: 't014', timestamp: new Date('2026-04-09'), matchup: 'NBA 4-Leg SGP', selection: 'LeBron 30+ pts + Lakers ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't015', timestamp: new Date('2026-04-08'), matchup: 'Steele vs Alcaraz (Tennis)', selection: 'Alcaraz -3.5', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '1.5u' },
  { id: 't016', timestamp: new Date('2026-04-07'), matchup: 'Pirates vs Phillies', selection: 'Phillies -1.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },

  // === APR 3-6, 2026 ===
  { id: 't017', timestamp: new Date('2026-04-06'), matchup: 'Cavaliers vs Bucks', selection: 'Cavaliers -3', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '2u' },
  { id: 't018', timestamp: new Date('2026-04-05'), matchup: 'Soccer 3-Leg Parlay', selection: 'Man City + Liverpool + Bayern ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't019', timestamp: new Date('2026-04-04'), matchup: 'Spurs vs OKC', selection: 'OKC -7.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't020', timestamp: new Date('2026-04-03'), matchup: 'Djokovic vs Zverev (Tennis)', selection: 'Djokovic ML', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '2u' },

  // === APR 1-2, 2026 ===
  { id: 't021', timestamp: new Date('2026-04-02'), matchup: 'Warriors vs Clippers', selection: 'Warriors +3', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't022', timestamp: new Date('2026-04-01'), matchup: 'UCL Bayern vs PSG', selection: 'PSG +1', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },

  // === MAR 28-31, 2026 ===
  { id: 't023', timestamp: new Date('2026-03-31'), matchup: 'NBA 5-Leg Parlay', selection: 'Celtics, Nuggets, OKC, Bucks, Cavs covers', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't024', timestamp: new Date('2026-03-30'), matchup: 'Venezuela vs Dominican Republic (WBC)', selection: 'Venezuela ML', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '2u' },
  { id: 't025', timestamp: new Date('2026-03-29'), matchup: 'Tennis 7-Leg Parlay', selection: 'Sinner, Alcaraz, Medvedev, Swiatek, Sabalenka, Rybakina, Gauff ML', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '1u', mathEv: 25.92 },
  { id: 't026', timestamp: new Date('2026-03-28'), matchup: 'Timberwolves vs Thunder', selection: 'Under 214', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },

  // === MAR 24-27, 2026 ===
  { id: 't027', timestamp: new Date('2026-03-27'), matchup: 'Pelicans vs Rockets', selection: 'Rockets ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't028', timestamp: new Date('2026-03-26'), matchup: 'Soccer 2-Leg Parlay', selection: 'Real Madrid + Ajax ML', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '1u', mathEv: 30.0, prospectTheoryRead: 'Real Madrid ML @6.00' },
  { id: 't029', timestamp: new Date('2026-03-25'), matchup: 'Mets vs Yankees', selection: 'Mets +1.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't030', timestamp: new Date('2026-03-24'), matchup: 'Suns vs Spurs', selection: 'Suns -9.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },

  // === MAR 20-23, 2026 ===
  { id: 't031', timestamp: new Date('2026-03-23'), matchup: 'Medvedev vs Hurkacz (Tennis)', selection: 'Medvedev ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't032', timestamp: new Date('2026-03-22'), matchup: 'UCL Chelsea vs Real Madrid', selection: 'Real Madrid +0.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't033', timestamp: new Date('2026-03-21'), matchup: 'NBA 3-Leg SGP Lakers', selection: 'LeBron 25+ pts, Lakers ML, Over 220', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't034', timestamp: new Date('2026-03-20'), matchup: 'Sinner vs Fritz (Tennis)', selection: 'Sinner -4.5', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '2u' },

  // === MAR 17-19, 2026 ===
  { id: 't035', timestamp: new Date('2026-03-19'), matchup: 'NBA 5-Leg Spread Parlay', selection: 'Celtics -5.5, Cavs -4, Bucks -3, OKC -8.5, Nuggets -6', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '1u', mathEv: 61.36 },
  { id: 't036', timestamp: new Date('2026-03-18'), matchup: 'Inter Miami vs Columbus', selection: 'Inter Miami ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't037', timestamp: new Date('2026-03-17'), matchup: 'Venezuela ML (Baseball)', selection: 'Venezuela ML', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '2u' },

  // === MAR 14-16, 2026 ===
  { id: 't038', timestamp: new Date('2026-03-16'), matchup: 'UCL Man City vs Juventus', selection: 'Man City ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't039', timestamp: new Date('2026-03-15'), matchup: 'Alcaraz vs Rublev (Tennis)', selection: 'Alcaraz ML', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '2u' },
  { id: 't040', timestamp: new Date('2026-03-14'), matchup: 'Pacers vs Knicks', selection: 'Over 228.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },

  // === MAR 11-13, 2026 ===
  { id: 't041', timestamp: new Date('2026-03-13'), matchup: 'Soccer Parlay 3-Leg', selection: 'Liverpool + Man United + Arsenal ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't042', timestamp: new Date('2026-03-12'), matchup: 'Bucks vs Bulls', selection: 'Bucks -9', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't043', timestamp: new Date('2026-03-11'), matchup: 'WBC Puerto Rico vs Cuba', selection: 'Puerto Rico ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },

  // === MAR 8-10, 2026 ===
  { id: 't044', timestamp: new Date('2026-03-10'), matchup: 'Suns vs Warriors', selection: 'Under 228', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't045', timestamp: new Date('2026-03-09'), matchup: 'UCL Barcelona vs Dortmund', selection: 'Barcelona -1', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '2u' },
  { id: 't046', timestamp: new Date('2026-03-08'), matchup: 'Gauff vs Swiatek (Tennis)', selection: 'Swiatek ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },

  // === MAR 5-7, 2026 ===
  { id: 't047', timestamp: new Date('2026-03-07'), matchup: 'Timberwolves vs Nuggets', selection: 'Nuggets -4.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't048', timestamp: new Date('2026-03-06'), matchup: 'NBA 4-Leg Parlay', selection: 'Celtics, Heat, Bucks, Cavs ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't049', timestamp: new Date('2026-03-05'), matchup: 'Santos vs Flamengo (Brazil)', selection: 'Flamengo ML', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '2u' },
  { id: 't050', timestamp: new Date('2026-03-05'), matchup: 'Draper vs Dimitrov (Tennis)', selection: 'Dimitrov ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },

  // === Additional trades from later data ===
  { id: 't051', timestamp: new Date('2026-04-16'), matchup: 'Braves vs Cardinals', selection: 'Braves ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't052', timestamp: new Date('2026-04-16'), matchup: 'Nets vs Pistons', selection: 'Pistons +7.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't053', timestamp: new Date('2026-04-14'), matchup: 'Raptors vs Bulls', selection: 'Under 218', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't054', timestamp: new Date('2026-04-12'), matchup: 'Man City vs Arsenal (EPL)', selection: 'Man City -0.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't055', timestamp: new Date('2026-04-11'), matchup: 'Sablenka vs Navarro (Tennis)', selection: 'Sabalenka ML', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '1.5u' },
  { id: 't056', timestamp: new Date('2026-04-09'), matchup: 'Blue Jays vs Red Sox', selection: 'Red Sox +1.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't057', timestamp: new Date('2026-04-08'), matchup: 'UFC 312 - Main Event', selection: 'Underdog ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't058', timestamp: new Date('2026-04-06'), matchup: 'Grizzlies vs Pelicans', selection: 'Grizzlies +4.5', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't059', timestamp: new Date('2026-04-04'), matchup: 'Royals vs White Sox', selection: 'Royals ML', actualOutcome: 'Perdida', alphaEdge: 'NEUTRAL', kellySizing: '1u' },
  { id: 't060', timestamp: new Date('2026-04-03'), matchup: 'Sinner vs Alcaraz (Tennis)', selection: 'Alcaraz ML', actualOutcome: 'Ganador', alphaEdge: 'SHARP', kellySizing: '2u' },
];

async function seedTrades() {
  console.log('Seeding trades...');
  for (const trade of allTrades) {
    await db.insert(trades).values(trade).onConflictDoNothing();
  }
  console.log(`Seeded ${allTrades.length} trades.`);
  process.exit(0);
}

seedTrades().catch(console.error);
