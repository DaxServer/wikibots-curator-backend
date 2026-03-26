Feature: Chunk Upload Retry Logic
  As a curator worker
  I want chunk uploads to retry on transient network errors
  So that uploads can succeed even when individual chunks fail

  Scenario: Chunk upload succeeds on first attempt
    Given a MediaWiki client with valid authentication
    And a file exists at "/tmp/test.jpg" with size 3MB
    When I upload the file using chunked upload
    Then the upload should succeed
    And all 3 chunks should be uploaded
    And no retries should occur

  Scenario: Chunk upload retries once on 502 error
    Given a MediaWiki client with valid authentication
    And a file exists at "/tmp/test.jpg" with size 3MB
    And the API request for chunk 2 fails with 502 error on first attempt
    When I upload the file using chunked upload
    Then the upload should succeed
    And chunk 2 should be retried once
    And a warning should be logged for the retry

  Scenario: Chunk upload fails after max retries
    Given a MediaWiki client with valid authentication
    And a file exists at "/tmp/test.jpg" with size 3MB
    And all API requests for chunk 2 fail with 502 error
    When I upload the file using chunked upload
    Then the upload should fail
    And the error message should include "Chunk 2/3"
    And the error message should include "after 4 attempts"

  Scenario: Chunk upload retry on timeout
    Given a MediaWiki client with valid authentication
    And a file exists at "/tmp/test.jpg" with size 3MB
    And the API request for chunk 1 times out on first attempt
    When I upload the file using chunked upload
    Then the upload should succeed
    And chunk 1 should be retried once

  Scenario: Duplicate error does not trigger retry
    Given a MediaWiki client with valid authentication
    And a file exists at "/tmp/test.jpg" with size 3MB
    And the API response for chunk 3 contains duplicate warning
    When I upload the file using chunked upload
    Then a DuplicateUploadError should be raised
    And no retries should occur for the duplicate error
