Feature: Batch Operations
  As a curator
  I want to fetch and manage batch uploads
  So that I can monitor upload progress

  Scenario: Fetching uploads for a batch
    Given I am a logged-in user with id "12345"
    And a batch exists with id 1 for user "12345"
    And 2 upload requests exist for batch 1 with various statuses
    When I fetch uploads for batch 1
    Then I should receive all upload requests for that batch
    And the response should include status information

  Scenario: Admin can list all upload requests
    Given I am logged in as admin "DaxServer"
    And there are 3 upload requests in the system
    When I request the admin list of upload requests
    Then the response should contain 3 upload requests

  Scenario: Admin can update an upload request
    Given I am logged in as admin "DaxServer"
    And an upload request exists with status "failed" and key "updatable_img"
    When I update the upload request status to "queued"
    Then the upload request should be updated in the database
