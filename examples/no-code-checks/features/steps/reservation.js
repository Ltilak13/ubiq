const assert = require("node:assert");
const { Given, When, Then } = require("@cucumber/cucumber");

Given("the limits are {int} to {int}", function (min, max) {
  this.limits = { min, max };
});

When("a customer reserves {int}", function (quantity) {
  const { min, max } = this.limits;
  this.accepted = quantity >= min && quantity <= max;
});

Then("the reservation is accepted", function () {
  assert.strictEqual(this.accepted, true);
});

Then("the reservation is rejected", function () {
  assert.strictEqual(this.accepted, false);
});
