import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { openInventory } from '../src/inventory.js';
import { items, reservations } from '../src/schema.js';

test('reserve and release preserve state and reject reusing a released ID', () => {
  const inventory = openInventory();
  try {
    inventory.db.insert(items).values({ id: 'widget', available: 5 }).run();
    assert.deepEqual(inventory.reserve({ reservationId: 'r1', itemId: 'widget', quantity: 3 }), { ok: true });
    assert.equal(inventory.db.select().from(reservations).get()?.status, 'active');
    assert.deepEqual(inventory.release({ reservationId: 'r1' }), { ok: true });
    assert.equal(inventory.db.select().from(reservations).get()?.status, 'released');
    assert.deepEqual(inventory.release({ reservationId: 'r1' }), { ok: true });
    assert.equal(inventory.db.select().from(items).get()?.available, 5);
    assert.deepEqual(inventory.reserve({ reservationId: 'r1', itemId: 'widget', quantity: 1 }), { ok: false, error: 'duplicate_reservation' });
  } finally { inventory.close(); }
});

test('input validation rejects invalid shapes and values without writes', () => {
  const inventory = openInventory();
  try {
    inventory.db.insert(items).values({ id: 'widget', available: 5 }).run();
    for (const quantity of [0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, '1', null])
      assert.deepEqual(inventory.reserve({ reservationId: 'r1', itemId: 'widget', quantity }), { ok: false, error: 'invalid_input' });
    for (const input of [null, {}, { reservationId: ' ' }, { reservationId: 'r1', extra: true }])
      assert.deepEqual(inventory.release(input), { ok: false, error: 'invalid_input' });
    assert.equal(inventory.db.select().from(items).get()?.available, 5);
    assert.equal(inventory.db.select().from(reservations).all().length, 0);
  } finally { inventory.close(); }
});

test('database constraints reject writes that bypass Zod', () => {
  const inventory = openInventory();
  try {
    inventory.db.insert(items).values({ id: 'widget', available: 5 }).run();
    for (const quantity of [0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1])
      assert.throws(() => inventory.sqlite.prepare("INSERT INTO reservations VALUES ('r', 'widget', ?, 'active')").run(quantity));
    assert.throws(() => inventory.sqlite.exec("INSERT INTO reservations VALUES ('r', 'missing', 1, 'active')"));
    assert.throws(() => inventory.sqlite.exec("INSERT INTO reservations VALUES ('r', 'widget', 1, 'invalid')"));
    for (const available of [-1, 1.5, Number.MAX_SAFE_INTEGER + 1])
      assert.throws(() => inventory.sqlite.prepare('UPDATE items SET available = ?').run(available));
    assert.equal(inventory.db.select().from(items).get()?.available, 5);
  } finally { inventory.close(); }
});

test('database failures roll back both reservation and release', () => {
  const inventory = openInventory();
  try {
    inventory.db.insert(items).values({ id: 'widget', available: 5 }).run();
    inventory.sqlite.exec("CREATE TRIGGER fail_insert BEFORE INSERT ON reservations BEGIN SELECT RAISE(ABORT, 'test failure'); END");
    assert.throws(() => inventory.reserve({ reservationId: 'r1', itemId: 'widget', quantity: 3 }));
    assert.equal(inventory.db.select().from(items).get()?.available, 5);
    assert.equal(inventory.db.select().from(reservations).all().length, 0);
    inventory.sqlite.exec('DROP TRIGGER fail_insert');
    inventory.reserve({ reservationId: 'r1', itemId: 'widget', quantity: 3 });
    inventory.sqlite.exec("CREATE TRIGGER fail_restore BEFORE UPDATE ON items BEGIN SELECT RAISE(ABORT, 'test failure'); END");
    assert.throws(() => inventory.release({ reservationId: 'r1' }));
    assert.equal(inventory.db.select().from(items).get()?.available, 2);
    assert.equal(inventory.db.select().from(reservations).get()?.status, 'active');
  } finally { inventory.close(); }
});

test('two connections cannot write through a held reservation transaction', () => {
  const folder = mkdtempSync(join(tmpdir(), 'inventory-lock-'));
  const first = openInventory(join(folder, 'inventory.sqlite'));
  const second = openInventory(join(folder, 'inventory.sqlite'));
  try {
    first.db.insert(items).values({ id: 'widget', available: 5 }).run();
    second.sqlite.pragma('busy_timeout = 0');
    first.sqlite.exec('BEGIN IMMEDIATE');
    first.reserve({ reservationId: 'r1', itemId: 'widget', quantity: 3 });
    assert.throws(() => second.reserve({ reservationId: 'r2', itemId: 'widget', quantity: 3 }), /locked/);
    first.sqlite.exec('COMMIT');
    assert.deepEqual(second.reserve({ reservationId: 'r2', itemId: 'widget', quantity: 3 }), { ok: false, error: 'insufficient_stock' });
    assert.equal(second.db.select().from(items).get()?.available, 2);
    assert.equal(second.db.select().from(reservations).all().length, 1);
  } finally { first.close(); second.close(); rmSync(folder, { recursive: true, force: true }); }
});
