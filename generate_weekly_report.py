#!/usr/bin/env python3
"""
FIXED: Weekly Trustpilot Report Generator
- Recalculates previous week snapshot before generating report
- Ensures snapshot data matches actual review data
"""

import os
import json
import requests
import io
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import database

load_dotenv()

SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive.file'
]

QUICKCHART_URL = "https://quickchart.io/chart"

# =============================================================================
# AUTH
# =============================================================================

def get_google_services():
    """Initialize Google APIs"""
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        return {
            'docs': build('docs', 'v1', credentials=creds),
            'drive': build('drive', 'v3', credentials=creds)
        }
    elif os.path.exists('service_account.json'):
        creds = service_account.Credentials.from_service_account_file(
            'service_account.json', scopes=SCOPES)
        return {
            'docs': build('docs', 'v1', credentials=creds),
            'drive': build('drive', 'v3', credentials=creds)
        }
    return None

# =============================================================================
# WEEK HELPERS
# =============================================================================

def get_previous_week():
    """Get previous week Monday-Sunday"""
    today = datetime.now()
    days_since_monday = (today.weekday() - 0) % 7
    if days_since_monday == 0 and today.hour < 12:
        last_monday = today - timedelta(days=7)
    else:
        last_monday = today - timedelta(days=days_since_monday + 7)
    
    last_monday = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
    last_sunday = last_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return last_monday, last_sunday

def get_week_key(monday):
    """Get ISO week key like '2025-W01'"""
    return monday.strftime("%Y-W%U")

# =============================================================================
# CHART GENERATION (unchanged)
# =============================================================================

def create_rating_chart(snapshots):
    """Rating trend chart"""
    weeks = [s['week_key'] for s in reversed(snapshots)]
    ratings = [s['avg_rating'] for s in reversed(snapshots)]
    
    chart_config = {
        "type": "line",
        "data": {
            "labels": weeks,
            "datasets": [{
                "label": "Rating",
                "data": ratings,
                "borderColor": "#3b82f6",
                "backgroundColor": "rgba(59, 130, 246, 0.1)",
                "borderWidth": 3,
                "pointRadius": 5,
                "pointBackgroundColor": "#3b82f6",
                "pointBorderColor": "#ffffff",
                "pointBorderWidth": 2,
                "tension": 0.3,
                "fill": True
            }]
        },
        "options": {
            "responsive": True,
            "plugins": {
                "legend": {"display": False},
                "title": {
                    "display": True,
                    "text": "8-Week Rating Trend",
                    "font": {"size": 16}
                }
            },
            "scales": {
                "y": {
                    "min": 1,
                    "max": 5,
                    "ticks": {"stepSize": 0.5}
                }
            }
        }
    }
    
    params = {"c": json.dumps(chart_config), "width": 600, "height": 300, "backgroundColor": "white"}
    response = requests.get(QUICKCHART_URL, params=params)
    return io.BytesIO(response.content) if response.status_code == 200 else None

def create_sentiment_chart(positive, neutral, negative):
    """Sentiment pie chart"""
    total = positive + neutral + negative
    if total == 0:
        return None
    
    chart_config = {
        "type": "doughnut",
        "data": {
            "labels": [
                f"Positive ({positive/total*100:.0f}%)",
                f"Neutral ({neutral/total*100:.0f}%)",
                f"Negative ({negative/total*100:.0f}%)"
            ],
            "datasets": [{
                "data": [positive, neutral, negative],
                "backgroundColor": ["#10b981", "#f59e0b", "#ef4444"],
                "borderColor": "#000000",
                "borderWidth": 1
            }]
        },
        "options": {
            "responsive": True,
            "plugins": {
                "legend": {"display": True, "position": "bottom"},
                "title": {
                    "display": True,
                    "text": "Sentiment Distribution",
                    "font": {"size": 46}
                }
            }
        }
    }
    
    params = {"c": json.dumps(chart_config), "width": 400, "height": 300, "backgroundColor": "white"}
    response = requests.get(QUICKCHART_URL, params=params)
    return io.BytesIO(response.content) if response.status_code == 200 else None

def create_volume_chart(snapshots):
    """Volume bar chart"""
    weeks = [s['week_key'] for s in reversed(snapshots)]
    volumes = [s['review_count'] for s in reversed(snapshots)]
    
    chart_config = {
        "type": "bar",
        "data": {
            "labels": weeks,
            "datasets": [{
                "data": volumes,
                "backgroundColor": "rgba(139, 92, 246, 0.7)",
                "borderColor": "#8b5cf6",
                "borderWidth": 1,
                "borderRadius": 4
            }]
        },
        "options": {
            "responsive": True,
            "plugins": {
                "legend": {"display": False},
                "title": {
                    "display": True,
                    "text": "Review Volume Trend",
                    "font": {"size": 16}
                }
            },
            "scales": {
                "y": {"beginAtZero": True}
            }
        }
    }
    
    params = {"c": json.dumps(chart_config), "width": 600, "height": 300, "backgroundColor": "white"}
    response = requests.get(QUICKCHART_URL, params=params)
    return io.BytesIO(response.content) if response.status_code == 200 else None

def upload_image_to_drive(services, image_bytes, filename):
    """Upload image to Drive"""
    if not image_bytes:
        return None
    
    image_bytes.seek(0)
    file_metadata = {'name': filename, 'mimeType': 'image/png'}
    media = MediaIoBaseUpload(image_bytes, mimetype='image/png', resumable=True)
    
    file = services['drive'].files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    
    services['drive'].permissions().create(
        fileId=file['id'],
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()
    
    return f"https://drive.google.com/uc?export=view&id={file['id']}"

# =============================================================================
# DATA PREPARATION 
# =============================================================================

def prepare_report_data(brand_id, week_start, week_end):
    """Prepare all data from database - RECALCULATES snapshot to ensure accuracy"""
    brand = database.get_brand_info(brand_id)
    if not brand:
        return None
    
    # 🔧 FIX: Recalculate the previous week's snapshot before generating report
    week_key = get_week_key(week_start)
    print(f"[FIX] Recalculating snapshot for {week_key} to ensure data accuracy...")
    database.calculate_and_save_snapshot(
        brand_id,
        week_key,
        week_start.isoformat(),
        week_end.isoformat(),
        None,  # top_mentions - will be calculated from reviews
        brand.get('ai_summary_text')  # Use latest AI summary from brand
    )
    
    # Now get fresh snapshots (including the one we just recalculated)
    snapshots = database.get_snapshots_for_brand(brand_id, limit=8)
    if not snapshots:
        return None
    
    # Find the snapshot for the week we're reporting on
    current_week = None
    for snap in snapshots:
        if snap['week_key'] == week_key:
            current_week = snap
            break
    
    if not current_week:
        print(f"[ERROR] Could not find snapshot for {week_key} after recalculation")
        return None
    
    # Get previous week for WoW comparison
    previous_week = None
    for snap in snapshots:
        if snap['week_key'] < week_key:
            previous_week = snap
            break
    
    # Get actual reviews for language breakdown
    reviews = database.get_reviews_for_week(brand_id, week_start.isoformat(), week_end.isoformat())
    
    # Language breakdown
    language_counts = {}
    for review in reviews:
        lang = review.get('language', 'unknown').upper()
        language_counts[lang] = language_counts.get(lang, 0) + 1
    
    languages_text = '\n'.join([f"• {lang}: {count} reviews" for lang, count in sorted(language_counts.items(), key=lambda x: x[1], reverse=True)])
    
    # WoW changes
    review_change = 0
    rating_change = 0
    if previous_week:
        review_change = current_week['review_count'] - previous_week['review_count']
        rating_change = current_week['avg_rating'] - previous_week['avg_rating']
    
    review_change_pct = (review_change / previous_week['review_count'] * 100) if previous_week and previous_week['review_count'] > 0 else 0
    
    # Topics
    topics = database.get_topics_by_sentiment(brand_id, week_start.isoformat(), week_end.isoformat())
    
    positive_topics_text = '\n'.join([f"• {t['topic']} ({t['count']} mentions)" for t in topics['positive'][:5]]) or "No significant positive topics this week"
    negative_topics_text = '\n'.join([f"• {t['topic']} ({t['count']} mentions)" for t in topics['negative'][:5]]) or "No significant negative topics this week"
    
    # Response metrics
    reviews_with_replies = sum(1 for r in reviews if r.get('reply_message'))
    response_rate = (reviews_with_replies / len(reviews) * 100) if reviews else 0
    
    avg_response_time = current_week['avg_response_time_hours']
    if avg_response_time is None or avg_response_time == 0:
        response_time_text = "N/A (no responses this week)"
    elif avg_response_time < 1:
        response_time_text = f"{avg_response_time * 60:.0f} minutes"
    elif avg_response_time < 24:
        response_time_text = f"{avg_response_time:.1f} hours"
    else:
        response_time_text = f"{avg_response_time / 24:.1f} days"
    
    # AI Summary
    ai_summary_text = "No AI summary available for this period."
    if brand.get('ai_summary_text'):
        ai_summary_text = f"{brand['ai_summary_text']}\n\nGenerated: {brand.get('ai_summary_updated_at', 'Unknown')} | Model: {brand.get('ai_summary_model_version', 'N/A')}"
    
    total = current_week['review_count']
    
    print(f"[INFO] Data validated: {total} reviews in snapshot = {len(reviews)} actual reviews ✓")
    
    return {
        'brand_name': brand['brand_name'],
        'date_range': f"{week_start.strftime('%B %d, %Y')} → {week_end.strftime('%B %d, %Y')}",
        'generated_date': datetime.now().strftime('%B %d, %Y at %I:%M %p'),
        'total_reviews': str(total),
        'avg_rating': f"{current_week['avg_rating']:.2f}",
        'review_change': f"{review_change:+d}",
        'review_change_pct': f"{review_change_pct:+.1f}",
        'positive_count': str(current_week['positive_count']),
        'positive_pct': f"{current_week['positive_count']/total*100:.1f}" if total > 0 else "0",
        'neutral_count': str(current_week['neutral_count']),
        'neutral_pct': f"{current_week['neutral_count']/total*100:.1f}" if total > 0 else "0",
        'negative_count': str(current_week['negative_count']),
        'negative_pct': f"{current_week['negative_count']/total*100:.1f}" if total > 0 else "0",
        'organic_count': str(current_week['organic_count']),
        'organic_pct': f"{current_week['organic_count']/total*100:.1f}" if total > 0 else "0",
        'verified_count': str(current_week['verified_count']),
        'verified_pct': f"{current_week['verified_count']/total*100:.1f}" if total > 0 else "0",
        'invited_count': str(current_week['invited_count']),
        'invited_pct': f"{current_week['invited_count']/total*100:.1f}" if total > 0 else "0",
        'languages': languages_text,
        'response_rate': f"{response_rate:.1f}",
        'avg_response_time': response_time_text,
        'positive_topics': positive_topics_text,
        'negative_topics': negative_topics_text,
        'ai_summary': ai_summary_text,
        'snapshots': snapshots,
        'current_week': current_week
    }

# =============================================================================
# TEMPLATE FUNCTIONS (unchanged)
# =============================================================================

def create_universal_template(services):
    """Create ONE universal template for all brands"""
    
    template_content = """Weekly Trustpilot Report

Client: {{brand_name}}
Period: {{date_range}}
Generated: {{generated_date}}

═══════════════════════════════════════════════

KEY PERFORMANCE INDICATORS

Total Reviews: {{total_reviews}}
Average Rating: {{avg_rating}} / 5.0
Week-over-Week: {{review_change}} ({{review_change_pct}}%)

═══════════════════════════════════════════════

SENTIMENT OVERVIEW

Positive (4-5★): {{positive_count}} ({{positive_pct}}%)
Neutral (3★): {{neutral_count}} ({{neutral_pct}}%)
Negative (1-2★): {{negative_count}} ({{negative_pct}}%)

{{sentiment_chart}}

═══════════════════════════════════════════════

RATING TREND (8 WEEKS)

{{rating_chart}}

═══════════════════════════════════════════════

REVIEW VOLUME TREND

{{volume_chart}}

═══════════════════════════════════════════════

REVIEW SOURCES

Organic: {{organic_count}} ({{organic_pct}}%)
Verified: {{verified_count}} ({{verified_pct}}%)
Invited: {{invited_count}} ({{invited_pct}}%)

═══════════════════════════════════════════════

LANGUAGE BREAKDOWN

{{languages}}

═══════════════════════════════════════════════

BRAND RESPONSE

Response Rate: {{response_rate}}%
Average Response Time: {{avg_response_time}}

═══════════════════════════════════════════════

TOP POSITIVE TOPICS

{{positive_topics}}

TOP NEGATIVE TOPICS

{{negative_topics}}

═══════════════════════════════════════════════

AI-GENERATED INSIGHTS

{{ai_summary}}
"""
    
    doc = services['docs'].documents().create(
        body={'title': 'Trustpilot Weekly Report - TEMPLATE'}
    ).execute()
    
    doc_id = doc['documentId']
    
    services['docs'].documents().batchUpdate(
        documentId=doc_id,
        body={'requests': [{
            'insertText': {
                'location': {'index': 1},
                'text': template_content
            }
        }]}
    ).execute()
    
    print(f"\n[SUCCESS] Universal template created!")
    print(f"[INFO] Template ID: {doc_id}")
    print(f"[INFO] View: https://docs.google.com/document/d/{doc_id}")
    print(f"\n[ACTION REQUIRED] Add to .env:")
    print(f"REPORT_TEMPLATE_ID={doc_id}")
    
    return doc_id

def get_or_create_template(services):
    """Get template ID from env or create new one"""
    template_id = os.getenv('REPORT_TEMPLATE_ID')
    
    if template_id:
        return template_id
    
    print("\n[INFO] No template found in .env")
    print("[INFO] Creating universal template...")
    return create_universal_template(services)

def fill_template(services, doc_id, data, chart_urls):
    """Fill template with actual data"""
    requests = []
    
    for key, value in data.items():
        if key not in ['snapshots', 'current_week']:
            requests.append({
                'replaceAllText': {
                    'containsText': {
                        'text': f'{{{{{key}}}}}',
                        'matchCase': True
                    },
                    'replaceText': str(value)
                }
            })
    
    services['docs'].documents().batchUpdate(
        documentId=doc_id,
        body={'requests': requests}
    ).execute()
    
    chart_replacements = [
        ('{{sentiment_chart}}', chart_urls[0]),
        ('{{rating_chart}}', chart_urls[1]),
        ('{{volume_chart}}', chart_urls[2])
    ]
    
    for placeholder, url in chart_replacements:
        if url:
            doc = services['docs'].documents().get(documentId=doc_id).execute()
            
            for element in doc.get('body', {}).get('content', []):
                if 'paragraph' in element:
                    for text_element in element['paragraph'].get('elements', []):
                        if 'textRun' in text_element:
                            content = text_element['textRun'].get('content', '')
                            if placeholder in content:
                                start_index = text_element['startIndex']
                                
                                image_requests = [
                                    {
                                        'deleteContentRange': {
                                            'range': {
                                                'startIndex': start_index,
                                                'endIndex': start_index + len(placeholder)
                                            }
                                        }
                                    },
                                    {
                                        'insertInlineImage': {
                                            'location': {'index': start_index},
                                            'uri': url,
                                            'objectSize': {
                                                'height': {'magnitude': 200, 'unit': 'PT'},
                                                'width': {'magnitude': 400, 'unit': 'PT'}
                                            }
                                        }
                                    }
                                ]
                                
                                services['docs'].documents().batchUpdate(
                                    documentId=doc_id,
                                    body={'requests': image_requests}
                                ).execute()
                                
                                break

# =============================================================================
# MAIN
# =============================================================================

def generate_report(brand_id):
    """Generate report from universal template"""
    brand = database.get_brand_info(brand_id)
    print(f"\n{'='*70}")
    print(f"GENERATING REPORT: {brand['brand_name']}")
    print('='*70)
    
    services = get_google_services()
    if not services:
        return False
    
    template_id = get_or_create_template(services)
    if not os.getenv('REPORT_TEMPLATE_ID'):
        print("\n[INFO] Template created. Please add REPORT_TEMPLATE_ID to .env and run again.")
        return False
    
    week_start, week_end = get_previous_week()
    print(f"[INFO] Period: {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}")
    
    data = prepare_report_data(brand_id, week_start, week_end)
    if not data:
        print("[WARNING] No data")
        return False
    
    print("\n[1/4] Generating charts...")
    chart1 = create_sentiment_chart(data['current_week']['positive_count'], data['current_week']['neutral_count'], data['current_week']['negative_count'])
    chart2 = create_rating_chart(data['snapshots'])
    chart3 = create_volume_chart(data['snapshots'])
    print("[SUCCESS] Charts generated")
    
    print("\n[2/4] Uploading charts...")
    week_key = data['snapshots'][0]['week_key']
    chart_urls = [
        upload_image_to_drive(services, chart1, f"{brand['brand_name']}_{week_key}_sentiment.png"),
        upload_image_to_drive(services, chart2, f"{brand['brand_name']}_{week_key}_rating.png"),
        upload_image_to_drive(services, chart3, f"{brand['brand_name']}_{week_key}_volume.png")
    ]
    print("[SUCCESS] Charts uploaded")
    
    print("\n[3/4] Creating report from template...")
    copied_file = services['drive'].files().copy(
        fileId=template_id,
        body={'name': f"{brand['brand_name']} - Weekly Report {week_key}"}
    ).execute()
    
    report_id = copied_file['id']
    print(f"[INFO] Report doc created")
    
    print("\n[4/4] Filling template...")
    fill_template(services, report_id, data, chart_urls)
    
    print(f"\n{'='*70}")
    print(f"[SUCCESS] Report ready!")
    print(f"View: https://docs.google.com/document/d/{report_id}")
    print('='*70)
    
    return True

def generate_all_reports():
    """Generate reports for all brands"""
    print("\n" + "="*70)
    print("WEEKLY REPORT GENERATION (FIXED)")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*70)
    
    conn = database.sqlite3.connect(database.DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, brand_name FROM brands")
    brands = cursor.fetchall()
    conn.close()
    
    if not brands:
        print("[WARNING] No brands in database")
        return
    
    success_count = 0
    for brand_id, brand_name in brands:
        try:
            if generate_report(brand_id):
                success_count += 1
        except Exception as e:
            print(f"[ERROR] {brand_name}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*70}")
    print(f"[COMPLETE] Generated {success_count}/{len(brands)} reports")
    print("="*70)

if __name__ == "__main__":
    generate_all_reports()