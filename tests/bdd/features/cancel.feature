Feature: Cancel Batch Uploads
  As a curator
  I want to cancel queued uploads in a batch
  So that I can stop processing before it starts

  Scenario: Cancel queued uploads via WebSocket
    Given I am a logged-in user with id "12345"
    And a batch exists with id 1 for user "12345"
    And 3 upload requests exist with status "queued" in batch 1
    And the upload requests have Celery task IDs stored
    When I cancel batch 1
    Then the upload requests should be marked as "cancelled"
    And the Celery tasks should be revoked
    And I should not receive an error message

  Scenario: Cancel batch with no queued items
    Given I am a logged-in user with id "12345"
    And a batch exists with id 1 for user "12345"
    And an upload request exists with status "in_progress" in batch 1
    When I cancel batch 1
    Then I should receive an error message "No queued items to cancel"
    And the in_progress upload should remain unchanged

  Scenario: Cancel batch not owned by user
    Given I am a logged-in user with id "12345"
    And a batch exists with id 1 for user "67890"
    When I cancel batch 1
    Then I should receive an error message "Permission denied"

  Scenario: Cancel non-existent batch
    Given I am a logged-in user with id "12345"
    When I cancel batch 999
    Then I should receive an error message "Batch 999 not found"

  Scenario: Cancel batch with some queued and some in_progress items
    Given I am a logged-in user with id "12345"
    And a batch exists with id 1 for user "12345"
    And 2 upload requests exist with status "queued" in batch 1
    And I manually update one upload to "in_progress" status
    And the upload requests have Celery task IDs stored
    When I cancel batch 1
    Then 1 upload should be marked as "cancelled"
    And 1 upload should remain "in_progress"
    And the Celery task for the cancelled upload should be revoked

  Scenario: Cancel batch uploads without task IDs
    Given I am a logged-in user with id "12345"
    And a batch exists with id 1 for user "12345"
    And 2 upload requests exist with status "queued" in batch 1
    And the upload requests do not have Celery task IDs
    When I cancel batch 1
    Then the upload requests should be marked as "cancelled"
    And no Celery tasks should be revoked
