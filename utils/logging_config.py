"""
Centralized logging configuration for the Media Monitoring Agent
"""
import logging
import logging.handlers
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import json

from config import settings

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record):
        """Format log record as JSON"""
        log_entry = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'user_id'):
            log_entry["user_id"] = record.user_id
        if hasattr(record, 'request_id'):
            log_entry["request_id"] = record.request_id
        if hasattr(record, 'operation'):
            log_entry["operation"] = record.operation
        if hasattr(record, 'duration'):
            log_entry["duration_ms"] = record.duration
        
        return json.dumps(log_entry)

class ColoredFormatter(logging.Formatter):
    """Colored formatter for console output"""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }
    
    def format(self, record):
        """Format log record with colors"""
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        
        # Format the message
        formatted_message = f"{color}[{timestamp}] {record.levelname:8} {record.name:20} | {record.getMessage()}{reset}"
        
        # Add exception info if present
        if record.exc_info:
            formatted_message += f"\n{self.formatException(record.exc_info)}"
        
        return formatted_message

def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_json_logging: bool = False,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> None:
    """
    Setup centralized logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        enable_json_logging: Whether to use JSON formatting for file logs
        max_file_size: Maximum size of log file before rotation
        backup_count: Number of backup files to keep
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create logs directory if it doesn't exist
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(ColoredFormatter())
    root_logger.addHandler(console_handler)
    
    # File handler with rotation if log file specified
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        
        if enable_json_logging:
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
            )
        
        root_logger.addHandler(file_handler)
    
    # Set specific logger levels
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured - Level: {log_level}, File: {log_file or 'None'}, JSON: {enable_json_logging}")

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)

def log_operation(logger: logging.Logger, operation: str, duration_ms: Optional[float] = None, **kwargs):
    """
    Log an operation with structured data
    
    Args:
        logger: Logger instance
        operation: Operation name
        duration_ms: Operation duration in milliseconds
        **kwargs: Additional fields to log
    """
    extra = {"operation": operation}
    if duration_ms is not None:
        extra["duration"] = duration_ms
    extra.update(kwargs)
    
    message = f"Operation: {operation}"
    if duration_ms is not None:
        message += f" (took {duration_ms:.2f}ms)"
    
    logger.info(message, extra=extra)

def log_error(logger: logging.Logger, error: Exception, operation: str = None, **kwargs):
    """
    Log an error with structured data
    
    Args:
        logger: Logger instance
        error: Exception that occurred
        operation: Operation that failed (optional)
        **kwargs: Additional fields to log
    """
    extra = {"error_type": type(error).__name__}
    if operation:
        extra["operation"] = operation
    extra.update(kwargs)
    
    message = f"Error: {str(error)}"
    if operation:
        message = f"Operation '{operation}' failed: {str(error)}"
    
    logger.error(message, exc_info=True, extra=extra)

# Initialize logging on module import
def init_logging():
    """Initialize logging with configuration from settings"""
    try:
        log_level = getattr(settings, 'LOG_LEVEL', 'INFO')
        log_file = getattr(settings, 'LOG_FILE', None)
        enable_json = getattr(settings, 'ENABLE_JSON_LOGGING', False)
        
        setup_logging(
            log_level=log_level,
            log_file=log_file,
            enable_json_logging=enable_json
        )
    except Exception as e:
        # Fallback to basic logging if configuration fails
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to initialize logging configuration: {e}")

# Auto-initialize logging
init_logging()
