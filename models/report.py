"""
Pydantic models for report data validation and serialization
"""
from pydantic import BaseModel, validator
from typing import Optional

from utils.security import validate_and_sanitize_text

class MediaReportRequest(BaseModel):
    """Model for media report generation requests"""
    pasted_content: str
    recipient_email: str
    
    @validator('pasted_content')
    def validate_pasted_content(cls, v):
        # Use security utility for text validation and sanitization
        return validate_and_sanitize_text(v, max_length=100000)
    
    @validator('recipient_email')
    def validate_recipient_email(cls, v):
        # Basic email validation
        import re
        if not v or not v.strip():
            raise ValueError('Recipient email is required')
        
        email = v.strip()
        if len(email) > 254:
            raise ValueError('Email address is too long')
        
        email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(email_regex, email):
            raise ValueError('Invalid email address format')
        
        return email

class HansardReportRequest(BaseModel):
    """Model for Hansard report generation requests"""
    recipient_email: str
    
    @validator('recipient_email')
    def validate_recipient_email(cls, v):
        # Basic email validation
        import re
        if not v or not v.strip():
            raise ValueError('Recipient email is required')
        
        email = v.strip()
        if len(email) > 254:
            raise ValueError('Email address is too long')
        
        email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(email_regex, email):
            raise ValueError('Invalid email address format')
        
        return email

class ReportResponse(BaseModel):
    """Model for report generation responses"""
    success: bool
    message: str
    report_id: Optional[str] = None
    
class ReportStatus(BaseModel):
    """Model for report status responses"""
    report_id: str
    status: str  # 'pending', 'processing', 'completed', 'failed'
    message: str
    progress: Optional[int] = None  # 0-100 percentage
