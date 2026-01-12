#!/usr/bin/env python3
"""
Trustpilot Scraper
Supports JWT authentication and unlimited pagination
"""

import json
import requests
import re
from datetime import datetime, timedelta
import time
import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

QUERY_PARAMS = "?date=last30days&languages=all"

def get_headers(use_jwt=False):
    """Get headers with optional JWT"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    if use_jwt:
        jwt_token = os.getenv('JWT_ACCESS_TOKEN', '').strip()
        if jwt_token:
            headers["Cookie"] = f"jwt={jwt_token}"
            print("[SUCCESS] Using JWT authentication (for unlimited scraping)")
        else:
            print("[WARNING] JWT not found in .env, proceeding without authentication")
    
    return headers

# Load topic translation map
try:
    with open('tp_topics.json') as f:
        ALL_TOPICS = json.load(f)
        print(f"[SUCCESS] Loaded {len(ALL_TOPICS)} Trustpilot topics")
except FileNotFoundError:
    print("[WARNING] tp_topics.json not found, topic translation disabled")
    ALL_TOPICS = {}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def extract_next_data(html):
    """Extract __NEXT_DATA__ JSON from HTML"""
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
    if match:
        return json.loads(match.group(1))
    return None

def get_top_mentions(business_id):
    """Fetch and translate top mentions/topics for the business"""
    url = f'https://www.trustpilot.com/api/businessunitprofile/businessunit/{business_id}/service-reviews/topics'
    try:
        response = requests.get(url, headers=get_headers())
        response_data = json.loads(response.text)
        
        options = response_data['topics']
        
        translated_topics = []
        for topic in options:
            readable_name = ALL_TOPICS.get(topic, topic.replace('_', ' ').title())
            translated_topics.append(readable_name)
        
        return translated_topics
    except Exception as e:
        print(f"  [WARNING] Failed to fetch top mentions: {e}")
        return []

def count_past_week_reviews(reviews):
    """Count reviews from the past 7 days"""
    week_ago = datetime.now() - timedelta(days=7)
    count = 0
    
    for review in reviews:
        try:
            pub_date = review['dates']['publishedDate']
            review_date = datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%S.%fZ")
            if review_date >= week_ago:
                count += 1
        except:
            continue
    
    return count

# =============================================================================
# MAIN SCRAPER
# =============================================================================

def scrape_brand(brand_domain, max_pages=10, use_jwt=False, last_review_id=None, filter_last_30_days=False, topic_filter=None):
    """
    Scrape a single brand
    max_pages=None for unlimited (onboarding with JWT)
    max_pages=N for limited scraping (daily, no JWT)
    last_review_id=ID to stop early when found (optimization)
    filter_last_30_days=True for daily scrapes (last 30 days only)
    topic_filter=str topic ID to filter by specific topic (e.g., "fraud", "refund")
    """
    print(f"\n{'='*70}")
    print(f"SCRAPING: {brand_domain}")
    if topic_filter:
        print(f"TOPIC FILTER: {topic_filter}")
    print(f"{'='*70}\n")
    
    BASE_URL_CLEAN = f"https://www.trustpilot.com/review/{brand_domain}"
    
    # Build query params
    params = ["languages=all"]
    if filter_last_30_days:
        params.append("date=last30days")
    if topic_filter:
        params.append(f"topics={topic_filter}")
    
    BASE_URL = f"{BASE_URL_CLEAN}?{'&'.join(params)}"
    
    all_reviews = []
    company_data = {}
    business_id = None
    found_last_review = False
    
    headers = get_headers(use_jwt=use_jwt)
    
    # Step 1: Fetch AI Summary from clean URL
    print(f"[1] Fetching AI summary and company info...")
    response_clean = requests.get(BASE_URL_CLEAN, headers=headers)
    
    if response_clean.status_code != 200:
        print(f"[WARNING] Failed to fetch page: HTTP {response_clean.status_code}")
        return None
    
    data_clean = extract_next_data(response_clean.text)
    if not data_clean:
        print("[WARNING] Could not extract data from page")
        return None
    
    # Step 2: Fetch reviews (with or without filter)
    if topic_filter:
        print(f"[2] Fetching reviews filtered by topic: {topic_filter}...")
    elif filter_last_30_days:
        print(f"[2] Fetching filtered reviews (last 30 days)...")
    else:
        print(f"[2] Fetching reviews (all time)...")
    response = requests.get(BASE_URL, headers=headers)
    
    if response.status_code != 200:
        data = data_clean
    else:
        data = extract_next_data(response.text)
        if not data:
            data = data_clean
    
    try:
        # Get AI summary from clean URL data
        page_props_clean = data_clean["props"]["pageProps"]
        business_unit = page_props_clean["businessUnit"]
        
        # Get reviews from filtered URL data
        page_props = data["props"]["pageProps"]
        
        # Extract company information
        company_data = {
            "brand_name": business_unit["displayName"],
            "business_id": business_unit["id"],
            "website": business_unit.get("websiteUrl", "N/A"),
            "logo_url": business_unit.get("profileImageUrl", ""),
            "total_reviews": business_unit["numberOfReviews"],
            "trust_score": business_unit["trustScore"],
            "stars": business_unit.get("stars", business_unit["trustScore"]),
            "is_claimed": business_unit.get("isClaimed", False),
            "categories": [cat["name"] for cat in business_unit.get("categories", [])],
        }
        
        # Fix logo URL
        if company_data["logo_url"] and company_data["logo_url"].startswith("//"):
            company_data["logo_url"] = "https:" + company_data["logo_url"]
        
        business_id = company_data["business_id"]
        
        # Get AI Summary
        ai_summary_data = page_props_clean.get("aiSummary")
        if ai_summary_data:
            company_data["ai_summary"] = {
                "summary": ai_summary_data.get("summary", "N/A"),
                "updated_at": ai_summary_data.get("updatedAt", "N/A"),
                "language": ai_summary_data.get("lang", "en"),
                "model_version": ai_summary_data.get("modelVersion", "N/A")
            }
            print("  [SUCCESS] AI Summary extracted")
        else:
            company_data["ai_summary"] = None
            print("  [WARNING] No AI Summary available")
        
        # Get initial reviews
        initial_reviews = page_props.get("reviews", [])
        
        # Check if we found the last saved review on page 1
        if last_review_id:
            for review in initial_reviews:
                if review['id'] == last_review_id:
                    found_last_review = True
                    print(f"  [WARNING] Found last saved review on page 1 - stopping early")
                    break
        
        all_reviews.extend(initial_reviews)
        print(f"  [SUCCESS] Extracted {len(initial_reviews)} reviews from page 1")
        
        # Get Top Mentions
        if business_id:
            company_data["top_mentions"] = get_top_mentions(business_id)
        
        print(f"\n[SUCCESS] Company Data Extracted:")
        print(f"    Brand: {company_data['brand_name']}")
        print(f"    Total Reviews: {company_data['total_reviews']}")
        print(f"    Trust Score: {company_data['trust_score']}/5")
        
    except KeyError as e:
        print(f"[WARNING] Failed to extract company data: {e}")
        return None
    
    # Pagination
    if not found_last_review and (max_pages is None or max_pages > 1):
        page_limit = max_pages if max_pages else 9999
        print(f"\n[3] Fetching additional pages (up to {page_limit if max_pages else 'unlimited'})...")
        page = 2
        
        while page <= page_limit:
            print(f"\n  Fetching page {page}...")
            url = f"{BASE_URL}&page={page}"
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 404:
                print(f"  [STOPPED] Reached end of pages (404)")
                break
            
            if response.status_code != 200:
                print(f"  [WARNING] HTTP {response.status_code}, stopping")
                break
            
            data = extract_next_data(response.text)
            if not data:
                break
            
            try:
                reviews = data["props"]["pageProps"]["reviews"]
                if not reviews:
                    print(f"  [STOPPED] No more reviews")
                    break
                
                # Check for last saved review
                if last_review_id:
                    for review in reviews:
                        if review['id'] == last_review_id:
                            found_last_review = True
                            print(f"  [WARNING] Found last saved review - stopping early")
                            break
                
                all_reviews.extend(reviews)
                print(f"  [SUCCESS] Extracted {len(reviews)} reviews (Total: {len(all_reviews)})")
                
                # Stop if we found the last review
                if found_last_review:
                    break
                
            except KeyError:
                break
            
            page += 1
            time.sleep(1)  # Be polite
    
    # Calculate past week reviews
    past_week_count = count_past_week_reviews(all_reviews)
    company_data["past_week_reviews"] = past_week_count
    
    # Compile final result
    result = {
        "company": company_data,
        "reviews": all_reviews,
        "extraction_date": datetime.now().isoformat(),
        "total_reviews_extracted": len(all_reviews)
    }
    
    print(f"\n{'='*70}")
    print("EXTRACTION COMPLETE")
    print(f"{'='*70}")
    print(f"Total Reviews Extracted: {len(all_reviews)}")
    print(f"Past Week Reviews: {past_week_count}")
    
    return result