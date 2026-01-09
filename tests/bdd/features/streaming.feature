Feature: Batch List Streaming
  As a curator
  I want to see a live-updating list of batches
  So that I can monitor the progress of my uploads

  Scenario: Initial sync of batches
    Given I am a logged-in user with id "12345"
    And 5 batches exist in the database for my user
    When I request to fetch my batches
    Then I should receive an initial full sync message with 5 batches
    And the total count in the message should be 5
