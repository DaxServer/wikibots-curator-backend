"""Tests for Handler.recategorize_files and ws.py dispatch."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from curator.asyncapi.RecategorizeFilesResponseData import RecategorizeFilesResponseData


@pytest.mark.asyncio
async def test_recategorize_files_sends_response_with_count(
    handler_instance, mock_sender
):
    """recategorize_files replaces category in all members and sends count."""
    mock_mw = MagicMock()
    mock_mw.get_category_members.return_value = ["File:A.jpg", "File:B.jpg"]
    mock_mw.replace_category_in_page.return_value = True
    mock_sender.send_recategorize_files_response = AsyncMock()

    with (
        patch("curator.core.handler.MediaWikiClient", return_value=mock_mw),
        patch("curator.core.handler.mark_created"),
    ):
        await handler_instance.recategorize_files(
            "Lens focal length 79.0 mm", "Lens focal length 79 mm"
        )

    mock_mw.get_category_members.assert_called_once_with("Lens focal length 79.0 mm")
    assert mock_mw.replace_category_in_page.call_count == 2
    mock_sender.send_recategorize_files_response.assert_called_once_with(
        RecategorizeFilesResponseData(source="Lens focal length 79.0 mm", count=2)
    )


@pytest.mark.asyncio
async def test_recategorize_files_counts_only_replaced(handler_instance, mock_sender):
    """recategorize_files counts only files where replace returned True."""
    mock_mw = MagicMock()
    mock_mw.get_category_members.return_value = [
        "File:A.jpg",
        "File:B.jpg",
        "File:C.jpg",
    ]
    mock_mw.replace_category_in_page.side_effect = [True, False, True]
    mock_sender.send_recategorize_files_response = AsyncMock()

    with (
        patch("curator.core.handler.MediaWikiClient", return_value=mock_mw),
        patch("curator.core.handler.mark_created"),
    ):
        await handler_instance.recategorize_files("Source cat", "Target cat")

    mock_sender.send_recategorize_files_response.assert_called_once_with(
        RecategorizeFilesResponseData(source="Source cat", count=2)
    )


@pytest.mark.asyncio
async def test_recategorize_files_sends_zero_count_for_empty_category(
    handler_instance, mock_sender
):
    """recategorize_files sends count=0 when category has no members."""
    mock_mw = MagicMock()
    mock_mw.get_category_members.return_value = []
    mock_sender.send_recategorize_files_response = AsyncMock()

    with (
        patch("curator.core.handler.MediaWikiClient", return_value=mock_mw),
        patch("curator.core.handler.mark_created"),
    ):
        await handler_instance.recategorize_files("Empty cat", "Target cat")

    mock_mw.replace_category_in_page.assert_not_called()
    mock_sender.send_recategorize_files_response.assert_called_once_with(
        RecategorizeFilesResponseData(source="Empty cat", count=0)
    )


@pytest.mark.asyncio
async def test_recategorize_files_closes_client(handler_instance, mock_sender):
    """recategorize_files closes the MediaWikiClient after use."""
    mock_mw = MagicMock()
    mock_mw.get_category_members.return_value = []
    mock_sender.send_recategorize_files_response = AsyncMock()

    with patch("curator.core.handler.MediaWikiClient", return_value=mock_mw):
        await handler_instance.recategorize_files("Source", "Target")

    mock_mw._client.close.assert_called_once()


@pytest.mark.asyncio
async def test_recategorize_files_marks_source_as_created_in_cache(
    handler_instance, mock_sender
):
    """recategorize_files marks source category as created in DuckDB cache."""
    mock_mw = MagicMock()
    mock_mw.get_category_members.return_value = ["File:A.jpg"]
    mock_mw.replace_category_in_page.return_value = True
    mock_sender.send_recategorize_files_response = AsyncMock()

    with (
        patch("curator.core.handler.MediaWikiClient", return_value=mock_mw),
        patch("curator.core.handler.mark_created") as mock_mark_created,
    ):
        await handler_instance.recategorize_files(
            "Lens_focal_length_79,0_mm", "Lens focal length 79 mm"
        )

    mock_mark_created.assert_called_once_with("Lens_focal_length_79,0_mm")
