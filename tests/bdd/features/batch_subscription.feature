Feature: Batch Subscription
  As a curator
  I want to subscribe to batch upload updates
  So that I can receive real-time progress updates

  Scenario: Subscribing to batch updates
    Given I am a logged-in user with id "12345"
    And a batch exists with id 1 for user "12345"
    When I subscribe to batch 1
    Then I should start receiving real-time updates for that batch

  Scenario: Unsubscribing from batch updates
    Given I am a logged-in user with id "12345"
    And a batch exists with id 1 for user "12345"
    And I am subscribed to batch 1
    When I unsubscribe from batch updates
    Then I should stop receiving updates for that batch
