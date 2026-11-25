import { createInsertSchema } from 'drizzle-zod';
import { z } from 'zod';
import { reservations } from './schema.js';

const identifier = z.string().trim().min(1);
const reservationInput = createInsertSchema(reservations, {
  id: identifier, itemId: identifier, quantity: z.number().int().positive().max(Number.MAX_SAFE_INTEGER),
});
export const reserveInput = reservationInput.pick({ itemId: true, quantity: true })
  .extend({ reservationId: reservationInput.shape.id }).strict();
export const releaseInput = reserveInput.pick({ reservationId: true }).strict();
