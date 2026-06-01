import sys
from pathlib import Path
from loguru import logger

def setup_logging(log_dir: str | None = None):

    # Default log directory
    if log_dir is None:
        log_dir = str(Path.home() / ".jarvis" / "logs")

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Console output (errors and above)
    logger.add(
        sys.stderr,
        level="DEBUG",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # File output - all messages
    logger.add(
        str(log_path / "jarvis.log"),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention=7,
    )

    # File output - errors only
    logger.add(
        str(log_path / "errors.log"),
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="5 MB",
        retention=7,
    )

    logger.info(f"Logging initialized to: {log_path}")
    logger.info(f"System: {sys.platform}")
    logger.info(f"Python: {sys.version}")

    return log_path

def get_log_path():
    """Get the log directory path."""
    return Path.home() / ".jarvis" / "logs"
