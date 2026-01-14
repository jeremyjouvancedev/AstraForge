import os
import logging
from typing import Any, Optional
from langgraph.checkpoint.memory import MemorySaver
from astraforge.infrastructure.ai.deepagent_runtime import _get_checkpointer_dsn

logger = logging.getLogger(__name__)

async def get_async_checkpointer() -> Any:
    """Build an AsyncPostgresSaver for Astra Control."""
    dsn = _get_checkpointer_dsn()
    if not dsn:
        return MemorySaver()
    
    try:
        import psycopg
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        
        # Use connection string from DSN
        conn = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
        saver = AsyncPostgresSaver(conn)
        # setup() is async for AsyncPostgresSaver
        await saver.setup()
        return saver
    except Exception as e:
        logger.warning(f"Failed to setup AsyncPostgresSaver, falling back to MemorySaver: {e}")
        return MemorySaver()
