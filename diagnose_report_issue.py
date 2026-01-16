#!/usr/bin/env python3
"""
Diagnostic script to identify the report data mismatch issue
"""

import sys
sys.path.insert(0, '/mnt/project')

import database
from datetime import datetime, timedelta

def get_previous_week():
    """Get previous week Monday-Sunday (same logic as report generator)"""
    today = datetime.now()
    days_since_monday = (today.weekday() - 0) % 7
    if days_since_monday == 0 and today.hour < 12:
        last_monday = today - timedelta(days=7)
    else:
        last_monday = today - timedelta(days=days_since_monday + 7)
    
    last_monday = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
    last_sunday = last_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return last_monday, last_sunday

def diagnose():
    """Check for data mismatches"""
    print("\n" + "="*70)
    print("DIAGNOSING REPORT DATA ISSUES")
    print("="*70 + "\n")
    
    # Get all brands
    conn = database.sqlite3.connect(database.DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, brand_name, domain FROM brands")
    brands = cursor.fetchall()
    conn.close()
    
    if not brands:
        print("[ERROR] No brands in database")
        return
    
    week_start, week_end = get_previous_week()
    print(f"Previous week: {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}")
    print(f"Week key: {week_start.strftime('%Y-W%U')}\n")
    
    for brand_id, brand_name, domain in brands:
        print(f"\n{'='*70}")
        print(f"BRAND: {brand_name}")
        print(f"{'='*70}")
        
        # Get snapshot data
        snapshots = database.get_snapshots_for_brand(brand_id, limit=8)
        if not snapshots:
            print("[WARNING] No snapshots found")
            continue
        
        current_week = snapshots[0]
        print(f"\n[SNAPSHOT DATA - Most Recent]")
        print(f"  Week: {current_week['week_key']}")
        print(f"  Date range: {current_week['week_start'][:10]} to {current_week['week_end'][:10]}")
        print(f"  Review count: {current_week['review_count']}")
        print(f"  Avg rating: {current_week['avg_rating']:.2f}")
        print(f"  Positive/Neutral/Negative: {current_week['positive_count']}/{current_week['neutral_count']}/{current_week['negative_count']}")
        print(f"  Organic/Verified/Invited: {current_week['organic_count']}/{current_week['verified_count']}/{current_week['invited_count']}")
        
        # Get actual review data for previous week
        reviews = database.get_reviews_for_week(brand_id, week_start.isoformat(), week_end.isoformat())
        
        print(f"\n[ACTUAL REVIEWS - Previous Week]")
        print(f"  Period: {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}")
        print(f"  Total reviews: {len(reviews)}")
        
        if reviews:
            # Language breakdown
            language_counts = {}
            for review in reviews:
                lang = review.get('language', 'unknown').upper()
                language_counts[lang] = language_counts.get(lang, 0) + 1
            
            print(f"  Languages: {dict(language_counts)}")
            
            # Rating breakdown
            positive = sum(1 for r in reviews if r['rating'] >= 4)
            neutral = sum(1 for r in reviews if r['rating'] == 3)
            negative = sum(1 for r in reviews if r['rating'] <= 2)
            print(f"  Positive/Neutral/Negative: {positive}/{neutral}/{negative}")
            
            # Source breakdown
            organic = sum(1 for r in reviews if r['source'] == 'Organic')
            verified = sum(1 for r in reviews if r['is_verified'])
            invited = len(reviews) - organic - verified
            print(f"  Organic/Verified/Invited: {organic}/{verified}/{invited}")
            
            # Check if snapshot exists for previous week
            prev_week_key = week_start.strftime('%Y-W%U')
            matching_snapshot = None
            for snap in snapshots:
                if snap['week_key'] == prev_week_key:
                    matching_snapshot = snap
                    break
            
            print(f"\n[COMPARISON]")
            if matching_snapshot:
                print(f"  ✓ Snapshot exists for previous week ({prev_week_key})")
                print(f"  Snapshot count: {matching_snapshot['review_count']}")
                print(f"  Actual count: {len(reviews)}")
                
                if matching_snapshot['review_count'] != len(reviews):
                    print(f"  ⚠️  MISMATCH DETECTED!")
                    print(f"  Difference: {len(reviews) - matching_snapshot['review_count']} reviews")
                    print(f"\n  ISSUE: Snapshot is outdated/incomplete")
                    print(f"  CAUSE: Snapshots are only updated for CURRENT week during daily scrapes")
                    print(f"  SOLUTION: Recalculate snapshot before generating report")
                else:
                    print(f"  ✓ Snapshot matches actual reviews")
            else:
                print(f"  ✗ NO snapshot found for previous week ({prev_week_key})")
                print(f"  ISSUE: Report will fail or use wrong data")
        
        print()

if __name__ == "__main__":
    diagnose()