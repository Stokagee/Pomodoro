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

    def __init__(self):
        """Initialize the AI Challenge Generator"""
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://ollama:11434')
        self.model = os.getenv('OLLAMA_MODEL', 'mistral:7b')
        self.enabled = os.getenv('OLLAMA_ENABLED', 'true').lower() == 'true'
        self.timeout = int(os.getenv('OLLAMA_TIMEOUT', '30'))

        # Cache for generated content
        self._cache: Dict[str, Any] = {}
        self._cache_expiry: Dict[str, datetime] = {}

        logger.info(f"AIChallengeGenerator initialized: enabled={self.enabled}, model={self.model}")

    def health_check(self) -> Dict[str, Any]:
        """Check if Ollama is available and responsive"""
        if not self.enabled:
            return {
                "status": "disabled",
                "message": "Ollama is disabled via OLLAMA_ENABLED=false",
                "ollama_url": self.ollama_url
            }

        try:
            import requests
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m.get('name', '') for m in models]
                has_model = any(self.model in name for name in model_names)

                return {
                    "status": "healthy" if has_model else "model_missing",
                    "message": f"Ollama is running. Model {self.model} {'found' if has_model else 'not found'}.",
                    "ollama_url": self.ollama_url,
                    "available_models": model_names,
                    "configured_model": self.model
                }
            else:
                return {
                    "status": "error",
                    "message": f"Ollama returned status {response.status_code}",
                    "ollama_url": self.ollama_url
                }
        except Exception as e:
            return {
                "status": "unavailable",
                "message": f"Cannot connect to Ollama: {str(e)}",
                "ollama_url": self.ollama_url
            }

    def _get_cache_key(self, prefix: str, context: Dict) -> str:
        """Generate cache key from context"""
        context_str = json.dumps(context, sort_keys=True)
        return f"{prefix}_{hashlib.md5(context_str.encode()).hexdigest()[:8]}"

    def _is_cache_valid(self, key: str, max_age_hours: int = 1) -> bool:
        """Check if cached value is still valid"""
        if key not in self._cache or key not in self._cache_expiry:
            return False
        return datetime.now() < self._cache_expiry[key]

    def _call_ollama(self, prompt: str, system_prompt: str = None) -> Optional[str]:
        """Make a call to Ollama API"""
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
                    "model": self.model,
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

        response = self._call_ollama(prompt, system_prompt)
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

        response = self._call_ollama(prompt, system_prompt)

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

        response = self._call_ollama(prompt, system_prompt)
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
