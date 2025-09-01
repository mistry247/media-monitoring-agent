# Media Monitoring Agent

A collaborative web application for collecting, processing, and reporting on media articles. The system allows team members to submit article URLs, processes them through AI summarization, and generates automated reports that can be emailed to stakeholders.

## Features

- **Article Submission**: Team members submit URLs through a web interface
- **AI Processing**: Articles are scraped and summarized using Claude AI
- **Report Generation**: Automated reports with summaries and insights
- **Email Distribution**: Reports sent to configured recipients
- **Archive Management**: Processed articles are archived for reference

## Technology Stack

- **Backend**: FastAPI with Python 3.8+
- **Database**: SQLAlchemy ORM with SQLite
- **AI Integration**: Google Gemini API
- **Web Scraping**: BeautifulSoup4 and newspaper3k
- **Email**: N8N webhook for reliable delivery
- **Frontend**: Vanilla HTML, CSS, JavaScript

## Quick Start

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

**Windows Users:** See [WINDOWS_SETUP.md](WINDOWS_SETUP.md) for Windows-specific installation instructions.

### Installation

1. Clone the repository:
```bash
git clone https://github.com/mistry247/media-monitoring-agent.git
cd media-monitoring-agent
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Initialize the database:
```bash
python init_db.py
```

6. Run the application:
```bash
python main.py
```

The application will be available at `http://localhost:8000`

## Configuration

### Environment Variables

Create a `.env` file in the root directory with the following variables:

```env
# Database Configuration
DATABASE_URL=sqlite:///media_monitoring.db

# Claude AI Configuration
CLAUDE_API_KEY=your-claude-api-key-here
CLAUDE_API_URL=https://api.anthropic.com/v1/messages

# Email Configuration (N8N Webhook - more reliable than SMTP)
N8N_WEBHOOK_URL=https://mistry247.app.n8n.cloud/webhook/ee237986-ca83-4bfa-bfc4-74a297f49450
EMAIL_RECIPIENTS=recipient1@example.com,recipient2@example.com

# Application Settings
DEBUG=false
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
```

### Required Configuration

1. **Gemini API Key**: Get your API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
2. **Email Webhook**: N8N webhook URL is pre-configured for reliable email delivery
3. **Recipients**: Set email addresses that should receive reports

## Usage

### For Team Members

1. Open the application in your web browser
2. Fill in your name and the article URL you want to submit
3. Click "Submit Article" to add it to the pending queue

### For Core Team Members

1. Access the dashboard section of the application
2. View pending articles in the table
3. Paste any paywalled content into the text area
4. Click "Generate Media Report" to process all pending articles
5. Click "Generate Hansard Report" for parliamentary question summaries

## API Endpoints

### Article Submission
```
POST /api/articles/submit
Content-Type: application/json

{
    "url": "https://example.com/article",
    "submitted_by": "John Doe"
}
```

### Get Pending Articles
```
GET /api/articles/pending
```

### Generate Reports
```
POST /api/reports/media
Content-Type: application/json

{
    "pasted_content": "Article content here..."
}
```

```
POST /api/reports/hansard
```

## Development

### Running in Development Mode

```bash
python main.py
```

This starts the server with auto-reload enabled for development.

### Running Tests

```bash
# Run all Python tests
pytest

# Run with coverage
pytest --cov=.

# Run JavaScript tests
npm run test:js
```

### Project Structure

```
├── api/                    # FastAPI route handlers
├── models/                 # Pydantic models for validation
├── services/               # Business logic layer
├── utils/                  # Shared utilities
├── static/                 # Frontend assets
├── tests/                  # Test suite
├── main.py                 # Application entry point
├── database.py             # Database models and config
├── config.py               # Configuration management
└── init_db.py              # Database initialization
```

## Production Deployment

### Automated Deployment Script

The easiest way to deploy is using the provided deployment script:

```bash
# For systemd deployment (Linux servers)
sudo ./deployment/deploy.sh systemd

# For Docker deployment
./deployment/deploy.sh docker
```

**📋 Production Deployment Checklist:** See `deployment/PRODUCTION_CHECKLIST.md` for a comprehensive deployment checklist to ensure nothing is missed.

### Manual systemd Deployment (Linux)

1. **Prepare the system:**
```bash
# Install dependencies
sudo apt-get update
sudo apt-get install python3 python3-pip python3-venv git nginx

# Create application user
sudo useradd -r -s /bin/false -d /opt/media-monitoring-agent www-data
```

2. **Deploy the application:**
```bash
# Copy application files
sudo cp -r . /opt/media-monitoring-agent/
cd /opt/media-monitoring-agent

# Set up Python environment
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r requirements-prod.txt

# Configure environment
sudo cp .env.example .env
sudo nano .env  # Edit with your configuration

# Set permissions
sudo chown -R www-data:www-data /opt/media-monitoring-agent
```

3. **Set up systemd service:**
```bash
sudo cp deployment/media-monitoring.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable media-monitoring
sudo systemctl start media-monitoring
```

4. **Configure nginx (optional):**
```bash
sudo cp deployment/nginx.conf /etc/nginx/
sudo nginx -t
sudo systemctl restart nginx
```

### Docker Deployment

1. **Using Docker Compose (recommended):**
```bash
# Basic deployment
docker-compose up -d

# With nginx reverse proxy
docker-compose --profile with-nginx up -d
```

2. **Manual Docker deployment:**
```bash
# Build the image
docker build -t media-monitoring-agent .

# Run the container
docker run -d \
  --name media-monitoring \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  --restart unless-stopped \
  media-monitoring-agent
```

### Database Management

**Run migrations:**
```bash
# In production environment
python migrate.py migrate

# Check migration status
python migrate.py status

# In Docker
docker exec media-monitoring-agent python migrate.py migrate
```

**Backup database:**
```bash
# Manual backup
sudo ./deployment/backup.sh

# Set up automated backups (cron)
sudo crontab -e
# Add: 0 2 * * * /opt/media-monitoring-agent/deployment/backup.sh
```

### Environment-Specific Settings

**Production checklist:**

1. **Security:**
   - Set `DEBUG=False` in `.env`
   - Use strong, unique API keys
   - Configure proper CORS origins
   - Set up SSL/TLS certificates
   - Enable rate limiting

2. **Performance:**
   - Use production requirements: `pip install -r requirements-prod.txt`
   - Configure appropriate worker processes
   - Set up database connection pooling
   - Enable gzip compression in nginx

3. **Monitoring:**
   - Set up log rotation
   - Configure health checks
   - Monitor disk space for SQLite database
   - Set up alerting for service failures

4. **Backup:**
   - Schedule regular database backups
   - Test backup restoration procedures
   - Store backups in secure, off-site location

### SSL/TLS Configuration

**Using Let's Encrypt with nginx:**
```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

**Update nginx configuration:**
```bash
# Edit /etc/nginx/nginx.conf
# Update SSL certificate paths:
ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
```

## Monitoring and Maintenance

### Health Monitoring

The application includes comprehensive health checks:

```bash
# Check application health
curl http://localhost:8000/health

# Monitor service status
sudo systemctl status media-monitoring

# View real-time logs
sudo journalctl -u media-monitoring -f

# Docker monitoring
docker-compose ps
docker-compose logs -f
```

### Log Management

**Production logging configuration:**
```bash
# Create log directory
sudo mkdir -p /var/log/media-monitoring
sudo chown www-data:www-data /var/log/media-monitoring

# Configure log rotation
sudo tee /etc/logrotate.d/media-monitoring << EOF
/var/log/media-monitoring/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 www-data www-data
    postrotate
        systemctl reload media-monitoring
    endscript
}
EOF
```

### Performance Monitoring

**Key metrics to monitor:**
- Response times for API endpoints
- Database query performance
- Memory and CPU usage
- Disk space (especially for SQLite database)
- External API rate limits (Claude, email)

**Monitoring commands:**
```bash
# System resources
htop
df -h
du -sh /opt/media-monitoring-agent/

# Application metrics
curl -s http://localhost:8000/health | jq
```

### Maintenance Tasks

**Regular maintenance:**
```bash
# Update dependencies (test in staging first)
pip install -r requirements-prod.txt --upgrade

# Clean up old logs
find /var/log/media-monitoring -name "*.log.*" -mtime +30 -delete

# Vacuum SQLite database (monthly)
sqlite3 /opt/media-monitoring-agent/data/media_monitoring.db "VACUUM;"

# Check disk space
df -h /opt/media-monitoring-agent/
```

## Troubleshooting

### Common Issues

1. **Database not found**: Run `python migrate.py migrate` to initialize
2. **Gemini API errors**: Check your API key and rate limits
3. **Email not sending**: Check N8N webhook URL and recipient configuration
4. **Port already in use**: Change the PORT in your `.env` file
5. **Permission denied**: Check file ownership and permissions
6. **Service won't start**: Check systemd logs with `journalctl -u media-monitoring`

### Debugging Steps

1. **Check service status:**
```bash
sudo systemctl status media-monitoring
```

2. **View detailed logs:**
```bash
sudo journalctl -u media-monitoring -n 50
```

3. **Test configuration:**
```bash
cd /opt/media-monitoring-agent
sudo -u www-data ./venv/bin/python -c "from config import *; print('Config loaded successfully')"
```

4. **Test database connection:**
```bash
sudo -u www-data ./venv/bin/python migrate.py status
```

5. **Test external services:**
```bash
curl -X POST http://localhost:8000/health
```

### Recovery Procedures

**Service recovery:**
```bash
# Restart service
sudo systemctl restart media-monitoring

# If service fails to start, check logs and fix issues
sudo systemctl status media-monitoring
sudo journalctl -u media-monitoring -n 20
```

**Database recovery:**
```bash
# Restore from backup
cd /opt/media-monitoring-agent
sudo systemctl stop media-monitoring
sudo -u www-data cp /var/backups/media-monitoring/latest_backup.tar.gz .
sudo -u www-data tar -xzf latest_backup.tar.gz
sudo systemctl start media-monitoring
```

### Health Check

The application includes a comprehensive health check endpoint:

```
GET /health
```

Returns:
- Application status
- Database connectivity
- External service availability
- System resource usage

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## License

[Add your license information here]

## Support

For issues and questions:
- Check the troubleshooting section above
- Review application logs
- Open an issue in the repository
