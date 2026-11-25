CREATE TABLE `items` (
	`id` text PRIMARY KEY NOT NULL,
	`available` integer NOT NULL,
	CONSTRAINT "item_id" CHECK(length(trim("items"."id")) > 0),
	CONSTRAINT "available_integer" CHECK(typeof("items"."available") = 'integer' AND "items"."available" BETWEEN 0 AND 9007199254740991)
);
--> statement-breakpoint
CREATE TABLE `reservations` (
	`id` text PRIMARY KEY NOT NULL,
	`item_id` text NOT NULL,
	`quantity` integer NOT NULL,
	`status` text NOT NULL,
	FOREIGN KEY (`item_id`) REFERENCES `items`(`id`) ON UPDATE no action ON DELETE no action,
	CONSTRAINT "reservation_id" CHECK(length(trim("reservations"."id")) > 0),
	CONSTRAINT "quantity_integer" CHECK(typeof("reservations"."quantity") = 'integer' AND "reservations"."quantity" BETWEEN 1 AND 9007199254740991),
	CONSTRAINT "reservation_status" CHECK("reservations"."status" IN ('active', 'released'))
);
