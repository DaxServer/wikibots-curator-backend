Feature: Mapillary Handler Camera Field Processing
  As a curator
  I want camera make and model fields from Mapillary to be cleaned
  So that "none" string values are converted to None

  Scenario: Mapillary sends "none" as camera make
    Given the Mapillary API response has make="none" and model="Canon EOS"
    When I convert the response using from_mapillary
    Then the MediaImage camera_make should be None
    And the MediaImage camera_model should be "Canon EOS"

  Scenario: Mapillary sends "none" as camera model
    Given the Mapillary API response has make="Canon" and model="none"
    When I convert the response using from_mapillary
    Then the MediaImage camera_make should be "Canon"
    And the MediaImage camera_model should be None

  Scenario: Mapillary sends valid camera make and model
    Given the Mapillary API response has make="Canon" and model="EOS 5D"
    When I convert the response using from_mapillary
    Then the MediaImage camera_make should be "Canon"
    And the MediaImage camera_model should be "EOS 5D"

  Scenario: Mapillary sends missing camera make and model
    Given the Mapillary API response has missing make and model
    When I convert the response using from_mapillary
    Then the MediaImage camera_make should be None
    And the MediaImage camera_model should be None

  Scenario: Mapillary sends "none" for both camera make and model
    Given the Mapillary API response has make="none" and model="none"
    When I convert the response using from_mapillary
    Then the MediaImage camera_make should be None
    And the MediaImage camera_model should be None
