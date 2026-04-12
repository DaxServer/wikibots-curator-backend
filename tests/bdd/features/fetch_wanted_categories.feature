Feature: Fetch Wanted Categories
  As a curator admin
  I want to fetch wanted categories from Wikimedia Commons
  So that I can identify missing category pages that are referenced but don't exist

  Scenario: Fetching wanted categories returns items from Commons replica
    Given I am a logged-in user with id "12345"
    When I fetch wanted categories
    Then I should receive a wanted categories response with 2 items
