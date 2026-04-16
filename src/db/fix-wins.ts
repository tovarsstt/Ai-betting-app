import { db } from './index.ts';
import { trades } from './schema.ts';
import { eq } from 'drizzle-orm';

async function fixWins() {
  console.log("Fixing win/loss records...");

  // First, let's see all trades and their outcomes
  const allTrades = await db.query.trades.findMany({
    orderBy: (trades, { desc }) => [desc(trades.timestamp)],
  });

  console.log(`Total trades in DB: ${allTrades.length}`);

  // These matchup substrings should be WIN based on the user's data (Pago > 0)
  const shouldBeWin = [
    // Apr 15 batch (already correct in seed.ts)
    // "ATL Braves vs MIA Marlins" - already WIN
    // "PHI 76ers vs ORL Magic" - already WIN

    // Apr 2 - NBA 5-leg (already WIN in seed-history.ts)
    // "DET Pistons vs MIN Timberwolves + CHA Hornets" - already WIN

    // Mar 17
    "Manchester City vs Real Madrid (UCL)", // Real Madrid ML @6.00 - Pago $30
    "UCL: Man City vs Real Madrid + Chelsea vs PSG + Arsenal vs Leverkusen", // UCL 3-leg - Pago $18.88
    "USA vs Venezuela (WBC)", // Venezuela ML - Pago $11.80

    // Mar 6
    "Tennis: Osorio vs Jovic + Paul vs Bergs + Anisimova", // Tennis 5-leg - Pago $15.74
    "Brazil vs USA (WBC)", // O16.5 - Pago $9.50
    "WBC + Soccer: Panama + Bayern", // 4-leg - Pago $26.97
    "Tennis + WBC: Kopriva vs Zheng + Sierra", // 3-leg - Pago $14.03

    // Mar 5
    "DEN Nuggets vs LA Lakers + SAC Kings vs NOP", // Nuggets ML + Zion - Pago $13.50
    "HOU Rockets vs GS Warriors + SA Spurs vs DET", // NBA 5-leg spreads - Pago $61.36
    "MIN Timberwolves vs TOR Raptors + PHX Suns", // Wolves ML + Bulls - Pago $31.66
    "Tennis: Shevchenko + Dimitrov + Vekic", // Tennis 7-leg - Pago $25.92
  ];

  let fixed = 0;
  for (const trade of allTrades) {
    const matchup = trade.matchup || '';
    for (const winStr of shouldBeWin) {
      if (matchup.includes(winStr.substring(0, 30))) {
        if (trade.actualOutcome !== 'WIN') {
          await db.update(trades)
            .set({ actualOutcome: 'WIN' })
            .where(eq(trades.id, trade.id));
          console.log(`  Fixed: ${matchup.substring(0, 60)}... → WIN`);
          fixed++;
        }
        break;
      }
    }
  }

  // Also fix the SAC Kings/Spurs + Nuggets/76ers team totals - Pago was 0, should be LOSS (already correct)

  // Recount
  const updated = await db.query.trades.findMany();
  const wins = updated.filter(t => t.actualOutcome === 'WIN').length;
  const losses = updated.filter(t => t.actualOutcome === 'LOSS').length;
  console.log(`\nFixed ${fixed} records`);
  console.log(`Final count: ${wins} Wins, ${losses} Losses out of ${updated.length} total`);
  console.log(`Win rate: ${(wins/updated.length*100).toFixed(1)}%`);

  process.exit(0);
}

fixWins().catch((err) => {
  console.error("Fix failed:", err);
  process.exit(1);
});
