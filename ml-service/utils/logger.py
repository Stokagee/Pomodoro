"""
Structured JSON Logger for Pomodoro ML Service
Optimized for Grafana Loki ingestion via Promtail
"""

import json
import sys
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from flask import has_request_context, request


class StructuredLogger:
    """
    Structured JSON logger for Loki integration.

    Outputs JSON logs to stdout which are collected by Promtail.
    Labels (low cardinality): service, level, event_type
    Context (high cardinality): prediction results, AI responses, etc.
    """

    def __init__(self, service_name: str = "pomodoro-ml"):
        self.service = service_name

    def _get_trace_id(self) -> str:
        """Get trace ID from request header or generate new one."""
        if has_request_context():
            return request.headers.get('X-Request-ID', str(uuid.uuid4())[:8])
        return str(uuid.uuid4())[:8]

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
            "trace_id": self._get_trace_id()
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
              context: Dict = None, error: Dict = None):
        """Log ERROR level event."""
        self._write(self._format_log("ERROR", event_type, message, context, error=error))

    def debug(self, event_type: str, message: str,
              context: Dict = None, metrics: Dict = None):
        """Log DEBUG level event."""
        self._write(self._format_log("DEBUG", event_type, message, context, metrics))

    # =========================================================================
    # ML-specific event helpers
    # =========================================================================

    def ml_recommendation(self, preset: str, confidence: float,
                          reason: str, latency_ms: int, category: str = None):
        """Log ML recommendation event."""
        self.info(
            event_type="ML_RECOMMENDATION",
            message=f"Recommended preset: {preset} (confidence: {confidence:.2f})",
            context={
                "recommended_preset": preset,
                "reason": reason,
                "category_context": category
            },
            metrics={
                "confidence": confidence,
                "latency_ms": latency_ms
            }
        )

    def ml_prediction(self, prediction_type: str, result: Dict,
                      confidence: float, latency_ms: int):
        """Log ML prediction event."""
        self.info(
            event_type="ML_PREDICTION",
            message=f"Prediction ({prediction_type}): confidence {confidence:.2f}",
            context={
                "prediction_type": prediction_type,
                "result_preview": str(result)[:300] if result else None
            },
            metrics={
                "confidence": confidence,
                "latency_ms": latency_ms
            }
        )

    def burnout_risk(self, risk_level: str, risk_score: float,
                     top_factors: list, latency_ms: int):
        """Log burnout risk calculation."""
        level = "WARNING" if risk_level in ["high", "critical"] else "INFO"
        self._write(self._format_log(
            level=level,
            event_type="BURNOUT_RISK",
            message=f"Burnout risk: {risk_level} ({risk_score:.1f}%)",
            context={
                "risk_level": risk_level,
                "top_factors": top_factors[:3] if top_factors else []
            },
            metrics={
                "risk_score": risk_score,
                "factors_count": len(top_factors) if top_factors else 0,
                "latency_ms": latency_ms
            }
        ))

    def anomaly_detected(self, anomaly_type: str, severity: str,
                         description: str, recommendation: str = None):
        """Log anomaly detection event."""
        level = "WARNING" if severity in ["high", "critical"] else "INFO"
        self._write(self._format_log(
            level=level,
            event_type="ANOMALY_DETECTED",
            message=f"Anomaly: {anomaly_type} ({severity})",
            context={
                "anomaly_type": anomaly_type,
                "severity": severity,
                "description": description,
                "recommendation": recommendation
            }
        ))

    def quality_prediction(self, predicted_productivity: float,
                           confidence: float, preset: str,
                           category: str, factors: list, latency_ms: int):
        """Log session quality prediction."""
        self.info(
            event_type="QUALITY_PREDICTION",
            message=f"Quality prediction: {predicted_productivity:.1f}% for {preset}",
            context={
                "preset": preset,
                "category": category,
                "positive_factors": [f for f in factors if f.get('type') == 'positive'],
                "negative_factors": [f for f in factors if f.get('type') == 'negative']
            },
            metrics={
                "predicted_productivity": predicted_productivity,
                "confidence": confidence,
                "factors_count": len(factors) if factors else 0,
                "latency_ms": latency_ms
            }
        )

    def optimal_schedule(self, sessions_planned: int, peak_hours: list,
                         avoid_hours: list, latency_ms: int):
        """Log optimal schedule generation."""
        self.info(
            event_type="OPTIMAL_SCHEDULE",
            message=f"Optimal schedule generated: {sessions_planned} sessions",
            context={
                "peak_hours": peak_hours,
                "avoid_hours": avoid_hours
            },
            metrics={
                "sessions_planned": sessions_planned,
                "peak_hours_count": len(peak_hours) if peak_hours else 0,
                "latency_ms": latency_ms
            }
        )

    # =========================================================================
    # AI/Ollama event helpers
    # =========================================================================

    def ai_request_start(self, endpoint: str, context_size: int = None,
                         model: str = None):
        """Log AI request start."""
        self.debug(
            event_type="AI_REQUEST_START",
            message=f"AI request starting: {endpoint}",
            context={
                "endpoint": endpoint,
                "model": model,
                "context_size": context_size
            }
        )

    def ai_request_complete(self, endpoint: str, latency_ms: int,
                            tokens_used: int = None, cache_hit: bool = False,
                            model: str = None):
        """Log AI request completion."""
        self.info(
            event_type="AI_REQUEST_COMPLETE",
            message=f"AI request completed: {endpoint} ({'cache hit' if cache_hit else 'new'})",
            context={
                "endpoint": endpoint,
                "model": model,
                "cache_hit": cache_hit
            },
            metrics={
                "latency_ms": latency_ms,
                "tokens_used": tokens_used
            }
        )

    def ai_request_error(self, endpoint: str, error_type: str,
                         error_message: str, retry_count: int = 0):
        """Log AI request error."""
        self.error(
            event_type="AI_REQUEST_ERROR",
            message=f"AI request failed: {endpoint}",
            context={
                "endpoint": endpoint,
                "retry_count": retry_count
            },
            error={
                "type": error_type,
                "message": error_message
            }
        )

    def ai_prompt(self, endpoint: str, provider: str, model: str,
                  prompt: str, system_prompt: str = None):
        """Log AI prompt being sent."""
        # Truncate prompt if too long for logging
        prompt_preview = prompt[:1500] + "..." if len(prompt) > 1500 else prompt
        system_preview = (system_prompt[:500] + "...") if system_prompt and len(system_prompt) > 500 else system_prompt

        self.info(
            event_type="AI_PROMPT",
            message=f"AI prompt sent: {endpoint} via {provider}/{model}",
            context={
                "endpoint": endpoint,
                "provider": provider,
                "model": model,
                "system_prompt": system_preview,
                "prompt": prompt_preview,
                "prompt_length": len(prompt)
            }
        )

    def ai_response(self, endpoint: str, provider: str, model: str,
                    response: str, input_tokens: int = 0, output_tokens: int = 0,
                    duration_seconds: float = 0):
        """Log AI response received."""
        # Truncate response if too long for logging
        response_preview = response[:2000] + "..." if len(response) > 2000 else response

        self.info(
            event_type="AI_RESPONSE",
            message=f"AI response received: {endpoint} ({input_tokens}+{output_tokens} tokens)",
            context={
                "endpoint": endpoint,
                "provider": provider,
                "model": model,
                "response": response_preview,
                "response_length": len(response)
            },
            metrics={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "duration_seconds": round(duration_seconds, 2)
            }
        )

    # =========================================================================
    # Cache event helpers
    # =========================================================================

    def cache_hit(self, cache_type: str, age_minutes: float = None):
        """Log cache hit event."""
        self.debug(
            event_type="CACHE_HIT",
            message=f"Cache hit: {cache_type}",
            context={
                "cache_type": cache_type
            },
            metrics={
                "age_minutes": age_minutes
            }
        )

    def cache_miss(self, cache_type: str, reason: str = None):
        """Log cache miss event."""
        self.debug(
            event_type="CACHE_MISS",
            message=f"Cache miss: {cache_type}",
            context={
                "cache_type": cache_type,
                "reason": reason
            }
        )

    def cache_invalidated(self, cache_type: str, trigger: str,
                          entries_cleared: int = None):
        """Log cache invalidation event."""
        self.info(
            event_type="CACHE_INVALIDATED",
            message=f"Cache invalidated: {cache_type} (trigger: {trigger})",
            context={
                "cache_type": cache_type,
                "trigger": trigger
            },
            metrics={
                "entries_cleared": entries_cleared
            }
        )

    def db_connected(self, db_type: str = "PostgreSQL"):
        """Log database connection event."""
        self.info(
            event_type="DB_CONNECTED",
            message=f"Database connected: {db_type}",
            context={
                "db_type": db_type
            }
        )

    def db_error(self, operation: str, error_message: str):
        """Log database error event."""
        self.error(
            event_type="DB_ERROR",
            message=f"Database error during {operation}",
            context={
                "operation": operation
            },
            error={
                "message": error_message
            }
        )


# Singleton instance
logger = StructuredLogger("pomodoro-ml")
