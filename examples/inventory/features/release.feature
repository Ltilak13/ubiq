@REQ-RELEASE
Feature: Release reserved stock once
  @SCN-RELEASE
  Scenario: Release and repeat the release
    Given item "widget" has 5 available units
    When I reserve 3 units of "widget" with ID "r1"
    Then the operation succeeds
    When I release reservation "r1"
    Then the operation succeeds
    And 5 units remain available
    When I release reservation "r1"
    Then the operation succeeds
    And 5 units remain available
    And 1 reservations exist

  @SCN-UNKNOWN-RESERVATION
  Scenario: Reject an unknown reservation
    Given item "widget" has 5 available units
    When I release reservation "missing"
    Then the error is "unknown_reservation"
    And 5 units remain available
