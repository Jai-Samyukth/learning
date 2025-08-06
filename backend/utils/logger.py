import logging
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

class StructuredLogger:
    """Production-ready structured logging for the backend"""
    
    def __init__(self, name: str, log_level: str = None):
        self.name = name
        self.log_level = log_level or os.getenv('LOG_LEVEL', 'INFO').upper()
        
        # Create logs directory if it doesn't exist
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # Configure logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, self.log_level))
        
        # Prevent duplicate handlers
        if self.logger.handlers:
            return
            
        # Console handler with structured format
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        
        # File handler for persistent logs
        file_handler = logging.FileHandler(
            f'logs/{name}_{datetime.now().strftime("%Y%m%d")}.log'
        )
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
    def _format_message(self, message: str, **kwargs) -> str:
        """Format message with optional structured data"""
        if kwargs:
            # Simple key=value format instead of JSON
            data_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
            return f"{message} | {data_str}"
        return message
    
    def debug(self, message: str, **kwargs):
        """Debug level logging"""
        self.logger.debug(self._format_message(message, **kwargs))
    
    def info(self, message: str, **kwargs):
        """Info level logging"""
        self.logger.info(self._format_message(message, **kwargs))
    
    def warning(self, message: str, **kwargs):
        """Warning level logging"""
        self.logger.warning(self._format_message(message, **kwargs))
    
    def error(self, message: str, exc_info: bool = True, **kwargs):
        """Error level logging"""
        self.logger.error(self._format_message(message, **kwargs), exc_info=exc_info)
    
    def critical(self, message: str, exc_info: bool = True, **kwargs):
        """Critical level logging"""
        self.logger.critical(self._format_message(message, **kwargs), exc_info=exc_info)

# Global logger instances
pdf_logger = StructuredLogger("pdf_service")
cache_logger = StructuredLogger("cache")
chat_logger = StructuredLogger("chat_service")
ip_logger = StructuredLogger("ip_detector")

# Convenience functions
def get_logger(name: str) -> StructuredLogger:
    """Get a logger instance for a specific module"""
    return StructuredLogger(name)
