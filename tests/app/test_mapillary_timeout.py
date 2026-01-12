from unittest.mock import MagicMock, patch

from curator.handlers.mapillary_handler import (
    _fetch_images_by_ids_api,
    _fetch_sequence_data,
    _fetch_single_image,
    _get_sequence_ids,
)


def test_fetch_sequence_data_timeout():
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        _fetch_sequence_data("seq123")

        mock_get.assert_called_once()


def test_get_sequence_ids_timeout():
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        _get_sequence_ids("seq123")

        mock_get.assert_called_once()


def test_fetch_images_by_ids_api_timeout():
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        _fetch_images_by_ids_api(["img1"])

        mock_get.assert_called_once()


def test_fetch_single_image_timeout():
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        _fetch_single_image("img1")

        mock_get.assert_called_once()
