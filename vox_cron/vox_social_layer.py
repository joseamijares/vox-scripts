#!/usr/bin/env python3
"""
VOX SOCIAL SENTIMENT LAYER
Adds Reddit and X/Twitter sentiment to the 6-layer VOX harness.
This is Layer 7: Social Sentiment.

Uses:
- web_search with site:reddit.com for Reddit sentiment
- web_search with site:twitter.com for X sentiment
- xurl API when authenticated (future upgrade)

Target: Detect meme stocks, pump-and-dump, real crowd sentiment.
"""

import os
import subprocess
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

class VoxSocialLayer:
    """Layer 7: Social Sentiment from Reddit and X."""
    
    def __init__(self):
        self.sentiment_data = {}
        self.sources = {
            'reddit': {},
            'twitter': {},
            'combined': {}
        }
    
    def search_reddit(self, ticker: str) -> Dict:
        """Search Reddit for stock mentions and sentiment."""
        # Use web_search tool via execute_code
        search_query = f"site:reddit.com {ticker} stock 2026"
        
        # For now, return mock data structure
        # In production, this would call web_search and parse results
        return {
            'ticker': ticker,
            'source': 'reddit',
            'mention_count': 0,  # Would be populated from search
            'sentiment': 'neutral',
            'confidence': 0,
            'top_posts': [],
            'wsb_rank': None,
            'pump_risk': False,
            'data_fresh': False
        }
    
    def search_twitter(self, ticker: str) -> Dict:
        """Search X/Twitter for stock mentions and sentiment."""
        # Use web_search tool via execute_code
        search_query = f"site:twitter.com ${ticker} stock 2026"
        
        # For now, return mock data structure
        # In production, this would call web_search and parse results
        return {
            'ticker': ticker,
            'source': 'twitter',
            'mention_count': 0,
            'sentiment': 'neutral',
            'confidence': 0,
            'top_tweets': [],
            'influencer_mentions': [],
            'pump_risk': False,
            'data_fresh': False
        }
    
    def calculate_social_score(self, reddit_data: Dict, twitter_data: Dict) -> int:
        """Calculate social sentiment score (0-100)."""
        score = 50  # Neutral base
        
        # Reddit factors
        if reddit_data.get('wsb_rank'):
            # WSB top picks often underperform
            if reddit_data['wsb_rank'] <= 5:
                score -= 15  # WSB top 5 = likely overhyped
            elif reddit_data['wsb_rank'] <= 10:
                score -= 10
        
        if reddit_data.get('pump_risk'):
            score -= 20  # Pump and dump detected
        
        if reddit_data.get('sentiment') == 'bullish':
            score += 10
        elif reddit_data.get('sentiment') == 'bearish':
            score -= 10
        
        # Twitter factors
        if twitter_data.get('influencer_mentions'):
            # Influencer mentions can be positive or negative
            for mention in twitter_data['influencer_mentions']:
                if mention.get('sentiment') == 'bullish':
                    score += 5
                elif mention.get('sentiment') == 'bearish':
                    score -= 5
        
        if twitter_data.get('pump_risk'):
            score -= 20
        
        # Clamp to 0-100
        return max(0, min(100, score))
    
    def analyze_stock(self, ticker: str) -> Dict:
        """Full social sentiment analysis for a stock."""
        reddit = self.search_reddit(ticker)
        twitter = self.search_twitter(ticker)
        
        social_score = self.calculate_social_score(reddit, twitter)
        
        analysis = {
            'ticker': ticker,
            'social_score': social_score,
            'reddit': reddit,
            'twitter': twitter,
            'warnings': [],
            'opportunities': []
        }
        
        # Warnings
        if reddit.get('pump_risk') or twitter.get('pump_risk'):
            analysis['warnings'].append('PUMP_AND_DUMP_RISK')
        
        if reddit.get('wsb_rank') and reddit['wsb_rank'] <= 5:
            analysis['warnings'].append('WSB_TOP_PICK_UNDERPERFORM')
        
        # Opportunities
        if twitter.get('influencer_mentions') and len(twitter['influencer_mentions']) > 3:
            analysis['opportunities'].append('INFLUENCER_MOMENTUM')
        
        if reddit.get('sentiment') == 'bearish' and twitter.get('sentiment') == 'bearish':
            analysis['opportunities'].append('CONTRARIAN_BUY')
        
        self.sentiment_data[ticker] = analysis
        return analysis
    
    def get_batch_analysis(self, tickers: List[str]) -> Dict[str, Dict]:
        """Analyze multiple stocks."""
        results = {}
        for ticker in tickers:
            results[ticker] = self.analyze_stock(ticker)
        return results
    
    def integrate_with_vox_grade(self, ticker: str, vox_grade: int, 
                                  social_score: int) -> Tuple[int, List[str]]:
        """Integrate social score with VOX grade."""
        adjustments = []
        
        # Social score adjustment
        if social_score >= 80:
            # Very positive social sentiment = possible bubble
            adjusted_grade = vox_grade - 5
            adjustments.append('SOCIAL_BUBBLE_RISK')
        elif social_score <= 20:
            # Very negative social sentiment = possible contrarian opportunity
            adjusted_grade = vox_grade + 5
            adjustments.append('SOCIAL_CONTRARIAN_OPPORTUNITY')
        elif social_score <= 40:
            # Negative sentiment = confirm with other layers
            adjusted_grade = vox_grade - 3
            adjustments.append('SOCIAL_NEGATIVE_CONFIRM')
        else:
            adjusted_grade = vox_grade
        
        # Clamp
        adjusted_grade = max(0, min(100, adjusted_grade))
        
        return adjusted_grade, adjustments

# Standalone execution
if __name__ == '__main__':
    layer = VoxSocialLayer()
    
    # Test with known tickers
    test_tickers = ['LLY', 'MU', 'CEG', 'IONQ', 'NVDA']
    
    print("="*70)
    print("VOX SOCIAL SENTIMENT LAYER v1.0")
    print("="*70)
    print()
    
    for ticker in test_tickers:
        analysis = layer.analyze_stock(ticker)
        print(f"{ticker}: Social Score = {analysis['social_score']}")
        print(f"  Warnings: {analysis['warnings']}")
        print(f"  Opportunities: {analysis['opportunities']}")
        print()
    
    print("="*70)
    print("NOTE: This is the framework. Integration with web_search")
    print("and xurl API will populate real data.")
    print("="*70)
