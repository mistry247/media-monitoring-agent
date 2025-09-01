"""
Web scraping service for extracting article content from URLs.

This service provides robust content extraction using newspaper3k and BeautifulSoup4
with proper error handling, timeout management, and content validation.
"""

import logging
import requests
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse
import time
from newspaper import Article
from bs4 import BeautifulSoup
import re

from config import settings

logger = logging.getLogger(__name__)


class ScrapingError(Exception):
    """Custom exception for scraping-related errors."""
    pass


class ScrapingService:
    """Service for scraping article content from web URLs."""
    
    def __init__(self, timeout: int = 30, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize the scraping service.
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        
        # Set user agent to avoid blocking
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def _validate_url(self, url: str) -> bool:
        """
        Validate if the URL is properly formatted and accessible.
        
        Args:
            url: URL to validate
            
        Returns:
            True if URL is valid, False otherwise
        """
        try:
            parsed = urlparse(url)
            return bool(parsed.netloc) and bool(parsed.scheme) and parsed.scheme in ['http', 'https']
        except Exception:
            return False
    
    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize extracted text content.
        
        Args:
            text: Raw text content
            
        Returns:
            Cleaned text content
        """
        if not text:
            return ""
        
        # First normalize line breaks (before general whitespace cleanup)
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        # Remove excessive whitespace but preserve single line breaks
        text = re.sub(r'[ \t]+', ' ', text.strip())
        
        return text
    
    def _extract_with_newspaper(self, url: str) -> Optional[Dict[str, str]]:
        """
        Extract content using newspaper3k library.
        
        Args:
            url: URL to scrape
            
        Returns:
            Dictionary with title and text, or None if extraction fails
        """
        try:
            article = Article(url)
            article.download()
            article.parse()
            
            if not article.text or len(article.text.strip()) < 50:
                return None
            
            return {
                'title': self._clean_text(article.title or ''),
                'text': self._clean_text(article.text),
                'authors': article.authors,
                'publish_date': str(article.publish_date) if article.publish_date else None
            }
        except Exception as e:
            logger.debug(f"Newspaper3k extraction failed for {url}: {str(e)}")
            return None
    
    def _extract_with_beautifulsoup(self, url: str) -> Optional[Dict[str, str]]:
        """
        Extract content using BeautifulSoup as fallback method.
        
        Args:
            url: URL to scrape
            
        Returns:
            Dictionary with title and text, or None if extraction fails
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "header", "footer", "aside"]):
                script.decompose()
            
            # Try to find title
            title = ""
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text()
            else:
                # Try h1 as fallback
                h1_tag = soup.find('h1')
                if h1_tag:
                    title = h1_tag.get_text()
            
            # Try to find main content
            content_selectors = [
                'article', '[role="main"]', 'main', '.content', '.article-content',
                '.post-content', '.entry-content', '#content', '.story-body'
            ]
            
            text = ""
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    text = content_elem.get_text()
                    break
            
            # Fallback to body if no specific content found
            if not text:
                body = soup.find('body')
                if body:
                    text = body.get_text()
            
            if not text or len(text.strip()) < 50:
                return None
            
            return {
                'title': self._clean_text(title),
                'text': self._clean_text(text),
                'authors': [],
                'publish_date': None
            }
        except Exception as e:
            logger.debug(f"BeautifulSoup extraction failed for {url}: {str(e)}")
            return None
    
    def scrape_article(self, url: str) -> Dict[str, any]:
        """
        Scrape content from a single article URL.
        
        Args:
            url: URL to scrape
            
        Returns:
            Dictionary containing:
            - success: bool indicating if scraping was successful
            - url: original URL
            - title: article title (if found)
            - text: article content (if found)
            - authors: list of authors (if found)
            - publish_date: publication date (if found)
            - error: error message (if scraping failed)
        """
        # LOCAL MODE: Return mock data instead of scraping
        if settings.LOCAL_MODE:
            logger.info(f"LOCAL_MODE: Returning mock data for {url}")
            return {
                'success': True,
                'url': url,
                'title': 'Mock Article: Breaking News in Technology',
                'text': 'This is a mock article content for testing purposes. In a real scenario, this would contain the actual scraped content from the provided URL. The article discusses recent developments in artificial intelligence and machine learning technologies. It covers various aspects including natural language processing, computer vision, and automated decision-making systems. The content is designed to be comprehensive enough to test AI summarization capabilities while remaining clearly identifiable as test data.',
                'authors': ['Mock Author', 'Test Writer'],
                'publish_date': '2025-08-23',
                'error': None
            }
        
        result = {
            'success': False,
            'url': url,
            'title': '',
            'text': '',
            'authors': [],
            'publish_date': None,
            'error': None
        }
        
        # Validate URL
        if not self._validate_url(url):
            result['error'] = 'Invalid URL format'
            logger.warning(f"Invalid URL format: {url}")
            return result
        
        # Try scraping with retries
        last_error = None
        for attempt in range(self.max_retries):
            try:
                # First try newspaper3k
                content = self._extract_with_newspaper(url)
                
                # Fallback to BeautifulSoup if newspaper3k fails
                if not content:
                    content = self._extract_with_beautifulsoup(url)
                
                if content:
                    result.update(content)
                    result['success'] = True
                    logger.info(f"Successfully scraped content from {url}")
                    return result
                else:
                    last_error = "No content could be extracted"
                    
            except requests.exceptions.Timeout:
                last_error = f"Request timeout after {self.timeout} seconds"
                logger.warning(f"Timeout scraping {url} (attempt {attempt + 1})")
            except requests.exceptions.ConnectionError:
                last_error = "Connection error - unable to reach URL"
                logger.warning(f"Connection error scraping {url} (attempt {attempt + 1})")
            except requests.exceptions.HTTPError as e:
                last_error = f"HTTP error: {e.response.status_code}"
                logger.warning(f"HTTP error scraping {url}: {e}")
                # Don't retry on 4xx errors
                if 400 <= e.response.status_code < 500:
                    break
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                logger.error(f"Unexpected error scraping {url}: {str(e)}")
            
            # Wait before retry (except on last attempt)
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)
        
        result['error'] = last_error
        logger.error(f"Failed to scrape {url} after {self.max_retries} attempts: {last_error}")
        return result
    
    def scrape_article_tuple(self, url: str) -> tuple:
        """
        Scrape article and return tuple format for compatibility
        
        Args:
            url: URL to scrape
            
        Returns:
            Tuple of (success: bool, content: dict, error: str)
        """
        # LOCAL MODE: Return mock data immediately
        if settings.LOCAL_MODE:
            logger.info(f"LOCAL_MODE: Returning mock data tuple for {url}")
            mock_content = {
                'title': 'Mock Article: Breaking News in Technology',
                'content': 'This is a mock article content for testing purposes. In a real scenario, this would contain the actual scraped content from the provided URL. The article discusses recent developments in artificial intelligence and machine learning technologies. It covers various aspects including natural language processing, computer vision, and automated decision-making systems. The content is designed to be comprehensive enough to test AI summarization capabilities while remaining clearly identifiable as test data.',
                'author': 'Mock Author',
                'publish_date': '2025-08-23'
            }
            return True, mock_content, None
        
        # Call the main scrape_article method
        result = self.scrape_article(url)
        
        if result['success']:
            content = {
                'title': result.get('title', ''),
                'content': result.get('text', ''),
                'author': ', '.join(result.get('authors', [])),
                'publish_date': result.get('publish_date', '')
            }
            return True, content, None
        else:
            return False, {}, result.get('error', 'Unknown error')
    
    def batch_scrape(self, urls: List[str]) -> List[Dict[str, any]]:
        """
        Scrape content from multiple URLs.
        
        Args:
            urls: List of URLs to scrape
            
        Returns:
            List of scraping results, one for each URL
        """
        if not urls:
            return []
        
        logger.info(f"Starting batch scrape of {len(urls)} URLs")
        results = []
        
        for i, url in enumerate(urls, 1):
            logger.info(f"Scraping URL {i}/{len(urls)}: {url}")
            result = self.scrape_article(url)
            results.append(result)
            
            # Small delay between requests to be respectful
            if i < len(urls):
                time.sleep(0.5)
        
        successful = sum(1 for r in results if r['success'])
        logger.info(f"Batch scrape completed: {successful}/{len(urls)} successful")
        
        return results


# Global instance for easy import
scraping_service = ScrapingService()
