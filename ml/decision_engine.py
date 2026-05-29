"""
ML Decision Engine — GPT-5.5 via Freemodel API for fast trading decisions.

Design principles:
- MINIMAL TOKENS: Each query is <200 tokens, response <100 tokens
- MARKET-SCOPED CONTEXT: Only active markets included, freed on close
- FAST: Single API call per decision cycle (~200ms)
- DECISIVE: Returns BUY/SKIP/SELL with confidence score

The ML is used for:
1. Signal validation (confirm/reject sniper signals)
2. Entry timing (should we buy now or wait?)
3. Position review (hold/sell open positions)
4. Market selection (which cities to prioritize today)

Token budget per call: ~150-300 tokens total (prompt + response)
"""

import time
import json
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

from config import Config
from logger import log



class MLDecisionEngine:
    """Fast ML-powered trading decisions using GPT-5.5."""

    def __init__(self):
        self.base_url = Config.ML_API_URL
        self.api_key = Config.ML_API_KEY
        self.model = Config.ML_MODEL
        self.enabled = bool(self.api_key)
        self._session = requests.Session()
        self._session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        })
        self._cache: Dict[str, Tuple[float, Dict]] = {}
        self._cache_ttl = 120  # 2 minutes
        self._total_tokens_used = 0

        if self.enabled:
            log.info(f"🧠 ML Engine: {self.model} via {self.base_url[:30]}...")
        else:
            log.info("🧠 ML Engine: disabled (no API key)")

    def validate_signal(self, city: str, bucket_label: str, entry_price: float,
                        our_prob: float, edge: float, forecast_temp: float,
                        n_models: int, weekly_context: str = '') -> Dict:
        """
        Ask ML to validate a trading signal. Returns:
        {action: 'BUY'|'SKIP', confidence: 0-1, reason: str}
        
        Uses minimal tokens (~150 total).
        """
        if not self.enabled:
            return {'action': 'BUY', 'confidence': 0.7, 'reason': 'ML disabled'}

        # Check cache
        cache_key = f"{city}_{bucket_label}_{entry_price:.3f}"
        now = time.time()
        if cache_key in self._cache:
            ts, result = self._cache[cache_key]
            if now - ts < self._cache_ttl:
                return result

        # Ultra-compact prompt (~100 tokens)
        prompt = (
            f"Weather trade signal. Reply JSON only: {{\"action\":\"BUY\"|\"SKIP\",\"conf\":0-1,\"why\":\"<5 words>\"}}\n"
            f"City:{city} Bucket:{bucket_label} Price:${entry_price:.3f} "
            f"OurProb:{our_prob:.0%} Edge:{edge:.0%} "
            f"Forecast:{forecast_temp:.1f}°C Models:{n_models}\n"
            f"History:{weekly_context[:80]}"
        )

        result = self._query(prompt, max_tokens=60)
        self._cache[cache_key] = (now, result)
        return result

    def review_position(self, city: str, bucket_label: str, entry_price: float,
                        current_price: float, hold_hours: float,
                        resolution_hours: float) -> Dict:
        """
        Ask ML whether to hold or sell an open position.
        Returns: {action: 'HOLD'|'SELL', confidence: 0-1, reason: str}
        """
        if not self.enabled:
            return {'action': 'HOLD', 'confidence': 0.5, 'reason': 'ML disabled'}

        roi_pct = ((current_price - entry_price) / entry_price) * 100

        prompt = (
            f"Position review. Reply JSON: {{\"action\":\"HOLD\"|\"SELL\",\"conf\":0-1,\"why\":\"<5 words>\"}}\n"
            f"City:{city} {bucket_label} Entry:${entry_price:.3f} "
            f"Now:${current_price:.3f} ROI:{roi_pct:+.0f}% "
            f"Held:{hold_hours:.0f}h Left:{resolution_hours:.0f}h"
        )

        return self._query(prompt, max_tokens=50)

    def select_markets(self, available_cities: List[str],
                       weekly_context: str = '') -> List[str]:
        """
        Ask ML which cities to prioritize today.
        Returns ranked list of cities.
        """
        if not self.enabled:
            return available_cities[:8]

        prompt = (
            f"Rank cities for weather trading today. Reply JSON array of top 5: [\"city1\",\"city2\",...]\n"
            f"Available: {','.join(available_cities[:15])}\n"
            f"Performance: {weekly_context[:100]}"
        )

        result = self._query(prompt, max_tokens=40)
        if isinstance(result.get('raw'), list):
            return result['raw']
        return available_cities[:8]


    def _query(self, prompt: str, max_tokens: int = 60) -> Dict:
        """
        Make a single API call to the ML model.
        Optimized for speed and minimal token usage.
        """
        try:
            resp = self._session.post(
                f"{self.base_url}/chat/completions",
                json={
                    'model': self.model,
                    'messages': [
                        {'role': 'system', 'content': 'You are a weather trading assistant. Reply with JSON only. Be extremely concise.'},
                        {'role': 'user', 'content': prompt},
                    ],
                    'max_tokens': max_tokens,
                    'temperature': 0.1,  # deterministic
                },
                timeout=8,  # 8s timeout (freemodel can be slow)
            )

            if resp.status_code != 200:
                log.debug(f"ML API {resp.status_code}: {resp.text[:100]}")
                return {'action': 'BUY', 'confidence': 0.5, 'reason': 'API error'}

            data = resp.json()
            content = data.get('choices', [{}])[0].get('message', {}).get('content', '{}')

            # Track token usage
            usage = data.get('usage', {})
            self._total_tokens_used += usage.get('total_tokens', 0)

            # Parse JSON response
            return self._parse_response(content)

        except requests.Timeout:
            log.debug("ML API timeout (5s)")
            return {'action': 'BUY', 'confidence': 0.5, 'reason': 'timeout'}
        except Exception as e:
            log.debug(f"ML query failed: {e}")
            return {'action': 'BUY', 'confidence': 0.5, 'reason': str(e)[:20]}

    def _parse_response(self, content: str) -> Dict:
        """Parse ML model response (handles various JSON formats)."""
        content = content.strip()
        # Remove markdown code blocks if present
        if content.startswith('```'):
            content = content.split('\n', 1)[-1].rsplit('```', 1)[0].strip()

        try:
            parsed = json.loads(content)

            # Handle array response (for select_markets)
            if isinstance(parsed, list):
                return {'raw': parsed, 'action': 'SELECT', 'confidence': 0.8, 'reason': ''}

            # Normalize keys
            action = parsed.get('action', parsed.get('act', 'BUY')).upper()
            confidence = float(parsed.get('conf', parsed.get('confidence', 0.5)))
            reason = parsed.get('why', parsed.get('reason', ''))

            return {
                'action': action,
                'confidence': min(1.0, max(0.0, confidence)),
                'reason': str(reason)[:50],
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            # Fallback: try to extract action from text
            content_upper = content.upper()
            if 'SKIP' in content_upper or 'NO' in content_upper:
                return {'action': 'SKIP', 'confidence': 0.5, 'reason': 'parsed from text'}
            if 'SELL' in content_upper:
                return {'action': 'SELL', 'confidence': 0.5, 'reason': 'parsed from text'}
            return {'action': 'BUY', 'confidence': 0.5, 'reason': 'parse failed'}

    def get_token_usage(self) -> int:
        """Total tokens used this session."""
        return self._total_tokens_used

    def get_status(self) -> Dict:
        """ML engine status."""
        return {
            'enabled': self.enabled,
            'model': self.model,
            'tokens_used': self._total_tokens_used,
            'cache_size': len(self._cache),
        }
