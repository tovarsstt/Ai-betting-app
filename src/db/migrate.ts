import { db } from './index.ts';
import { migrate } from 'drizzle-orm/pglite/migrator';

async function runMigrate() {
  console.log("⏳ Running migrations...");
  const start = Date.now();
  await migrate(db, { migrationsFolder: 'drizzle' });
  const end = Date.now();
  console.log(`✅ Migrations completed in ${end - start}ms`);
  process.exit(0);
}

runMigrate().catch((err) => {
  console.error("❌ Migration failed");
  console.error(err);
  process.exit(1);
});
