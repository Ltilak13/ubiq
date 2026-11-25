@REQ-VALIDATION
Feature: Validate reservation quantities
  @SCN-ZERO
  Scenario: Reject zero units
    Given item "widget" has 5 available units
    When I reserve 0 units of "widget" with ID "r1"
    Then the error is "invalid_input"
    And 5 units remain available
    And 0 reservations exist

  @SCN-NEGATIVE
  Scenario: Reject negative units
    Given item "widget" has 5 available units
    When I reserve -1 units of "widget" with ID "r1"
    Then the error is "invalid_input"
    And 5 units remain available
    And 0 reservations exist

  @SCN-FRACTION
  Scenario: Reject fractional units
    Given item "widget" has 5 available units
    When I reserve 1.5 units of "widget" with ID "r1"
    Then the error is "invalid_input"
    And 5 units remain available
    And 0 reservations exist

  @SCN-UNSAFE
  Scenario: Reject an unsafe integer
    Given item "widget" has 5 available units
    When I reserve 9007199254740992 units of "widget" with ID "r1"
    Then the error is "invalid_input"
    And 5 units remain available
    And 0 reservations exist
