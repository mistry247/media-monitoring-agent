"""
Centralized error handling utilities and standardized error responses
"""
import logging
from typing import Dict, Any, Optional, Union
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from pydantic import ValidationError
import traceback

from utils.logging_config import get_logger, log_error

logger = get_logger(__name__)

class MediaMonitoringError(Exception):
    """Base exception class for Media Monitoring Agent"""
    
    def __init__(self, message: str, error_code: str = None, details: Dict[str, Any] = None):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)

class ArticleServiceError(MediaMonitoringError):
    """Exception for article service operations"""
    pass

class ScrapingServiceError(MediaMonitoringError):
    """Exception for web scraping operations"""
    pass

class AIServiceError(MediaMonitoringError):
    """Exception for AI service operations"""
    pass

class EmailServiceError(MediaMonitoringError):
    """Exception for email service operations"""
    pass

class ReportServiceError(MediaMonitoringError):
    """Exception for report service operations"""
    pass

class DatabaseError(MediaMonitoringError):
    """Exception for database operations"""
    pass

class ConfigurationError(MediaMonitoringError):
    """Exception for configuration issues"""
    pass

class ExternalServiceError(MediaMonitoringError):
    """Exception for external service failures"""
    pass

def create_error_response(
    error_code: str,
    message: str,
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a standardized error response
    
    Args:
        error_code: Unique error code
        message: Human-readable error message
        status_code: HTTP status code
        details: Additional error details
        request_id: Request ID for tracking
        
    Returns:
        Standardized error response dictionary
    """
    error_response = {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
            "status_code": status_code
        }
    }
    
    if details:
        error_response["error"]["details"] = details
    
    if request_id:
        error_response["error"]["request_id"] = request_id
    
    return error_response

def handle_database_error(error: Exception, operation: str = "database operation") -> HTTPException:
    """
    Handle database-related errors and convert to appropriate HTTP exceptions
    
    Args:
        error: Database exception
        operation: Description of the operation that failed
        
    Returns:
        HTTPException with appropriate status code and message
    """
    log_error(logger, error, operation=operation)
    
    if isinstance(error, IntegrityError):
        if "UNIQUE constraint failed" in str(error):
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=create_error_response(
                    "DUPLICATE_ENTRY",
                    "A record with this information already exists",
                    status.HTTP_409_CONFLICT
                )
            )
        else:
            return HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=create_error_response(
                    "DATA_INTEGRITY_ERROR",
                    "Data integrity constraint violation",
                    status.HTTP_400_BAD_REQUEST
                )
            )
    
    elif isinstance(error, SQLAlchemyError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(
                "DATABASE_ERROR",
                "A database error occurred",
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        )
    
    else:
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(
                "UNKNOWN_DATABASE_ERROR",
                "An unexpected database error occurred",
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        )

def handle_validation_error(error: Union[ValidationError, RequestValidationError]) -> HTTPException:
    """
    Handle validation errors and convert to appropriate HTTP exceptions
    
    Args:
        error: Validation exception
        
    Returns:
        HTTPException with validation error details
    """
    log_error(logger, error, operation="request validation")
    
    if isinstance(error, RequestValidationError):
        validation_errors = []
        for err in error.errors():
            validation_errors.append({
                "field": ".".join(str(x) for x in err["loc"]),
                "message": err["msg"],
                "type": err["type"]
            })
        
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=create_error_response(
                "VALIDATION_ERROR",
                "Request validation failed",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"validation_errors": validation_errors}
            )
        )
    
    else:
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_error_response(
                "INVALID_DATA",
                "Invalid data provided",
                status.HTTP_400_BAD_REQUEST,
                details={"error": str(error)}
            )
        )

def handle_service_error(error: MediaMonitoringError) -> HTTPException:
    """
    Handle service-specific errors and convert to appropriate HTTP exceptions
    
    Args:
        error: Service exception
        
    Returns:
        HTTPException with appropriate status code and message
    """
    log_error(logger, error, operation="service operation")
    
    # Map service errors to HTTP status codes
    status_mapping = {
        ArticleServiceError: status.HTTP_400_BAD_REQUEST,
        ScrapingServiceError: status.HTTP_502_BAD_GATEWAY,
        AIServiceError: status.HTTP_502_BAD_GATEWAY,
        EmailServiceError: status.HTTP_502_BAD_GATEWAY,
        ReportServiceError: status.HTTP_500_INTERNAL_SERVER_ERROR,
        DatabaseError: status.HTTP_500_INTERNAL_SERVER_ERROR,
        ConfigurationError: status.HTTP_500_INTERNAL_SERVER_ERROR,
        ExternalServiceError: status.HTTP_502_BAD_GATEWAY
    }
    
    http_status = status_mapping.get(type(error), status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return HTTPException(
        status_code=http_status,
        detail=create_error_response(
            error.error_code,
            error.message,
            http_status,
            details=error.details
        )
    )

def handle_generic_error(error: Exception, operation: str = "operation") -> HTTPException:
    """
    Handle generic exceptions and convert to HTTP exceptions
    
    Args:
        error: Generic exception
        operation: Description of the operation that failed
        
    Returns:
        HTTPException with generic error message
    """
    log_error(logger, error, operation=operation)
    
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=create_error_response(
            "INTERNAL_SERVER_ERROR",
            "An unexpected error occurred",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"operation": operation}
        )
    )

async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler for unhandled exceptions
    
    Args:
        request: FastAPI request object
        exc: Unhandled exception
        
    Returns:
        JSONResponse with error details
    """
    request_id = getattr(request.state, 'request_id', None)
    
    # Log the unhandled exception
    logger.error(
        f"Unhandled exception in {request.method} {request.url.path}",
        exc_info=True,
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query_params": str(request.query_params)
        }
    )
    
    # Create error response
    error_response = create_error_response(
        "UNHANDLED_EXCEPTION",
        "An unexpected error occurred while processing your request",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handler for request validation exceptions
    
    Args:
        request: FastAPI request object
        exc: Validation exception
        
    Returns:
        JSONResponse with validation error details
    """
    request_id = getattr(request.state, 'request_id', None)
    
    validation_errors = []
    for err in exc.errors():
        validation_errors.append({
            "field": ".".join(str(x) for x in err["loc"]),
            "message": err["msg"],
            "type": err["type"],
            "input": err.get("input")
        })
    
    logger.warning(
        f"Validation error in {request.method} {request.url.path}",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "validation_errors": validation_errors
        }
    )
    
    error_response = create_error_response(
        "VALIDATION_ERROR",
        "Request validation failed",
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"validation_errors": validation_errors},
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response
    )

def safe_execute(func, *args, error_handler=None, operation: str = None, **kwargs):
    """
    Safely execute a function with error handling
    
    Args:
        func: Function to execute
        *args: Function arguments
        error_handler: Custom error handler function
        operation: Operation description for logging
        **kwargs: Function keyword arguments
        
    Returns:
        Function result or raises appropriate HTTPException
    """
    try:
        return func(*args, **kwargs)
    except MediaMonitoringError as e:
        if error_handler:
            return error_handler(e)
        raise handle_service_error(e)
    except (SQLAlchemyError, IntegrityError) as e:
        if error_handler:
            return error_handler(e)
        raise handle_database_error(e, operation or "database operation")
    except (ValidationError, RequestValidationError) as e:
        if error_handler:
            return error_handler(e)
        raise handle_validation_error(e)
    except Exception as e:
        if error_handler:
            return error_handler(e)
        raise handle_generic_error(e, operation or "operation")
