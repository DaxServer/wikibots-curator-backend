Feature: Image Ingestion Worker
  As a background system
  I want to process queued upload requests
  So that images are correctly uploaded to Wikimedia Commons

  Scenario: Successfully processing a queued upload
    Given an upload request exists with status "queued" and key "img1"
    When the ingestion worker processes this upload request
    Then the upload status should be updated to "completed" in the database
    And the success URL should be recorded for the request
    And the access token for this request should be cleared for security

  Scenario: Handling a blacklisted title
    Given an upload request exists with status "queued" and title "Blacklisted.jpg"
    And the title "Blacklisted.jpg" is on the Commons blacklist
    When the ingestion worker processes this upload request
    Then the upload status should be updated to "failed"
    And the error message should include "blacklisted"

  Scenario: Handling a duplicate upload with SDC merge
    Given an upload request exists with status "queued" and key "duplicate_img"
    And the file already exists on Commons
    When the ingestion worker processes this upload request
    Then the SDC should be merged with the existing file
    And the upload status should be "duplicated_sdc_updated" or "duplicated_sdc_not_updated"
