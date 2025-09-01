"""
Health check utilities for monitoring application status
"""
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import asyncio

# Optional imports
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from database import get_db, engine
from config import settings
from utils.logging_config import get_logger

logger = get_logger(__name__)

class HealthStatus(Enum):
    """Health check status enumeration"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class HealthCheckResult:
    """Result of a health check"""
    name: str
    status: HealthStatus
    message: str
    duration_ms: float
    details: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

class HealthChecker:
    """Health checker for various system components"""
    
    def __init__(self):
        self.checks = {}
        self.last_results = {}
    
    def register_check(self, name: str, check_func, timeout: float = 5.0):
        """
        Register a health check function
        
        Args:
            name: Name of the health check
            check_func: Async function that performs the check
            timeout: Timeout in seconds for the check
        """
        self.checks[name] = {
            "func": check_func,
            "timeout": timeout
        }
    
    async def run_check(self, name: str) -> HealthCheckResult:
        """
        Run a specific health check
        
        Args:
            name: Name of the health check to run
            
        Returns:
            HealthCheckResult with check results
        """
        if name not in self.checks:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check '{name}' not found",
                duration_ms=0.0
            )
        
        check_info = self.checks[name]
        start_time = time.time()
        
        try:
            # Run the check with timeout
            result = await asyncio.wait_for(
                check_info["func"](),
                timeout=check_info["timeout"]
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            if isinstance(result, HealthCheckResult):
                result.duration_ms = duration_ms
                return result
            else:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    message="Check passed",
                    duration_ms=duration_ms,
                    details=result if isinstance(result, dict) else None
                )
        
        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check timed out after {check_info['timeout']}s",
                duration_ms=duration_ms
            )
        
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Health check '{name}' failed: {e}")
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}",
                duration_ms=duration_ms,
                details={"error": str(e), "error_type": type(e).__name__}
            )
    
    async def run_all_checks(self) -> Dict[str, HealthCheckResult]:
        """
        Run all registered health checks
        
        Returns:
            Dictionary of health check results
        """
        results = {}
        
        # Run all checks concurrently
        tasks = []
        for name in self.checks:
            tasks.append(self.run_check(name))
        
        check_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, name in enumerate(self.checks):
            result = check_results[i]
            if isinstance(result, Exception):
                results[name] = HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check execution failed: {str(result)}",
                    duration_ms=0.0
                )
            else:
                results[name] = result
        
        # Cache results
        self.last_results = results
        
        return results
    
    def get_overall_status(self, results: Dict[str, HealthCheckResult]) -> HealthStatus:
        """
        Determine overall system health status
        
        Args:
            results: Dictionary of health check results
            
        Returns:
            Overall health status
        """
        if not results:
            return HealthStatus.UNHEALTHY
        
        statuses = [result.status for result in results.values()]
        
        if all(status == HealthStatus.HEALTHY for status in statuses):
            return HealthStatus.HEALTHY
        elif any(status == HealthStatus.UNHEALTHY for status in statuses):
            return HealthStatus.UNHEALTHY
        else:
            return HealthStatus.DEGRADED

# Global health checker instance
health_checker = HealthChecker()

async def check_database_health() -> HealthCheckResult:
    """Check database connectivity and basic operations"""
    try:
        # Test database connection
        db = next(get_db())
        
        # Test a simple query
        from sqlalchemy import text
        result = db.execute(text("SELECT 1")).fetchone()
        
        if result and result[0] == 1:
            # Test table existence
            tables_query = text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('pending_articles', 'processed_archive', 'hansard_questions')
            """)
            tables = db.execute(tables_query).fetchall()
            table_names = [table[0] for table in tables]
            
            expected_tables = ['pending_articles', 'processed_archive', 'hansard_questions']
            missing_tables = [table for table in expected_tables if table not in table_names]
            
            if missing_tables:
                return HealthCheckResult(
                    name="database",
                    status=HealthStatus.DEGRADED,
                    message=f"Database connected but missing tables: {missing_tables}",
                    duration_ms=0.0,
                    details={"missing_tables": missing_tables, "existing_tables": table_names}
                )
            
            return HealthCheckResult(
                name="database",
                status=HealthStatus.HEALTHY,
                message="Database is healthy",
                duration_ms=0.0,
                details={"tables": table_names}
            )
        else:
            return HealthCheckResult(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message="Database query failed",
                duration_ms=0.0
            )
    
    except Exception as e:
        return HealthCheckResult(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=f"Database connection failed: {str(e)}",
            duration_ms=0.0,
            details={"error": str(e)}
        )

async def check_gemini_api_health() -> HealthCheckResult:
    """Check Gemini API connectivity"""
    try:
        # Skip external API check in LOCAL_MODE
        if getattr(settings, 'LOCAL_MODE', False):
            return HealthCheckResult(
                name="gemini_api",
                status=HealthStatus.HEALTHY,
                message="Gemini API check skipped (LOCAL_MODE)",
                duration_ms=0.0,
                details={"local_mode": True}
            )
        
        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            return HealthCheckResult(
                name="gemini_api",
                status=HealthStatus.UNHEALTHY,
                message="Gemini API key not configured",
                duration_ms=0.0
            )
        
        # Test Gemini API with a simple request
        import google.generativeai as genai
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Simple test generation
        response = model.generate_content(
            "Hello",
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=10,
                temperature=0.1
            )
        )
        
        if response.text:
            return HealthCheckResult(
                name="gemini_api",
                status=HealthStatus.HEALTHY,
                message="Gemini API is accessible",
                duration_ms=0.0
            )
        else:
            return HealthCheckResult(
                name="gemini_api",
                status=HealthStatus.DEGRADED,
                message="Gemini API responded but with no content",
                duration_ms=0.0
            )
    
    except asyncio.TimeoutError:
        return HealthCheckResult(
            name="gemini_api",
            status=HealthStatus.UNHEALTHY,
            message="Gemini API request timed out",
            duration_ms=0.0
        )
    except Exception as e:
        error_str = str(e)
        if "api_key" in error_str.lower() or "authentication" in error_str.lower():
            return HealthCheckResult(
                name="gemini_api",
                status=HealthStatus.UNHEALTHY,
                message="Gemini API authentication failed",
                duration_ms=0.0,
                details={"error": error_str}
            )
        else:
            return HealthCheckResult(
                name="gemini_api",
                status=HealthStatus.UNHEALTHY,
                message=f"Gemini API check failed: {error_str}",
                duration_ms=0.0,
                details={"error": error_str}
            )

async def check_webhook_health() -> HealthCheckResult:
    """Check N8N webhook connectivity"""
    try:
        # Skip external webhook check in LOCAL_MODE
        if getattr(settings, 'LOCAL_MODE', False):
            return HealthCheckResult(
                name="webhook",
                status=HealthStatus.HEALTHY,
                message="Webhook check skipped (LOCAL_MODE)",
                duration_ms=0.0,
                details={"local_mode": True}
            )
        
        webhook_url = getattr(settings, 'N8N_WEBHOOK_URL', None)
        
        if not webhook_url:
            return HealthCheckResult(
                name="webhook",
                status=HealthStatus.UNHEALTHY,
                message="N8N webhook URL not configured",
                duration_ms=0.0
            )
        
        if not webhook_url.startswith(('http://', 'https://')):
            return HealthCheckResult(
                name="webhook",
                status=HealthStatus.UNHEALTHY,
                message="N8N webhook URL is not a valid HTTP/HTTPS URL",
                duration_ms=0.0,
                details={"webhook_url": webhook_url}
            )
        
        # For webhook, we just validate the URL format and configuration
        # We don't test the actual webhook to avoid sending test emails
        return HealthCheckResult(
            name="webhook",
            status=HealthStatus.HEALTHY,
            message="N8N webhook is configured",
            duration_ms=0.0,
            details={"webhook_configured": True}
        )
    
    except Exception as e:
        return HealthCheckResult(
            name="webhook",
            status=HealthStatus.UNHEALTHY,
            message=f"Webhook check failed: {str(e)}",
            duration_ms=0.0,
            details={"error": str(e)}
        )

async def check_disk_space() -> HealthCheckResult:
    """Check available disk space"""
    try:
        import shutil
        
        # Check disk space for current directory
        total, used, free = shutil.disk_usage(".")
        
        # Convert to GB
        total_gb = total / (1024**3)
        used_gb = used / (1024**3)
        free_gb = free / (1024**3)
        
        # Calculate usage percentage
        usage_percent = (used / total) * 100
        
        # Determine status based on free space
        if free_gb < 1.0:  # Less than 1GB free
            status = HealthStatus.UNHEALTHY
            message = f"Critical: Only {free_gb:.2f}GB free space remaining"
        elif free_gb < 5.0:  # Less than 5GB free
            status = HealthStatus.DEGRADED
            message = f"Warning: Only {free_gb:.2f}GB free space remaining"
        else:
            status = HealthStatus.HEALTHY
            message = f"Disk space is adequate: {free_gb:.2f}GB free"
        
        return HealthCheckResult(
            name="disk_space",
            status=status,
            message=message,
            duration_ms=0.0,
            details={
                "total_gb": round(total_gb, 2),
                "used_gb": round(used_gb, 2),
                "free_gb": round(free_gb, 2),
                "usage_percent": round(usage_percent, 2)
            }
        )
    
    except Exception as e:
        return HealthCheckResult(
            name="disk_space",
            status=HealthStatus.UNHEALTHY,
            message=f"Disk space check failed: {str(e)}",
            duration_ms=0.0,
            details={"error": str(e)}
        )

async def check_memory_usage() -> HealthCheckResult:
    """Check memory usage"""
    try:
        # Skip memory check in LOCAL_MODE or if psutil is not available
        if getattr(settings, 'LOCAL_MODE', False):
            return HealthCheckResult(
                name="memory",
                status=HealthStatus.HEALTHY,
                message="Memory check skipped (LOCAL_MODE)",
                duration_ms=0.0,
                details={"local_mode": True}
            )
        
        try:
            import psutil
        except ImportError:
            return HealthCheckResult(
                name="memory",
                status=HealthStatus.HEALTHY,
                message="Memory monitoring not available (psutil not installed)",
                duration_ms=0.0,
                details={"psutil_available": False}
            )
        
        # Get memory information
        memory = psutil.virtual_memory()
        
        # Convert to MB
        total_mb = memory.total / (1024**2)
        available_mb = memory.available / (1024**2)
        used_mb = memory.used / (1024**2)
        
        usage_percent = memory.percent
        
        # Determine status based on memory usage
        if usage_percent > 90:
            status = HealthStatus.UNHEALTHY
            message = f"Critical: Memory usage at {usage_percent:.1f}%"
        elif usage_percent > 80:
            status = HealthStatus.DEGRADED
            message = f"Warning: Memory usage at {usage_percent:.1f}%"
        else:
            status = HealthStatus.HEALTHY
            message = f"Memory usage is normal: {usage_percent:.1f}%"
        
        return HealthCheckResult(
            name="memory",
            status=status,
            message=message,
            duration_ms=0.0,
            details={
                "total_mb": round(total_mb, 2),
                "used_mb": round(used_mb, 2),
                "available_mb": round(available_mb, 2),
                "usage_percent": round(usage_percent, 2)
            }
        )
    
    except Exception as e:
        return HealthCheckResult(
            name="memory",
            status=HealthStatus.HEALTHY,
            message=f"Memory check skipped due to error: {str(e)}",
            duration_ms=0.0,
            details={"error": str(e)}
        )

# Register all health checks
health_checker.register_check("database", check_database_health, timeout=5.0)
health_checker.register_check("gemini_api", check_gemini_api_health, timeout=10.0)
health_checker.register_check("webhook", check_webhook_health, timeout=2.0)
health_checker.register_check("disk_space", check_disk_space, timeout=2.0)
health_checker.register_check("memory", check_memory_usage, timeout=2.0)

async def get_health_status() -> Dict[str, Any]:
    """
    Get comprehensive health status of the application
    
    Returns:
        Dictionary with overall status and individual check results
    """
    start_time = time.time()
    
    # Run all health checks
    results = await health_checker.run_all_checks()
    
    # Determine overall status
    overall_status = health_checker.get_overall_status(results)
    
    # Calculate total duration
    total_duration = (time.time() - start_time) * 1000
    
    # Convert results to serializable format
    serializable_results = {}
    for name, result in results.items():
        serializable_results[name] = {
            "status": result.status.value,
            "message": result.message,
            "duration_ms": round(result.duration_ms, 2),
            "timestamp": result.timestamp.isoformat() if result.timestamp else None,
            "details": result.details
        }
    
    return {
        "status": overall_status.value,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_duration_ms": round(total_duration, 2),
        "checks": serializable_results,
        "summary": {
            "total_checks": len(results),
            "healthy": sum(1 for r in results.values() if r.status == HealthStatus.HEALTHY),
            "degraded": sum(1 for r in results.values() if r.status == HealthStatus.DEGRADED),
            "unhealthy": sum(1 for r in results.values() if r.status == HealthStatus.UNHEALTHY)
        }
    }
