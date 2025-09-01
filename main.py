"""
Media Monitoring Agent - FastAPI Application Entry Point
"""
import uuid
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
import os

from api.articles import router as articles_router
from api.reports import router as reports_router
from api.manual_articles import router as manual_articles_router
from config import settings
from database import init_db
from utils.logging_config import get_logger, log_operation
from utils.error_handlers import (
    global_exception_handler,
    validation_exception_handler,
    create_error_response
)
from utils.health_check import get_health_status

# Initialize logging
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Media Monitoring Agent...")
    
    try:
        # Initialize database
        init_db()
        logger.info("Database initialized successfully")
        
        # Log configuration (masked)
        config_info = settings.get_masked_config()
        logger.info(f"Application configuration loaded: {config_info}")
        
        # Perform startup health checks for external service connectivity
        if settings.LOCAL_MODE:
            logger.info("Skipping health checks (LOCAL_MODE enabled)")
            logger.info("Media Monitoring Agent started in LOCAL_MODE - using mock services")
        else:
            logger.info("Performing startup health checks...")
            startup_health = await get_health_status()
            
            # Log health check results
            healthy_services = []
            degraded_services = []
            unhealthy_services = []
            
            for service_name, check_result in startup_health["checks"].items():
                if check_result["status"] == "healthy":
                    healthy_services.append(service_name)
                elif check_result["status"] == "degraded":
                    degraded_services.append(service_name)
                else:
                    unhealthy_services.append(service_name)
            
            if healthy_services:
                logger.info(f"Healthy services: {', '.join(healthy_services)}")
            
            if degraded_services:
                logger.warning(f"Degraded services (may have limited functionality): {', '.join(degraded_services)}")
            
            if unhealthy_services:
                logger.error(f"Unhealthy services (functionality unavailable): {', '.join(unhealthy_services)}")
            
            # Log overall startup status
            overall_status = startup_health["status"]
            if overall_status == "healthy":
                logger.info("Media Monitoring Agent started successfully - all systems healthy")
            elif overall_status == "degraded":
                logger.warning("Media Monitoring Agent started with degraded functionality - some services may be limited")
            else:
                logger.error("Media Monitoring Agent started with unhealthy services - some functionality may be unavailable")
        
        # Verify static files exist
        static_files = ["static/index.html", "static/app.js", "static/styles.css"]
        missing_files = []
        for file_path in static_files:
            if not os.path.exists(file_path):
                missing_files.append(file_path)
        
        if missing_files:
            logger.error(f"Missing static files: {', '.join(missing_files)}")
            raise FileNotFoundError(f"Required static files not found: {', '.join(missing_files)}")
        else:
            logger.info("All required static files are present")
        
        logger.info(f"Application ready to serve requests on {settings.HOST}:{settings.PORT}")
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Media Monitoring Agent...")
    logger.info("Application shutdown complete")

# Create FastAPI application instance
app = FastAPI(
    title="Media Monitoring Agent",
    description="A collaborative application for collecting, processing, and reporting on media articles",
    version="1.0.0",
    lifespan=lifespan
)

# Add security and request tracking middleware
@app.middleware("http")
async def security_and_tracking_middleware(request: Request, call_next):
    """Add security headers, request tracking, and rate limiting"""
    from utils.security import SecurityHeaders, check_rate_limit, RateLimitExceeded
    
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    start_time = time.time()
    
    # Log request
    logger.info(
        f"Request started: {request.method} {request.url.path}",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query_params": str(request.query_params),
            "client_ip": request.client.host if request.client else None
        }
    )
    
    try:
        # Apply rate limiting to API endpoints
        if request.url.path.startswith("/api/"):
            try:
                # Different limits for different endpoints
                if request.url.path.startswith("/api/articles/submit"):
                    # Higher limit for testing
                    rate_limit_info = check_rate_limit(request, max_requests=1000, window_seconds=3600)
                elif request.url.path.startswith("/api/reports/"):
                    # Higher limit for testing
                    rate_limit_info = check_rate_limit(request, max_requests=100, window_seconds=3600)
                else:
                    # Default rate limit for other API endpoints
                    rate_limit_info = check_rate_limit(request)
                
                # Store rate limit info for response headers
                request.state.rate_limit_info = rate_limit_info
                
            except RateLimitExceeded as e:
                logger.warning(
                    f"Rate limit exceeded: {request.method} {request.url.path}",
                    extra={
                        "request_id": request_id,
                        "client_ip": request.client.host if request.client else None,
                        "path": request.url.path
                    }
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "RATE_LIMIT_EXCEEDED",
                        "message": str(e),
                        "request_id": request_id
                    },
                    headers={
                        "X-Request-ID": request_id,
                        "Retry-After": "3600"
                    }
                )
        
        response = await call_next(request)
        
        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000
        
        # Add security headers
        security_headers = SecurityHeaders.get_security_headers()
        for header_name, header_value in security_headers.items():
            response.headers[header_name] = header_value
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        # Add rate limit headers if available
        if hasattr(request.state, 'rate_limit_info'):
            rate_info = request.state.rate_limit_info
            response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(rate_info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(rate_info["reset"])
        
        # Log response
        logger.info(
            f"Request completed: {request.method} {request.url.path} - {response.status_code}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return response
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        
        logger.error(
            f"Request failed: {request.method} {request.url.path}",
            exc_info=True,
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round(duration_ms, 2),
                "error": str(e)
            }
        )
        
        raise

# Add CORS middleware for frontend API access
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add global exception handlers - TEMPORARILY DISABLED FOR DEBUGGING
# app.add_exception_handler(Exception, global_exception_handler)
# app.add_exception_handler(RequestValidationError, validation_exception_handler)

# Include API routers
app.include_router(articles_router)
app.include_router(reports_router)
app.include_router(manual_articles_router)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_root():
    """Serve the main HTML page"""
    try:
        # Check if the file exists before serving
        if not os.path.exists("static/index.html"):
            logger.error("index.html not found in static directory")
            return JSONResponse(
                status_code=404,
                content=create_error_response(
                    "FILE_NOT_FOUND",
                    "Main page not found. Please ensure static files are properly deployed.",
                    404
                )
            )
        
        return FileResponse(
            "static/index.html",
            media_type="text/html",
            headers={"Cache-Control": "no-cache"}
        )
    except Exception as e:
        logger.error(f"Failed to serve index.html: {e}")
        return JSONResponse(
            status_code=500,
            content=create_error_response(
                "INTERNAL_SERVER_ERROR",
                "Unable to serve the main page",
                500
            )
        )

@app.get("/api/csrf-token")
async def get_csrf_token():
    """Get CSRF token for form submissions"""
    from utils.security import CSRFProtection
    
    token = CSRFProtection.generate_token()
    
    # In a production app, you'd store this in a session or database
    # For simplicity, we'll use a simple approach with headers
    response = JSONResponse(content={"csrf_token": token})
    response.set_cookie(
        key="csrf_token",
        value=token,
        httponly=True,
        secure=True,  # Only send over HTTPS
        samesite="strict",
        max_age=3600  # 1 hour
    )
    
    return response

@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint for monitoring"""
    try:
        start_time = time.time()
        
        # Get comprehensive health status
        health_status = await get_health_status()
        
        # Determine HTTP status code based on health
        if health_status["status"] == "healthy":
            status_code = 200
        elif health_status["status"] == "degraded":
            status_code = 200  # Still operational but with warnings
        else:
            status_code = 503  # Service unavailable
        
        # Log health check
        duration_ms = (time.time() - start_time) * 1000
        log_operation(
            logger,
            "health_check",
            duration_ms,
            overall_status=health_status["status"],
            checks_count=health_status["summary"]["total_checks"]
        )
        
        return JSONResponse(
            status_code=status_code,
            content=health_status
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "message": "Health check system failure",
                "error": str(e),
                "timestamp": time.time()
            }
        )

@app.get("/health/simple")
async def simple_health_check():
    """Simple health check endpoint for basic monitoring"""
    return {
        "status": "healthy",
        "message": "Media Monitoring Agent is running",
        "timestamp": time.time()
    }

@app.get("/version")
async def get_version():
    """Get application version information"""
    return {
        "name": "Media Monitoring Agent",
        "version": "1.0.0",
        "description": "A collaborative application for collecting, processing, and reporting on media articles"
    }

@app.get("/static-files/status")
async def static_files_status():
    """Check status of required static files"""
    try:
        required_files = {
            "index.html": "static/index.html",
            "app.js": "static/app.js", 
            "styles.css": "static/styles.css"
        }
        
        file_status = {}
        all_present = True
        
        for name, path in required_files.items():
            exists = os.path.exists(path)
            if exists:
                # Get file size
                size = os.path.getsize(path)
                file_status[name] = {
                    "exists": True,
                    "size_bytes": size,
                    "path": path
                }
            else:
                file_status[name] = {
                    "exists": False,
                    "path": path
                }
                all_present = False
        
        return {
            "status": "healthy" if all_present else "unhealthy",
            "message": "All static files present" if all_present else "Some static files are missing",
            "files": file_status,
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Static files status check failed: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Failed to check static files: {str(e)}",
                "timestamp": time.time()
            }
        )

if __name__ == "__main__":
    import uvicorn
    
    # Configure uvicorn logging
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["default"]["fmt"] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_config["formatters"]["access"]["fmt"] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_config=log_config
    )
