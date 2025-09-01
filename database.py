"""
Database configuration and models for Media Monitoring Agent
"""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from config import settings

# Create SQLAlchemy engine
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()

class PendingArticle(Base):
    """Model for articles pending processing"""
    __tablename__ = "pending_articles"
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, nullable=False, index=True)
    pasted_text = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    submitted_by = Column(String, nullable=False)

class ProcessedArchive(Base):
    """Model for processed articles archive"""
    __tablename__ = "processed_archive"
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    submitted_by = Column(String, nullable=False)
    processed_date = Column(DateTime, default=datetime.utcnow, nullable=False)

class HansardQuestion(Base):
    """Model for Hansard questions"""
    __tablename__ = "hansard_questions"
    
    id = Column(Integer, primary_key=True, index=True)
    question_text = Column(Text, nullable=False)
    category = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    source_articles = Column(Text, nullable=True)  # JSON array of related article IDs

class ManualInputArticle(Base):
    """Model for manually input articles for processing"""
    __tablename__ = "manual_input_articles"
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=False, index=True)
    submitted_by = Column(String, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    article_content = Column(Text, nullable=True)  # Can store long article text, initially empty/null

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_database():
    """Initialize database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully")
        return True
    except Exception as e:
        print(f"Error creating database tables: {e}")
        return False

def init_db():
    """Alias for init_database for compatibility"""
    return init_database()

def check_database_connection():
    """Check if database connection is working"""
    try:
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except Exception as e:
        print(f"Database connection error: {e}")
        return False
