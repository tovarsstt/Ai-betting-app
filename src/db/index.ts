import { drizzle } from "drizzle-orm/pglite";
import { PGlite } from "@electric-sql/pglite";
import * as schema from "./schema.ts"; 
import dotenv from "dotenv";
dotenv.config();

// Embeds the PostgreSQL instance directly inside the .data folder of the project
const client = new PGlite('./.data/postgres');
export const db = drizzle(client, { schema });
