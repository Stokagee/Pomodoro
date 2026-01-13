"""
AI Challenge Generator - Uses Ollama for dynamic challenge generation
"""

import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


class AIChallengeGenerator:
    """Generates personalized challenges and quests using Ollama AI"""

    # Fallback challenges when Ollama is unavailable
    FALLBACK_DAILY_CHALLENGES = [
        {
            "id": "dc_morning_3",
            "title": "Ranni produktivita",
            "description": "Dokoncete 3 sessions pred polednem",
            "target": 3,
            "condition": "before_12",
            "difficulty": "easy",
            "xp_reward": 25,
            "category": None
        },
        {
            "id": "dc_deep_work_2",
            "title": "Deep Work Focus",
            "description": "Dokoncete 2 deep work sessions",
            "target": 2,
            "condition": "preset_deep_work",
            "difficulty": "medium",
            "xp_reward": 50,
            "category": None
        },
        {
            "id": "dc_coding_4",
            "title": "Coding Marathon",
            "description": "Dokoncete 4 coding sessions",
            "target": 4,
            "condition": "category_coding",
            "difficulty": "medium",
            "xp_reward": 50,
            "category": "Coding"
        },
        {
            "id": "dc_perfect_day",
            "title": "Perfektni den",
            "description": "Dokoncete 5 sessions s prumerem 4+ rating",
            "target": 5,
            "condition": "rating_4plus",
            "difficulty": "hard",
            "xp_reward": 75,
            "category": None
        },
        {
            "id": "dc_learning_3",
            "title": "Studijni den",
            "description": "Dokoncete 3 learning sessions",
            "target": 3,
            "condition": "category_learning",
            "difficulty": "medium",
            "xp_reward": 50,
            "category": "Learning"
        }
    ]

    FALLBACK_WEEKLY_QUESTS = [
        {
            "id": "wq_sessions_20",
            "title": "Tydenni cil",
            "description": "Dokoncete 20 sessions tento tyden",
            "target": 20,
            "xp_reward": 150,
            "category": None
        },
        {
            "id": "wq_coding_15",
            "title": "Coding Sprint",
            "description": "15 coding sessions tento tyden",
            "target": 15,
            "xp_reward": 150,
            "category": "Coding"
        },
        {
            "id": "wq_streak_7",
            "title": "Tydenni streak",
            "description": "Session kazdy den tento tyden",
            "target": 7,
            "xp_reward": 200,
            "category": None
        }
    ]

    MOTIVATION_MESSAGES = [
        "Kazda session te priblizuje k tvym cilum!",
        "Jsi na spravne ceste. Pokracuj!",
        "Konzistence je klic k uspechu.",
        "Male kroky vedou k velkym vysledkum.",
        "Dnes je perfektni den pro produktivitu!",
        "Tvoje budouci ja ti podekuje.",
        "Fokus je tvoje superschopnost.",
        "Vydrz! Vysledky prijdou.",
    ]

    def __init__(self, categories: List[str] = None):
        """Initialize the AI Challenge Generator

        Args:
            categories: User's configured categories (from config.json)
        """
        # AI Provider selection: 'ollama' (default) or 'cloud'
        self.ai_provider = os.getenv('AI_PROVIDER', 'ollama').lower()

        # Ollama settings (local)
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://ollama:11434')
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'qwen2.5:0.5b')

        # Cloud AI settings (DeepSeek, OpenAI, etc.)
        self.cloud_api_key = os.getenv('AI_API_KEY', '')
        self.cloud_api_url = os.getenv('AI_API_URL', 'https://api.deepseek.com/v1')
        self.cloud_model = os.getenv('AI_CLOUD_MODEL', 'deepseek-chat')

        # Backward compatibility
        self.model = self.cloud_model if self.ai_provider == 'cloud' else self.ollama_model
        self.enabled = os.getenv('OLLAMA_ENABLED', 'true').lower() == 'true'
        self.timeout = int(os.getenv('OLLAMA_TIMEOUT', '180'))

        # Cache for generated content
        self._cache: Dict[str, Any] = {}
        self._cache_expiry: Dict[str, datetime] = {}

        # User's categories for AI suggestions
        self.categories = categories or []

        logger.info(f"AIChallengeGenerator initialized: provider={self.ai_provider}, model={self.model}")

    def update_categories(self, categories: List[str]):
        """Update categories at runtime (called when web service sends new categories).

        Args:
            categories: List of category names from config
        """
        self.categories = categories or []
        logger.info(f"AIChallengeGenerator categories updated: {len(self.categories)} categories")

    def clear_cache(self, cache_type: str = None) -> int:
        """Clear internal cache.

        Args:
            cache_type: Optional specific cache type to clear (e.g., 'next_session', 'learning_rec').
                       If None, clears all caches.

        Returns:
            Number of cache entries cleared
        """
        if cache_type:
            # Clear specific cache type
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(cache_type)]
            for key in keys_to_remove:
                del self._cache[key]
                if key in self._cache_expiry:
                    del self._cache_expiry[key]
            logger.info(f"Cleared {len(keys_to_remove)} cache entries for type: {cache_type}")
            return len(keys_to_remove)
        else:
            # Clear all cache
            count = len(self._cache)
            self._cache.clear()
            self._cache_expiry.clear()
            logger.info(f"Cleared all {count} cache entries")
            return count

    def health_check(self) -> Dict[str, Any]:
        """Check if AI provider is available (Ollama or Cloud)"""
        import requests

        base_info = {
            "ai_provider": self.ai_provider,
            "configured_model": self.model
        }

        # Cloud AI provider
        if self.ai_provider == 'cloud':
            if not self.cloud_api_key:
                return {**base_info, "status": "not_configured", "message": "Cloud AI API key not set"}

            try:
                headers = {"Authorization": f"Bearer {self.cloud_api_key}", "Content-Type": "application/json"}
                response = requests.post(
                    f"{self.cloud_api_url}/chat/completions",
                    headers=headers,
                    json={"model": self.cloud_model, "messages": [{"role": "user", "content": "test"}], "max_tokens": 5},
                    timeout=10
                )
                if response.status_code == 200:
                    return {**base_info, "status": "healthy", "message": f"Cloud AI ({self.cloud_model}) is available."}
                return {**base_info, "status": "error", "message": f"Cloud AI returned {response.status_code}"}
            except Exception as e:
                return {**base_info, "status": "unavailable", "message": str(e)}

        # Ollama provider (default)
        if not self.enabled:
            return {**base_info, "status": "disabled", "message": "Ollama is disabled", "ollama_url": self.ollama_url}

        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m.get('name', '') for m in models]
                has_model = any(self.ollama_model in name for name in model_names)
                return {
                    **base_info,
                    "status": "healthy" if has_model else "model_missing",
                    "message": f"Ollama is running. Model {self.ollama_model} {'found' if has_model else 'not found'}.",
                    "ollama_url": self.ollama_url,
                    "available_models": model_names
                }
            return {**base_info, "status": "error", "message": f"Ollama returned {response.status_code}", "ollama_url": self.ollama_url}
        except Exception as e:
            return {**base_info, "status": "unavailable", "message": str(e), "ollama_url": self.ollama_url}

    def _get_cache_key(self, prefix: str, context: Dict) -> str:
        """Generate cache key from context"""
        context_str = json.dumps(context, sort_keys=True)
        return f"{prefix}_{hashlib.md5(context_str.encode()).hexdigest()[:8]}"

    def _is_cache_valid(self, key: str, max_age_hours: int = 1) -> bool:
        """Check if cached value is still valid"""
        if key not in self._cache or key not in self._cache_expiry:
            return False
        return datetime.now() < self._cache_expiry[key]

    def _call_llm(self, prompt: str, system_prompt: str = None) -> Optional[str]:
        """Route LLM call to appropriate provider (Ollama or Cloud)."""
        if self.ai_provider == 'cloud':
            return self._call_cloud_api(prompt, system_prompt)
        return self._call_ollama(prompt, system_prompt)

    def _call_cloud_api(self, prompt: str, system_prompt: str = None) -> Optional[str]:
        """Make a call to Cloud AI API (DeepSeek, OpenAI-compatible)."""
        if not self.cloud_api_key:
            logger.warning("Cloud AI API key not configured")
            return None

        try:
            import requests
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = requests.post(
                f"{self.cloud_api_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.cloud_api_key}", "Content-Type": "application/json"},
                json={"model": self.cloud_model, "messages": messages, "temperature": 0.7, "max_tokens": 500},
                timeout=self.timeout
            )

            if response.status_code == 200:
                return response.json().get('choices', [{}])[0].get('message', {}).get('content', '')
            logger.error(f"Cloud AI error: {response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Cloud AI call failed: {e}")
            return None

    def _call_ollama(self, prompt: str, system_prompt: str = None) -> Optional[str]:
        """Make a call to Ollama API (local)"""
        if not self.enabled:
            return None

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
                        "num_predict": 500
                    }
                },
                timeout=self.timeout
            )

            if response.status_code == 200:
                result = response.json()
                return result.get('message', {}).get('content', '')
            else:
                logger.error(f"Ollama API error: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            return None

    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """Extract JSON from AI response"""
        if not response:
            return None

        try:
            # Try direct parse
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in response
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except json.JSONDecodeError:
            pass

        return None

    def generate_daily_challenge(self, user_context: Dict) -> Dict:
        """
        Generate a personalized daily challenge

        Args:
            user_context: Dict with user stats (level, avg_sessions, top_category, streak, etc.)

        Returns:
            Dict with challenge details
        """
        cache_key = self._get_cache_key("daily", {"date": datetime.now().strftime("%Y-%m-%d")})

        if self._is_cache_valid(cache_key, max_age_hours=12):
            return self._cache[cache_key]

        # Try AI generation
        if self.enabled:
            challenge = self._generate_ai_challenge(user_context)
            if challenge:
                self._cache[cache_key] = challenge
                self._cache_expiry[cache_key] = datetime.now() + timedelta(hours=12)
                return challenge

        # Fallback to predefined challenge
        challenge = self._select_fallback_challenge(user_context)
        challenge['ai_generated'] = False

        self._cache[cache_key] = challenge
        self._cache_expiry[cache_key] = datetime.now() + timedelta(hours=12)

        return challenge

    def _generate_ai_challenge(self, user_context: Dict) -> Optional[Dict]:
        """Generate challenge using Ollama"""
        system_prompt = """Jsi pomocnik pro Pomodoro timer aplikaci. Generujes denni vyzvy pro uzivatele.
Odpovez POUZE validnim JSON objektem bez dalsiho textu."""

        prompt = f"""Vygeneruj denni vyzvu pro Pomodoro timer uzivatele.

Kontext uzivatele:
- Level: {user_context.get('level', 1)}
- Prumer sessions/den: {user_context.get('avg_sessions', 3)}
- Nejcastejsi kategorie: {user_context.get('top_category', 'Coding')}
- Aktualni streak: {user_context.get('streak', 0)} dni
- Slaba mista: {user_context.get('weak_areas', 'zadna data')}

Pravidla:
1. Vyzva musi byt dosazitelna ale motivujici
2. Pro nizsi levely jednodussi ukoly
3. Pis cesky bez hacku a carek
4. XP reward: easy=25, medium=50, hard=75

Vrat JSON v tomto formatu:
{{
    "id": "dc_YYYYMMDD",
    "title": "Nazev vyzvy",
    "description": "Popis co udelat",
    "target": 3,
    "difficulty": "medium",
    "xp_reward": 50,
    "category": null
}}"""

        response = self._call_llm(prompt, system_prompt)
        challenge = self._parse_json_response(response)

        if challenge:
            challenge['ai_generated'] = True
            challenge['id'] = f"dc_{datetime.now().strftime('%Y%m%d')}"
            return challenge

        return None

    def _select_fallback_challenge(self, user_context: Dict) -> Dict:
        """Select appropriate fallback challenge based on user context"""
        level = user_context.get('level', 1)
        top_category = user_context.get('top_category', '')

        # Filter challenges by difficulty based on level
        if level < 5:
            candidates = [c for c in self.FALLBACK_DAILY_CHALLENGES
                         if c['difficulty'] in ['easy', 'medium']]
        else:
            candidates = self.FALLBACK_DAILY_CHALLENGES

        # Prefer challenges matching user's top category
        category_matches = [c for c in candidates
                          if c.get('category') and top_category and
                          c['category'].lower() == top_category.lower()]

        if category_matches:
            candidates = category_matches

        # Select based on day of year for variety
        day_index = datetime.now().timetuple().tm_yday % len(candidates)
        return candidates[day_index].copy()

    def generate_weekly_quests(self, user_profile: Dict) -> List[Dict]:
        """
        Generate weekly quests

        Args:
            user_profile: Dict with user profile data

        Returns:
            List of quest dicts
        """
        cache_key = self._get_cache_key("weekly", {
            "week": datetime.now().isocalendar()[1]
        })

        if self._is_cache_valid(cache_key, max_age_hours=24):
            return self._cache[cache_key]

        # Try AI generation
        if self.enabled:
            quests = self._generate_ai_quests(user_profile)
            if quests:
                self._cache[cache_key] = quests
                self._cache_expiry[cache_key] = datetime.now() + timedelta(hours=24)
                return quests

        # Fallback quests
        week_num = datetime.now().isocalendar()[1]
        quests = []
        for i, quest in enumerate(self.FALLBACK_WEEKLY_QUESTS):
            q = quest.copy()
            q['id'] = f"wq_w{week_num}_{i}"
            q['ai_generated'] = False
            quests.append(q)

        self._cache[cache_key] = quests
        self._cache_expiry[cache_key] = datetime.now() + timedelta(hours=24)

        return quests

    def _generate_ai_quests(self, user_profile: Dict) -> Optional[List[Dict]]:
        """Generate weekly quests using Ollama"""
        system_prompt = """Jsi pomocnik pro Pomodoro timer. Generujes tydeni questy.
Odpovez POUZE validnim JSON polem bez dalsiho textu."""

        prompt = f"""Vygeneruj 3 tydeni questy pro Pomodoro timer uzivatele.

Profil uzivatele:
- Level: {user_profile.get('level', 1)}
- XP: {user_profile.get('xp', 0)}
- Prumer sessions/tyden: {user_profile.get('weekly_avg', 15)}
- Nejlepsi kategorie: {user_profile.get('best_categories', ['Coding'])}

Pravidla:
1. Kazdy quest by mel trvat cely tyden
2. Ruznorode ukoly (sessions, kategorie, streaky)
3. XP reward: 100-200 podle obtiznosti
4. Pis cesky bez hacku a carek

Vrat JSON pole v tomto formatu:
[
    {{"id": "wq_1", "title": "Nazev", "description": "Popis", "target": 20, "xp_reward": 150, "category": null}},
    {{"id": "wq_2", "title": "Nazev", "description": "Popis", "target": 15, "xp_reward": 150, "category": "Coding"}},
    {{"id": "wq_3", "title": "Nazev", "description": "Popis", "target": 7, "xp_reward": 200, "category": null}}
]"""

        response = self._call_llm(prompt, system_prompt)

        if not response:
            return None

        try:
            # Try to parse as array
            quests = json.loads(response)
            if isinstance(quests, list) and len(quests) > 0:
                week_num = datetime.now().isocalendar()[1]
                for i, q in enumerate(quests):
                    q['id'] = f"wq_w{week_num}_{i}"
                    q['ai_generated'] = True
                return quests
        except json.JSONDecodeError:
            # Try to find array in response
            try:
                start = response.find('[')
                end = response.rfind(']') + 1
                if start >= 0 and end > start:
                    quests = json.loads(response[start:end])
                    if isinstance(quests, list):
                        week_num = datetime.now().isocalendar()[1]
                        for i, q in enumerate(quests):
                            q['id'] = f"wq_w{week_num}_{i}"
                            q['ai_generated'] = True
                        return quests
            except json.JSONDecodeError:
                pass

        return None

    def generate_motivation_message(self, context: Dict) -> str:
        """
        Generate personalized motivation message

        Args:
            context: Dict with current user state (streak, sessions_today, etc.)

        Returns:
            Motivation message string
        """
        if self.enabled:
            message = self._generate_ai_motivation(context)
            if message:
                return message

        # Fallback to random predefined message
        import random
        return random.choice(self.MOTIVATION_MESSAGES)

    def _generate_ai_motivation(self, context: Dict) -> Optional[str]:
        """Generate motivation using Ollama"""
        system_prompt = "Jsi motivacni kouč pro produktivitu. Odpovez jednou vetou cesky bez hacku a carek."

        prompt = f"""Napise kratkou motivacni zpravu (1 veta) pro uzivatele Pomodoro timeru.

Kontext:
- Dnesni sessions: {context.get('sessions_today', 0)}
- Aktualni streak: {context.get('streak', 0)} dni
- Cas: {datetime.now().strftime('%H:%M')}
- Nalada: {context.get('mood', 'neutralni')}

Odpovez pouze jednou motivacni vetou."""

        response = self._call_llm(prompt, system_prompt)
        if response:
            # Clean up response
            response = response.strip().strip('"').strip("'")
            if len(response) < 200:  # Sanity check
                return response

        return None

    def suggest_achievement_focus(self, achievements: List[Dict]) -> Dict:
        """
        Suggest which achievement to focus on next

        Args:
            achievements: List of achievement dicts with progress

        Returns:
            Dict with suggestion and reason
        """
        # Find achievements closest to completion
        in_progress = [a for a in achievements
                      if not a.get('unlocked') and a.get('percentage', 0) > 0]

        if not in_progress:
            # Find easiest locked achievements
            locked = [a for a in achievements if not a.get('unlocked')]
            if locked:
                # Sort by target (lower = easier)
                locked.sort(key=lambda x: x.get('target', 999))
                suggestion = locked[0]
                return {
                    "achievement_id": suggestion.get('id'),
                    "name": suggestion.get('name'),
                    "reason": f"Zacni s {suggestion.get('name')} - je nejsnazsi k odemceni!",
                    "progress": 0,
                    "target": suggestion.get('target')
                }
            return {
                "achievement_id": None,
                "name": None,
                "reason": "Vsechny achievements jsou odemcene!",
                "progress": 100,
                "target": 100
            }

        # Sort by percentage (highest = closest)
        in_progress.sort(key=lambda x: x.get('percentage', 0), reverse=True)
        closest = in_progress[0]

        return {
            "achievement_id": closest.get('id'),
            "name": closest.get('name'),
            "reason": f"{closest.get('name')} - uz mas {closest.get('percentage', 0):.0f}%!",
            "progress": closest.get('progress', 0),
            "target": closest.get('target', 1)
        }

    # =========================================================================
    # FocusAI - Learning Recommendation System
    # =========================================================================

    FOCUSAI_SYSTEM_PROMPT = """You are FocusAI - pragmatic mentor for a QA Test Automation Engineer actively job hunting.

PRIORITY ORDER (always respect):
1. JOB HUNTING - CV, portfolio, interview prep, LinkedIn, applications
2. SKILL BUILDING - Robot Framework, API testing (Postman/SOAP UI), SQL, automation
3. LEARNING - new tools, certifications (self-study only, no paid courses)

STYLE:
- Direct, no fluff, max 2 sentences per point
- Always say: WHAT + WHY + WHEN
- Data-backed when possible

RULES:
1. If no Job Hunting in 2+ days -> remind about priority #1
2. If time > 18:00 -> suggest rest, not more work
3. If < 4 sessions today -> suggest lighter tasks
4. Every recommendation has EXPIRATION: today | this_week | ongoing
5. Skip generic advice - be specific to QA testing context
6. If recommending learning: explain how it helps job hunting

RECOMMENDATION FORMAT:
- priority: 1|2|3
- action: specific task (max 50 chars)
- reason: why now (max 30 chars)
- expires: today|this_week|ongoing
- skip_if: when to ignore this advice

OUTPUT: JSON only, no additional text."""

    def generate_learning_recommendations(self, user_data: Dict) -> Dict:
        """
        Generate comprehensive learning recommendations using FocusAI.

        Args:
            user_data: Dict containing:
                - recent_sessions: List of recent sessions
                - category_distribution: Dict with category percentages
                - skill_levels: List of category skill levels
                - streak_data: Dict with streak statistics
                - recent_tasks: List of recent task descriptions
                - productivity_by_time: Dict with hourly productivity
                - achievements_progress: List of near-completion achievements
                - user_profile: Dict with user profile data

        Returns:
            LearningRecommendation as dict
        """
        cache_key = self._get_cache_key("learning_rec", {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "sessions_count": len(user_data.get('recent_sessions', []))
        })

        if self._is_cache_valid(cache_key, max_age_hours=2):
            return self._cache[cache_key]

        # Try AI generation
        if self.enabled:
            recommendation = self._generate_ai_learning_recommendations(user_data)
            if recommendation:
                self._cache[cache_key] = recommendation
                self._cache_expiry[cache_key] = datetime.now() + timedelta(hours=2)
                return recommendation

        # Fallback
        from .pydantic_models import FallbackSuggestion
        fallback = FallbackSuggestion.get_learning_recommendation()
        self._cache[cache_key] = fallback
        self._cache_expiry[cache_key] = datetime.now() + timedelta(hours=6)
        return fallback

    def _generate_ai_learning_recommendations(self, user_data: Dict) -> Optional[Dict]:
        """Generate learning recommendations using Ollama with structured output"""
        # Prepare context summary
        category_dist = user_data.get('category_distribution', {})
        skill_levels = user_data.get('skill_levels', [])
        recent_tasks = user_data.get('recent_tasks', [])
        user_profile = user_data.get('user_profile', {})

        # Format category distribution
        cat_summary = "\n".join([
            f"- {cat}: {data.get('percentage', 0)}% ({data.get('sessions', 0)} sessions)"
            for cat, data in category_dist.items()
        ]) or "Zadna data"

        # Format skill levels
        skill_summary = "\n".join([
            f"- {s.get('category', 'Unknown')}: Level {s.get('level', 1)}"
            for s in skill_levels
        ]) or "Zadna data"

        # Format recent tasks (limit to 20)
        task_list = [t.get('task', '') for t in recent_tasks[:20] if t.get('task')]
        tasks_summary = ", ".join(task_list[:15]) if task_list else "Zadna data"

        prompt = f"""Analyzuj data uzivatele a vygeneruj doporuceni pro uceni.

UZIVATELSKA DATA:

Profil:
- Level: {user_profile.get('level', 1)}
- Celkem XP: {user_profile.get('total_xp_earned', 0)}
- Streak: {user_profile.get('streak', 0)} dni

Rozdeleni kategorii (posledni mesic):
{cat_summary}

Skill levely:
{skill_summary}

Posledni ulohy:
{tasks_summary}

Dnesni datum: {datetime.now().strftime('%Y-%m-%d')}
Aktualni cas: {datetime.now().strftime('%H:%M')}

TVUJ UKOL:
1. Identifikuj skill mezery (kategorie s nizkym levelem nebo malo sessions)
2. Navrhni 3-5 konkretnich temat k uceni
3. Analyzuj vyvazenost kategorii
4. Dej 2-3 personalizovane tipy
5. Doporuc dalsi session
6. Extrahuj technologie/koncepty z uloh
7. Napisi motivacni zpravu

Vrat JSON v tomto PRESNEM formatu:
{{
    "skill_gaps": [
        {{"category": "Learning", "current_level": 1, "recommended_level": 2, "gap_description": "Malo uceni sessions", "importance": "high"}}
    ],
    "recommended_topics": [
        {{"topic": "Konkretni tema", "category": "Coding", "reason": "Proc se to ucit", "priority": "high", "estimated_sessions": 5, "related_to": null}}
    ],
    "category_balance": [
        {{"category": "Coding", "current_percentage": 80, "recommended_percentage": 50, "status": "too_much"}}
    ],
    "personalized_tips": ["Tip 1", "Tip 2"],
    "next_session_suggestion": {{"category": "Learning", "topic": "Konkretni tema", "preset": "deep_work", "reason": "Proc ted", "confidence": 0.8}},
    "user_knowledge": {{"technologies": ["React", "Python"], "concepts": ["async", "hooks"], "expertise_areas": ["frontend"]}},
    "motivational_message": "Motivacni zprava",
    "analysis_summary": "Kratke shrnuti analyzy",
    "confidence_score": 0.85
}}"""

        response = self._call_llm(prompt, self.FOCUSAI_SYSTEM_PROMPT)
        result = self._parse_json_response(response)

        if result:
            result['generated_at'] = datetime.now().isoformat()
            result['ai_generated'] = True
            return result

        return None

    def suggest_next_session_topic(self, context: Dict) -> Dict:
        """
        Generate a quick suggestion for the next session.
        Optimized for fast response at timer start.

        Args:
            context: Dict containing:
                - last_category: Last used category
                - last_task: Last task description
                - time_of_day: Current hour (0-23)
                - sessions_today: Number of sessions completed today
                - exclude_topic: Topic to exclude (for "Jiný nápad" functionality)

        Returns:
            SessionSuggestion as dict
        """
        # Check if we need to skip cache (user wants different suggestion)
        exclude_topic = context.get('exclude_topic', '')
        bypass_cache = context.get('bypass_cache', False)  # Force refresh without cache

        cache_key = self._get_cache_key("next_session", {
            "date": datetime.now().strftime("%Y-%m-%d"),  # Include date for daily variety
            "hour": context.get('time_of_day', 12),
            "sessions": context.get('sessions_today', 0)
        })

        # Skip cache if exclude_topic is provided OR bypass_cache is True
        if not exclude_topic and not bypass_cache and self._is_cache_valid(cache_key, max_age_hours=0.25):  # 15 minutes
            return self._cache[cache_key]

        # Try AI generation with shorter timeout
        if self.enabled:
            suggestion = self._generate_ai_session_suggestion(context)
            if suggestion:
                # Only cache if not excluding topic (normal request)
                if not exclude_topic:
                    self._cache[cache_key] = suggestion
                    self._cache_expiry[cache_key] = datetime.now() + timedelta(minutes=15)
                return suggestion

        # Fallback
        from .pydantic_models import FallbackSuggestion
        fallback = FallbackSuggestion.get_session_suggestion(
            context.get('last_category'),
            context.get('time_of_day', 12)
        )
        self._cache[cache_key] = fallback
        self._cache_expiry[cache_key] = datetime.now() + timedelta(minutes=5)
        return fallback

    def _generate_ai_session_suggestion(self, context: Dict) -> Optional[Dict]:
        """Generate quick session suggestion using AI (Ollama or Cloud API)"""
        # Build category list string - use user's categories or fallback to "Other"
        categories_str = ", ".join(self.categories) if self.categories else "Other"

        # Získat bohatší kontext
        weekly_stats = context.get('weekly_stats', {})
        user_profile = context.get('user_profile', {})

        # System prompt - pragmatic mentor for QA tester job hunting
        system_prompt = f"""You are FocusAI - pragmatic mentor for QA Test Automation Engineer actively job hunting.

STYLE:
- Direct, no fluff
- Efficiency-focused
- Actionable, specific tasks only

USER CONTEXT - QA TESTER tools:
- Postman (API testing)
- SOAP UI (web services, SOAP/REST)
- Robot Framework (test automation)
- DBeaver (database verification)

PRIORITY ORDER:
1. JOB HUNTING - CV, LinkedIn, interview prep, applications, portfolio
2. SKILL BUILDING - automation, API testing, SQL queries
3. LEARNING - new tools (self-study only)

TASK TYPES to suggest:
- API tests in Postman (collections, environments, assertions)
- Automated tests in Robot Framework
- SOAP/REST testing in SOAP UI
- DB data verification via DBeaver
- Test case writing, bug reports
- Defect analysis, root cause analysis
- Regression and smoke tests
- CV/LinkedIn updates (for Job Hunting category)

CRITICAL RULES:
- Category MUST be exactly one of: {categories_str}
- If no Job Hunting in 2+ days -> prioritize Job Hunting
- If time > 18:00 -> suggest rest or light tasks
- Reply with VALID JSON only
- Topic: specific (max 50 chars)
- Reason: brief (max 100 chars)
- English only"""

        hour = context.get('time_of_day', 12)
        time_context = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
        day_name = context.get('day_name', 'today')

        # Format category breakdown from weekly stats
        categories_breakdown = weekly_stats.get('categories', {})
        categories_info = ", ".join([f"{k}: {v}x" for k, v in categories_breakdown.items()]) if categories_breakdown else "no data"

        # Check if Job Hunting was done recently
        job_hunting_count = categories_breakdown.get('Job Hunting', 0)
        job_hunting_note = "ALERT: No Job Hunting this week!" if job_hunting_count == 0 else f"Job Hunting: {job_hunting_count}x this week"

        # Build exclusion note for "Jiný nápad" functionality
        exclude_topic = context.get('exclude_topic', '')
        exclusion_note = f"\n\nIMPORTANT: User wants a DIFFERENT suggestion. Do NOT suggest this topic: '{exclude_topic}'. Suggest something completely different!\n" if exclude_topic else ""

        prompt = f"""Suggest next Pomodoro session.{exclusion_note}

CURRENT CONTEXT:
- Time: {hour}:00 ({time_context})
- Day: {day_name}
- Sessions today: {context.get('sessions_today', 0)}
- Last category: {context.get('last_category', 'unknown')}
- Last task: {context.get('last_task', 'unknown')}

WEEKLY STATS (last 7 days):
- Total sessions: {weekly_stats.get('weekly_total', 0)}
- Avg productivity: {weekly_stats.get('avg_productivity', 0)}/5
- Category distribution: {categories_info}
- Streak: {weekly_stats.get('streak', 0)} days
- {job_hunting_note}

ALLOWED CATEGORIES: {categories_str}

DECISION LOGIC:
1. Morning (6-12): Deep work - complex tasks, {self._get_time_recommendation(hour)}
2. Afternoon (12-17): Learning or routine tasks
3. Evening (17+): Light tasks, documentation, planning, OR rest

4. If Job Hunting < 2 sessions this week -> prioritize Job Hunting
5. If one category > 50% of weekly sessions -> suggest different category for balance
6. If productivity < 3.0 -> suggest shorter/lighter session (quick_tasks preset)
7. If time > 18:00 -> prefer rest or very light tasks

Return ONLY this JSON (no other text):
{{
    "category": "<exactly one of: {categories_str}>",
    "topic": "Specific task (max 50 chars)",
    "preset": "deep_work|learning|quick_tasks|flow_mode",
    "reason": "Brief reason (max 100 chars)",
    "confidence": 0.0-1.0
}}"""

        response = self._call_llm(prompt, system_prompt)
        result = self._parse_json_response(response)
        if result and 'topic' in result:
            # Validate and fix category if needed
            result = self._validate_and_fix_category(result)
            result['ai_generated'] = True
            return result

        return None

    def _validate_and_fix_category(self, result: Dict) -> Dict:
        """Validate AI response category and fix if necessary.

        Args:
            result: AI response dict with 'category' field

        Returns:
            Result with validated/corrected category
        """
        suggested_category = result.get('category', '')

        if self.categories:
            # Check exact match
            if suggested_category in self.categories:
                return result

            # Check case-insensitive match
            for cat in self.categories:
                if cat.lower() == suggested_category.lower():
                    result['category'] = cat
                    return result

            # Fallback: use 'Other' if available, otherwise first category
            if 'Other' in self.categories:
                result['category'] = 'Other'
            else:
                result['category'] = self.categories[0]

            result['category_corrected'] = True
            logger.warning(f"AI suggested invalid category '{suggested_category}', corrected to '{result['category']}'")

        return result

    def _get_time_recommendation(self, hour: int) -> str:
        """Get recommendation based on time of day"""
        if 5 <= hour < 12:
            return "complex tasks (automation, API testing) - morning brain is fresh"
        elif 12 <= hour < 14:
            return "lighter tasks (review, planning) - post-lunch energy dip"
        elif 14 <= hour < 18:
            return "learning or routine work - afternoon is good for skill building"
        else:
            return "planning tomorrow or rest - evening is for reflection, not heavy work"

    def extract_topics_from_tasks(self, tasks: List[Dict]) -> Dict:
        """
        Extract technologies, concepts, and expertise areas from task history.

        Args:
            tasks: List of task dicts with 'task' and 'category' fields

        Returns:
            UserKnowledge as dict
        """
        if not tasks:
            return {
                "technologies": [],
                "concepts": [],
                "expertise_areas": []
            }

        cache_key = self._get_cache_key("topics", {
            "task_count": len(tasks),
            "first_task": tasks[0].get('task', '')[:20] if tasks else ''
        })

        if self._is_cache_valid(cache_key, max_age_hours=1):
            return self._cache[cache_key]

        if self.enabled:
            result = self._generate_ai_topic_extraction(tasks)
            if result:
                self._cache[cache_key] = result
                self._cache_expiry[cache_key] = datetime.now() + timedelta(hours=1)
                return result

        # Fallback - simple keyword extraction
        result = self._simple_topic_extraction(tasks)
        self._cache[cache_key] = result
        self._cache_expiry[cache_key] = datetime.now() + timedelta(minutes=30)
        return result

    def _generate_ai_topic_extraction(self, tasks: List[Dict]) -> Optional[Dict]:
        """Extract topics using Ollama"""
        system_prompt = """Analyzuj ulohy a extrahuj technologie, koncepty a oblasti expertizy.
Odpovez POUZE JSON objektem."""

        task_list = [t.get('task', '') for t in tasks[:30] if t.get('task')]
        tasks_text = "\n".join([f"- {t}" for t in task_list])

        prompt = f"""Analyzuj tyto ulohy uzivatele a identifikuj:

ULOHY:
{tasks_text}

Extrahuj:
1. technologies - programovaci jazyky, frameworky, nastroje (napr. React, Python, Docker)
2. concepts - koncepty ktere se uci (napr. async, hooks, testing, API design)
3. expertise_areas - oblasti expertizy (napr. frontend, backend, DevOps, data)

Vrat JSON:
{{
    "technologies": ["React", "Python", "Docker"],
    "concepts": ["async", "hooks", "testing"],
    "expertise_areas": ["frontend", "backend"]
}}"""

        response = self._call_llm(prompt, system_prompt)
        return self._parse_json_response(response)

    def _simple_topic_extraction(self, tasks: List[Dict]) -> Dict:
        """Simple keyword-based topic extraction as fallback"""
        technologies = set()
        concepts = set()
        expertise_areas = set()

        # Common technology keywords
        tech_keywords = {
            'react': 'React', 'vue': 'Vue', 'angular': 'Angular',
            'python': 'Python', 'javascript': 'JavaScript', 'typescript': 'TypeScript',
            'docker': 'Docker', 'kubernetes': 'Kubernetes', 'aws': 'AWS',
            'node': 'Node.js', 'flask': 'Flask', 'django': 'Django',
            'sql': 'SQL', 'mongodb': 'MongoDB', 'postgres': 'PostgreSQL',
            'git': 'Git', 'api': 'API', 'rest': 'REST', 'graphql': 'GraphQL'
        }

        # Common concept keywords
        concept_keywords = {
            'async': 'async programming', 'testing': 'testing', 'test': 'testing',
            'hooks': 'React hooks', 'state': 'state management',
            'auth': 'authentication', 'security': 'security',
            'refactor': 'refactoring', 'optimization': 'optimization',
            'design': 'design patterns', 'architecture': 'architecture'
        }

        # Expertise area keywords
        area_keywords = {
            'frontend': 'Frontend', 'backend': 'Backend', 'fullstack': 'Full-stack',
            'devops': 'DevOps', 'database': 'Database', 'mobile': 'Mobile',
            'ui': 'UI/UX', 'ux': 'UI/UX', 'ml': 'Machine Learning',
            'data': 'Data Engineering'
        }

        for task in tasks:
            task_text = task.get('task', '').lower()
            category = task.get('category', '').lower()

            # Check for technologies
            for keyword, tech in tech_keywords.items():
                if keyword in task_text:
                    technologies.add(tech)

            # Check for concepts
            for keyword, concept in concept_keywords.items():
                if keyword in task_text:
                    concepts.add(concept)

            # Check for expertise areas
            for keyword, area in area_keywords.items():
                if keyword in task_text or keyword in category:
                    expertise_areas.add(area)

            # Map categories to expertise areas
            category_to_area = {
                'coding': 'Software Development',
                'learning': 'Continuous Learning',
                'design': 'UI/UX',
                'review': 'Code Review',
                'planning': 'Project Management'
            }
            if category in category_to_area:
                expertise_areas.add(category_to_area[category])

        return {
            "technologies": list(technologies)[:10],
            "concepts": list(concepts)[:10],
            "expertise_areas": list(expertise_areas)[:5]
        }

    def analyze_productivity_patterns(self, data: Dict) -> Dict:
        """
        Analyze productivity patterns and provide recommendations.

        Args:
            data: Dict with productivity data (hourly stats, daily stats, etc.)

        Returns:
            PatternAnalysis as dict
        """
        hourly_stats = data.get('hourly_productivity', {})
        daily_stats = data.get('daily_stats', {})

        # Calculate best and worst hours
        if hourly_stats:
            sorted_hours = sorted(
                hourly_stats.items(),
                key=lambda x: x[1].get('sessions', 0),
                reverse=True
            )
            best_hours = [int(h) for h, _ in sorted_hours[:3]]
            worst_hours = [int(h) for h, _ in sorted_hours[-3:] if sorted_hours]
        else:
            best_hours = [9, 10, 14]
            worst_hours = [12, 13, 22]

        # Find best day
        if daily_stats:
            best_day = max(daily_stats.items(), key=lambda x: x[1].get('sessions', 0))[0]
        else:
            best_day = "Unknown"

        # Calculate average sessions
        total_sessions = sum(d.get('sessions', 0) for d in daily_stats.values())
        days_count = len(daily_stats) or 1
        avg_sessions = round(total_sessions / days_count, 1)

        # Generate recommendations
        recommendations = []
        if best_hours:
            recommendations.append(
                f"Tvoje nejproduktivnejsi hodiny jsou kolem {best_hours[0]}:00 - plánuj náročné úkoly na tento čas"
            )
        if avg_sessions < 3:
            recommendations.append(
                "Zkus zvýšit počet sessions na den - konzistence je klíč k úspěchu"
            )
        if len(hourly_stats) > 12:
            recommendations.append(
                "Pracuješ v širokem časovém rozmezí - zkus se soustředit na menší počet produktivních hodin"
            )

        return {
            "productivity": {
                "best_hours": best_hours,
                "worst_hours": worst_hours,
                "best_day": best_day,
                "avg_sessions_per_day": avg_sessions,
                "consistency_score": min(1.0, avg_sessions / 5)  # 5 sessions/day = 100%
            },
            "recommendations": recommendations,
            "warnings": []
        }

    # =========================================================================
    # Expand Suggestion - Follow-up questions for AI recommendations
    # =========================================================================

    def expand_suggestion(self, suggestion: Dict, question_type: str, user_context: Dict = None) -> Dict:
        """
        Expand a previous AI suggestion with more details based on question type.

        Args:
            suggestion: Original suggestion dict with category, topic, reason
            question_type: Type of follow-up question:
                - 'resources': Learning resources, documentation, tutorials
                - 'steps': Concrete action steps
                - 'time_estimate': Time needed to complete/learn
                - 'connection': How it connects to career goals
            user_context: Optional dict with real user data:
                - recent_tasks: List of actual user tasks
                - category_sessions: Recent sessions in this category
                - user_tools: List of user's tools/technologies

        Returns:
            Dict with expanded answer
        """
        from prompts import EXPAND_SUGGESTION_PROMPT

        # Map question types to icons
        icons = {
            'resources': '📚',
            'steps': '🎯',
            'time_estimate': '⏱️',
            'connection': '🔗'
        }

        # Validate question type
        if question_type not in icons:
            question_type = 'resources'

        # Prepare user context data for prompt
        user_tasks = "Žádné záznamy"
        recent_sessions = "Žádné záznamy"
        user_tools = "Postman, Robot Framework, DBeaver, SOAP UI"  # default

        if user_context:
            # Format user tasks
            tasks = user_context.get('recent_tasks', [])
            if tasks:
                user_tasks = "\n".join([f"• {t}" for t in tasks[:10] if t])

            # Format sessions with notes
            sessions = user_context.get('category_sessions', [])
            if sessions:
                session_lines = []
                for s in sessions[:5]:
                    task = s.get('task', 'Unknown task')
                    rating = s.get('productivity_rating', 'N/A')
                    notes = s.get('notes', '')
                    line = f"• {task} (produktivita: {rating})"
                    if notes:
                        line += f"\n  Poznámky: {notes[:100]}..."
                    session_lines.append(line)
                recent_sessions = "\n".join(session_lines)

            # User tools
            tools = user_context.get('user_tools', [])
            if tools:
                user_tools = ", ".join(tools)

        prompt = EXPAND_SUGGESTION_PROMPT.format(
            category=suggestion.get('category', 'Unknown'),
            topic=suggestion.get('topic', 'Unknown'),
            reason=suggestion.get('reason', 'No reason provided'),
            question_type=question_type,
            user_tasks=user_tasks,
            recent_sessions=recent_sessions,
            user_tools=user_tools
        )

        response = self._call_llm(prompt, self.FOCUSAI_SYSTEM_PROMPT)
        result = self._parse_json_response(response)

        if result:
            result['ai_generated'] = True
            result['original_suggestion'] = {
                'category': suggestion.get('category'),
                'topic': suggestion.get('topic')
            }
            result['used_user_context'] = bool(user_context)
            # Ensure icon is set
            if 'icon' not in result:
                result['icon'] = icons.get(question_type, '💡')
            return result

        # Fallback response
        return self._get_expand_fallback(suggestion, question_type, icons)

    def _get_expand_fallback(self, suggestion: Dict, question_type: str, icons: Dict) -> Dict:
        """Generate fallback response when AI is unavailable."""
        category = suggestion.get('category', 'Learning')
        topic = suggestion.get('topic', 'this topic')

        fallbacks = {
            'resources': f"• Oficiální dokumentace pro {topic}\n• YouTube tutoriály\n• Praktické cvičení v reálném projektu",
            'steps': f"• Začni s základy {topic}\n• Procvič si na malém projektu\n• Aplikuj v praxi",
            'time_estimate': f"• Základy: 2-3 sessions (cca 2 hodiny)\n• Praktická znalost: 5-8 sessions\n• Pokročilá úroveň: 15+ sessions",
            'connection': f"• {category} je důležitá pro QA Test Automation\n• Zlepší tvoje portfolio\n• Zvýší šance při pohovorech"
        }

        return {
            'answer': fallbacks.get(question_type, 'Více informací není k dispozici.'),
            'type': question_type,
            'icon': icons.get(question_type, '💡'),
            'confidence': 0.3,
            'ai_generated': False,
            'fallback': True
        }
