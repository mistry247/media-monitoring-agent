#!/usr/bin/env python3
"""
Database initialization script for Media Monitoring Agent

This script creates the database tables and performs initial setup.
Run this script once before starting the application for the first time.
"""

import os
import sys
import logging
from pathlib import Path

# Add the current directory to Python path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

try:
    from database import init_database, check_database_connection, engine, Base
    from config import settings
    import sqlalchemy
    from sqlalchemy import text
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Make sure you have installed all dependencies with: pip install -r requirements.txt")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_data_directory():
    """Create data directory if it doesn't exist"""
    try:
        # Extract directory from database URL if it's SQLite
        db_url = settings.DATABASE_URL
        if db_url.startswith('sqlite:///'):
            db_path = db_url.replace('sqlite:///', '')
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"Created database directory: {db_dir}")
    except Exception as e:
        logger.warning(f"Could not create data directory: {e}")

def check_existing_tables():
    """Check if tables already exist"""
    try:
        with engine.connect() as conn:
            # Check if any of our tables exist
            result = conn.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name IN ('pending_articles', 'processed_archive', 'hansard_questions', 'manual_input_articles')
            """))
            existing_tables = [row[0] for row in result.fetchall()]
            return existing_tables
    except Exception as e:
        logger.error(f"Error checking existing tables: {e}")
        return []

def initialize_database():
    """Initialize the database with all required tables"""
    try:
        logger.info("Starting database initialization...")
        
        # Create data directory if needed
        create_data_directory()
        
        # Check for existing tables
        existing_tables = check_existing_tables()
        if existing_tables:
            logger.info(f"Found existing tables: {existing_tables}")
            response = input("Database tables already exist. Do you want to recreate them? (y/N): ")
            if response.lower() != 'y':
                logger.info("Skipping database initialization")
                return True
            
            # Drop existing tables
            logger.warning("Dropping existing tables...")
            Base.metadata.drop_all(bind=engine)
            logger.info("Existing tables dropped")
        
        # Create all tables
        logger.info("Creating database tables...")
        success = init_database()
        
        if success:
            logger.info("✅ Database initialized successfully!")
            
            # Verify tables were created
            created_tables = check_existing_tables()
            logger.info(f"Created tables: {created_tables}")
            
            # Test database connection
            if check_database_connection():
                logger.info("✅ Database connection test passed!")
                return True
            else:
                logger.error("❌ Database connection test failed!")
                return False
        else:
            logger.error("❌ Database initialization failed!")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error during database initialization: {e}")
        return False

def show_configuration_info():
    """Display configuration information"""
    logger.info("=== Configuration Information ===")
    logger.info(f"Database URL: {settings.DATABASE_URL}")
    logger.info(f"Gemini API Key configured: {'Yes' if settings.GEMINI_API_KEY else 'No'}")
    logger.info(f"N8N Webhook URL: {settings.N8N_WEBHOOK_URL}")
    logger.info(f"Email Recipients: {len(settings.EMAIL_RECIPIENTS)} configured")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info(f"Log Level: {settings.LOG_LEVEL}")
    logger.info("================================")

def main():
    """Main initialization function"""
    print("Media Monitoring Agent - Database Initialization")
    print("=" * 50)
    
    try:
        # Show configuration
        show_configuration_info()
        
        # Initialize database
        success = initialize_database()
        
        if success:
            print("\n🎉 Database initialization completed successfully!")
            print("\nNext steps:")
            print("1. Configure your .env file with API keys and settings")
            print("2. Run the application with: python main.py")
            print("3. Open http://localhost:8000 in your browser")
            return 0
        else:
            print("\n❌ Database initialization failed!")
            print("\nTroubleshooting:")
            print("1. Check that you have write permissions in the current directory")
            print("2. Verify your DATABASE_URL in the .env file")
            print("3. Make sure SQLite is available on your system")
            return 1
            
    except KeyboardInterrupt:
        print("\n\nInitialization cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"\n❌ Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
