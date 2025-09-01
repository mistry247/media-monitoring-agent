"""
API endpoints for report generation and management
"""
import time
import asyncio
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from models.report import MediaReportRequest, HansardReportRequest, ReportResponse, ReportStatus
from services.report_service import get_report_service, ReportGenerationError
from utils.logging_config import get_logger, log_operation, log_error
from utils.error_handlers import (
    handle_service_error,
    handle_generic_error,
    safe_execute,
    create_error_response,
    ReportServiceError
)
from utils.security import InvalidInputError

logger = get_logger(__name__)

# Create router for report endpoints
router = APIRouter(prefix="/api/reports", tags=["reports"])

# In-memory storage for report status tracking (in production, use Redis or database)
report_status_store: Dict[str, Dict[str, Any]] = {}

def update_report_status(report_id: str, status: str, message: str, progress: int = None):
    """Update report status in the status store"""
    report_status_store[report_id] = {
        "report_id": report_id,
        "status": status,
        "message": message,
        "progress": progress,
        "updated_at": datetime.now()
    }

async def generate_media_report_async(report_id: str, pasted_content: str, recipient_email: str, db: Session):
    """
    Async function to generate media report in background
    
    Args:
        report_id: Unique identifier for the report
        pasted_content: Pasted content from the request
        recipient_email: Email address to send the report to
        db: Database session
    """
    start_time = time.time()
    
    try:
        # Update status to processing
        update_report_status(report_id, "processing", "Starting media report generation", 10)
        
        logger.info(
            f"Starting media report generation: {report_id}",
            extra={
                "report_id": report_id,
                "operation": "generate_media_report",
                "content_length": len(pasted_content) if pasted_content else 0
            }
        )
        
        # Get report service
        report_service = get_report_service(db)
        
        # Update progress
        update_report_status(report_id, "processing", "Scraping articles and processing content", 50)
        
        # Generate the report
        success, message, _ = report_service.generate_media_report(pasted_content, recipient_email)
        
        duration_ms = (time.time() - start_time) * 1000
        
        if success:
            update_report_status(report_id, "completed", message, 100)
            log_operation(
                logger,
                "generate_media_report",
                duration_ms,
                report_id=report_id,
                status="completed"
            )
        else:
            update_report_status(report_id, "failed", message, 0)
            log_error(
                logger,
                ReportGenerationError(message),
                operation="generate_media_report",
                report_id=report_id,
                duration_ms=duration_ms
            )
            
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        error_message = f"Unexpected error during media report generation: {str(e)}"
        update_report_status(report_id, "failed", error_message, 0)
        log_error(
            logger,
            e,
            operation="generate_media_report",
            report_id=report_id,
            duration_ms=duration_ms
        )

async def generate_hansard_report_async(report_id: str, recipient_email: str, db: Session):
    """
    Async function to generate Hansard report in background
    
    Args:
        report_id: Unique identifier for the report
        recipient_email: Email address to send the report to
        db: Database session
    """
    start_time = time.time()
    
    try:
        # Update status to processing
        update_report_status(report_id, "processing", "Starting Hansard report generation", 10)
        
        logger.info(
            f"Starting Hansard report generation: {report_id}",
            extra={
                "report_id": report_id,
                "operation": "generate_hansard_report"
            }
        )
        
        # Get report service
        report_service = get_report_service(db)
        
        # Update progress
        update_report_status(report_id, "processing", "Processing articles and generating questions", 50)
        
        # Generate the report
        success, message, _ = report_service.generate_hansard_report(recipient_email)
        
        duration_ms = (time.time() - start_time) * 1000
        
        if success:
            update_report_status(report_id, "completed", message, 100)
            log_operation(
                logger,
                "generate_hansard_report",
                duration_ms,
                report_id=report_id,
                status="completed"
            )
        else:
            update_report_status(report_id, "failed", message, 0)
            log_error(
                logger,
                ReportGenerationError(message),
                operation="generate_hansard_report",
                report_id=report_id,
                duration_ms=duration_ms
            )
            
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        error_message = f"Unexpected error during Hansard report generation: {str(e)}"
        update_report_status(report_id, "failed", error_message, 0)
        log_error(
            logger,
            e,
            operation="generate_hansard_report",
            report_id=report_id,
            duration_ms=duration_ms
        )

@router.post("/media", response_model=ReportResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_media_report(
    report_request: MediaReportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Generate a comprehensive media report from pending articles and pasted content
    
    Args:
        report_request: MediaReportRequest with pasted content
        request: FastAPI request object for tracking
        background_tasks: FastAPI background tasks for async processing
        db: Database session dependency
        
    Returns:
        ReportResponse with success status, message, and report ID
        
    Raises:
        HTTPException: For validation errors or service unavailability
    """
    start_time = time.time()
    request_id = getattr(request.state, 'request_id', None)
    
    def start_media_report_operation():
        try:
            # Generate unique report ID
            report_id = f"media_report_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            
            # Initialize report status
            update_report_status(report_id, "pending", "Media report queued for processing", 0)
            
            # Add background task for report generation
            background_tasks.add_task(
                generate_media_report_async,
                report_id,
                report_request.pasted_content,
                report_request.recipient_email,
                db
            )
            
            log_operation(
                logger,
                "start_media_report",
                (time.time() - start_time) * 1000,
                request_id=request_id,
                report_id=report_id,
                content_length=len(report_request.pasted_content) if report_request.pasted_content else 0
            )
            
            return ReportResponse(
                success=True,
                message="Media report generation started. Use the report ID to check status.",
                report_id=report_id
            )
        
        except InvalidInputError as e:
            logger.warning(
                f"Invalid input in media report request: {e}",
                extra={
                    "request_id": request_id,
                    "operation": "start_media_report",
                    "error": str(e)
                }
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=create_error_response(
                    "INVALID_INPUT",
                    str(e),
                    status.HTTP_400_BAD_REQUEST,
                    request_id=request_id
                )
            )
    
    return safe_execute(
        start_media_report_operation,
        operation="start_media_report"
    )

@router.post("/hansard", response_model=ReportResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_hansard_report(
    report_request: HansardReportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Generate a Hansard report with parliamentary questions based on current media content
    
    Args:
        report_request: HansardReportRequest (currently empty)
        request: FastAPI request object for tracking
        background_tasks: FastAPI background tasks for async processing
        db: Database session dependency
        
    Returns:
        ReportResponse with success status, message, and report ID
        
    Raises:
        HTTPException: For validation errors or service unavailability
    """
    start_time = time.time()
    request_id = getattr(request.state, 'request_id', None)
    
    def start_hansard_report_operation():
        # Generate unique report ID
        report_id = f"hansard_report_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        # Initialize report status
        update_report_status(report_id, "pending", "Hansard report queued for processing", 0)
        
        # Add background task for report generation
        background_tasks.add_task(
            generate_hansard_report_async,
            report_id,
            report_request.recipient_email,
            db
        )
        
        log_operation(
            logger,
            "start_hansard_report",
            (time.time() - start_time) * 1000,
            request_id=request_id,
            report_id=report_id
        )
        
        return ReportResponse(
            success=True,
            message="Hansard report generation started. Use the report ID to check status.",
            report_id=report_id
        )
    
    return safe_execute(
        start_hansard_report_operation,
        operation="start_hansard_report"
    )

@router.get("/status/{report_id}", response_model=ReportStatus)
async def get_report_status(report_id: str, request: Request):
    """
    Get the current status of a report generation process
    
    Args:
        report_id: ID of the report to check status for
        request: FastAPI request object for tracking
        
    Returns:
        ReportStatus with current status, message, and progress
        
    Raises:
        HTTPException: If report ID not found
    """
    start_time = time.time()
    request_id = getattr(request.state, 'request_id', None)
    
    def get_status_operation():
        if report_id not in report_status_store:
            logger.warning(
                f"Report status requested for unknown report ID: {report_id}",
                extra={
                    "request_id": request_id,
                    "report_id": report_id,
                    "operation": "get_report_status"
                }
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=create_error_response(
                    "REPORT_NOT_FOUND",
                    f"Report with ID {report_id} not found",
                    status.HTTP_404_NOT_FOUND,
                    request_id=request_id
                )
            )
        
        status_info = report_status_store[report_id]
        
        log_operation(
            logger,
            "get_report_status",
            (time.time() - start_time) * 1000,
            request_id=request_id,
            report_id=report_id,
            report_status=status_info["status"]
        )
        
        return ReportStatus(
            report_id=status_info["report_id"],
            status=status_info["status"],
            message=status_info["message"],
            progress=status_info.get("progress")
        )
    
    return safe_execute(
        get_status_operation,
        operation="get_report_status"
    )

@router.get("/hansard/recent")
async def get_recent_hansard_questions(
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Retrieve recent Hansard questions from the database
    
    Args:
        limit: Maximum number of questions to retrieve (default: 10)
        db: Database session dependency
        
    Returns:
        List of recent Hansard questions
        
    Raises:
        HTTPException: For database errors
    """
    try:
        # Validate limit parameter
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limit must be between 1 and 100"
            )
        
        # Get report service
        report_service = get_report_service(db)
        
        # Retrieve recent questions
        questions = report_service.get_recent_hansard_questions(limit)
        
        logger.info(f"Retrieved {len(questions)} recent Hansard questions")
        
        return {
            "questions": questions,
            "count": len(questions)
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error retrieving recent Hansard questions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving Hansard questions"
        )

@router.delete("/status/{report_id}")
async def clear_report_status(report_id: str):
    """
    Clear the status information for a completed or failed report
    
    Args:
        report_id: ID of the report to clear status for
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If report ID not found
    """
    try:
        if report_id not in report_status_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {report_id} not found"
            )
        
        # Only allow clearing completed or failed reports
        status_info = report_status_store[report_id]
        if status_info["status"] not in ["completed", "failed"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only clear status for completed or failed reports"
            )
        
        # Remove from status store
        del report_status_store[report_id]
        
        logger.info(f"Cleared status for report {report_id}")
        
        return {"message": f"Status cleared for report {report_id}"}
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error clearing report status for {report_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while clearing report status"
        )
