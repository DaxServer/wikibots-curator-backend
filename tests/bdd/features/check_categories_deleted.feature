Feature: Check Categories Deleted
  As a curator
  I want to check which wanted categories have been deleted on Commons
  So that I can warn the user before they try to create already-deleted categories

  Scenario: Some categories are deleted, others are not
    Given I am a logged-in user with id "12345"
    When I check if categories "Foo" and "Bar" are deleted and "Foo" is deleted
    Then I should receive a categories deleted response with "Foo" in the deleted list
