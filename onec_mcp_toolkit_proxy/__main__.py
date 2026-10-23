"""Точка входа для запуска модуля: python -m onec_mcp_toolkit_proxy"""

import os
import uvicorn
from .config import settings


def main():
    """Запуск сервера."""
    uvicorn.run(
        "onec_mcp_toolkit_proxy.server:app",
        host="127.0.0.1" if os.getenv("FILE_BRIDGE_ROOT") else "0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.debug,
        http="h11",  # Явно указываем h11
        timeout_keep_alive=5,  # Короткий keep-alive
    )


if __name__ == "__main__":
    main()
