#!/usr/bin/env python3
"""
Topic Tagging - Tags reviews with topics after daily scrape
Only processes current week + previous week (for Monday reports)
"""

import scraper
import database
import json
import sqlite3
from datetime import datetime, timedelta

DB_FILE = "trustpilot.db"

def get_target_weeks():
    """
    Get date ranges for current week and previous week
    Returns: (current_start, current_end, prev_start, prev_end)
    """
    today = datetime.now()
    
    # Current week (Monday to today)
    current_monday = today - timedelta(days=today.weekday())
    current_monday = current_monday.replace(hour=0, minute=0, second=0, microsecond=0)
    current_end = today.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Previous week (last Monday to Sunday)
    prev_monday = current_monday - timedelta(days=7)
    prev_sunday = current_monday - timedelta(seconds=1)
    
    return (
        current_monday.isoformat(),
        current_end.isoformat(),
        prev_monday.isoformat(),
        prev_sunday.isoformat()
    )

def tag_reviews_with_topics(brand_domain, brand_id, top_mentions):
    """
    For each topic, scrape filtered reviews and tag them
    Only processes current week + previous week
    """
    if not top_mentions:
        print("  [INFO] No top mentions to tag")
        return
    
    current_start, current_end, prev_start, prev_end = get_target_weeks()
    
    print(f"\n[INFO] Tagging reviews with topics ({len(top_mentions)} topics)...")
    print(f"  Target period: {prev_start[:10]} to {current_end[:10]}")
    
    # Topic mapping from readable names to TP topic IDs
    try:
        with open('tp_topics.json') as f:
            topic_map = json.load(f)
            reverse_map = {v.lower(): k for k, v in topic_map.items()}
    except:
        print("[WARNING] Could not load tp_topics.json, using direct topic names")
        reverse_map = {}
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    total_tagged = 0
    
    for topic_name in top_mentions[:10]:  # Limit to top 10
        topic_id = reverse_map.get(topic_name.lower(), topic_name.lower().replace(' ', '_'))
        
        print(f"  [INFO] Processing topic: {topic_name} (filter: {topic_id})")
        
        # Scrape with topic filter (last 30 days to cover both weeks)
        topic_data = scraper.scrape_brand(
            brand_domain,
            max_pages=10,
            use_jwt=False,
            filter_last_30_days=True,
            topic_filter=topic_id
        )
        
        if not topic_data or not topic_data.get('reviews'):
            print(f"    [INFO] No reviews found for topic: {topic_name}")
            continue
        
        # Tag each review with this topic (only if in DB and in target period)
        reviews_tagged_this_topic = 0
        
        for review in topic_data['reviews']:
            review_id = review['id']
            
            # Check if review exists in DB and is in target period
            cursor.execute("""
                SELECT topics FROM reviews
                WHERE id = ?
                AND brand_id = ?
                AND (
                    (published_date >= ? AND published_date <= ?)
                    OR (published_date >= ? AND published_date <= ?)
                )
            """, (review_id, brand_id, prev_start, prev_end, current_start, current_end))
            
            result = cursor.fetchone()
            
            if not result:
                # Review not in DB or not in target period
                continue
            
            current_topics = result[0]
            
            # Parse existing topics
            if current_topics:
                topics_list = json.loads(current_topics)
            else:
                topics_list = []
            
            # Add topic if not already present
            if topic_name not in topics_list:
                topics_list.append(topic_name)
                
                cursor.execute(
                    "UPDATE reviews SET topics = ? WHERE id = ?",
                    (json.dumps(topics_list), review_id)
                )
                total_tagged += 1
                reviews_tagged_this_topic += 1
        
        if reviews_tagged_this_topic > 0:
            print(f"    [SUCCESS] Tagged {reviews_tagged_this_topic} reviews in target period")
        else:
            print(f"    [INFO] No matching reviews in target period")
    
    conn.commit()
    conn.close()
    
    print(f"\n  [SUCCESS] Total review-topic associations created: {total_tagged}")

if __name__ == "__main__":
    print("This script is meant to be called from daily_scrape.py")
    print("It requires brand_domain, brand_id, and top_mentions as parameters")