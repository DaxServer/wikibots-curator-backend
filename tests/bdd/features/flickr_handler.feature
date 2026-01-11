Feature: Flickr Handler Integration
  As a curator
  I want to fetch images from Flickr albums using the handler enum
  So that I can curate and upload Flickr content to Wikimedia Commons

  Scenario: Flickr handler enum maps to FlickrHandler
    Given the ImageHandler enum value is "flickr"
    When I get the handler for this type
    Then the FlickrHandler should be returned
