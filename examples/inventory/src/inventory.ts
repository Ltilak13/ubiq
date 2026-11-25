import Database from 'better-sqlite3';
import { and, eq, gte, sql } from 'drizzle-orm';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import { migrate } from 'drizzle-orm/better-sqlite3/migrator';
import { fileURLToPath } from 'node:url';
import { releaseInput, reserveInput } from './contracts.js';
import { items, reservations } from './schema.js';

export type Failure = 'invalid_input' | 'unknown_item' | 'unknown_reservation' | 'duplicate_reservation' | 'insufficient_stock';
export type Result = { ok: true } | { ok: false; error: Failure };

export function openInventory(filename = ':memory:') {
  const sqlite = new Database(filename);
  sqlite.pragma('foreign_keys = ON');
  const db = drizzle(sqlite);
  migrate(db, { migrationsFolder: fileURLToPath(new URL('../drizzle', import.meta.url)) });

  function reserve(input: unknown): Result {
    const parsed = reserveInput.safeParse(input);
    if (!parsed.success) return { ok: false, error: 'invalid_input' };
    const { reservationId, itemId, quantity } = parsed.data;
    return db.transaction((tx): Result => {
      if (tx.select().from(reservations).where(eq(reservations.id, reservationId)).get())
        return { ok: false, error: 'duplicate_reservation' };
      if (!tx.select().from(items).where(eq(items.id, itemId)).get())
        return { ok: false, error: 'unknown_item' };
      const updated = tx.update(items).set({ available: sql`${items.available} - ${quantity}` })
        .where(and(eq(items.id, itemId), gte(items.available, quantity))).run();
      if (!updated.changes) return { ok: false, error: 'insufficient_stock' };
      tx.insert(reservations).values({ id: reservationId, itemId, quantity, status: 'active' }).run();
      return { ok: true };
    }, { behavior: 'immediate' });
  }

  function release(input: unknown): Result {
    const parsed = releaseInput.safeParse(input);
    if (!parsed.success) return { ok: false, error: 'invalid_input' };
    return db.transaction((tx): Result => {
      const reservation = tx.select().from(reservations)
        .where(eq(reservations.id, parsed.data.reservationId)).get();
      if (!reservation) return { ok: false, error: 'unknown_reservation' };
      if (reservation.status === 'released') return { ok: true };
      tx.update(reservations).set({ status: 'released' })
        .where(and(eq(reservations.id, reservation.id), eq(reservations.status, 'active'))).run();
      tx.update(items).set({ available: sql`${items.available} + ${reservation.quantity}` })
        .where(eq(items.id, reservation.itemId)).run();
      return { ok: true };
    }, { behavior: 'immediate' });
  }

  return { sqlite, db, reserve, release, close: () => sqlite.close() };
}
