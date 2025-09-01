"""
Pydantic models for article data validation and serialization
"""
from pydantic import BaseModel, validator
from datetime import datetime
from typing import Optional

from utils.security import validate_and_sanitize_url, validate_and_sanitize_name

class ArticleSubmission(BaseModel):
    """Model for article submission requests"""
    url: str
    submitted_by: str
    
    @validator('submitted_by')
    def validate_submitted_by(cls, v):
        # Use security utility for name validation
        return validate_and_sanitize_name(v, max_length=100)
    
    @validator('url')
    def validate_url(cls, v):
        # Use security utility for URL validation and sanitization
        return validate_and_sanitize_url(str(v))

class Article(BaseModel):
    """Model for article data"""
    id: Optional[int] = None
    url: str
    pasted_text: Optional[str] = None
    timestamp: datetime
    submitted_by: str
    
    class Config:
        from_attributes = True

class ArticleResponse(BaseModel):
    """Model for article API responses"""
    success: bool
    message: str
    article: Optional[Article] = None

class PendingArticlesResponse(BaseModel):
    """Model for pending articles list response"""
    articles: list[Article]
    count: int
