import { sql } from 'drizzle-orm';
import { check, integer, sqliteTable, text } from 'drizzle-orm/sqlite-core';

export const items = sqliteTable('items', {
  id: text('id').primaryKey(),
  available: integer('available').notNull(),
}, (table) => [
  check('item_id', sql`length(trim(${table.id})) > 0`),
  check('available_integer', sql`typeof(${table.available}) = 'integer' AND ${table.available} BETWEEN 0 AND 9007199254740991`),
]);

export const reservations = sqliteTable('reservations', {
  id: text('id').primaryKey(),
  itemId: text('item_id').notNull().references(() => items.id),
  quantity: integer('quantity').notNull(),
  status: text('status', { enum: ['active', 'released'] }).notNull(),
}, (table) => [
  check('reservation_id', sql`length(trim(${table.id})) > 0`),
  check('quantity_integer', sql`typeof(${table.quantity}) = 'integer' AND ${table.quantity} BETWEEN 1 AND 9007199254740991`),
  check('reservation_status', sql`${table.status} IN ('active', 'released')`),
]);
