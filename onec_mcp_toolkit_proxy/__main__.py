"""Запуск HTTP-прокси MCP Toolkit."""
import os

import uvicorn

from .config import settings


def main():
    uvicorn.run(
        "onec_mcp_toolkit_proxy.server:app",
        host="127.0.0.1" if os.getenv("FILE_BRIDGE_ROOT") else "0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.debug,
        http="h11",
        timeout_keep_alive=5,
    )


if __name__ == '__main__':
    main()
