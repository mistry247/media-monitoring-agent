"""
Article service for handling article submission, retrieval, and archiving operations
"""
import time
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from datetime import datetime

from database import PendingArticle, ProcessedArchive, get_db
from models.article import ArticleSubmission, Article
from utils.logging_config import get_logger, log_operation, log_error
from utils.error_handlers import ArticleServiceError, DatabaseError

logger = get_logger(__name__)

class ArticleService:
    """Service class for article operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def submit_article(self, submission: ArticleSubmission) -> Tuple[bool, str, Optional[Article]]:
        """
        Submit a new article for processing
        
        Args:
            submission: ArticleSubmission model with URL and submitted_by
            
        Returns:
            Tuple of (success: bool, message: str, article: Optional[Article])
        """
        start_time = time.time()
        
        try:
            # Check for duplicates in pending_articles table
            existing_pending = self.db.query(PendingArticle).filter(
                PendingArticle.url == submission.url
            ).first()
            
            if existing_pending:
                logger.info(
                    f"Duplicate URL found in pending_articles: {submission.url}",
                    extra={
                        "operation": "submit_article",
                        "url": submission.url,
                        "submitted_by": submission.submitted_by,
                        "duplicate_location": "pending"
                    }
                )
                return False, "This article URL is already pending processing", None
            
            # Check for duplicates in processed_archive table
            existing_processed = self.db.query(ProcessedArchive).filter(
                ProcessedArchive.url == submission.url
            ).first()
            
            if existing_processed:
                logger.info(
                    f"Duplicate URL found in processed_archive: {submission.url}",
                    extra={
                        "operation": "submit_article",
                        "url": submission.url,
                        "submitted_by": submission.submitted_by,
                        "duplicate_location": "processed"
                    }
                )
                return False, "This article URL has already been processed", None
            
            # Create new pending article
            new_article = PendingArticle(
                url=submission.url,
                submitted_by=submission.submitted_by,
                timestamp=datetime.utcnow()
            )
            
            self.db.add(new_article)
            self.db.commit()
            self.db.refresh(new_article)
            
            # Convert to Pydantic model
            article = Article(
                id=new_article.id,
                url=new_article.url,
                pasted_text=new_article.pasted_text,
                timestamp=new_article.timestamp,
                submitted_by=new_article.submitted_by
            )
            
            duration_ms = (time.time() - start_time) * 1000
            log_operation(
                logger,
                "submit_article",
                duration_ms,
                url=submission.url,
                submitted_by=submission.submitted_by,
                article_id=article.id
            )
            
            return True, "Article submitted successfully", article
            
        except IntegrityError as e:
            self.db.rollback()
            log_error(logger, e, operation="submit_article", url=submission.url)
            raise DatabaseError("URL constraint violation - article may already exist", "DUPLICATE_URL_CONSTRAINT")
            
        except SQLAlchemyError as e:
            self.db.rollback()
            log_error(logger, e, operation="submit_article", url=submission.url)
            raise DatabaseError("Database operation failed", "DATABASE_OPERATION_FAILED")
            
        except Exception as e:
            self.db.rollback()
            log_error(logger, e, operation="submit_article", url=submission.url)
            raise ArticleServiceError("Failed to submit article", "ARTICLE_SUBMISSION_FAILED")
    
    def get_pending_articles(self) -> List[Article]:
        """
        Retrieve all pending articles
        
        Returns:
            List of Article models
        """
        start_time = time.time()
        
        try:
            pending_articles = self.db.query(PendingArticle).order_by(
                PendingArticle.timestamp.desc()
            ).all()
            
            # Convert to Pydantic models
            articles = []
            for article in pending_articles:
                articles.append(Article(
                    id=article.id,
                    url=article.url,
                    pasted_text=article.pasted_text,
                    timestamp=article.timestamp,
                    submitted_by=article.submitted_by
                ))
            
            duration_ms = (time.time() - start_time) * 1000
            log_operation(
                logger,
                "get_pending_articles",
                duration_ms,
                articles_count=len(articles)
            )
            
            return articles
            
        except SQLAlchemyError as e:
            log_error(logger, e, operation="get_pending_articles")
            raise DatabaseError("Failed to retrieve pending articles", "DATABASE_QUERY_FAILED")
            
        except Exception as e:
            log_error(logger, e, operation="get_pending_articles")
            raise ArticleServiceError("Failed to retrieve pending articles", "ARTICLE_RETRIEVAL_FAILED")
    
    def get_pending_article_by_id(self, article_id: int) -> Optional[Article]:
        """
        Retrieve a specific pending article by ID
        
        Args:
            article_id: ID of the article to retrieve
            
        Returns:
            Article model or None if not found
        """
        try:
            article = self.db.query(PendingArticle).filter(
                PendingArticle.id == article_id
            ).first()
            
            if not article:
                return None
            
            return Article(
                id=article.id,
                url=article.url,
                pasted_text=article.pasted_text,
                timestamp=article.timestamp,
                submitted_by=article.submitted_by
            )
            
        except Exception as e:
            logger.error(f"Error retrieving article {article_id}: {e}")
            return None
    
    def move_to_archive(self, article_ids: List[int]) -> Tuple[bool, str, int]:
        """
        Move processed articles from pending to archive
        
        Args:
            article_ids: List of article IDs to archive
            
        Returns:
            Tuple of (success: bool, message: str, archived_count: int)
        """
        try:
            archived_count = 0
            
            for article_id in article_ids:
                # Get the pending article
                pending_article = self.db.query(PendingArticle).filter(
                    PendingArticle.id == article_id
                ).first()
                
                if not pending_article:
                    logger.warning(f"Article {article_id} not found in pending_articles")
                    continue
                
                # Create archive entry
                archive_entry = ProcessedArchive(
                    url=pending_article.url,
                    timestamp=pending_article.timestamp,
                    submitted_by=pending_article.submitted_by,
                    processed_date=datetime.utcnow()
                )
                
                # Add to archive and remove from pending
                self.db.add(archive_entry)
                self.db.delete(pending_article)
                archived_count += 1
            
            self.db.commit()
            
            logger.info(f"Archived {archived_count} articles successfully")
            return True, f"Successfully archived {archived_count} articles", archived_count
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error archiving articles: {e}")
            return False, "An error occurred while archiving articles", 0
    
    def get_processed_articles(self, limit: int = 100) -> List[dict]:
        """
        Retrieve processed articles from archive
        
        Args:
            limit: Maximum number of articles to retrieve
            
        Returns:
            List of processed article dictionaries
        """
        try:
            processed_articles = self.db.query(ProcessedArchive).order_by(
                ProcessedArchive.processed_date.desc()
            ).limit(limit).all()
            
            articles = []
            for article in processed_articles:
                articles.append({
                    "id": article.id,
                    "url": article.url,
                    "timestamp": article.timestamp,
                    "submitted_by": article.submitted_by,
                    "processed_date": article.processed_date
                })
            
            logger.info(f"Retrieved {len(articles)} processed articles")
            return articles
            
        except Exception as e:
            logger.error(f"Error retrieving processed articles: {e}")
            return []
    
    def is_url_duplicate(self, url: str) -> Tuple[bool, str]:
        """
        Check if URL already exists in pending or processed tables
        
        Args:
            url: URL to check for duplicates
            
        Returns:
            Tuple of (is_duplicate: bool, location: str)
        """
        try:
            # Check pending articles
            pending_exists = self.db.query(PendingArticle).filter(
                PendingArticle.url == url
            ).first()
            
            if pending_exists:
                return True, "pending"
            
            # Check processed archive
            processed_exists = self.db.query(ProcessedArchive).filter(
                ProcessedArchive.url == url
            ).first()
            
            if processed_exists:
                return True, "processed"
            
            return False, "none"
            
        except Exception as e:
            logger.error(f"Error checking URL duplicate: {e}")
            return False, "error"

def get_article_service(db: Session = None) -> ArticleService:
    """
    Factory function to get ArticleService instance
    
    Args:
        db: Database session (optional, will create new if not provided)
        
    Returns:
        ArticleService instance
    """
    if db is None:
        db = next(get_db())
    
    return ArticleService(db)
