import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";

export function createDb(databaseUrl = process.env.DATABASE_URL) {
  if (!databaseUrl) {
    throw new Error("DATABASE_URL is required");
  }

  const client = postgres(databaseUrl);

  return drizzle(client);
}

export const db = createDb();
