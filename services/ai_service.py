"""
AI service for Google Gemini API integration and content summarization
"""
import logging
import time
import json
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SummaryResult:
    """Result of a summarization operation"""
    success: bool
    content: Optional[str] = None
    error: Optional[str] = None
    tokens_used: Optional[int] = None

class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, max_requests_per_minute: int = 50):
        self.max_requests = max_requests_per_minute
        self.requests = []
    
    def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        now = time.time()
        # Remove requests older than 1 minute
        self.requests = [req_time for req_time in self.requests if now - req_time < 60]
        
        if len(self.requests) >= self.max_requests:
            # Wait until the oldest request is more than 1 minute old
            sleep_time = 60 - (now - self.requests[0]) + 1
            if sleep_time > 0:
                logger.info(f"Rate limit reached, waiting {sleep_time:.1f} seconds")
                time.sleep(sleep_time)
                # Clean up old requests after waiting
                now = time.time()
                self.requests = [req_time for req_time in self.requests if now - req_time < 60]
        
        self.requests.append(now)

class GeminiAPIClient:
    """Client for interacting with Google Gemini API"""
    
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model_name = model_name
        self.rate_limiter = RateLimiter()
        
        # Configure Gemini API
        genai.configure(api_key=api_key)
        
        # Initialize the model with safety settings
        self.model = genai.GenerativeModel(
            model_name=model_name,
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            }
        )
    
    def _make_request(self, content: str, max_tokens: int = 1000) -> Dict[str, Any]:
        """Make a request to Gemini API"""
        # Apply rate limiting
        self.rate_limiter.wait_if_needed()
        
        try:
            # Configure generation parameters
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=0.1,  # Lower temperature for more consistent summaries
                top_p=0.8,
                top_k=40
            )
            
            response = self.model.generate_content(
                content,
                generation_config=generation_config
            )
            
            # Check if the response was blocked
            if response.candidates[0].finish_reason.name == "SAFETY":
                raise Exception("Content was blocked by safety filters")
            
            return {
                "content": response.text,
                "usage": {
                    "input_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                    "output_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
                    "total_tokens": response.usage_metadata.total_token_count if response.usage_metadata else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Gemini API request failed: {e}")
            raise
    
    def summarize(self, content: str, summary_type: str = "media", article_url: str = "") -> SummaryResult:
        """
        Summarize content using Gemini API
        
        Args:
            content: Text content to summarize
            summary_type: Type of summary ("media" or "hansard")
            
        Returns:
            SummaryResult with success status and content or error
        """
        # LOCAL MODE: Return mock summary instead of calling API
        if settings.LOCAL_MODE:
            logger.info(f"LOCAL_MODE: Returning mock summary for {summary_type} content")
            mock_summary = {
                "media": "MOCK SUMMARY: This article discusses recent developments in technology and artificial intelligence. Key points include advancements in machine learning, potential impacts on various industries, and considerations for future implementation. The content highlights both opportunities and challenges in the current technological landscape.",
                "hansard": "MOCK HANSARD QUESTIONS: 1. What steps is the government taking to address technological advancement impacts? 2. How will AI developments affect employment in key sectors? 3. What regulatory frameworks are being considered for emerging technologies?"
            }
            return SummaryResult(
                success=True,
                content=mock_summary.get(summary_type, mock_summary["media"]),
                tokens_used=150
            )
        
        if not content.strip():
            return SummaryResult(success=False, error="Empty content provided")
        
        try:
            # Create appropriate prompt based on summary type
            if summary_type == "media":
                prompt = self._create_media_summary_prompt(content, article_url)
            elif summary_type == "hansard":
                prompt = self._create_hansard_summary_prompt(content)
            else:
                prompt = f"Please provide a concise summary of the following content:\n\n{content}"
            
            response = self._make_request(prompt)
            
            # Extract content from response
            if "content" in response and response["content"]:
                summary_text = response["content"]
                tokens_used = response.get("usage", {}).get("output_tokens", 0)
                
                return SummaryResult(
                    success=True,
                    content=summary_text,
                    tokens_used=tokens_used
                )
            else:
                return SummaryResult(success=False, error="No content in API response")
                
        except Exception as e:
            error_str = str(e)
            
            # Handle common Gemini API errors
            if "quota" in error_str.lower() or "rate" in error_str.lower():
                error_msg = "Rate limit or quota exceeded"
            elif "api_key" in error_str.lower() or "authentication" in error_str.lower():
                error_msg = "Authentication failed - check API key"
            elif "safety" in error_str.lower() or "blocked" in error_str.lower():
                error_msg = "Content was blocked by safety filters"
            elif "token" in error_str.lower() and "limit" in error_str.lower():
                error_msg = "Content too long - exceeds token limit"
            else:
                error_msg = f"Unexpected error: {error_str}"
            
            logger.error(f"Gemini API error: {error_msg}")
            return SummaryResult(success=False, error=error_msg)
    
    def _create_media_summary_prompt(self, content: str, article_url: str = "") -> str:
        """Create a prompt for media article summarization"""
        return f"""ROLE
You are a highly skilled Senior Media Analyst and Editor, specializing in producing concise, formal, and neutral summaries of news articles for executive briefings. Your writing must be objective, information-dense, and adhere to a strict, professional format.

INPUTS YOU WILL RECEIVE
Article URL: The full URL of the original news story.
Article Text: The cleaned text content of that news story.

TASK & FORMATTING RULES
Your goal is to produce a single, perfectly formatted paragraph that summarizes the provided article. You must follow these steps precisely:

Analyze the Article URL to infer the common name of the news organization (e.g., from www.theguardian.com you should infer The Guardian). If the URL is 'Pasted Article', infer the source from the text content or state 'A provided text'.

Write a Summary:
Your summary must be a concise and neutral distillation of the key points from the Article Text.
Content Focus: Prioritize the "Five Ws" (Who, What, When, Where, Why). Identify the main subjects (people, organizations), the core event or issue, and the key outcomes or implications.
Include Key Details: If the article contains important data, statistics, or financial figures, include them in your summary to provide context and weight.
Tone and Style: Maintain a consistently formal, objective, and impartial tone. Avoid any informal language, slang, or personal opinions. Use sophisticated, professional vocabulary appropriate for a corporate or political audience.

Construct Your Response:
The entire response must be a single paragraph wrapped in <p>...</p> tags.
The response MUST begin with a hyperlink to the news organization. The link text should be the source's common name.
The hyperlink must be immediately followed by the word "reports" (e.g., The Guardian reports...).
The rest of the paragraph is your summary.
The required format is exactly: <a href="[Article URL]">[Source Name]</a> reports [your summary text here].

OUTPUT EXAMPLES (Your summary must be formatted and written exactly like these examples)

YOUR ASSIGNMENT
Now, process the following inputs based on all the rules and examples above. Respond with only the single, complete <p>...</p> HTML block.

Article URL: {article_url}
Article Text: {content}

SPECIAL RULE: If the article URL is from any BBC domain (bbc.com, bbc.co.uk, or their subdomains), always use 'BBC News' as the source name in the hyperlink, regardless of what the URL or article text says.

IMPORTANT: In your output, always use the actual Article URL provided in the input for the hyperlink. Never use a placeholder, example, or the literal text '[Article URL]'."""
    
    def _create_hansard_summary_prompt(self, content: str) -> str:
        """Create a prompt for Hansard-style parliamentary questions"""
        return f"""Based on the following media content, generate potential parliamentary questions that could be asked in the style of Hansard records. 
Focus on accountability, policy clarification, and matters of public interest that would be appropriate for parliamentary inquiry.

Content to analyze:
{content}

Please provide 2-3 well-structured parliamentary questions that could arise from this content, formatted appropriately for Hansard records."""

class AIService:
    """Service class for AI operations"""
    
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        if not api_key:
            raise ValueError("Gemini API key is required")
        
        self.client = GeminiAPIClient(api_key, model_name)
        logger.info("AI Service initialized successfully with Gemini API")
    
    def summarize_article(self, title: str, content: str, url: str) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Summarize an article - wrapper method for compatibility
        
        Args:
            title: Article title
            content: Article content
            url: Article URL
            
        Returns:
            Tuple of (success: bool, summary_dict: dict, error: str)
        """
        full_content = f"Title: {title}\n\nContent: {content}"
        result = self.summarize_content(full_content, "media", url)
        
        if result.success:
            summary_dict = {
                "summary": result.content,
                "key_points": [
                    "Technology and AI developments",
                    "Industry impact analysis", 
                    "Future implementation considerations"
                ],
                "sentiment": "neutral",
                "word_count": len(result.content.split()) if result.content else 0
            }
            return True, summary_dict, None
        else:
            return False, {}, result.error
    
    def summarize_content(self, content: str, summary_type: str = "media", article_url: str = "") -> SummaryResult:
        """
        Summarize a single piece of content
        
        Args:
            content: Text content to summarize
            summary_type: Type of summary ("media" or "hansard")
            
        Returns:
            SummaryResult with success status and content or error
        """
        # LOCAL MODE: Return mock summary instead of calling API
        if settings.LOCAL_MODE:
            logger.info(f"LOCAL_MODE: Returning mock summary for {summary_type} content")
            mock_summary = {
                "media": "MOCK SUMMARY: This article discusses recent developments in technology and artificial intelligence. Key points include advancements in machine learning, potential impacts on various industries, and considerations for future implementation. The content highlights both opportunities and challenges in the current technological landscape.",
                "hansard": "MOCK HANSARD QUESTIONS: 1. What steps is the government taking to address technological advancement impacts? 2. How will AI developments affect employment in key sectors? 3. What regulatory frameworks are being considered for emerging technologies?"
            }
            return SummaryResult(
                success=True,
                content=mock_summary.get(summary_type, mock_summary["media"]),
                tokens_used=150
            )
        
        if not content or not content.strip():
            logger.warning("Empty content provided for summarization")
            return SummaryResult(success=False, error="No content provided")
        
        # Truncate content if too long (Gemini has token limits)
        max_chars = 200000  # Gemini 1.5 Flash has higher limits than Claude
        if len(content) > max_chars:
            logger.warning(f"Content truncated from {len(content)} to {max_chars} characters")
            content = content[:max_chars] + "\n\n[Content truncated due to length]"
        
        logger.info(f"Summarizing content of {len(content)} characters")
        result = self.client.summarize(content, summary_type, article_url)
        
        if result.success:
            logger.info(f"Content summarized successfully, tokens used: {result.tokens_used}")
        else:
            logger.error(f"Content summarization failed: {result.error}")
        
        return result
    
    def batch_summarize(self, contents: List[str], summary_type: str = "media") -> List[SummaryResult]:
        """
        Summarize multiple pieces of content
        
        Args:
            contents: List of text content to summarize
            summary_type: Type of summary ("media" or "hansard")
            
        Returns:
            List of SummaryResult objects
        """
        if not contents:
            logger.warning("Empty contents list provided for batch summarization")
            return []
        
        logger.info(f"Starting batch summarization of {len(contents)} items")
        results = []
        total_tokens = 0
        
        for i, content in enumerate(contents):
            logger.info(f"Processing item {i + 1}/{len(contents)}")
            
            result = self.summarize_content(content, summary_type)
            results.append(result)
            
            if result.success and result.tokens_used:
                total_tokens += result.tokens_used
            
            # Small delay between requests to be respectful to the API
            if i < len(contents) - 1:  # Don't sleep after the last item
                time.sleep(0.5)
        
        successful_summaries = sum(1 for r in results if r.success)
        logger.info(f"Batch summarization completed: {successful_summaries}/{len(contents)} successful, {total_tokens} total tokens used")
        
        return results
    
    def combine_summaries(self, summaries: List[str], report_type: str = "media") -> str:
        """
        Combine multiple summaries into a single report
        
        Args:
            summaries: List of summary texts
            report_type: Type of report ("media" or "hansard")
            
        Returns:
            Combined report as HTML string
        """
        if not summaries:
            return "<p>No summaries available.</p>"
        
        if report_type == "media":
            title = "Media Monitoring Report"
            intro = "This report summarizes recent media articles relevant to political monitoring."
        else:
            title = "Hansard Questions Report"
            intro = "This report contains potential parliamentary questions based on recent media coverage."
        
        html_parts = [
            f"<h1>{title}</h1>",
            f"<p><em>Generated on {time.strftime('%Y-%m-%d %H:%M:%S')}</em></p>",
            f"<p>{intro}</p>",
            "<hr>"
        ]
        
        for i, summary in enumerate(summaries, 1):
            html_parts.extend([
                f"<h2>Summary {i}</h2>",
                f"<div>{summary}</div>",
                "<hr>" if i < len(summaries) else ""
            ])
        
        return "\n".join(html_parts)

def get_ai_service(api_key: str, model_name: str = "gemini-1.5-flash") -> AIService:
    """
    Factory function to get AIService instance
    
    Args:
        api_key: Gemini API key
        model_name: Gemini model name (optional)
        
    Returns:
        AIService instance
    """
    return AIService(api_key, model_name)
