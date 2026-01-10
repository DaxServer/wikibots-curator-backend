Feature: Admin Panel
  As an administrator
  I want to manage the system data
  So that I can monitor usage and fix issues

  Scenario: Admin can list all batches
    Given I am logged in as admin "DaxServer"
    And there are 3 batches in the system
    When I request the admin list of batches
    Then the response should contain 3 batches

  Scenario: Non-admin cannot access admin panel
    Given I am logged in as user "testuser"
    When I request the admin list of batches
    Then I should receive a 403 Forbidden response

  Scenario: Admin can list all users
    Given I am logged in as admin "DaxServer"
    And there are 2 users in the system
    When I request the admin list of users
    Then the response should contain 2 users

  Scenario: Admin users endpoint returns properly serialized user data
    Given I am logged in as admin "DaxServer"
    And there are 2 users in the system
    When I request the admin list of users
    Then the response should contain 2 users
    And each user should have username and userid fields
