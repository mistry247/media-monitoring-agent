"""
Report generation service for orchestrating the complete workflow:
scraping, AI processing, email sending, and archiving
"""
import logging
import json
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from database import get_db, HansardQuestion
from services.article_service import get_article_service
from services.scraping_service import scraping_service
from services.ai_service import get_ai_service
from services.email_service import email_service
from config import settings

logger = logging.getLogger(__name__)

class ReportGenerationError(Exception):
    """Custom exception for report generation errors"""
    pass

class ReportService:
    """Service for generating and distributing media and Hansard reports"""
    
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())
        self.article_service = get_article_service(self.db)
        
        # Initialize AI service with API key from settings
        if not settings.GEMINI_API_KEY:
            raise ValueError("Gemini API key is required for report generation")
        self.ai_service = get_ai_service(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
    
    def generate_media_report(self, pasted_content: str = "", recipient_email: str = None) -> Tuple[bool, str, Optional[str]]:
        """
        Generate a comprehensive media report by orchestrating the complete workflow
        
        Args:
            pasted_content: Additional paywalled content pasted by user
            recipient_email: Email address to send the report to
            
        Returns:
            Tuple of (success: bool, message: str, report_id: Optional[str])
        """
        report_id = f"media_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            logger.info(f"Starting media report generation: {report_id}")
            
            # Step 1: Get all pending articles
            pending_articles = self.article_service.get_pending_articles()
            if not pending_articles and not pasted_content.strip():
                return False, "No pending articles or pasted content to process", None
            
            logger.info(f"Found {len(pending_articles)} pending articles")
            
            # Step 2: Scrape non-paywalled articles
            scraped_content = []
            failed_scrapes = []
            article_ids_to_archive = []
            article_ids_to_move_to_manual = []
            
            for article in pending_articles:
                logger.info(f"Scraping article: {article.url}")
                
                try:
                    scrape_result = scraping_service.scrape_article(article.url)
                    
                    if scrape_result['success']:
                        scraped_content.append({
                            'id': article.id,
                            'url': article.url,
                            'title': scrape_result['title'],
                            'content': scrape_result['text'],
                            'submitted_by': article.submitted_by,
                            'timestamp': article.timestamp
                        })
                        article_ids_to_archive.append(article.id)
                    else:
                        # Scraping failed - move to manual processing
                        failed_scrapes.append({
                            'url': article.url,
                            'error': scrape_result['error'],
                            'submitted_by': article.submitted_by
                        })
                        article_ids_to_move_to_manual.append(article.id)
                        logger.warning(f"Failed to scrape {article.url}: {scrape_result['error']} - moving to manual processing")
                
                except Exception as e:
                    # Exception during scraping - move to manual processing
                    failed_scrapes.append({
                        'url': article.url,
                        'error': f"Scraping exception: {str(e)}",
                        'submitted_by': article.submitted_by
                    })
                    article_ids_to_move_to_manual.append(article.id)
                    logger.error(f"Exception while scraping {article.url}: {e} - moving to manual processing")
            
            # Move failed articles to manual processing table
            if article_ids_to_move_to_manual:
                self._move_articles_to_manual_processing(article_ids_to_move_to_manual)
            
            logger.info(f"Successfully scraped {len(scraped_content)} articles, {len(failed_scrapes)} moved to manual processing")
            
            # Step 3: Prepare content for AI processing
            content_for_ai = []
            
            # Add scraped content
            for item in scraped_content:
                if item['content'].strip():
                    content_text = f"Title: {item['title']}\nURL: {item['url']}\nContent: {item['content']}"
                    content_for_ai.append(content_text)
            
            # Add pasted content if provided
            if pasted_content.strip():
                content_for_ai.append(f"Pasted Content:\n{pasted_content.strip()}")
                logger.info("Added pasted content to processing queue")
            
            if not content_for_ai:
                return False, "No content available for processing after scraping", None
            
            # Step 4: Generate AI summaries
            logger.info(f"Sending {len(content_for_ai)} items to AI for summarization")
            summary_results = self.ai_service.batch_summarize(content_for_ai, "media")
            
            successful_summaries = []
            failed_summaries = []
            
            for i, result in enumerate(summary_results):
                if result.success:
                    # Match summary back to original article if it's from scraped content
                    if i < len(scraped_content):
                        summary_data = scraped_content[i].copy()
                        summary_data['summary'] = result.content
                    else:
                        # This is from pasted content
                        summary_data = {
                            'title': 'Pasted Content Summary',
                            'summary': result.content,
                            'url': '',
                            'submitted_by': 'Manual Entry',
                            'timestamp': datetime.now()
                        }
                    successful_summaries.append(summary_data)
                else:
                    failed_summaries.append({
                        'index': i,
                        'error': result.error
                    })
                    logger.warning(f"AI summarization failed for item {i}: {result.error}")
            
            if not successful_summaries:
                return False, "All AI summarization attempts failed", None
            
            logger.info(f"Successfully generated {len(successful_summaries)} summaries")
            
            # Step 5: Generate HTML report
            html_report = email_service.format_html_report(successful_summaries, "Media Monitoring Report")
            
            # Step 6: Send email report
            email_subject = f"Media Monitoring Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            recipients = [recipient_email] if recipient_email else None
            email_sent = email_service.send_report(html_report, recipients=recipients, subject=email_subject)
            
            if not email_sent:
                logger.error("Failed to send email report")
                return False, "Report generated but email sending failed", report_id
            
            logger.info("Email report sent successfully")
            
            # Step 7: Archive processed articles (only if email was sent successfully)
            if article_ids_to_archive:
                archive_success, archive_message, archived_count = self.article_service.move_to_archive(article_ids_to_archive)
                if archive_success:
                    logger.info(f"Archived {archived_count} articles successfully")
                else:
                    logger.warning(f"Failed to archive articles: {archive_message}")
            
            # Prepare success message
            success_message = f"Media report generated successfully. Processed {len(successful_summaries)} items"
            if failed_scrapes:
                success_message += f", {len(failed_scrapes)} scraping failures"
            if failed_summaries:
                success_message += f", {len(failed_summaries)} summarization failures"
            
            return True, success_message, report_id
            
        except Exception as e:
            logger.error(f"Error generating media report: {str(e)}")
            # Rollback any partial changes if needed
            try:
                self.db.rollback()
            except:
                pass
            return False, f"Report generation failed: {str(e)}", None
    
    def generate_hansard_report(self, recipient_email: str = None) -> Tuple[bool, str, Optional[str]]:
        """
        Generate a Hansard report with parliamentary questions based on current media content
        
        Args:
            recipient_email: Email address to send the report to
            
        Returns:
            Tuple of (success: bool, message: str, report_id: Optional[str])
        """
        report_id = f"hansard_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            logger.info(f"Starting Hansard report generation: {report_id}")
            
            # Step 1: Get all pending articles
            pending_articles = self.article_service.get_pending_articles()
            if not pending_articles:
                return False, "No pending articles available for Hansard report generation", None
            
            logger.info(f"Found {len(pending_articles)} pending articles for Hansard processing")
            
            # Step 2: Scrape articles for content
            scraped_content = []
            article_ids_processed = []
            
            for article in pending_articles:
                logger.info(f"Scraping article for Hansard: {article.url}")
                scrape_result = scraping_service.scrape_article(article.url)
                
                if scrape_result['success']:
                    content_text = f"Title: {scrape_result['title']}\nURL: {article.url}\nContent: {scrape_result['text']}"
                    scraped_content.append(content_text)
                    article_ids_processed.append(article.id)
                else:
                    logger.warning(f"Failed to scrape {article.url} for Hansard: {scrape_result['error']}")
            
            if not scraped_content:
                return False, "No content could be scraped for Hansard report generation", None
            
            # Step 3: Generate Hansard-style questions using AI
            logger.info(f"Generating Hansard questions from {len(scraped_content)} articles")
            
            # Combine all content for Hansard processing
            combined_content = "\n\n---\n\n".join(scraped_content)
            hansard_result = self.ai_service.summarize_content(combined_content, "hansard")
            
            if not hansard_result.success:
                return False, f"Failed to generate Hansard questions: {hansard_result.error}", None
            
            # Step 4: Save Hansard questions to database
            hansard_question = HansardQuestion(
                question_text=hansard_result.content,
                category="Media-based Questions",
                timestamp=datetime.now(),
                source_articles=json.dumps(article_ids_processed)
            )
            
            self.db.add(hansard_question)
            self.db.commit()
            self.db.refresh(hansard_question)
            
            logger.info(f"Saved Hansard questions to database with ID: {hansard_question.id}")
            
            # Step 5: Format Hansard report for email
            hansard_summaries = [{
                'title': 'Parliamentary Questions Based on Recent Media',
                'summary': hansard_result.content,
                'url': '',
                'submitted_by': 'System Generated',
                'timestamp': datetime.now()
            }]
            
            html_report = email_service.format_html_report(hansard_summaries, "Hansard Questions Report")
            
            # Step 6: Send email report
            email_subject = f"Hansard Questions Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            recipients = [recipient_email] if recipient_email else None
            email_sent = email_service.send_report(html_report, recipients=recipients, subject=email_subject)
            
            if not email_sent:
                logger.error("Failed to send Hansard email report")
                return False, "Hansard report generated but email sending failed", report_id
            
            logger.info("Hansard email report sent successfully")
            
            success_message = f"Hansard report generated successfully from {len(scraped_content)} articles"
            return True, success_message, report_id
            
        except Exception as e:
            logger.error(f"Error generating Hansard report: {str(e)}")
            # Rollback any partial changes
            try:
                self.db.rollback()
            except:
                pass
            return False, f"Hansard report generation failed: {str(e)}", None
    
    def get_report_status(self, report_id: str) -> Dict[str, Any]:
        """
        Get the status of a report generation process
        
        Args:
            report_id: ID of the report to check
            
        Returns:
            Dictionary with report status information
        """
        # This is a placeholder for future implementation of async report tracking
        return {
            'report_id': report_id,
            'status': 'completed',
            'message': 'Report status tracking not yet implemented'
        }
    
    def get_recent_hansard_questions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieve recent Hansard questions from the database
        
        Args:
            limit: Maximum number of questions to retrieve
            
        Returns:
            List of Hansard question dictionaries
        """
        try:
            questions = self.db.query(HansardQuestion).order_by(
                HansardQuestion.timestamp.desc()
            ).limit(limit).all()
            
            result = []
            for question in questions:
                result.append({
                    'id': question.id,
                    'question_text': question.question_text,
                    'category': question.category,
                    'timestamp': question.timestamp,
                    'source_articles': json.loads(question.source_articles) if question.source_articles else []
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error retrieving Hansard questions: {str(e)}")
            return []
    
    def _move_articles_to_manual_processing(self, article_ids: List[int]) -> None:
        """
        Move articles from pending_articles to manual_input_articles table
        
        Args:
            article_ids: List of article IDs to move to manual processing
        """
        try:
            from database import PendingArticle, ManualInputArticle
            from datetime import datetime
            
            moved_count = 0
            
            for article_id in article_ids:
                # Get the pending article
                pending_article = self.db.query(PendingArticle).filter(
                    PendingArticle.id == article_id
                ).first()
                
                if not pending_article:
                    logger.warning(f"Article {article_id} not found in pending_articles")
                    continue
                
                # Create manual input entry
                manual_article = ManualInputArticle(
                    url=pending_article.url,
                    submitted_by=pending_article.submitted_by,
                    submitted_at=datetime.utcnow(),
                    article_content=None  # Initially empty, will be filled manually
                )
                
                # Add to manual input table and remove from pending
                self.db.add(manual_article)
                self.db.delete(pending_article)
                moved_count += 1
                
                logger.info(f"Moved article {article_id} ({pending_article.url}) to manual processing")
            
            self.db.commit()
            logger.info(f"Successfully moved {moved_count} articles to manual processing")
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error moving articles to manual processing: {e}")
            raise

def get_report_service(db: Session = None) -> ReportService:
    """
    Factory function to get ReportService instance
    
    Args:
        db: Database session (optional, will create new if not provided)
        
    Returns:
        ReportService instance
    """
    return ReportService(db)
