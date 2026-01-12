#!/usr/bin/env python3
"""
Brand Onboarding - Full Historical Scrape
Scrapes until 404, stores all reviews, calculates all weekly snapshots
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
import database
import scraper

load_dotenv()

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_week_boundaries(date):
    """Get Monday-Sunday for a given date"""
    monday = date - timedelta(days=date.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return monday, sunday

def get_week_key(monday):
    """Get ISO week key like '2025-W01'"""
    return monday.strftime("%Y-W%U")

def group_reviews_by_week(reviews):
    """Group reviews into week buckets"""
    weeks = {}
    
    for review in reviews:
        pub_date = datetime.fromisoformat(review['dates']['publishedDate'].replace('Z', ''))
        week_monday, week_sunday = get_week_boundaries(pub_date)
        week_key = get_week_key(week_monday)
        
        if week_key not in weeks:
            weeks[week_key] = {
                'start': week_monday.isoformat(),
                'end': week_sunday.isoformat(),
                'reviews': []
            }
        
        weeks[week_key]['reviews'].append(review)
    
    return weeks

# =============================================================================
# ONBOARDING
# =============================================================================

def onboard_brand(domain):
    """Full onboarding process for a new brand"""
    print(f"\n{'='*70}")
    print(f"ONBOARDING: {domain}")
    print(f"{'='*70}\n")
    
    # Check if JWT is available
    jwt_token = os.getenv('JWT_ACCESS_TOKEN', '').strip()
    
    if jwt_token:
        # Step 1a: Full scrape with JWT (unlimited pages)
        print("[1/4] Full historical scrape (unlimited pages with JWT)...")
        data = scraper.scrape_brand(domain, max_pages=None, use_jwt=True, filter_last_30_days=False)
    else:
        # Step 1b: Fallback to limited scrape (10 pages, no JWT)
        print("[WARNING] JWT not found in .env - falling back to limited scrape")
        print("[1/4] Limited historical scrape (10 pages, no JWT)...")
        data = scraper.scrape_brand(domain, max_pages=10, use_jwt=False, filter_last_30_days=False)
    
    if not data:
        print("[WARNING] Scrape failed")
        return False
    
    print(f"\n[SUCCESS] Scraped {len(data['reviews'])} total reviews")
    
    # Step 2: Add brand to database (skip logo optimization for minimal setup)
    print("\n[2/3] Adding brand to database...")
    brand_id = database.add_brand(domain, data['company'], logo_base64=None)
    
    # Step 3: Insert all reviews
    print("\n[3/3] Storing reviews and calculating snapshots...")
    database.insert_reviews(brand_id, data['reviews'])
    
    # Step 5: Calculate weekly snapshots for all weeks
    weeks = group_reviews_by_week(data['reviews'])
    
    print(f"\n[SUCCESS] Calculating {len(weeks)} weekly snapshots...")
    for week_key in sorted(weeks.keys()):
        week_data = weeks[week_key]
        
        # For the most recent week, include AI summary and top mentions
        is_latest = week_key == max(weeks.keys())
        ai_summary = data['company'].get('ai_summary', {}).get('summary') if is_latest else None
        top_mentions = data['company'].get('top_mentions') if is_latest else None
        
        database.calculate_and_save_snapshot(
            brand_id,
            week_key,
            week_data['start'],
            week_data['end'],
            top_mentions,
            ai_summary
        )
    
    print(f"\n{'='*70}")
    print("[COMPLETE] ONBOARDING COMPLETE!")
    print(f"{'='*70}")
    print(f"Brand: {data['company']['brand_name']}")
    print(f"Total Reviews: {len(data['reviews'])}")
    print(f"Weeks Created: {len(weeks)}")
    print()
    
    return True