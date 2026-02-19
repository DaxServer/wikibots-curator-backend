import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlmodel import Session

from curator.app.dal import (
    count_batches_optimized,
    get_batch_ids_with_recent_changes,
    get_batches_minimal,
    get_batches_optimized,
    get_latest_update_time,
)
from curator.app.db import get_session
from curator.asyncapi import BatchesListData
from curator.protocol import AsyncAPIWebSocket

logger = logging.getLogger(__name__)


class OptimizedBatchStreamer:
    """Optimized batch streaming with intelligent updates and reduced payload size."""

    def __init__(self, socket: AsyncAPIWebSocket, username: str):
        self.socket = socket
        self.username = username
        self.last_update_time: Optional[datetime] = None
        self.is_running = False
        self.page = 1
        self.limit = 100

    async def start_streaming(
        self,
        userid: Optional[str] = None,
        filter_text: Optional[str] = None,
        page: int = 1,
        limit: int = 100,
        update_check_interval: int = 2,  # Check for updates every 2 seconds
    ):
        """Start optimized batch streaming with intelligent updates."""
        self.is_running = True
        self.page = page
        self.limit = limit
        logger.info(
            f"[ws] [resp] Starting optimized batch streaming for {self.username} (page: {page}, limit: {limit})"
        )

        try:
            # Initial full sync
            with get_session() as session:
                await self._send_full_sync(session, userid, filter_text)
                self.last_update_time = get_latest_update_time(
                    session, userid, filter_text
                )

            # If not the first page, we don't stream further updates
            if self.page > 1:
                logger.info(
                    f"[ws] [resp] Pagination detected (page {self.page}), not streaming updates for {self.username}"
                )
                return

            while self.is_running:
                await asyncio.sleep(update_check_interval)

                with get_session() as session:
                    current_latest = get_latest_update_time(
                        session, userid, filter_text
                    )

                    if current_latest and (
                        self.last_update_time is None
                        or current_latest > self.last_update_time
                    ):
                        logger.info(
                            f"[ws] [resp] Updates detected for {self.username}, sending incremental update"
                        )
                        # Use self.last_update_time if available, otherwise use a very old date
                        # to ensure all changes are captured.
                        check_time = self.last_update_time or datetime.min
                        await self._send_incremental_updates(
                            session, userid, filter_text, check_time
                        )
                        self.last_update_time = current_latest

        except asyncio.CancelledError:
            logger.info(
                f"[ws] [resp] Stopping optimized batch streaming for {self.username}"
            )
        except Exception as e:
            logger.error(f"[ws] [resp] Error in optimized batch streaming: {e}")
            raise

    async def stop_streaming(self):
        """Stop the streaming process."""
        if self.is_running:
            self.is_running = False
            logger.info(
                f"[ws] [resp] Stopped optimized batch streaming for {self.username}"
            )

    async def _send_full_sync(
        self, session: Session, userid: Optional[str], filter_text: Optional[str]
    ):
        """Send a full sync of all batches."""
        # Calculate offset based on page and limit
        offset = (self.page - 1) * self.limit

        # Use optimized single-query approach
        batch_items = get_batches_optimized(
            session, userid, offset, self.limit, filter_text
        )
        total_count = count_batches_optimized(session, userid, filter_text)
        current_data = BatchesListData(items=batch_items, total=total_count)

        await self.socket.send_batches_list(current_data, partial=False)

        logger.info(
            f"[ws] [resp] Full sync completed for {self.username}: sent {len(batch_items)} batches (total: {total_count})"
        )

    async def _send_incremental_updates(
        self,
        session: Session,
        userid: Optional[str],
        filter_text: Optional[str],
        last_update_time: datetime,
    ):
        """Send only batches that have changed recently."""
        # Get batch IDs that had changes since last_update_time
        changed_batch_ids = get_batch_ids_with_recent_changes(
            session, last_update_time, userid, filter_text
        )

        if not changed_batch_ids:
            return

        # Get minimal data for only the changed batches
        changed_batches = get_batches_minimal(session, changed_batch_ids)

        if not changed_batches:
            return

        total_count = count_batches_optimized(session, userid, filter_text)

        # Send only the changed batches as an update with the current total
        update_data = BatchesListData(items=changed_batches, total=total_count)

        # Send as a partial update
        await self.socket.send_batches_list(update_data, partial=True)

        logger.info(
            f"[ws] [resp] Sent incremental update for {self.username}: {len(changed_batches)} batches (total: {total_count})"
        )
