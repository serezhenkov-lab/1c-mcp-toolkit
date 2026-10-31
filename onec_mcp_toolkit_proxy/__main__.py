"""Запуск HTTP (по умолчанию) или stdio с одним файловым каналом."""
import argparse
import asyncio
import logging
import os


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport', choices=('http', 'stdio'), default='http')
    parser.add_argument('--file-root', help='Local exchange root (FILE_BRIDGE_ROOT)')
    parser.add_argument('--channel', help='Exactly one file channel for stdio')
    args = parser.parse_args()
    if args.transport == 'stdio':
        from .file_transport import configured_channels
        root = args.file_root or os.getenv('FILE_BRIDGE_ROOT')
        raw_channel = args.channel if args.channel is not None else os.getenv('FILE_BRIDGE_CHANNELS', '')
        if not root:
            parser.error('stdio requires --file-root or FILE_BRIDGE_ROOT')
        try:
            channels = configured_channels({'FILE_BRIDGE_ROOT': root,
                                            'FILE_BRIDGE_CHANNELS': raw_channel})
        except ValueError as exc:
            parser.error(str(exc))
        if len(channels) != 1:
            parser.error('stdio requires exactly one file channel')
        from .config import settings
        logging.basicConfig(level=settings.log_level.upper())  # Только stderr.
        from .stdio import run_stdio
        try:
            asyncio.run(run_stdio(root, channels[0]))
        except KeyboardInterrupt:
            pass
        except Exception as exc:
            logging.getLogger(__name__).error('%s', exc)
            raise SystemExit(1) from exc
    else:
        if args.file_root is not None or args.channel is not None:
            parser.error('--file-root/--channel are stdio options; HTTP uses FILE_BRIDGE_ROOT/FILE_BRIDGE_CHANNELS')
        import uvicorn
        from .config import settings
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
