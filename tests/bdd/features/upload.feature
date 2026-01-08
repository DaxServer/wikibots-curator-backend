Feature: Upload Workflow
  As a curator
  I want to create batches and upload image data
  So that I can eventually upload them to Wikimedia Commons

  Scenario: Creating a new batch
    Given I am a logged-in user with id "12345"
    When I request to create a new batch
    Then a new batch should exist in the database for my user
    And I should receive a message with the new batch id

  Scenario: Uploading multiple images to a batch
    Given a batch exists with id 1 for user "12345"
    And I am a logged-in user with id "12345"
    When I upload a slice with 2 images to batch 1
    Then 2 upload requests should be created in the database for batch 1
    And these 2 uploads should be enqueued for background processing
    And I should receive an acknowledgment for slice 1
