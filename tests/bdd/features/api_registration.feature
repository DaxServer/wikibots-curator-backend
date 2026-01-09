Feature: API Key Registration
  As a developer
  I want to register using an API key
  So that I can test the application without OAuth

  Scenario: Successful registration with valid API key
    Given the server has API key registration configured
    When I register with a valid API key
    Then I should be successfully authenticated
    And my session should contain the test user

  Scenario: Registration fails with invalid API key
    Given the server has API key registration configured
    When I register with an invalid API key
    Then I should receive a 401 Unauthorized response

  Scenario: Registration fails when API key is missing
    Given the server has API key registration configured
    When I register without providing an API key
    Then I should receive a 400 Bad Request response
