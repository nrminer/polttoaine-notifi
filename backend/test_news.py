"""
Test script for the enhanced news.py module.
Tests both basic scraping and AI-powered relevance scoring.
"""
import asyncio
import os
from news import fetch_news, fetch_news_with_ai_relevance, calculate_relevance_with_ai

def test_basic_scraping():
    """Test basic news scraping without AI."""
    print("=" * 60)
    print("TEST 1: Basic News Scraping (no AI)")
    print("=" * 60)
    
    items = fetch_news(max_age_days=7, limit=10)
    
    print(f"\nFound {len(items)} fuel-related news items\n")
    
    for idx, item in enumerate(items, 1):
        age_str = f"{int(item['age_hours'])}h" if item.get('age_hours') else "?"
        breaking_str = " [BREAKING]" if item.get('breaking') else ""
        severity_str = f" (severity: {item['severity']})" if item.get('severity', 0) > 0 else ""
        
        print(f"{idx}. [{age_str}] {item['title']}{breaking_str}{severity_str}")
        print(f"   Source: {item['source']}")
        print(f"   Link: {item['link'][:60]}...")
        print()
    
    return items


async def test_ai_relevance(sample_items):
    """Test AI relevance scoring on a few sample items."""
    print("\n" + "=" * 60)
    print("TEST 2: AI Relevance Scoring")
    print("=" * 60)
    
    if not (os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")):
        print("\n⚠ ANTHROPIC_AUTH_TOKEN not set - skipping AI test")
        return
    
    # Take first 5 items for testing
    test_items = sample_items[:5]
    
    print(f"\nAnalyzing {len(test_items)} items with AI...\n")
    
    analyzed = await calculate_relevance_with_ai(test_items)
    
    for idx, item in enumerate(analyzed, 1):
        print(f"{idx}. {item['title']}")
        print(f"   Source: {item['source']}")
        
        if item.get('relevance_score') is not None:
            print(f"   ✓ Relevance Score: {item['relevance_score']}/100")
            print(f"   ✓ Impact Direction: {item['impact_direction']}")
            print(f"   ✓ Impact Magnitude: {item['impact_magnitude']}")
            if item.get('ai_reasoning'):
                print(f"   ✓ Reasoning: {item['ai_reasoning']}")
        else:
            print(f"   ✗ AI analysis failed")
        print()


def test_full_workflow():
    """Test the complete workflow with AI filtering."""
    print("\n" + "=" * 60)
    print("TEST 3: Full Workflow (Scrape + AI + Filter)")
    print("=" * 60)
    
    if not (os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")):
        print("\n⚠ ANTHROPIC_AUTH_TOKEN not set - skipping full workflow test")
        return
    
    print("\nFetching news with AI relevance (min_relevance=50)...\n")
    
    items = fetch_news_with_ai_relevance(
        max_age_days=7,
        limit=10,
        min_relevance=50,
        use_ai=True
    )
    
    print(f"Found {len(items)} highly relevant items (sorted by relevance):\n")
    
    for idx, item in enumerate(items, 1):
        score = item.get('relevance_score', 0)
        direction = item.get('impact_direction', 'unknown')
        magnitude = item.get('impact_magnitude', 'unknown')
        age_str = f"{int(item['age_hours'])}h" if item.get('age_hours') else "?"
        
        # Visual indicator based on relevance
        if score >= 80:
            indicator = "🔴"
        elif score >= 60:
            indicator = "🟠"
        else:
            indicator = "🟡"
        
        print(f"{idx}. {indicator} [{age_str}] {item['title']}")
        print(f"   Relevance: {score}/100 | Direction: {direction} | Magnitude: {magnitude}")
        print(f"   Source: {item['source']}")
        print()


def main():
    """Run all tests."""
    print("\n🧪 Testing Enhanced News Module\n")
    
    # Test 1: Basic scraping
    items = test_basic_scraping()
    
    # Test 2: AI relevance on sample
    if items:
        asyncio.run(test_ai_relevance(items))
    
    # Test 3: Full workflow
    test_full_workflow()
    
    print("\n" + "=" * 60)
    print("✓ All tests completed")
    print("=" * 60)


if __name__ == "__main__":
    main()
