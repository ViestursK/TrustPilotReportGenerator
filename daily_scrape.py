#!/usr/bin/env python3
"""
Daily incremental scrape with auto-onboarding
1. Checks for new brands → triggers onboarding
2. Scrapes existing brands (last 30 days, max 10 pages)
3. Updates database with deduplication
"""
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import database
import scraper
import onboarding

load_dotenv()

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_week_boundaries(date=None):
    """Get Monday-Sunday for a given date (or today)"""
    if date is None:
        date = datetime.now()
    
    monday = date - timedelta(days=date.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    
    return monday, sunday

def get_week_key(monday):
    """Get ISO week key like '2025-W01'"""
    return monday.strftime("%Y-W%U")

# =============================================================================
# DAILY SCRAPE FOR EXISTING BRAND
# =============================================================================

def daily_scrape_brand(domain, brand_id):
    """Daily scrape for an existing brand (no JWT, smart pagination)"""
    print(f"\n{'='*60}")
    print(f"DAILY SCRAPE: {domain}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print('='*60)
    
    # Get last saved review ID for smart pagination
    last_review_id = database.get_latest_review_id(brand_id)
    if last_review_id:
        print(f"[INFO] Last saved review: {last_review_id}")
    
    # Scrape last 30 days (max 10 pages, no JWT, stop early if found)
    max_pages = int(os.getenv('MAX_PAGES', 10))
    print(f"\n[INFO] Scraping last 30 days (max {max_pages} pages, public data)...")
    new_data = scraper.scrape_brand(
        domain, 
        max_pages=max_pages, 
        use_jwt=False,  # No JWT for daily scrapes
        last_review_id=last_review_id,  # Stop early when found
        filter_last_30_days=True  # Only last 30 days for daily updates
    )
    
    if not new_data:
        print("[WARNING] Scrape failed")
        return False
    
    print(f"[INFO] Retrieved {len(new_data['reviews'])} reviews")
    
    # Update brand metadata
    database.update_brand_metadata(brand_id, new_data['company'])
    
    # Insert reviews (with deduplication)
    inserted, skipped = database.insert_reviews(brand_id, new_data['reviews'])
    
    if inserted == 0:
        print("[WARNING] No new reviews")
        # Still tag topics even if no new reviews (might be updating existing ones)
    
    # Tag reviews with topics (multilingual support)
    top_mentions = new_data['company'].get('top_mentions', [])
    if top_mentions:
        import tag_topics
        tag_topics.tag_reviews_with_topics(domain, brand_id, top_mentions)
    
    # Update current week snapshot
    today = datetime.now()
    current_monday, current_sunday = get_week_boundaries(today)
    week_key = get_week_key(current_monday)
    
    print(f"\n[INFO] Updating current week snapshot: {week_key}")
    database.calculate_and_save_snapshot(
        brand_id,
        week_key,
        current_monday.isoformat(),
        current_sunday.isoformat(),
        new_data['company'].get('top_mentions'),
        new_data['company'].get('ai_summary', {}).get('summary')
    )
    
    print(f"\n[COMPLETE] Daily scrape complete")
    return True

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("\n" + "="*70)
    print("DAILY SCRAPE AUTOMATION")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*70)
    
    # Initialize database
    database.init_db()
    
    # Get brands from .env
    brands_env = os.getenv('BRANDS', '').split(',')
    brands_env = [b.strip() for b in brands_env if b.strip()]
    
    if not brands_env:
        print("[WARNING] No brands found in .env file")
        return
    
    # Get existing brands from DB
    existing_brands = database.get_all_brand_domains()
    
    # Check for new brands
    new_brands = [b for b in brands_env if b not in existing_brands]
    
    if new_brands:
        print(f"\n{'='*70}")
        print(f"[WARNING] NEW BRANDS DETECTED: {len(new_brands)}")
        print(f"{'='*70}")
        for brand in new_brands:
            print(f"  - {brand}")
        
        print("\n[INFO] Starting onboarding process...")
        for brand in new_brands:
            try:
                onboarding.onboard_brand(brand)
            except Exception as e:
                print(f"\n[WARNING] Onboarding failed for {brand}: {e}")
                import traceback
                traceback.print_exc()
        
        # Refresh existing brands list
        existing_brands = database.get_all_brand_domains()
    
    # Daily scrape for all existing brands (excluding newly onboarded ones)
    brands_to_scrape = [b for b in existing_brands if b not in new_brands]
    
    if brands_to_scrape:
        print(f"\n{'='*70}")
        print(f"DAILY SCRAPE: {len(brands_to_scrape)} BRANDS")
        print(f"{'='*70}")
        
        for brand in brands_to_scrape:
            brand_id = database.get_brand_id(brand)
            try:
                daily_scrape_brand(brand, brand_id)
            except Exception as e:
                print(f"\n[WARNING] Error scraping {brand}: {e}")
                import traceback
                traceback.print_exc()
    else:
        print(f"\n[INFO] No existing brands to scrape (all were just onboarded)")
    
    print("\n" + "="*70)
    print("[COMPLETE] DAILY SCRAPE COMPLETE")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()