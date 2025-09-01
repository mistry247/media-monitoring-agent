"""
API endpoints for manual article processing
"""
import time
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database import get_db, ManualInputArticle
from services.ai_service import get_ai_service
from services.email_service import EmailService
from config import settings
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Create router for manual articles endpoints
router = APIRouter(prefix="/api/manual-articles", tags=["manual-articles"])

# Pydantic models for request/response
class ManualArticleResponse(BaseModel):
    id: int
    url: str
    submitted_by: str
    submitted_at: str
    article_content: str = None
    has_content: bool

class UpdateContentRequest(BaseModel):
    article_content: str

class ProcessBatchRequest(BaseModel):
    recipient_email: str = None

@router.get("/", response_model=List[ManualArticleResponse])
async def get_manual_articles(db: Session = Depends(get_db)):
    """
    Get all articles waiting for manual input
    
    Returns:
        List of manual articles with their current content status
    """
    try:
        manual_articles = db.query(ManualInputArticle).order_by(
            ManualInputArticle.submitted_at.desc()
        ).all()
        
        articles_response = []
        for article in manual_articles:
            articles_response.append(ManualArticleResponse(
                id=article.id,
                url=article.url,
                submitted_by=article.submitted_by,
                submitted_at=article.submitted_at.isoformat(),
                article_content=article.article_content or "",
                has_content=bool(article.article_content and article.article_content.strip())
            ))
        
        logger.info(f"Retrieved {len(articles_response)} manual articles")
        
        return articles_response
        
    except Exception as e:
        logger.error(f"Error retrieving manual articles: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve manual articles"
        )

@router.post("/{article_id}")
async def update_article_content(
    article_id: int,
    request: UpdateContentRequest,
    db: Session = Depends(get_db)
):
    """
    Save the pasted text content for a specific article
    
    Args:
        article_id: ID of the article to update
        request: Request containing the article content
        
    Returns:
        Success message with updated article info
    """
    try:
        # Find the article
        article = db.query(ManualInputArticle).filter(
            ManualInputArticle.id == article_id
        ).first()
        
        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Manual article with ID {article_id} not found"
            )
        
        # Update the content
        article.article_content = request.article_content.strip()
        db.commit()
        db.refresh(article)
        
        logger.info(f"Updated content for manual article {article_id} ({article.url})")
        
        return {
            "success": True,
            "message": "Article content updated successfully",
            "id": article.id,
            "url": article.url,
            "content_length": len(article.article_content) if article.article_content else 0,
            "has_content": bool(article.article_content and article.article_content.strip())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating article content for {article_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update article content"
        )

@router.delete("/{article_id}")
async def remove_manual_article(
    article_id: int,
    db: Session = Depends(get_db)
):
    """
    Remove an article from the manual queue
    
    Args:
        article_id: ID of the article to remove
        
    Returns:
        Success message
    """
    try:
        # Find the article
        article = db.query(ManualInputArticle).filter(
            ManualInputArticle.id == article_id
        ).first()
        
        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Manual article with ID {article_id} not found"
            )
        
        # Store info for logging before deletion
        article_url = article.url
        article_submitter = article.submitted_by
        
        # Delete the article
        db.delete(article)
        db.commit()
        
        logger.info(f"Removed manual article {article_id} ({article_url}) submitted by {article_submitter}")
        
        return {
            "success": True,
            "message": "Article removed from manual queue",
            "id": article_id,
            "url": article_url
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error removing manual article {article_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove article"
        )

@router.post("/process-batch")
async def process_manual_articles_batch(
    request: ProcessBatchRequest,
    db: Session = Depends(get_db)
):
    """
    Trigger AI processing for all manual articles that have content
    
    Args:
        request: Request containing recipient email
        
    Returns:
        Processing results and report information
    """
    start_time = time.time()
    
    try:
        # Get all manual articles that have content
        articles_with_content = db.query(ManualInputArticle).filter(
            ManualInputArticle.article_content.isnot(None),
            ManualInputArticle.article_content != ""
        ).all()
        
        if not articles_with_content:
            return {
                "success": False,
                "message": "No manual articles with content found to process",
                "processed_count": 0
            }
        
        logger.info(f"Processing {len(articles_with_content)} manual articles with content")
        
        # Initialize AI service
        if not settings.GEMINI_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI service not configured - missing API key"
            )
        
        ai_service = get_ai_service(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
        
        # Process each article through AI
        successful_summaries = []
        failed_summaries = []
        processed_articles = []
        
        for article in articles_with_content:
            try:
                logger.info(f"Processing manual article: {article.url}")
                
                # Create content for AI processing
                content_text = f"Title: Manual Input Article\nURL: {article.url}\nContent: {article.article_content}"
                
                # Get AI summary
                summary_result = ai_service.summarize_content(content_text, "media", article.url)
                
                if summary_result.success:
                    successful_summaries.append({
                        'id': article.id,
                        'url': article.url,
                        'title': f"Manual Input: {article.url}",
                        'summary': summary_result.content,
                        'submitted_by': article.submitted_by,
                        'timestamp': article.submitted_at,
                        'content_length': len(article.article_content)
                    })
                    processed_articles.append(article.id)
                    logger.info(f"Successfully processed manual article {article.id}")
                else:
                    failed_summaries.append({
                        'id': article.id,
                        'url': article.url,
                        'error': summary_result.error
                    })
                    logger.warning(f"Failed to process manual article {article.id}: {summary_result.error}")
                    
            except Exception as e:
                failed_summaries.append({
                    'id': article.id,
                    'url': article.url,
                    'error': f"Processing exception: {str(e)}"
                })
                logger.error(f"Exception processing manual article {article.id}: {e}")
        
        if not successful_summaries:
            return {
                "success": False,
                "message": "All manual article processing attempts failed",
                "processed_count": 0,
                "failed_count": len(failed_summaries),
                "errors": failed_summaries
            }
        
        # Generate and send email report
        email_service = EmailService()
        html_report = email_service.format_html_report(
            successful_summaries, 
            "Manual Articles Processing Report"
        )
        
        # Send email report
        email_subject = f"Manual Articles Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        recipients = [request.recipient_email] if request.recipient_email else None
        email_sent = email_service.send_report(html_report, recipients=recipients, subject=email_subject)
        
        # Remove processed articles from manual queue
        if processed_articles:
            db.query(ManualInputArticle).filter(
                ManualInputArticle.id.in_(processed_articles)
            ).delete(synchronize_session=False)
            db.commit()
            logger.info(f"Removed {len(processed_articles)} processed articles from manual queue")
        
        duration_ms = (time.time() - start_time) * 1000
        
        result = {
            "success": True,
            "message": f"Successfully processed {len(successful_summaries)} manual articles",
            "processed_count": len(successful_summaries),
            "failed_count": len(failed_summaries),
            "email_sent": email_sent,
            "processing_time_ms": duration_ms
        }
        
        if failed_summaries:
            result["errors"] = failed_summaries
        
        if not email_sent:
            result["message"] += " (email sending failed)"
        
        logger.info(f"Manual articles batch processing completed: {len(successful_summaries)} successful, {len(failed_summaries)} failed")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error in manual articles batch processing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch processing failed: {str(e)}"
        )
