Feature: Retry Failed Uploads
  As a curator
  I want to retry failed uploads
  So that I can recover from transient errors

  Scenario: Retrying failed uploads via WebSocket
    Given I am a logged-in user with id "12345"
    And a batch exists with id 1 for user "12345"
    And an upload request exists with status "failed" and key "img1"
    When I retry uploads for batch 1
    Then the upload requests should be reset to "queued" status
    And I should receive a confirmation with the number of retries

  Scenario: Admin can retry selected upload IDs
    Given I am logged in as admin "DaxServer"
    And there are 3 batches in the system
    And upload requests exist with status "failed"
    When I request to retry uploads with IDs "[1,2,3]" via admin API
    Then the response should indicate successful retry
    And only the selected uploads should be queued for processing

  Scenario: Admin retry ignores in_progress uploads
    Given I am logged in as admin "DaxServer"
    And an upload request exists with status "in_progress" and ID 1
    And an upload request exists with status "failed" and ID 2
    When I request to retry uploads with IDs "[1,2]" via admin API
    Then only upload ID 2 should be queued
    And upload ID 1 should remain in_progress

  Scenario: Admin retry ignores non-existent IDs
    Given I am logged in as admin "DaxServer"
    And an upload request exists with status "failed" and ID 1
    When I request to retry uploads with IDs "[1,999,1000]" via admin API
    Then the response should indicate 1 retried out of 3 requested
    And only upload ID 1 should be queued

  Scenario: Admin retry with empty list
    Given I am logged in as admin "DaxServer"
    When I request to retry uploads with empty IDs list
    Then the response should indicate 0 retried
