#!/usr/bin/env python3
"""
SQLite Database Schema and Helper Functions
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_FILE = "trustpilot.db"

# =============================================================================
# SCHEMA CREATION
# =============================================================================

def init_db():
    """Create database tables if they don't exist"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Brands table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE NOT NULL,
            business_id TEXT NOT NULL,
            brand_name TEXT NOT NULL,
            trust_score REAL,
            stars INTEGER,
            total_reviews INTEGER,
            past_week_reviews INTEGER,
            logo_base64 TEXT,
            website TEXT,
            is_claimed BOOLEAN,
            categories TEXT,
            ai_summary_text TEXT,
            ai_summary_updated_at TEXT,
            ai_summary_language TEXT,
            ai_summary_model_version TEXT,
            created_at TEXT NOT NULL,
            last_scraped_at TEXT
        )
    """)
    
    # Reviews table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY,
            brand_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            text TEXT,
            title TEXT,
            author_name TEXT,
            author_id TEXT,
            author_image_url TEXT,
            author_review_count INTEGER,
            author_country_code TEXT,
            author_has_image BOOLEAN,
            published_date TEXT NOT NULL,
            updated_date TEXT,
            experienced_date TEXT,
            language TEXT,
            source TEXT,
            is_verified BOOLEAN,
            likes INTEGER DEFAULT 0,
            reply_message TEXT,
            reply_date TEXT,
            labels_merged TEXT,
            topics TEXT,
            scraped_at TEXT NOT NULL,
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        )
    """)
    
    # Weekly snapshots table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weekly_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id INTEGER NOT NULL,
            week_key TEXT NOT NULL,
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            review_count INTEGER,
            avg_rating REAL,
            positive_count INTEGER,
            neutral_count INTEGER,
            negative_count INTEGER,
            organic_count INTEGER,
            verified_count INTEGER,
            invited_count INTEGER,
            avg_response_time_hours REAL,
            top_mentions TEXT,
            ai_summary TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(brand_id, week_key),
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        )
    """)
    
    # Create indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_brand ON reviews(brand_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_date ON reviews(published_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_brand ON weekly_snapshots(brand_id)")
    
    conn.commit()
    conn.close()
    
    print(f"[SUCCESS] Database initialized: {DB_FILE}")

# =============================================================================
# BRAND OPERATIONS
# =============================================================================

def get_all_brand_domains():
    """Get list of all brand domains in DB"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT domain FROM brands")
    domains = [row[0] for row in cursor.fetchall()]
    conn.close()
    return domains

def add_brand(domain, company_data, logo_base64=None):
    """Add new brand to database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Extract AI summary if present
    ai_summary = company_data.get('ai_summary', {})
    if ai_summary:
        ai_summary_text = ai_summary.get('summary')
        ai_summary_updated_at = ai_summary.get('updatedAt') or ai_summary.get('updated_at')
        ai_summary_language = ai_summary.get('lang') or ai_summary.get('language')
        ai_summary_model_version = ai_summary.get('modelVersion') or ai_summary.get('model_version')
    else:
        ai_summary_text = None
        ai_summary_updated_at = None
        ai_summary_language = None
        ai_summary_model_version = None
    
    cursor.execute("""
        INSERT INTO brands (
            domain, business_id, brand_name, trust_score, stars,
            total_reviews, past_week_reviews, logo_base64, website, is_claimed,
            categories, ai_summary_text, ai_summary_updated_at, 
            ai_summary_language, ai_summary_model_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        domain,
        company_data['business_id'],
        company_data['brand_name'],
        company_data['trust_score'],
        company_data.get('stars', company_data['trust_score']),
        company_data['total_reviews'],
        company_data.get('past_week_reviews', 0),
        logo_base64,
        company_data.get('website', ''),
        company_data.get('is_claimed', False),
        json.dumps(company_data.get('categories', [])),
        ai_summary_text,
        ai_summary_updated_at,
        ai_summary_language,
        ai_summary_model_version,
        datetime.now().isoformat()
    ))
    
    brand_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    print(f"  [SUCCESS] Brand added: {company_data['brand_name']} (ID: {brand_id})")
    return brand_id

def get_brand_id(domain):
    """Get brand ID by domain"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM brands WHERE domain = ?", (domain,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def update_brand_metadata(brand_id, company_data):
    """Update brand metadata after scraping"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Extract AI summary if present
    ai_summary = company_data.get('ai_summary', {})
    if ai_summary:
        ai_summary_text = ai_summary.get('summary')
        ai_summary_updated_at = ai_summary.get('updatedAt') or ai_summary.get('updated_at')
        ai_summary_language = ai_summary.get('lang') or ai_summary.get('language')
        ai_summary_model_version = ai_summary.get('modelVersion') or ai_summary.get('model_version')
    else:
        ai_summary_text = None
        ai_summary_updated_at = None
        ai_summary_language = None
        ai_summary_model_version = None
    
    cursor.execute("""
        UPDATE brands SET
            trust_score = ?,
            stars = ?,
            total_reviews = ?,
            past_week_reviews = ?,
            ai_summary_text = ?,
            ai_summary_updated_at = ?,
            ai_summary_language = ?,
            ai_summary_model_version = ?,
            last_scraped_at = ?
        WHERE id = ?
    """, (
        company_data['trust_score'],
        company_data.get('stars', company_data['trust_score']),
        company_data['total_reviews'],
        company_data.get('past_week_reviews', 0),
        ai_summary_text,
        ai_summary_updated_at,
        ai_summary_language,
        ai_summary_model_version,
        datetime.now().isoformat(),
        brand_id
    ))
    
    conn.commit()
    conn.close()

def get_brand_info(brand_id):
    """Get brand info by ID"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM brands WHERE id = ?", (brand_id,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None

# =============================================================================
# REVIEW OPERATIONS
# =============================================================================

def insert_reviews(brand_id, reviews):
    """Insert reviews with automatic deduplication"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    inserted = 0
    skipped = 0
    
    for review in reviews:
        try:
            # Extract consumer/author data
            consumer = review.get('consumer', {})
            
            # Extract reply data
            reply = review.get('reply')
            reply_message = reply.get('message') if reply else None
            reply_date = reply.get('publishedDate') if reply else None
            
            # Extract labels merged
            labels_merged = review.get('labels', {}).get('merged')
            labels_merged_json = json.dumps(labels_merged) if labels_merged else None
            
            cursor.execute("""
                INSERT INTO reviews (
                    id, brand_id, rating, text, title,
                    author_name, author_id, author_image_url, author_review_count,
                    author_country_code, author_has_image,
                    published_date, updated_date, experienced_date,
                    language, source, is_verified, likes,
                    reply_message, reply_date, labels_merged, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                review['id'],
                brand_id,
                review['rating'],
                review.get('text', ''),
                review.get('title', ''),
                consumer.get('displayName', ''),
                consumer.get('id', ''),
                consumer.get('imageUrl', ''),
                consumer.get('numberOfReviews', 0),
                consumer.get('countryCode', ''),
                consumer.get('hasImage', False),
                review['dates']['publishedDate'],
                review['dates'].get('updatedDate'),
                review['dates'].get('experiencedDate'),
                review.get('language', ''),
                review.get('source', ''),
                review.get('labels', {}).get('verification', {}).get('isVerified', False),
                review.get('likes', 0),
                reply_message,
                reply_date,
                labels_merged_json,
                datetime.now().isoformat()
            ))
            inserted += 1
        except sqlite3.IntegrityError:
            # Duplicate review ID - skip
            skipped += 1
    
    conn.commit()
    conn.close()
    
    print(f"  [SUCCESS] Reviews: {inserted} inserted, {skipped} duplicates skipped")
    return inserted, skipped

def get_reviews_for_week(brand_id, week_start, week_end):
    """Get all reviews for a specific week"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM reviews
        WHERE brand_id = ?
        AND published_date >= ?
        AND published_date <= ?
        ORDER BY published_date DESC
    """, (brand_id, week_start, week_end))
    
    reviews = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return reviews

def get_all_reviews_for_brand(brand_id):
    """Get all reviews for a brand"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM reviews
        WHERE brand_id = ?
        ORDER BY published_date DESC
    """, (brand_id,))
    
    reviews = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return reviews

def get_latest_review_id(brand_id):
    """Get the most recent review ID for smart pagination"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id FROM reviews
        WHERE brand_id = ?
        ORDER BY published_date DESC
        LIMIT 1
    """, (brand_id,))
    
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

# =============================================================================
# WEEKLY SNAPSHOT OPERATIONS
# =============================================================================

def calculate_and_save_snapshot(brand_id, week_key, week_start, week_end, top_mentions=None, ai_summary=None):
    """Calculate weekly snapshot from reviews"""
    reviews = get_reviews_for_week(brand_id, week_start, week_end)
    
    if not reviews:
        print(f"  [WARNING] No reviews for week {week_key}")
        return
    
    # Calculate stats
    review_count = len(reviews)
    avg_rating = sum(r['rating'] for r in reviews) / review_count
    positive = sum(1 for r in reviews if r['rating'] >= 4)
    neutral = sum(1 for r in reviews if r['rating'] == 3)
    negative = sum(1 for r in reviews if r['rating'] <= 2)
    organic = sum(1 for r in reviews if r['source'] == 'Organic')
    verified = sum(1 for r in reviews if r['is_verified'])
    invited = review_count - organic - verified
    
    # Calculate average response time
    reviews_with_replies = [r for r in reviews if r.get('reply_message') and r.get('reply_date')]
    avg_response_time_hours = None
    
    if reviews_with_replies:
        response_times = []
        for r in reviews_with_replies:
            try:
                published = datetime.fromisoformat(r['published_date'].replace('Z', ''))
                replied = datetime.fromisoformat(r['reply_date'].replace('Z', ''))
                diff_hours = (replied - published).total_seconds() / 3600
                if diff_hours >= 0:
                    response_times.append(diff_hours)
            except:
                continue
        
        if response_times:
            avg_response_time_hours = sum(response_times) / len(response_times)
    
    # Save snapshot
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT OR REPLACE INTO weekly_snapshots (
            brand_id, week_key, week_start, week_end,
            review_count, avg_rating,
            positive_count, neutral_count, negative_count,
            organic_count, verified_count, invited_count,
            avg_response_time_hours,
            top_mentions, ai_summary, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        brand_id, week_key, week_start, week_end,
        review_count, avg_rating,
        positive, neutral, negative,
        organic, verified, invited,
        avg_response_time_hours,
        json.dumps(top_mentions) if top_mentions else None,
        ai_summary,
        datetime.now().isoformat()
    ))
    
    conn.commit()
    conn.close()
    
    response_time_info = f", {avg_response_time_hours:.1f}h avg response" if avg_response_time_hours else ""
    print(f"  [SUCCESS] Snapshot saved: {week_key} ({review_count} reviews, {avg_rating:.1f}★{response_time_info})")

def get_snapshots_for_brand(brand_id, limit=8):
    """Get recent weekly snapshots for a brand"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM weekly_snapshots
        WHERE brand_id = ?
        ORDER BY week_start DESC
        LIMIT ?
    """, (brand_id, limit))
    
    snapshots = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return snapshots

def get_topics_by_sentiment(brand_id, week_start, week_end):
    """
    Get topic breakdown by sentiment for a specific week
    Returns: {
        'positive': [{'topic': 'service', 'count': 5}, ...],
        'negative': [{'topic': 'refund', 'count': 8}, ...]
    }
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get all reviews for this week with topics
    cursor.execute("""
        SELECT rating, topics
        FROM reviews
        WHERE brand_id = ?
        AND published_date >= ?
        AND published_date <= ?
        AND topics IS NOT NULL
    """, (brand_id, week_start, week_end))
    
    reviews = cursor.fetchall()
    conn.close()
    
    positive_topics = {}  # 4-5 stars
    negative_topics = {}  # 1-2 stars
    
    for rating, topics_json in reviews:
        if not topics_json:
            continue
        
        topics_list = json.loads(topics_json)
        
        for topic in topics_list:
            if rating >= 4:
                positive_topics[topic] = positive_topics.get(topic, 0) + 1
            elif rating <= 2:
                negative_topics[topic] = negative_topics.get(topic, 0) + 1
    
    # Sort by count
    positive_sorted = [{'topic': t, 'count': c} for t, c in sorted(positive_topics.items(), key=lambda x: x[1], reverse=True)]
    negative_sorted = [{'topic': t, 'count': c} for t, c in sorted(negative_topics.items(), key=lambda x: x[1], reverse=True)]
    
    return {
        'positive': positive_sorted,
        'negative': negative_sorted
    }