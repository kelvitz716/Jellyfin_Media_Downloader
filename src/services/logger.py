"""
Structured Logging - JSON-formatted logs with context.

This module provides structured logging functionality with
JSON output for easier parsing and analysis.

Usage:
    from src.services.logger import get_logger
    
    logger = get_logger(__name__)
    logger.info("download_complete", filename="movie.mkv", size=1024000, user_id=12345)
"""
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """
    Formatter that outputs JSON-structured log lines.
    
    Output format:
    {"timestamp": "...", "level": "INFO", "logger": "module", "message": "...", ...extra}
    """
    
    def format(self, record: logging.LogRecord) -> str:
        # Base log data
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add location info for errors
        if record.levelno >= logging.WARNING:
            log_data["location"] = f"{record.filename}:{record.lineno}"
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add any extra fields passed via extra={}
        for key, value in record.__dict__.items():
            if key not in (
                'name', 'msg', 'args', 'created', 'filename', 'funcName',
                'levelname', 'levelno', 'lineno', 'module', 'msecs',
                'pathname', 'process', 'processName', 'relativeCreated',
                'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
                'message', 'taskName'
            ):
                log_data[key] = value
        
        return json.dumps(log_data)


class ContextLogger(logging.Logger):
    """
    Logger that supports passing extra context directly in log calls.
    
    Example:
        logger.info("event_name", user_id=123, action="download")
    """
    
    def __init__(self, name: str, level: int = logging.NOTSET):
        super().__init__(name, level)
        self._context: Dict[str, Any] = {}
    
    def bind(self, **kwargs) -> 'ContextLogger':
        """Create a child logger with bound context."""
        child = ContextLogger(self.name)
        child._context = {**self._context, **kwargs}
        child.handlers = self.handlers
        child.level = self.level
        return child
    
    def _log_with_context(self, level: int, msg: str, args: tuple, 
                          exc_info=None, extra: Optional[Dict] = None, **kwargs):
        """Log with merged context and kwargs."""
        merged_extra = {**self._context, **(extra or {}), **kwargs}
        super()._log(level, msg, args, exc_info=exc_info, extra=merged_extra)
    
    def debug(self, msg: str, *args, **kwargs):
        if self.isEnabledFor(logging.DEBUG):
            self._log_with_context(logging.DEBUG, msg, args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        if self.isEnabledFor(logging.INFO):
            self._log_with_context(logging.INFO, msg, args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        if self.isEnabledFor(logging.WARNING):
            self._log_with_context(logging.WARNING, msg, args, **kwargs)
    
    def error(self, msg: str, *args, exc_info=True, **kwargs):
        if self.isEnabledFor(logging.ERROR):
            self._log_with_context(logging.ERROR, msg, args, exc_info=exc_info, **kwargs)
    
    def critical(self, msg: str, *args, exc_info=True, **kwargs):
        if self.isEnabledFor(logging.CRITICAL):
            self._log_with_context(logging.CRITICAL, msg, args, exc_info=exc_info, **kwargs)


# Register custom logger class
logging.setLoggerClass(ContextLogger)


def setup_structured_logging(
    level: int = logging.INFO,
    json_output: bool = True,
    stream=None
) -> None:
    """
    Configure root logger with structured output.
    
    Args:
        level: Logging level (default INFO)
        json_output: If True, use JSON format; otherwise use standard format
        stream: Output stream (default sys.stdout)
    """
    root = logging.getLogger()
    root.setLevel(level)
    
    # Remove existing handlers
    root.handlers.clear()
    
    # Create handler
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setLevel(level)
    
    if json_output:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        ))
    
    root.addHandler(handler)


def get_logger(name: str) -> ContextLogger:
    """
    Get a structured logger for the given module.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        ContextLogger with structured output support
    """
    return logging.getLogger(name)


# Pre-configured loggers for common use cases
def get_download_logger() -> ContextLogger:
    """Get logger for download operations."""
    return get_logger("download")


def get_organize_logger() -> ContextLogger:
    """Get logger for file organization."""
    return get_logger("organize")


def get_api_logger() -> ContextLogger:
    """Get logger for API operations."""
    return get_logger("api")
