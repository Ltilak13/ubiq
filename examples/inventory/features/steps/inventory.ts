import assert from 'node:assert/strict';
import { After, Before, Given, When, Then, World, setWorldConstructor } from '@cucumber/cucumber';
import { openInventory, type Result } from '../../src/inventory.js';
import { items, reservations } from '../../src/schema.js';

class InventoryWorld extends World {
  inventory!: ReturnType<typeof openInventory>;
  result!: Result;
}
setWorldConstructor(InventoryWorld);
Before(function (this: InventoryWorld) { this.inventory = openInventory(); });
After(function (this: InventoryWorld) { this.inventory.close(); });
Given('item {string} has {int} available units', function (this: InventoryWorld, id: string, available: number) {
  this.inventory.db.insert(items).values({ id, available }).run();
});
When('I reserve {float} units of {string} with ID {string}', function (this: InventoryWorld, quantity: number, itemId: string, reservationId: string) {
  this.result = this.inventory.reserve({ reservationId, itemId, quantity });
});
When('I release reservation {string}', function (this: InventoryWorld, reservationId: string) {
  this.result = this.inventory.release({ reservationId });
});
Then('the operation succeeds', function (this: InventoryWorld) { assert.deepEqual(this.result, { ok: true }); });
Then('the error is {string}', function (this: InventoryWorld, error: string) { assert.deepEqual(this.result, { ok: false, error }); });
Then('{int} units remain available', function (this: InventoryWorld, available: number) {
  assert.equal(this.inventory.db.select().from(items).get()?.available, available);
});
Then('{int} reservations exist', function (this: InventoryWorld, count: number) {
  assert.equal(this.inventory.db.select().from(reservations).all().length, count);
});
