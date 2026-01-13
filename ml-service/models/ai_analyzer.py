"""
AI Analyzer - Full LLM-based analysis with session notes
Uses Ollama or Cloud AI (OpenAI/DeepSeek) for comprehensive analysis of user productivity patterns.
"""

import os
import json
import logging
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple

# Import PostgreSQL database module
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db as database

# Import metrics
try:
    from utils.metrics import record_ai_usage, CACHE_HITS, CACHE_MISSES
except ImportError:
    # Fallback if metrics not available
    def record_ai_usage(*args, **kwargs):
        pass
    CACHE_HITS = None
    CACHE_MISSES = None

# Structured logger for Loki
try:
    from utils.logger import logger as structured_logger
except ImportError:
    structured_logger = None

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages AI response caching in PostgreSQL."""

    # Cache durations in hours
    CACHE_DURATIONS = {
        'morning_briefing': 4,
        'evening_review': 12,  # Until next day effectively
        'integrated_insight': 2,
        'analyze_burnout': 6,
        'analyze_anomalies': 6,
        'analyze_quality': 0.5,  # 30 minutes
        'optimal_schedule': 4,
        'prediction': 2,
        'learning': 2  # Changed from 24h for more dynamic recommendations
    }

    def __init__(self):
        """Initialize cache manager with PostgreSQL database."""
        pass  # PostgreSQL connection is handled by db module

    def _generate_key(self, params: dict) -> str:
        """Generate cache key from parameters."""
        params_str = json.dumps(params, sort_keys=True, default=str)
        return hashlib.md5(params_str.encode()).hexdigest()[:16]

    def get_cached(self, cache_type: str, params: dict = None) -> Optional[Dict]:
        """Get cached response if valid."""
        try:
            cache_key = self._generate_key(params) if params else None
            result = database.get_cached(cache_type, cache_key)
            if result:
                logger.info(f"Cache hit for {cache_type}")
                return result
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None

    def set_cache(self, cache_type: str, data: Dict, params: dict = None):
        """Store response in cache."""
        try:
            ttl_hours = self.CACHE_DURATIONS.get(cache_type, 1)
            cache_key = self._generate_key(params) if params else None
            database.set_cache(cache_type, data, cache_key, ttl_hours)
            logger.info(f"Cached {cache_type} for {ttl_hours} hours")
        except Exception as e:
            logger.error(f"Cache set error: {e}")

    def invalidate_all(self):
        """Invalidate all caches (called on new session)."""
        try:
            count = database.invalidate_all_cache()
            logger.info(f"Invalidated {count} cache entries")
            return count
        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")
            return 0

    def clear_all(self):
        """Clear entire cache (called on docker-compose up)."""
        try:
            count = database.clear_all_cache()
            logger.info(f"Cleared {count} cache entries")
            return count
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            return 0

    def get_status(self) -> Dict:
        """Get current cache status."""
        try:
            return database.get_cache_status()
        except Exception as e:
            logger.error(f"Cache status error: {e}")
            return {'error': str(e)}


class AIAnalyzer:
    """Full LLM-based analyzer using Ollama or Cloud AI (DeepSeek/OpenAI)."""

    def __init__(self, categories: List[str] = None):
        """Initialize AI Analyzer.

        Args:
            categories: User's configured categories (from config.json)
        """
        self.categories = categories or []

        # AI Provider selection: 'ollama' (default) or 'cloud'
        self.ai_provider = os.getenv('AI_PROVIDER', 'ollama').lower()

        # Ollama settings (local)
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://ollama:11434')
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'qwen2.5:0.5b')

        # Cloud AI settings (DeepSeek, OpenAI, etc.)
        self.cloud_api_key = os.getenv('AI_API_KEY', '')
        self.cloud_api_url = os.getenv('AI_API_URL', 'https://api.deepseek.com/v1')
        self.cloud_model = os.getenv('AI_CLOUD_MODEL', 'deepseek-chat')

        # Backward compatibility: use OLLAMA_MODEL if AI_PROVIDER is ollama
        self.model = self.cloud_model if self.ai_provider == 'cloud' else self.ollama_model

        self.enabled = os.getenv('OLLAMA_ENABLED', 'true').lower() == 'true'
        self.timeout = int(os.getenv('OLLAMA_TIMEOUT', '180'))

        self.cache = CacheManager()

        # Import prompts
        from prompts import (
            MASTER_SYSTEM_PROMPT,
            SESSION_PREDICTION_PROMPT,
            QUALITY_PREDICTION_PROMPT,
            ANOMALY_DETECTION_PROMPT,
            BURNOUT_DETECTION_PROMPT,
            SCHEDULE_OPTIMIZATION_PROMPT,
            MORNING_BRIEFING_PROMPT,
            EVENING_REVIEW_PROMPT,
            INTEGRATED_INSIGHT_PROMPT,
            LEARNING_RECOMMENDATION_PROMPT,
            format_session_data,
            format_category_distribution,
            get_master_prompt_with_categories
        )

        self.prompts = {
            'master': MASTER_SYSTEM_PROMPT,
            'prediction': SESSION_PREDICTION_PROMPT,
            'quality': QUALITY_PREDICTION_PROMPT,
            'anomaly': ANOMALY_DETECTION_PROMPT,
            'burnout': BURNOUT_DETECTION_PROMPT,
            'schedule': SCHEDULE_OPTIMIZATION_PROMPT,
            'morning': MORNING_BRIEFING_PROMPT,
            'evening': EVENING_REVIEW_PROMPT,
            'integrated': INTEGRATED_INSIGHT_PROMPT,
            'learning': LEARNING_RECOMMENDATION_PROMPT
        }
        self.format_session_data = format_session_data
        self.format_category_distribution = format_category_distribution
        self._get_master_prompt_with_categories = get_master_prompt_with_categories

        logger.info(f"AIAnalyzer initialized: provider={self.ai_provider}, model={self.model}, enabled={self.enabled}, categories={len(self.categories)}")

    def update_categories(self, categories: List[str]):
        """Update categories at runtime (called when web service sends new categories)."""
        self.categories = categories or []
        logger.info(f"Categories updated: {len(self.categories)} categories")

    def _get_system_prompt(self) -> str:
        """Get system prompt with dynamic categories filled in."""
        if self.categories:
            return self._get_master_prompt_with_categories(self.categories)
        return self.prompts['master']

    def _get_sessions_with_notes(self, days: int = 30) -> List[Dict]:
        """Get all sessions with notes from specified period."""
        try:
            sessions = database.get_sessions_with_notes(days)

            # Format for prompts
            formatted = []
            for s in sessions:
                formatted.append({
                    'date': s.get('date', ''),
                    'time': s.get('time', ''),
                    'preset': s.get('preset', 'standard'),
                    'category': s.get('category', 'Unknown'),
                    'task': s.get('task', ''),
                    'notes': s.get('notes', ''),
                    'productivity_rating': s.get('productivity_rating'),
                    'duration_minutes': s.get('duration_minutes', 25),
                    'hour': s.get('hour', 12),
                    'day_of_week': s.get('day_of_week', 0)
                })

            return formatted
        except Exception as e:
            logger.error(f"Error getting sessions: {e}")
            return []

    def _get_today_sessions(self) -> List[Dict]:
        """Get today's sessions with notes."""
        try:
            sessions = database.get_today_sessions()

            return [{
                'time': s.get('time', ''),
                'preset': s.get('preset', 'standard'),
                'category': s.get('category', 'Unknown'),
                'task': s.get('task', ''),
                'notes': s.get('notes', ''),
                'productivity_rating': s.get('productivity_rating'),
                'duration_minutes': s.get('duration_minutes', 25)
            } for s in sessions]
        except Exception as e:
            logger.error(f"Error getting today's sessions: {e}")
            return []

    def _get_baseline_stats(self, sessions: List[Dict]) -> Dict:
        """Calculate baseline statistics from sessions."""
        if not sessions:
            return {
                'avg_sessions': 0,
                'avg_productivity': 0,
                'typical_hours': 'N/A',
                'top_category': 'N/A'
            }

        # Group by date
        by_date = {}
        for s in sessions:
            date = s.get('date', '')
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(s)

        avg_sessions = len(sessions) / max(len(by_date), 1)

        # Average productivity
        ratings = [s.get('productivity_rating') for s in sessions if s.get('productivity_rating')]
        avg_productivity = sum(ratings) / len(ratings) if ratings else 0

        # Typical hours
        hours = [s.get('hour', 12) for s in sessions]
        if hours:
            avg_hour = sum(hours) / len(hours)
            typical_hours = f"{int(avg_hour)}:00 - {int(avg_hour)+2}:00"
        else:
            typical_hours = 'N/A'

        # Top category
        categories = {}
        for s in sessions:
            cat = s.get('category', 'Unknown')
            categories[cat] = categories.get(cat, 0) + 1
        top_category = max(categories, key=categories.get) if categories else 'N/A'

        return {
            'avg_sessions': round(avg_sessions, 1),
            'avg_productivity': round(avg_productivity, 1),
            'typical_hours': typical_hours,
            'top_category': top_category
        }

    def _call_llm(self, prompt: str, system_prompt: str = None, endpoint: str = 'unknown') -> Optional[str]:
        """Route LLM call to appropriate provider (Ollama or Cloud)."""
        if self.ai_provider == 'cloud':
            return self._call_cloud_api(prompt, system_prompt, endpoint)
        else:
            return self._call_ollama(prompt, system_prompt, endpoint)

    def _call_cloud_api(self, prompt: str, system_prompt: str = None, endpoint: str = 'unknown') -> Optional[str]:
        """Make a call to Cloud AI API (DeepSeek, OpenAI-compatible)."""
        if not self.cloud_api_key:
            logger.warning("Cloud AI API key not configured (AI_API_KEY)")
            return None

        start_time = time.time()
        input_tokens = 0
        output_tokens = 0
        error_type = None

        # Log prompt being sent
        if structured_logger:
            structured_logger.ai_prompt(
                endpoint=endpoint,
                provider='cloud',
                model=self.cloud_model,
                prompt=prompt,
                system_prompt=system_prompt
            )

        try:
            import requests

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            headers = {
                "Authorization": f"Bearer {self.cloud_api_key}",
                "Content-Type": "application/json"
            }

            response = requests.post(
                f"{self.cloud_api_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.cloud_model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2000
                },
                timeout=self.timeout
            )

            duration = time.time() - start_time

            if response.status_code == 200:
                result = response.json()

                # Extract token usage from response
                usage = result.get('usage', {})
                input_tokens = usage.get('prompt_tokens', 0)
                output_tokens = usage.get('completion_tokens', 0)

                # Record metrics
                record_ai_usage(
                    provider='cloud',
                    model=self.cloud_model,
                    endpoint=endpoint,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_seconds=duration
                )

                response_content = result.get('choices', [{}])[0].get('message', {}).get('content', '')

                # Log response received
                if structured_logger:
                    structured_logger.ai_response(
                        endpoint=endpoint,
                        provider='cloud',
                        model=self.cloud_model,
                        response=response_content,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        duration_seconds=duration
                    )

                logger.info(f"Cloud AI call: {endpoint}, tokens={input_tokens}+{output_tokens}, duration={duration:.2f}s")

                return response_content
            else:
                error_type = f"status_{response.status_code}"
                logger.error(f"Cloud AI returned status {response.status_code}: {response.text}")
                record_ai_usage(
                    provider='cloud',
                    model=self.cloud_model,
                    endpoint=endpoint,
                    duration_seconds=duration,
                    error=error_type
                )
                return None

        except requests.exceptions.Timeout:
            error_type = 'timeout'
            logger.error(f"Cloud AI timeout after {self.timeout}s")
        except requests.exceptions.ConnectionError:
            error_type = 'connection_error'
            logger.error("Cloud AI connection error")
        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"Cloud AI call error: {e}")

        # Record error
        record_ai_usage(
            provider='cloud',
            model=self.cloud_model,
            endpoint=endpoint,
            duration_seconds=time.time() - start_time,
            error=error_type
        )
        return None

    def _call_ollama(self, prompt: str, system_prompt: str = None, endpoint: str = 'unknown') -> Optional[str]:
        """Make a call to Ollama API (local)."""
        if not self.enabled:
            logger.warning("Ollama is disabled")
            return None

        start_time = time.time()
        error_type = None

        # Log prompt being sent
        if structured_logger:
            structured_logger.ai_prompt(
                endpoint=endpoint,
                provider='ollama',
                model=self.ollama_model,
                prompt=prompt,
                system_prompt=system_prompt
            )

        try:
            import requests

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 2000
                    }
                },
                timeout=self.timeout
            )

            duration = time.time() - start_time

            if response.status_code == 200:
                result = response.json()

                # Ollama returns eval_count (output tokens) and prompt_eval_count (input tokens)
                input_tokens = result.get('prompt_eval_count', 0)
                output_tokens = result.get('eval_count', 0)

                record_ai_usage(
                    provider='ollama',
                    model=self.ollama_model,
                    endpoint=endpoint,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_seconds=duration
                )

                response_content = result.get('message', {}).get('content', '')

                # Log response received
                if structured_logger:
                    structured_logger.ai_response(
                        endpoint=endpoint,
                        provider='ollama',
                        model=self.ollama_model,
                        response=response_content,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        duration_seconds=duration
                    )

                logger.info(f"Ollama call: {endpoint}, tokens={input_tokens}+{output_tokens}, duration={duration:.2f}s")

                return response_content
            else:
                error_type = f"status_{response.status_code}"
                logger.error(f"Ollama returned status {response.status_code}")
                record_ai_usage(
                    provider='ollama',
                    model=self.ollama_model,
                    endpoint=endpoint,
                    duration_seconds=duration,
                    error=error_type
                )
                return None

        except requests.exceptions.Timeout:
            error_type = 'timeout'
            logger.error(f"Ollama timeout after {self.timeout}s")
        except requests.exceptions.ConnectionError:
            error_type = 'connection_error'
            logger.error("Ollama connection error")
        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"Ollama call error: {e}")

        record_ai_usage(
            provider='ollama',
            model=self.ollama_model,
            endpoint=endpoint,
            duration_seconds=time.time() - start_time,
            error=error_type
        )
        return None

    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """Parse JSON from LLM response."""
        if not response:
            return None

        try:
            # Try direct parse
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from response
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except json.JSONDecodeError:
            pass

        logger.error(f"Failed to parse JSON from response: {response[:200]}")
        return None

    def _get_category_distribution(self, sessions: List[Dict]) -> Dict:
        """Calculate category distribution from sessions."""
        categories = {}
        total = len(sessions)

        for s in sessions:
            cat = s.get('category', 'Unknown')
            if cat not in categories:
                categories[cat] = {'sessions': 0, 'percentage': 0}
            categories[cat]['sessions'] += 1

        for cat in categories:
            categories[cat]['percentage'] = round(
                (categories[cat]['sessions'] / total * 100) if total > 0 else 0,
                1
            )

        return categories

    def _get_skill_levels(self) -> List[Dict]:
        """Get skill levels from database."""
        try:
            skills = database.get_skill_levels()
            return [{
                'category': s.get('category', 'Unknown'),
                'level': s.get('level', 1),
                'xp': s.get('xp', 0)
            } for s in skills]
        except Exception as e:
            logger.error(f"Error getting skills: {e}")
            return []

    def _get_user_profile(self) -> Dict:
        """Get user profile from database."""
        try:
            profile = database.get_user_profile()
            return {
                'level': profile.get('level', 1),
                'total_xp': profile.get('total_xp', 0),
                'streak': profile.get('streak', 0)
            }
        except Exception as e:
            logger.error(f"Error getting profile: {e}")
            return {'level': 1, 'total_xp': 0, 'streak': 0}

    def _get_rag_context(self, query: str, limit: int = 5) -> str:
        """Get RAG context by finding semantically similar session notes.

        Uses embedding service to generate query embedding and searches
        pgvector for similar session notes.

        Args:
            query: The query text to find similar sessions for
            limit: Maximum number of similar sessions to retrieve

        Returns:
            Formatted context string with relevant session notes
        """
        try:
            from services.embedding_service import embedding_service

            # Generate embedding for query
            query_embedding = embedding_service.embed(query)
            if not query_embedding:
                logger.warning("Could not generate embedding for RAG query")
                return ""

            # Search for similar sessions
            similar = database.semantic_search_sessions(
                query_embedding,
                limit=limit,
                min_similarity=0.4,
                days_back=30
            )

            if not similar:
                return ""

            # Format context
            context = "\n📚 Semantic search results (related past sessions):\n"
            for s in similar:
                rating_str = f" (productivity: {s['productivity_rating']}%)" if s.get('productivity_rating') else ""
                context += f"- [{s['date']}] {s['category']}: {s['notes'][:200]}{rating_str}\n"

            return context

        except ImportError:
            logger.warning("Embedding service not available for RAG")
            return ""
        except Exception as e:
            logger.error(f"Error getting RAG context: {e}")
            return ""

    def _create_fallback(self, endpoint: str, error: str = None) -> Dict:
        """Create fallback response when AI is unavailable."""
        return {
            'ai_available': False,
            'fallback': True,
            'from_cache': False,
            'error': error or 'AI service unavailable',
            'message': 'Using fallback response - AI analysis not available',
            'timestamp': datetime.now().isoformat()
        }

    def _get_preset_recommender_fallback(self) -> Dict:
        """Create recommendation using PresetRecommender as fallback when AI is unavailable."""
        from models.preset_recommender import PresetRecommender

        try:
            # Get sessions for PresetRecommender
            sessions = self._get_sessions_with_notes(30)

            # Create preset recommendation
            recommender = PresetRecommender(sessions)
            rec = recommender.recommend()

            # Calculate predicted sessions based on confidence
            confidence = rec.get('confidence', 0.5)
            predicted_sessions = max(3, int(confidence * 8))  # 3-8 sessions
            productivity_prediction = int(confidence * 100)

            return {
                'ai_available': False,
                'fallback': True,
                'from_cache': False,
                'using_preset_recommender': True,  # Indicator for frontend
                'yesterday_summary': rec.get('reason', ''),
                'recommendation': rec.get('reason', 'Doporučuji začít s Deep Work presetem.'),
                'prediction': {
                    'predicted_sessions': predicted_sessions,
                    'productivity_prediction': productivity_prediction,
                    'best_hours': '9:00 - 12:00'
                },
                'wellbeing': 'Dbej na pravidelné přestávky a hydrataci.',
                'generated_at': datetime.now().isoformat(),
                'recommended_preset': rec.get('recommended_preset', 'deep_work'),
                'confidence': confidence
            }
        except Exception as e:
            logger.error(f"PresetRecommender fallback failed: {e}")
            # Ultimate fallback if even PresetRecommender fails
            return {
                'ai_available': False,
                'fallback': True,
                'from_cache': False,
                'using_preset_recommender': True,
                'yesterday_summary': 'Zatím nemám dostatek dat pro analýzu.',
                'recommendation': 'Doporučuji začít s Deep Work presetem (52 min práce / 17 min přestávka).',
                'prediction': {
                    'predicted_sessions': 4,
                    'productivity_prediction': 75,
                    'best_hours': '9:00 - 12:00'
                },
                'wellbeing': 'Dbej na pravidelné přestávky a hydrataci.',
                'generated_at': datetime.now().isoformat(),
                'recommended_preset': 'deep_work',
                'confidence': 0.5
            }

    # =========================================================================
    # PUBLIC ANALYSIS METHODS
    # =========================================================================

    def morning_briefing(self) -> Dict:
        """Generate comprehensive morning briefing with RAG context."""
        # Check cache
        cached = self.cache.get_cached('morning_briefing')
        if cached:
            return cached

        sessions = self._get_sessions_with_notes(30)
        if not sessions:
            # Use PresetRecommender fallback instead of empty fallback
            return self._get_preset_recommender_fallback()

        profile = self._get_user_profile()
        today = datetime.now()
        yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')

        # Yesterday's data
        yesterday_sessions = [s for s in sessions if s.get('date') == yesterday]
        yesterday_notes = "\n".join([
            f"- {s.get('notes', '')}" for s in yesterday_sessions if s.get('notes')
        ]) or "No notes from yesterday"

        yesterday_ratings = [s.get('productivity_rating') for s in yesterday_sessions if s.get('productivity_rating')]
        yesterday_rating = sum(yesterday_ratings) / len(yesterday_ratings) if yesterday_ratings else 0

        # Get RAG context for productivity patterns
        rag_context = self._get_rag_context(
            f"morning productivity patterns {today.strftime('%A')} focus work",
            limit=5
        )

        context = {
            'session_data': self.format_session_data(sessions[:15]),  # Limit for faster response
            'day_of_week': today.strftime('%A'),
            'date': today.strftime('%Y-%m-%d'),
            'current_time': today.strftime('%H:%M'),
            'yesterday_sessions': len(yesterday_sessions),
            'yesterday_rating': round(yesterday_rating, 1),
            'streak': profile.get('streak', 0),
            'yesterday_notes': yesterday_notes
        }

        # Build prompt with RAG context
        prompt = self.prompts['morning'].format(**context)
        if rag_context:
            prompt = f"{rag_context}\n\n{prompt}"

        response = self._call_llm(prompt, self._get_system_prompt(), endpoint='morning_briefing')
        result = self._parse_json_response(response)

        if result:
            result['generated_at'] = datetime.now().isoformat()
            result['ai_generated'] = True
            self.cache.set_cache('morning_briefing', result)
            return result

        # Use PresetRecommender fallback when LLM fails
        return self._get_preset_recommender_fallback()

    def evening_review(self) -> Dict:
        """Generate evening review and reflection."""
        cached = self.cache.get_cached('evening_review')
        if cached:
            return cached

        today_sessions = self._get_today_sessions()
        if not today_sessions:
            return self._create_fallback('evening_review', 'No sessions today')

        profile = self._get_user_profile()
        today_notes = "\n".join([
            f"[{s.get('time')}] {s.get('notes', '')}"
            for s in today_sessions if s.get('notes')
        ]) or "No notes today"

        ratings = [s.get('productivity_rating') for s in today_sessions if s.get('productivity_rating')]
        actual_rating = sum(ratings) / len(ratings) if ratings else 0

        context = {
            'today_sessions': self.format_session_data(today_sessions),
            'today_notes': today_notes,
            'predicted_sessions': 5,  # Could get from morning prediction
            'predicted_productivity': 75,
            'actual_sessions': len(today_sessions),
            'actual_rating': round(actual_rating, 1),
            'streak': profile.get('streak', 0),
            'streak_maintained': len(today_sessions) > 0
        }

        prompt = self.prompts['evening'].format(**context)
        response = self._call_llm(prompt, self._get_system_prompt(), endpoint='evening_review')
        result = self._parse_json_response(response)

        if result:
            result['generated_at'] = datetime.now().isoformat()
            result['ai_generated'] = True
            self.cache.set_cache('evening_review', result)
            return result

        return self._create_fallback('evening_review')

    def analyze_burnout(self) -> Dict:
        """Full LLM burnout risk analysis with RAG context."""
        cached = self.cache.get_cached('analyze_burnout')
        if cached:
            return cached

        sessions = self._get_sessions_with_notes(14)  # 2 weeks
        if len(sessions) < 5:
            return self._create_fallback('analyze_burnout', 'Insufficient data (need 5+ sessions)')

        profile = self._get_user_profile()
        baseline = self._get_baseline_stats(sessions)

        # Calculate night percentage
        night_sessions = len([s for s in sessions if s.get('hour', 12) >= 21])
        night_percentage = (night_sessions / len(sessions) * 100) if sessions else 0

        # This week's data
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        weekly_sessions = [s for s in sessions if s.get('date', '') >= week_ago]
        weekly_ratings = [s.get('productivity_rating') for s in weekly_sessions if s.get('productivity_rating')]
        weekly_rating = sum(weekly_ratings) / len(weekly_ratings) if weekly_ratings else 0

        # Get RAG context for burnout-related patterns
        rag_context = self._get_rag_context(
            "tired exhausted stress burnout overwork fatigue low energy",
            limit=5
        )

        context = {
            'session_data': self.format_session_data(sessions),
            'streak': profile.get('streak', 0),
            'weekly_sessions': len(weekly_sessions),
            'weekly_rating': round(weekly_rating, 1),
            'night_percentage': round(night_percentage, 1)
        }

        prompt = self.prompts['burnout'].format(**context)
        if rag_context:
            prompt = f"{rag_context}\n\n{prompt}"

        response = self._call_llm(prompt, self._get_system_prompt(), endpoint='analyze_burnout')
        result = self._parse_json_response(response)

        if result:
            result['generated_at'] = datetime.now().isoformat()
            result['ai_generated'] = True
            result['sessions_analyzed'] = len(sessions)
            self.cache.set_cache('analyze_burnout', result)
            return result

        return self._create_fallback('analyze_burnout')

    def analyze_anomalies(self) -> Dict:
        """Full LLM anomaly detection."""
        cached = self.cache.get_cached('analyze_anomalies')
        if cached:
            return cached

        sessions = self._get_sessions_with_notes(14)
        if len(sessions) < 7:
            return self._create_fallback('analyze_anomalies', 'Insufficient data (need 7+ sessions)')

        baseline = self._get_baseline_stats(sessions)

        context = {
            'session_data': self.format_session_data(sessions),
            'avg_sessions': baseline['avg_sessions'],
            'avg_productivity': baseline['avg_productivity'],
            'typical_hours': baseline['typical_hours'],
            'top_category': baseline['top_category']
        }

        prompt = self.prompts['anomaly'].format(**context)
        response = self._call_llm(prompt, self._get_system_prompt(), endpoint='analyze_anomalies')
        result = self._parse_json_response(response)

        if result:
            result['generated_at'] = datetime.now().isoformat()
            result['ai_generated'] = True
            result['sessions_analyzed'] = len(sessions)
            self.cache.set_cache('analyze_anomalies', result)
            return result

        return self._create_fallback('analyze_anomalies')

    def analyze_quality(self, preset: str = 'deep_work', category: str = None) -> Dict:
        """Full LLM quality prediction before session."""
        params = {'preset': preset, 'category': category}
        cached = self.cache.get_cached('analyze_quality', params)
        if cached:
            return cached

        sessions = self._get_sessions_with_notes(30)
        today_sessions = self._get_today_sessions()

        now = datetime.now()

        # Minutes since last session
        minutes_since_last = 60  # Default
        if today_sessions:
            try:
                last_time = today_sessions[-1].get('time', '12:00')
                last_hour, last_min = map(int, last_time.split(':'))
                last_dt = now.replace(hour=last_hour, minute=last_min)
                minutes_since_last = int((now - last_dt).total_seconds() / 60)
            except:
                pass

        context = {
            'session_data': self.format_session_data(sessions[:30]),
            'hour': now.hour,
            'day_of_week': now.strftime('%A'),
            'preset': preset,
            'category': category or 'Not specified',
            'sessions_today': len(today_sessions),
            'minutes_since_last': max(0, minutes_since_last)
        }

        prompt = self.prompts['quality'].format(**context)
        response = self._call_llm(prompt, self._get_system_prompt(), endpoint='analyze_quality')
        result = self._parse_json_response(response)

        if result:
            result['generated_at'] = datetime.now().isoformat()
            result['ai_generated'] = True
            self.cache.set_cache('analyze_quality', result, params)
            return result

        return self._create_fallback('analyze_quality')

    def get_optimal_schedule(self, day: str = 'today', num_sessions: int = 6) -> Dict:
        """Full LLM schedule optimization."""
        params = {'day': day, 'num_sessions': num_sessions}
        cached = self.cache.get_cached('optimal_schedule', params)
        if cached:
            return cached

        sessions = self._get_sessions_with_notes(30)
        if len(sessions) < 10:
            return self._create_fallback('optimal_schedule', 'Insufficient data (need 10+ sessions)')

        target_day = datetime.now().strftime('%A') if day == 'today' else day.capitalize()

        context = {
            'session_data': self.format_session_data(sessions),
            'target_day': target_day,
            'num_sessions': num_sessions
        }

        prompt = self.prompts['schedule'].format(**context)
        response = self._call_llm(prompt, self._get_system_prompt(), endpoint='optimal_schedule')
        result = self._parse_json_response(response)

        if result:
            result['generated_at'] = datetime.now().isoformat()
            result['ai_generated'] = True
            result['for_day'] = target_day
            self.cache.set_cache('optimal_schedule', result, params)
            return result

        return self._create_fallback('optimal_schedule')

    def integrated_insight(self) -> Dict:
        """Cross-model integrated recommendation."""
        cached = self.cache.get_cached('integrated_insight')
        if cached:
            return cached

        # Get results from other analyses (use cache if available)
        burnout = self.analyze_burnout()
        anomalies = self.analyze_anomalies()
        sessions = self._get_sessions_with_notes(30)

        # Get productivity patterns
        baseline = self._get_baseline_stats(sessions)
        productivity_analysis = {
            'baseline': baseline,
            'recent_trend': 'stable',  # Could calculate
            'sessions_last_7_days': len([s for s in sessions if s.get('date', '') >= (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')])
        }

        # Get schedule analysis
        schedule = self.get_optimal_schedule()

        context = {
            'burnout_analysis': json.dumps(burnout, default=str),
            'anomaly_analysis': json.dumps(anomalies, default=str),
            'productivity_analysis': json.dumps(productivity_analysis, default=str),
            'schedule_analysis': json.dumps(schedule, default=str),
            'session_data': self.format_session_data(sessions[:20])  # Recent context
        }

        prompt = self.prompts['integrated'].format(**context)
        response = self._call_llm(prompt, self._get_system_prompt(), endpoint='integrated_insight')
        result = self._parse_json_response(response)

        if result:
            result['generated_at'] = datetime.now().isoformat()
            result['ai_generated'] = True
            result['models_integrated'] = ['burnout', 'anomaly', 'productivity', 'schedule']
            self.cache.set_cache('integrated_insight', result)
            return result

        return self._create_fallback('integrated_insight')

    def get_learning_recommendations(self) -> Dict:
        """Full LLM learning recommendations."""
        cached = self.cache.get_cached('learning')
        if cached:
            return cached

        sessions = self._get_sessions_with_notes(30)
        if len(sessions) < 5:
            return self._create_fallback('learning', 'Insufficient data')

        profile = self._get_user_profile()
        category_dist = self._get_category_distribution(sessions)
        skill_levels = self._get_skill_levels()

        # Top categories
        top_categories = sorted(
            category_dist.items(),
            key=lambda x: x[1]['sessions'],
            reverse=True
        )[:3]
        top_cat_names = [c[0] for c in top_categories]

        context = {
            'session_data': self.format_session_data(sessions),
            'level': profile.get('level', 1),
            'total_xp': profile.get('total_xp', 0),
            'streak': profile.get('streak', 0),
            'top_categories': ', '.join(top_cat_names),
            'category_distribution': self.format_category_distribution(category_dist),
            'skill_levels': json.dumps(skill_levels, default=str)
        }

        prompt = self.prompts['learning'].format(**context)
        response = self._call_llm(prompt, self._get_system_prompt(), endpoint='learning')
        result = self._parse_json_response(response)

        if result:
            result['generated_at'] = datetime.now().isoformat()
            result['ai_generated'] = True
            self.cache.set_cache('learning', result)
            return result

        return self._create_fallback('learning')

    def health_check(self) -> Dict:
        """Check if AI provider is available (Ollama or Cloud)."""
        import requests

        base_info = {
            'ai_provider': self.ai_provider,
            'configured_model': self.model,
            'cache_status': self.cache.get_status()
        }

        # Cloud AI provider
        if self.ai_provider == 'cloud':
            if not self.cloud_api_key:
                return {
                    **base_info,
                    'status': 'not_configured',
                    'message': 'Cloud AI API key not set (AI_API_KEY)',
                    'cloud_api_url': self.cloud_api_url
                }

            try:
                # Test cloud API with a minimal request
                headers = {
                    "Authorization": f"Bearer {self.cloud_api_key}",
                    "Content-Type": "application/json"
                }
                response = requests.post(
                    f"{self.cloud_api_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.cloud_model,
                        "messages": [{"role": "user", "content": "test"}],
                        "max_tokens": 5
                    },
                    timeout=10
                )

                if response.status_code == 200:
                    return {
                        **base_info,
                        'status': 'healthy',
                        'message': f"Cloud AI ({self.cloud_model}) is available.",
                        'cloud_api_url': self.cloud_api_url
                    }
                else:
                    return {
                        **base_info,
                        'status': 'error',
                        'message': f"Cloud AI returned status {response.status_code}",
                        'cloud_api_url': self.cloud_api_url
                    }
            except Exception as e:
                return {
                    **base_info,
                    'status': 'unavailable',
                    'message': f"Cannot connect to Cloud AI: {str(e)}",
                    'cloud_api_url': self.cloud_api_url
                }

        # Ollama provider (default)
        if not self.enabled:
            return {
                **base_info,
                'status': 'disabled',
                'message': 'Ollama is disabled via OLLAMA_ENABLED=false',
                'ollama_url': self.ollama_url
            }

        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m.get('name', '') for m in models]
                has_model = any(self.ollama_model in name for name in model_names)

                return {
                    **base_info,
                    'status': 'healthy' if has_model else 'model_missing',
                    'message': f"Ollama is running. Model {self.ollama_model} {'found' if has_model else 'not found'}.",
                    'ollama_url': self.ollama_url,
                    'available_models': model_names
                }
            return {
                **base_info,
                'status': 'error',
                'message': f"Ollama returned status {response.status_code}",
                'ollama_url': self.ollama_url
            }
        except Exception as e:
            return {
                **base_info,
                'status': 'unavailable',
                'message': f"Cannot connect to Ollama: {str(e)}",
                'ollama_url': self.ollama_url
            }
