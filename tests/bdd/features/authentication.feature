Feature: Authentication
  As a user
  I want to manage my session
  So that I can securely use the tool

  Scenario: Checking current user identity
    Given I have an active session for "testuser" with id "12345"
    When I request "whoami"
    Then the response should contain username "testuser" and id "12345"

  Scenario: Logging out clears the session
    Given I have an active session for "testuser"
    When I request to logout
    Then I should be redirected to the home page
    And my session should be empty
