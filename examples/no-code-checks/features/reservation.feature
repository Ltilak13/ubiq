Feature: Reservation
  A reservation is accepted only inside the configured limits.

  Scenario: A quantity inside the limits is accepted
    Given the limits are 1 to 10
    When a customer reserves 3
    Then the reservation is accepted

  Scenario: A quantity above the limits is rejected
    Given the limits are 1 to 10
    When a customer reserves 11
    Then the reservation is rejected
