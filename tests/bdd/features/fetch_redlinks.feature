Feature: Fetch Redlinks
  As a curator
  I want to fetch category redlinks from Wikimedia Commons
  So that I can identify broken category links without waiting for the cache

  Scenario: Fetching redlinks returns items from Commons replica
    Given I am a logged-in user with id "12345"
    When I fetch redlinks
    Then I should receive a redlinks response with 2 items
