"""
Market Scanner — Discover active weather markets on Polymarket.

Fetches weather-related markets from Gamma API, extracts:
- City/location from market title
- Temperature/weather buckets and their token IDs
- Current prices for each outcome
- Resolution time
"""

import json
import time
import re
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field

from config import Config
from logger import log


@dataclass
class WeatherMarket:
    """A discovered weather market on Polymarket."""
    event_id: str
    title: str
    description: str
    city: str
    country: str
    market_type: str          # 'temperature', 'precipitation', 'wind', etc.
    resolution_time: Optional[datetime]
    outcomes: List[Dict]      # [{label, token_id, price, bucket_low, bucket_high}]
    active: bool
    volume: float
    liquidity: float
    slug: str
    raw: Dict = field(default_factory=dict)


class MarketScanner:
    """Scan Polymarket for active weather markets."""

    def __init__(self):
        self.base_url = Config.GAMMA_API_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': f'WeatherSniper/{Config.VERSION}',
            'Accept': 'application/json',
        })
        self._cache: Dict[str, Tuple[float, List[WeatherMarket]]] = {}
        self._cache_ttl = 30.0


    def scan_weather_markets(self) -> List[WeatherMarket]:
        """
        Discover all active weather markets on Polymarket.
        
        Strategy:
        1. Paginate through ALL active events (Gamma API tag filter is unreliable)
        2. Filter locally using strict weather detection
        3. Also try slug-based lookups for known city patterns
        """
        cache_key = 'weather_scan'
        now = time.time()
        if cache_key in self._cache:
            cached_time, cached = self._cache[cache_key]
            if now - cached_time < self._cache_ttl:
                return cached

        markets = []
        seen_ids = set()

        # Method 1: Paginate ALL active events and filter locally
        try:
            for offset in range(0, 500, 100):
                resp = self.session.get(
                    f"{self.base_url}/events",
                    params={
                        'active': 'true',
                        'closed': 'false',
                        'limit': 100,
                        'offset': offset,
                    },
                    timeout=15,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                events = data if isinstance(data, list) else data.get('events', [])
                if not events:
                    break
                for event in events:
                    market = self._parse_event(event)
                    if market and market.event_id not in seen_ids:
                        seen_ids.add(market.event_id)
                        markets.append(market)
        except Exception as e:
            log.debug(f"Paginated scan error: {e}")

        # Method 2: Try known weather slug patterns
        try:
            slug_markets = self._try_known_slugs()
            for m in slug_markets:
                if m.event_id not in seen_ids:
                    seen_ids.add(m.event_id)
                    markets.append(m)
        except Exception as e:
            log.debug(f"Slug scan error: {e}")

        # Filter to only active, tradeable markets
        active_markets = [m for m in markets if m.active and m.outcomes]
        active_markets.sort(key=lambda m: m.volume, reverse=True)

        self._cache[cache_key] = (now, active_markets)
        log.info(f"Found {len(active_markets)} active weather markets")
        return active_markets

    def _try_known_slugs(self) -> List[WeatherMarket]:
        """Try common slug patterns for weather markets."""
        from datetime import timedelta
        results = []
        now_dt = datetime.now(timezone.utc)

        cities = ['tokyo', 'taipei', 'hong-kong', 'seoul', 'new-york',
                  'singapore', 'manila', 'bangkok', 'london', 'sydney']

        for day_offset in range(0, 3):
            target = now_dt + timedelta(days=day_offset)
            date_str = target.strftime('%B-%d-%Y').lower()
            date_str2 = target.strftime('%B-%d').lower()

            for city in cities:
                slug_patterns = [
                    f'{city}-high-temperature-{date_str}',
                    f'{city}-daily-temperature-{date_str}',
                    f'{city}-temperature-{date_str2}',
                    f'daily-temperature-{city}-{target.strftime("%Y-%m-%d")}',
                ]
                for slug in slug_patterns:
                    try:
                        resp = self.session.get(
                            f"{self.base_url}/events",
                            params={'slug': slug},
                            timeout=5,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            events = data if isinstance(data, list) else data.get('events', [])
                            if events and events[0].get('slug') == slug:
                                market = self._parse_event(events[0])
                                if market:
                                    results.append(market)
                                    break  # found it, skip other patterns
                    except Exception:
                        continue

        return results

    def _search_markets(self, keyword: str) -> List[WeatherMarket]:
        """Search Gamma API for markets matching keyword."""
        results = []
        try:
            # Search events
            resp = self.session.get(
                f"{self.base_url}/events",
                params={
                    'closed': 'false',
                    'active': 'true',
                    'archived': 'false',
                    'limit': 50,
                    'order': 'volume24hr',
                    'ascending': 'false',
                    'tag': keyword,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                events = data if isinstance(data, list) else data.get('events', [])
                for event in events:
                    market = self._parse_event(event)
                    if market:
                        results.append(market)
        except Exception as e:
            log.debug(f"Gamma search '{keyword}' error: {e}")

        # Also try markets endpoint with text search
        try:
            resp2 = self.session.get(
                f"{self.base_url}/markets",
                params={
                    'closed': 'false',
                    'active': 'true',
                    'limit': 50,
                    'text_query': keyword,
                },
                timeout=10,
            )
            if resp2.status_code == 200:
                data = resp2.json()
                items = data if isinstance(data, list) else data.get('markets', [])
                for item in items:
                    market = self._parse_market_item(item)
                    if market:
                        results.append(market)
        except Exception as e:
            log.debug(f"Gamma text search '{keyword}' error: {e}")

        return results


    def _search_by_tag(self, tag: str) -> List[WeatherMarket]:
        """Search by Polymarket tag."""
        results = []
        try:
            resp = self.session.get(
                f"{self.base_url}/events",
                params={
                    'tag': tag,
                    'closed': 'false',
                    'active': 'true',
                    'limit': 100,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                events = data if isinstance(data, list) else data.get('events', [])
                for event in events:
                    market = self._parse_event(event)
                    if market:
                        results.append(market)
        except Exception as e:
            log.debug(f"Tag search '{tag}' error: {e}")
        return results

    def _parse_event(self, event: Dict) -> Optional[WeatherMarket]:
        """Parse a Gamma API event into a WeatherMarket."""
        title = event.get('title', '')
        if not self._is_weather_market(title):
            return None

        markets = event.get('markets', [])
        if not markets:
            return None

        # Extract city and market type
        city, country = self._extract_location(title)
        market_type = self._detect_market_type(title)

        # Parse outcomes from all markets in the event
        outcomes = []
        for m in markets:
            outcome = self._parse_outcome(m)
            if outcome:
                outcomes.append(outcome)

        if not outcomes:
            return None

        # Resolution time
        end_str = event.get('endDate') or event.get('end_date_iso')
        resolution_time = None
        if end_str:
            try:
                resolution_time = datetime.fromisoformat(
                    end_str.replace('Z', '+00:00'))
            except Exception:
                pass

        return WeatherMarket(
            event_id=str(event.get('id', '')),
            title=title,
            description=event.get('description', ''),
            city=city,
            country=country,
            market_type=market_type,
            resolution_time=resolution_time,
            outcomes=outcomes,
            active=event.get('active', False),
            volume=float(event.get('volume', 0) or 0),
            liquidity=float(event.get('liquidity', 0) or 0),
            slug=event.get('slug', ''),
            raw=event,
        )

    def _parse_market_item(self, item: Dict) -> Optional[WeatherMarket]:
        """Parse a single market item from search."""
        question = item.get('question', '') or item.get('title', '')
        if not self._is_weather_market(question):
            return None

        city, country = self._extract_location(question)
        market_type = self._detect_market_type(question)

        # Token IDs
        raw_ids = item.get('clobTokenIds', '[]')
        if isinstance(raw_ids, str):
            try:
                clob_ids = json.loads(raw_ids)
            except Exception:
                clob_ids = []
        else:
            clob_ids = raw_ids if isinstance(raw_ids, list) else []

        outcomes = []
        # For single-outcome markets (Yes/No)
        if clob_ids:
            price = float(item.get('outcomePrices', '[0.5]').strip('[]').split(',')[0]
                         if isinstance(item.get('outcomePrices'), str)
                         else 0.5)
            bucket_lo, bucket_hi = self._parse_bucket_bounds(question)
            outcomes.append({
                'label': item.get('outcome', question),
                'token_id': clob_ids[0] if clob_ids else '',
                'price': price,
                'bucket_low': bucket_lo,
                'bucket_high': bucket_hi,
            })

        if not outcomes:
            return None

        end_str = item.get('endDate') or item.get('end_date_iso')
        resolution_time = None
        if end_str:
            try:
                resolution_time = datetime.fromisoformat(
                    end_str.replace('Z', '+00:00'))
            except Exception:
                pass

        return WeatherMarket(
            event_id=str(item.get('conditionId', item.get('id', ''))),
            title=question,
            description=item.get('description', ''),
            city=city,
            country=country,
            market_type=market_type,
            resolution_time=resolution_time,
            outcomes=outcomes,
            active=item.get('active', True),
            volume=float(item.get('volume', 0) or 0),
            liquidity=float(item.get('liquidity', 0) or 0),
            slug=item.get('slug', ''),
            raw=item,
        )


    def _parse_outcome(self, market: Dict) -> Optional[Dict]:
        """Parse a market into an outcome dict."""
        question = market.get('question', '') or market.get('groupItemTitle', '')

        raw_ids = market.get('clobTokenIds', '[]')
        if isinstance(raw_ids, str):
            try:
                clob_ids = json.loads(raw_ids)
            except Exception:
                clob_ids = []
        else:
            clob_ids = raw_ids if isinstance(raw_ids, list) else []

        if not clob_ids:
            return None

        # Parse price
        raw_prices = market.get('outcomePrices', '[]')
        if isinstance(raw_prices, str):
            try:
                prices = json.loads(raw_prices)
            except Exception:
                prices = [0.5]
        else:
            prices = raw_prices if isinstance(raw_prices, list) else [0.5]

        price = float(prices[0]) if prices else 0.5
        bucket_lo, bucket_hi = self._parse_bucket_bounds(question)

        return {
            'label': question or market.get('outcome', 'Unknown'),
            'token_id': clob_ids[0],
            'token_id_no': clob_ids[1] if len(clob_ids) > 1 else None,
            'price': price,
            'bucket_low': bucket_lo,
            'bucket_high': bucket_hi,
            'market_id': market.get('id', ''),
        }

    def _is_weather_market(self, text: str) -> bool:
        """Check if text indicates a weather-related market."""
        text_lower = text.lower()

        # Strong indicators (must have at least one)
        strong_keywords = [
            '°c', '°f', 'celsius', 'fahrenheit',
            'high temp', 'low temp', 'high temperature', 'low temperature',
            'precipitation', 'rainfall', 'snowfall',
            'wind speed', 'humidity',
            'heat wave', 'cold snap',
            'daily high', 'daily low',
        ]
        if any(kw in text_lower for kw in strong_keywords):
            return True

        # Require "temperature" + a city name to avoid false positives
        if 'temperature' in text_lower or 'weather' in text_lower:
            cities = ['tokyo', 'taipei', 'hong kong', 'seoul', 'singapore',
                      'new york', 'nyc', 'los angeles', 'chicago', 'miami',
                      'london', 'paris', 'berlin', 'sydney', 'delhi',
                      'mumbai', 'shanghai', 'bangkok', 'manila', 'osaka',
                      'dubai', 'phoenix', 'houston', 'denver']
            if any(city in text_lower for city in cities):
                return True

        return False

    def _extract_location(self, text: str) -> Tuple[str, str]:
        """Extract city and country from market title."""
        text_lower = text.lower()

        # Known cities to check
        cities = {
            'tokyo': ('Tokyo', 'Japan'),
            'taipei': ('Taipei', 'Taiwan'),
            'hong kong': ('Hong Kong', 'China'),
            'seoul': ('Seoul', 'South Korea'),
            'singapore': ('Singapore', 'Singapore'),
            'manila': ('Manila', 'Philippines'),
            'bangkok': ('Bangkok', 'Thailand'),
            'new york': ('New York', 'USA'),
            'nyc': ('New York', 'USA'),
            'los angeles': ('Los Angeles', 'USA'),
            'chicago': ('Chicago', 'USA'),
            'miami': ('Miami', 'USA'),
            'london': ('London', 'UK'),
            'paris': ('Paris', 'France'),
            'berlin': ('Berlin', 'Germany'),
            'sydney': ('Sydney', 'Australia'),
            'dubai': ('Dubai', 'UAE'),
            'delhi': ('Delhi', 'India'),
            'mumbai': ('Mumbai', 'India'),
            'shanghai': ('Shanghai', 'China'),
            'beijing': ('Beijing', 'China'),
            'osaka': ('Osaka', 'Japan'),
        }

        for key, (city, country) in cities.items():
            if key in text_lower:
                return city, country

        return 'Unknown', 'Unknown'

    def _detect_market_type(self, text: str) -> str:
        """Detect what type of weather market this is."""
        text_lower = text.lower()
        if any(w in text_lower for w in ['high temp', 'temperature', '°c', '°f', 'celsius', 'degrees']):
            return 'temperature'
        if any(w in text_lower for w in ['rain', 'precipitation', 'mm']):
            return 'precipitation'
        if any(w in text_lower for w in ['wind', 'mph', 'km/h']):
            return 'wind'
        if any(w in text_lower for w in ['snow', 'snowfall']):
            return 'snow'
        return 'weather'

    def _parse_bucket_bounds(self, text: str) -> Tuple[float, float]:
        """
        Parse temperature bucket bounds from outcome text.
        e.g. "24°C" → (23.5, 24.5)
             "25°C or higher" → (24.5, inf)
             "23°C or lower" → (-inf, 23.5)
        """
        text_lower = text.lower()

        # Match patterns like "24°C", "24 degrees", "24C"
        temp_match = re.search(r'(\d+)\s*°?\s*[cC]', text)
        if not temp_match:
            temp_match = re.search(r'(\d+)\s*degrees', text_lower)
        if not temp_match:
            return (float('-inf'), float('inf'))

        temp = float(temp_match.group(1))

        if 'or higher' in text_lower or 'or more' in text_lower or '+' in text:
            return (temp - 0.5, float('inf'))
        elif 'or lower' in text_lower or 'or less' in text_lower or 'below' in text_lower:
            return (float('-inf'), temp + 0.5)
        else:
            return (temp - 0.5, temp + 0.5)

    def get_outcome_prices(self, market: WeatherMarket) -> Dict[str, float]:
        """Fetch live prices for all outcomes in a market via CLOB."""
        prices = {}
        for outcome in market.outcomes:
            token_id = outcome.get('token_id')
            if not token_id:
                continue
            try:
                resp = self.session.get(
                    f"{Config.CLOB_API_URL}/price",
                    params={'token_id': token_id, 'side': 'BUY'},
                    timeout=5,
                )
                if resp.status_code == 200:
                    price = float(resp.json().get('price', 0))
                    prices[outcome['label']] = price
                    outcome['price'] = price
                else:
                    prices[outcome['label']] = outcome.get('price', 0.5)
            except Exception:
                prices[outcome['label']] = outcome.get('price', 0.5)

        return prices
