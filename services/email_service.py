"""
Email service for sending media reports via n8n webhook
"""
import requests
import logging
from typing import List, Dict, Any
from datetime import datetime
from config import settings

logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending HTML email reports via n8n webhook"""
    
    def __init__(self):
        pass
    
    @property
    def webhook_url(self):
        return getattr(settings, 'N8N_WEBHOOK_URL', 'https://placeholder-webhook-url.com/webhook')
    
    def send_report(self, html_content: str, recipients: List[str] = None, subject: str = None) -> bool:
        """
        Send HTML email report via n8n webhook
        
        Args:
            html_content: HTML content of the report
            recipients: List of email addresses (uses first recipient if provided)
            subject: Email subject (uses default if None)
            
        Returns:
            bool: True if webhook request sent successfully, False otherwise
        """
        try:
            # Use the first recipient if provided, otherwise use a default
            recipient = recipients[0] if recipients and len(recipients) > 0 else "default@example.com"
            
            if subject is None:
                subject = f"Media Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            # Prepare webhook payload
            payload = {
                "recipient": recipient,
                "subject": subject,
                "body": html_content
            }
            
            # Send webhook request
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Email report sent successfully via webhook to {recipient}")
                return True
            else:
                logger.error(f"Webhook request failed with status {response.status_code}: {response.text}")
                return False
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send webhook request: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Failed to send email report via webhook: {str(e)}")
            return False
    
    def format_html_report(self, summaries: List[Dict[str, Any]], report_type: str = "Media Report") -> str:
        """
        Format summaries into HTML report template
        
        Args:
            summaries: List of article summaries with metadata
            report_type: Type of report (e.g., "Media Report", "Hansard Report")
            
        Returns:
            str: Formatted HTML content
        """
        current_date = datetime.now().strftime('%B %d, %Y at %H:%M')
        
        html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report_type}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f4f4f4;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            border-bottom: 3px solid #007bff;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #007bff;
            margin: 0;
            font-size: 2.2em;
        }}
        .date {{
            color: #666;
            font-size: 1.1em;
            margin-top: 10px;
        }}
        .summary-section {{
            margin-bottom: 40px;
            padding: 20px;
            border-left: 4px solid #007bff;
            background-color: #f8f9fa;
        }}
        .summary-title {{
            font-size: 1.3em;
            font-weight: bold;
            color: #007bff;
            margin-bottom: 10px;
        }}
        .summary-content {{
            font-size: 1em;
            line-height: 1.7;
        }}
        .source-info {{
            margin-top: 15px;
            padding-top: 10px;
            border-top: 1px solid #ddd;
            font-size: 0.9em;
            color: #666;
        }}
        .source-url {{
            word-break: break-all;
            color: #007bff;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            color: #666;
            font-size: 0.9em;
        }}
        .no-content {{
            text-align: center;
            color: #666;
            font-style: italic;
            padding: 40px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{report_type}</h1>
            <div class="date">Generated on {current_date}</div>
        </div>
        
        <div class="content">
"""
        
        if not summaries:
            html_template += """
            <div class="no-content">
                <p>No articles were processed for this report.</p>
            </div>
"""
        else:
            for i, summary in enumerate(summaries, 1):
                title = summary.get('title', f'Article {i}')
                content = summary.get('summary', summary.get('content', 'No summary available'))
                source_url = summary.get('url', '')
                submitted_by = summary.get('submitted_by', 'Unknown')
                
                html_template += f"""
            <div class="summary-section">
                <div class="summary-title">{title}</div>
                <div class="summary-content">{content}</div>
                <div class="source-info">
                    <strong>Submitted by:</strong> {submitted_by}<br>
"""
                
                if source_url:
                    html_template += f"""
                    <strong>Source:</strong> <a href="{source_url}" class="source-url">{source_url}</a>
"""
                
                html_template += """
                </div>
            </div>
"""
        
        html_template += f"""
        </div>
        
        <div class="footer">
            <p>This report was automatically generated by the Media Monitoring Agent.</p>
            <p>Report contains {len(summaries)} article{'s' if len(summaries) != 1 else ''}.</p>
        </div>
    </div>
</body>
</html>
"""
        
        return html_template

# Global email service instance
email_service = EmailService()
