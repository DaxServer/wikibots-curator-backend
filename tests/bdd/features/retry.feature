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

  Scenario: Admin can retry any batch
    Given I am logged in as admin "DaxServer"
    And there are 3 batches in the system
    And an upload request exists with status "failed" and key "admin_img"
    When I request to retry batch 1 via admin API
    Then the response should indicate successful retry
    And the uploads should be queued for processing
