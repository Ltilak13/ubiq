@REQ-RESERVE
Feature: Reserve available stock
  @SCN-RESERVE
  Scenario: Reserve part of the available stock
    Given item "widget" has 5 available units
    When I reserve 3 units of "widget" with ID "r1"
    Then the operation succeeds
    And 2 units remain available
    And 1 reservations exist

  @SCN-INSUFFICIENT
  Scenario: Reject a reservation above available stock
    Given item "widget" has 5 available units
    When I reserve 6 units of "widget" with ID "r1"
    Then the error is "insufficient_stock"
    And 5 units remain available
    And 0 reservations exist

  @SCN-COMPETING
  Scenario: A second reservation cannot spend reserved stock
    Given item "widget" has 5 available units
    When I reserve 3 units of "widget" with ID "r1"
    Then the operation succeeds
    When I reserve 3 units of "widget" with ID "r2"
    Then the error is "insufficient_stock"
    And 2 units remain available
    And 1 reservations exist

  @SCN-DUPLICATE
  Scenario: Reject a repeated reservation identifier
    Given item "widget" has 5 available units
    When I reserve 2 units of "widget" with ID "r1"
    Then the operation succeeds
    When I reserve 2 units of "widget" with ID "r1"
    Then the error is "duplicate_reservation"
    And 3 units remain available
    And 1 reservations exist

  @SCN-UNKNOWN-ITEM
  Scenario: Reject an unknown item
    When I reserve 2 units of "missing" with ID "r1"
    Then the error is "unknown_item"
    And 0 reservations exist
