Feature: Create Category
  As a curator
  I want to create a category page on Wikimedia Commons via WebSocket
  So that I can create missing wanted categories without a separate HTTP request

  Scenario: Successfully creating a category
    Given I am a logged-in user with id "12345"
    When I send a create category request for "Foo" with text "{{subst:unc}}"
    Then I should receive a category created response with title "Category:Foo"

  Scenario: Creating a category that already exists returns an error
    Given I am a logged-in user with id "12345"
    When I send a create category request for "Foo" and the page already exists
    Then I should receive an error response

  Scenario: Creating a category with a Wikidata QID adds P373 and sitelink
    Given I am a logged-in user with id "12345"
    When I send a create category request for "Foo" with text "{{WI}}" and wikidata_qid "Q123"
    Then I should receive a category created response with title "Category:Foo"
    And the Wikidata item "Q123" should have P373 and sitelink added

  Scenario: Wikidata edit failure does not prevent category creation success
    Given I am a logged-in user with id "12345"
    When I send a create category request for "Foo" with text "{{WI}}" and wikidata_qid "Q123" but Wikidata edit fails
    Then I should receive a category created response with title "Category:Foo"
