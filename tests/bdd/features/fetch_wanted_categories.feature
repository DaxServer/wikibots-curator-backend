Feature: Fetch Wanted Categories
  As a curator admin
  I want to fetch wanted categories from Wikimedia Commons
  So that I can identify missing category pages that are referenced but don't exist

  Scenario: Fetching wanted categories returns items and total from Commons replica
    Given I am a logged-in user with id "12345"
    When I fetch wanted categories at offset 0
    Then I should receive a wanted categories response with 2 items and total 50

  Scenario: Fetching wanted categories at an offset passes offset to the query
    Given I am a logged-in user with id "12345"
    When I fetch wanted categories at offset 100
    Then the DuckDB query should have been called with offset 100

  Scenario: Fetching wanted categories with a filter passes filter text to the query
    Given I am a logged-in user with id "12345"
    When I fetch wanted categories with filter "Germany"
    Then the DuckDB query should have been called with filter "Germany"
