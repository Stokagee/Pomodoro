"""
Structured JSON Logger for Pomodoro Web Service
Optimized for Grafana Loki ingestion via Promtail
"""

import json
import sys
import uuid
import traceback
from datetime import datetime
from typing import Optional, Dict, Any
from flask import has_request_context, request


class StructuredLogger:
    """
    Structured JSON logger for Loki integration.

    Outputs JSON logs to stdout which are collected by Promtail.
    Labels (low cardinality): service, level, event_type
    Context (high cardinality): session_id, user data, etc.
    """

    def __init__(self, service_name: str = "pomodoro-web"):
        self.service = service_name
        self._trace_id = None  # For externally set trace IDs

    def get_trace_id(self) -> str:
        """Get trace ID from externally set value, request header, or generate new one."""
        # Priority: externally set > request header > generate new
        if self._trace_id:
            return self._trace_id
        if has_request_context():
            return request.headers.get('X-Request-ID', str(uuid.uuid4())[:8])
        return str(uuid.uuid4())[:8]

    def set_trace_id(self, trace_id: str):
        """Set trace ID externally (for distributed tracing)."""
        self._trace_id = trace_id

    def _get_request_context(self) -> Dict[str, Any]:
        """Extract request context if available."""
        if has_request_context():
            return {
                "endpoint": request.endpoint,
                "method": request.method,
                "path": request.path,
                "remote_addr": request.remote_addr
            }
        return {}

    def _format_log(
        self,
        level: str,
        event_type: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format log entry as JSON string."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "service": self.service,
            "event_type": event_type,
            "message": message,
            "trace_id": self.get_trace_id()
        }

        # Add request context if available
        request_ctx = self._get_request_context()
        if request_ctx:
            log_entry["request"] = request_ctx

        # Add optional fields
        if context:
            log_entry["context"] = context
        if metrics:
            log_entry["metrics"] = metrics
        if error:
            log_entry["error"] = error

        return json.dumps(log_entry, ensure_ascii=False, default=str)

    def _write(self, log_json: str):
        """Write log to stdout (collected by Promtail)."""
        print(log_json, file=sys.stdout, flush=True)

    # =========================================================================
    # Core logging methods
    # =========================================================================

    def info(self, event_type: str, message: str,
             context: Dict = None, metrics: Dict = None):
        """Log INFO level event."""
        self._write(self._format_log("INFO", event_type, message, context, metrics))

    def warning(self, event_type: str, message: str,
                context: Dict = None, metrics: Dict = None):
        """Log WARNING level event."""
        self._write(self._format_log("WARNING", event_type, message, context, metrics))

    def error(self, event_type: str, message: str,
              context: Dict = None, error: Dict = None, exception: Exception = None):
        """Log ERROR level event with optional exception details."""
        error_dict = error or {}
        if exception:
            error_dict.update({
                "type": type(exception).__name__,
                "message": str(exception),
                "traceback": traceback.format_exc()
            })
        self._write(self._format_log("ERROR", event_type, message, context, error=error_dict if error_dict else None))

    def critical(self, event_type: str, message: str,
                 context: Dict = None, error: Dict = None, exception: Exception = None):
        """Log CRITICAL level event for severe failures."""
        error_dict = error or {}
        if exception:
            error_dict.update({
                "type": type(exception).__name__,
                "message": str(exception),
                "traceback": traceback.format_exc()
            })
        self._write(self._format_log("CRITICAL", event_type, message, context, error=error_dict if error_dict else None))

    def debug(self, event_type: str, message: str,
              context: Dict = None, metrics: Dict = None):
        """Log DEBUG level event."""
        self._write(self._format_log("DEBUG", event_type, message, context, metrics))

    # =========================================================================
    # Business event helpers
    # =========================================================================

    def session_started(self, preset: str, category: str,
                        planned_duration: int, task: str = None):
        """Log session start event."""
        self.info(
            event_type="SESSION_STARTED",
            message=f"Session started: {preset} - {category}",
            context={
                "preset": preset,
                "category": category,
                "planned_duration_minutes": planned_duration,
                "task": task,
                "hour": datetime.now().hour,
                "day_of_week": datetime.now().weekday()
            }
        )

    def session_completed(self, session_id: str, preset: str, category: str,
                          duration: int, rating: int = None, completed: bool = True,
                          xp_earned: int = 0, achievements_count: int = 0):
        """Log session completion event."""
        self.info(
            event_type="SESSION_COMPLETED",
            message=f"Session {'completed' if completed else 'cancelled'}: {preset}",
            context={
                "session_id": session_id,
                "preset": preset,
                "category": category,
                "duration_minutes": duration,
                "productivity_rating": rating,
                "completed": completed
            },
            metrics={
                "xp_earned": xp_earned,
                "achievements_unlocked": achievements_count
            }
        )

    def achievement_unlocked(self, achievement_id: str, name: str,
                             xp_reward: int, category: str = None):
        """Log achievement unlock event."""
        self.info(
            event_type="ACHIEVEMENT_UNLOCKED",
            message=f"Achievement unlocked: {name}",
            context={
                "achievement_id": achievement_id,
                "name": name,
                "category": category
            },
            metrics={
                "xp_reward": xp_reward
            }
        )

    def level_up(self, old_level: int, new_level: int,
                 new_title: str, total_xp: int):
        """Log level up event."""
        self.info(
            event_type="LEVEL_UP",
            message=f"Level up: {old_level} -> {new_level} ({new_title})",
            context={
                "old_level": old_level,
                "new_level": new_level,
                "new_title": new_title
            },
            metrics={
                "total_xp": total_xp
            }
        )

    def daily_focus_set(self, date: str, themes: list,
                        total_planned: int, notes: str = None):
        """Log daily focus setting event."""
        self.info(
            event_type="DAILY_FOCUS_SET",
            message=f"Daily focus set for {date}: {len(themes)} themes",
            context={
                "date": date,
                "themes": [t.get('theme') for t in themes] if themes else [],
                "notes_length": len(notes) if notes else 0
            },
            metrics={
                "themes_count": len(themes) if themes else 0,
                "total_planned_sessions": total_planned
            }
        )

    def challenge_completed(self, challenge_type: str, xp_reward: int,
                            challenge_id: str = None):
        """Log challenge completion event."""
        self.info(
            event_type="CHALLENGE_COMPLETED",
            message=f"{challenge_type.capitalize()} challenge completed",
            context={
                "challenge_type": challenge_type,
                "challenge_id": challenge_id
            },
            metrics={
                "xp_reward": xp_reward
            }
        )

    def streak_update(self, current_streak: int, freeze_used: bool = False,
                      vacation_mode: bool = False):
        """Log streak update event."""
        self.info(
            event_type="STREAK_UPDATE",
            message=f"Streak: {current_streak} days",
            context={
                "freeze_used": freeze_used,
                "vacation_mode": vacation_mode
            },
            metrics={
                "current_streak": current_streak
            }
        )

    def ml_request(self, endpoint: str, success: bool,
                   latency_ms: int, result: Dict = None):
        """Log ML service request."""
        level = "INFO" if success else "WARNING"
        self._write(self._format_log(
            level=level,
            event_type="ML_REQUEST",
            message=f"ML request to {endpoint}: {'success' if success else 'failed'}",
            context={
                "endpoint": endpoint,
                "success": success,
                "result_preview": str(result)[:200] if result else None
            },
            metrics={
                "latency_ms": latency_ms
            }
        ))

    def api_error(self, endpoint: str, error_type: str,
                  error_message: str, status_code: int = 500):
        """Log API error event."""
        self.error(
            event_type="API_ERROR",
            message=f"API error on {endpoint}: {error_type}",
            context={
                "endpoint": endpoint,
                "status_code": status_code
            },
            error={
                "type": error_type,
                "message": error_message
            }
        )

    def websocket_event(self, event: str, client_count: int = None):
        """Log WebSocket event."""
        self.debug(
            event_type="WEBSOCKET",
            message=f"WebSocket: {event}",
            context={
                "event": event
            },
            metrics={
                "active_clients": client_count
            } if client_count is not None else None
        )


# Singleton instance
logger = StructuredLogger("pomodoro-web")
