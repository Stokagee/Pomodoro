/**
 * Pomodoro Timer - JavaScript Logic v2.0
 * IT Optimized with 52/17 Deep Work mode
 * With productivity rating support
 */

class PomodoroTimer {
    constructor(config) {
        this.config = config;
        this.currentPreset = config.default_preset;
        this.isRunning = false;
        this.isBreak = false;
        this.sessionCount = 1;
        this.totalSeconds = 0;
        this.remainingSeconds = 0;
        this.interval = null;
        this.targetEndTime = null;  // For accurate time tracking in background tabs
        this.socket = null;
        this.pendingRating = null;
        this.selectedRating = null;
        this.lastWorkMinutes = 0;  // Track actual worked minutes for proportional break
        this.todayFocus = null;  // Today's focus theme

        this.initializeSocket();
        this.initializeElements();
        this.bindEvents();
        this.initializeRatingModal();
        this.setPreset(this.currentPreset);
        this.loadTodayFocus();  // Load daily focus
        this.loadTimerState();  // Restore timer state from localStorage
    }

    // === Timer State Persistence (localStorage) ===

    saveTimerState() {
        const state = {
            targetEndTime: this.targetEndTime,
            isRunning: this.isRunning,
            isBreak: this.isBreak,
            currentPreset: this.currentPreset,
            sessionCount: this.sessionCount,
            totalSeconds: this.totalSeconds,
            remainingSeconds: this.remainingSeconds,
            category: this.categorySelect?.value || '',
            task: this.taskInput?.value || '',
            savedAt: Date.now()
        };
        localStorage.setItem('pomodoroTimerState', JSON.stringify(state));
    }

    loadTimerState() {
        try {
            const saved = localStorage.getItem('pomodoroTimerState');
            if (!saved) return false;

            const state = JSON.parse(saved);

            // Check date AND age - reset if different day or older than 24 hours
            const savedDate = new Date(state.savedAt).toDateString();
            const today = new Date().toDateString();
            if (savedDate !== today || Date.now() - state.savedAt > 24 * 60 * 60 * 1000) {
                this.clearTimerState();
                return false;
            }

            // Restore state (sessionCount is synced from DB, not localStorage)
            this.currentPreset = state.currentPreset;
            this.isBreak = state.isBreak;
            this.totalSeconds = state.totalSeconds;

            if (state.isRunning && state.targetEndTime) {
                // Timer was running - recalculate remaining time
                const now = Date.now();
                this.remainingSeconds = Math.max(0, Math.ceil((state.targetEndTime - now) / 1000));

                if (this.remainingSeconds <= 0) {
                    // Timer completed during navigation
                    this.clearTimerState();
                    this.completePhase();
                    return true;
                }

                this.targetEndTime = state.targetEndTime;
                // Auto-start timer
                setTimeout(() => this.start(), 100);
            } else {
                this.remainingSeconds = state.remainingSeconds;
            }

            // Restore UI
            if (state.category && this.categorySelect) {
                this.categorySelect.value = state.category;
            }
            if (state.task && this.taskInput) {
                this.taskInput.value = state.task;
            }

            this.updatePresetButtons();
            this.updatePhaseDisplay();
            this.updateDisplay();
            this.updateSessionDisplay();

            return true;
        } catch (e) {
            console.log('Could not load timer state:', e);
            return false;
        }
    }

    clearTimerState() {
        localStorage.removeItem('pomodoroTimerState');
    }

    async syncSessionCount() {
        try {
            const res = await fetch('/api/stats/today');
            const stats = await res.json();
            const completed = stats.completed_sessions || 0;
            const cycle = this.config.sessions_before_long_break;

            // Calculate correct sessionCount for current/next session
            this.sessionCount = (completed % cycle) + 1;

            this.updateSessionDisplay();
            this.saveTimerState();

            console.log(`Session synced: ${completed} completed → Session ${this.sessionCount}/${cycle}`);
        } catch (e) {
            console.error('Failed to sync session count:', e);
        }
    }

    updatePresetButtons() {
        this.presetBtns.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.preset === this.currentPreset);
        });
        const preset = this.config.presets[this.currentPreset];
        if (preset) {
            document.documentElement.style.setProperty('--current-preset-color', preset.color);
            this.progressRing.style.stroke = preset.color;
        }
    }

    updatePhaseDisplay() {
        if (this.isBreak) {
            this.timerPhase.textContent = 'BREAK';
            this.timerPhase.classList.remove('work');
            this.timerPhase.classList.add('break');
            this.progressRing.classList.add('break');
        } else {
            this.timerPhase.textContent = 'WORK';
            this.timerPhase.classList.remove('break');
            this.timerPhase.classList.add('work');
            this.progressRing.classList.remove('break');
        }
    }

    initializeSocket() {
        try {
            this.socket = io();
            this.socket.on('connect', () => {
                console.log('Connected to server');
            });
            this.socket.on('session_logged', (data) => {
                console.log('Session logged:', data);
                this.updateStats();
            });
        } catch (e) {
            console.log('Socket.IO not available, running in standalone mode');
        }
    }

    initializeElements() {
        // Timer elements
        this.timerPhase = document.getElementById('timer-phase');
        this.timerTime = document.getElementById('timer-time');
        this.timerSession = document.getElementById('timer-session');
        this.progressRing = document.getElementById('progress-ring');

        // Control buttons
        this.btnStart = document.getElementById('btn-start');
        this.btnPause = document.getElementById('btn-pause');
        this.btnReset = document.getElementById('btn-reset');
        this.btnSkip = document.getElementById('btn-skip');

        // Preset buttons
        this.presetBtns = document.querySelectorAll('.preset-btn');

        // Task inputs
        this.categorySelect = document.getElementById('category-select');
        this.taskInput = document.getElementById('task-input');

        // Stats elements
        this.statSessions = document.getElementById('stat-sessions');
        this.statHours = document.getElementById('stat-hours');
        this.statRating = document.getElementById('stat-rating');
        this.progressFill = document.getElementById('progress-fill');
        this.navSessions = document.getElementById('nav-sessions');

        // Audio elements
        this.audioWorkEnd = document.getElementById('audio-work-end');
        this.audioBreakEnd = document.getElementById('audio-break-end');

        // Rating modal elements
        this.ratingModal = document.getElementById('rating-modal');
        this.ratingStars = document.getElementById('rating-stars');
        this.ratingSkip = document.getElementById('rating-skip');
        this.ratingSave = document.getElementById('rating-save');
        this.sessionNotes = document.getElementById('session-notes');
    }

    initializeRatingModal() {
        if (!this.ratingStars) return;

        // Procentuální rating element
        this.ratingPercentage = document.getElementById('rating-percentage');

        // Check if SVG rating system
        const svg = this.ratingStars.querySelector('svg');
        if (svg) {
            // Nový SVG systém - rating 0-100%
            this.isDragging = false;

            // Mouse events pro SVG kontejner
            this.ratingStars.addEventListener('mousedown', (e) => {
                this.isDragging = true;
                this.setRatingFromPosition(e);
            });

            this.ratingStars.addEventListener('mousemove', (e) => {
                if (this.isDragging) {
                    this.setRatingFromPosition(e);
                }
            });

            this.ratingStars.addEventListener('mouseup', () => {
                this.isDragging = false;
            });

            this.ratingStars.addEventListener('mouseleave', () => {
                this.isDragging = false;
            });

            // Klik na konkrétní pozici
            this.ratingStars.addEventListener('click', (e) => {
                this.setRatingFromPosition(e);
            });

            // Touch events pro mobily
            this.ratingStars.addEventListener('touchstart', (e) => {
                e.preventDefault();
                this.isDragging = true;
                this.setRatingFromPosition(e.touches[0]);
            });

            this.ratingStars.addEventListener('touchmove', (e) => {
                e.preventDefault();
                if (this.isDragging) {
                    this.setRatingFromPosition(e.touches[0]);
                }
            });

            this.ratingStars.addEventListener('touchend', () => {
                this.isDragging = false;
            });
        } else {
            // Fallback pro staré button hvězdy (zpětná kompatibilita)
            const stars = this.ratingStars.querySelectorAll('.star-btn');
            stars.forEach((star, index) => {
                star.addEventListener('click', () => {
                    // Konverze 1-5 na 0-100%
                    this.selectedRating = parseInt(star.dataset.rating) * 20;
                    this.updateStarDisplay(this.selectedRating);
                    this.ratingSave.disabled = false;
                });
            });
        }

        if (this.ratingSkip) {
            this.ratingSkip.addEventListener('click', () => {
                this.submitRating(null);
            });
        }

        if (this.ratingSave) {
            this.ratingSave.addEventListener('click', () => {
                this.submitRating(this.selectedRating);
            });
        }
    }

    setRatingFromPosition(event) {
        const rect = this.ratingStars.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const width = rect.width;

        // Vypočti procento (0-100) zaokrouhlené na 5%
        let percentage = (x / width) * 100;
        percentage = Math.round(percentage / 5) * 5;
        percentage = Math.max(0, Math.min(100, percentage));

        this.setRating(percentage);
    }

    setRating(percentage) {
        this.selectedRating = percentage;
        this.updateStarsFill(percentage);
        this.updatePercentageDisplay(percentage);
        if (this.ratingSave) {
            this.ratingSave.disabled = false;
        }
    }

    updateStarsFill(percentage) {
        // 5 hvězd = 100%, každá hvězda = 20%
        const percentPerStar = 20;

        for (let i = 0; i < 5; i++) {
            const starStart = i * percentPerStar;
            const starEnd = (i + 1) * percentPerStar;

            let fillPercent;
            if (percentage >= starEnd) {
                fillPercent = 100;  // Plná hvězda
            } else if (percentage <= starStart) {
                fillPercent = 0;    // Prázdná hvězda
            } else {
                // Částečně vyplněná
                fillPercent = ((percentage - starStart) / percentPerStar) * 100;
            }

            this.setStarFill(i, fillPercent);
        }
    }

    setStarFill(starIndex, fillPercent) {
        const gradient = document.getElementById(`star-gradient-${starIndex}`);
        if (gradient) {
            const fillStop = gradient.querySelector('.fill-stop');
            const emptyStop = gradient.querySelector('.empty-stop');
            if (fillStop && emptyStop) {
                fillStop.setAttribute('offset', `${fillPercent}%`);
                emptyStop.setAttribute('offset', `${fillPercent}%`);
            }
        }
    }

    updatePercentageDisplay(percentage) {
        if (this.ratingPercentage) {
            this.ratingPercentage.textContent = `${percentage}%`;
        }
    }

    updateStarDisplay(rating, isHover = false) {
        // Zpětná kompatibilita pro staré button hvězdy
        const stars = this.ratingStars.querySelectorAll('.star-btn');
        if (stars.length === 0) {
            // Nový SVG systém - rating je v procentech (0-100)
            this.updateStarsFill(rating);
            this.updatePercentageDisplay(rating);
            return;
        }

        // Staré button hvězdy (rating 1-5)
        const starRating = Math.ceil(rating / 20);  // Konverze % na 1-5
        stars.forEach((star, index) => {
            if (index < starRating) {
                star.innerHTML = '&#9733;'; // filled star
                star.classList.add('active');
            } else {
                star.innerHTML = '&#9734;'; // empty star
                star.classList.remove('active');
            }
        });
    }

    showRatingModal() {
        this.selectedRating = null;
        this.updateStarDisplay(0);
        if (this.ratingSave) this.ratingSave.disabled = true;
        if (this.sessionNotes) this.sessionNotes.value = '';
        if (this.ratingModal) this.ratingModal.style.display = 'flex';
    }

    hideRatingModal() {
        if (this.ratingModal) this.ratingModal.style.display = 'none';
    }

    submitRating(rating) {
        if (this.pendingRating) {
            this.pendingRating.productivity_rating = rating;
            this.pendingRating.notes = this.sessionNotes ? this.sessionNotes.value.trim() : '';
            this.sendSessionLog(this.pendingRating);
            this.pendingRating = null;
        }
        this.hideRatingModal();

        // Auto-clear task input po dokončení session
        if (this.taskInput) {
            this.taskInput.value = '';
        }

        this.startBreak();

        // Auto-start break if enabled
        if (this.config.auto_start_break) {
            setTimeout(() => this.start(), 500);
        }
    }

    bindEvents() {
        // Control buttons
        this.btnStart.addEventListener('click', () => this.start());
        this.btnPause.addEventListener('click', () => this.pause());
        this.btnReset.addEventListener('click', () => this.reset());
        this.btnSkip.addEventListener('click', () => this.skip());

        // Preset buttons
        this.presetBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const preset = btn.dataset.preset;
                this.setPreset(preset);
            });
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Don't handle shortcuts when modal is open
            if (this.ratingModal && this.ratingModal.style.display === 'flex') {
                return;
            }

            if (e.code === 'Space' && !e.target.matches('input, textarea')) {
                e.preventDefault();
                if (this.isRunning) {
                    this.pause();
                } else {
                    this.start();
                }
            }
            if (e.code === 'KeyR' && !e.target.matches('input, textarea')) {
                e.preventDefault();
                this.reset();
            }
        });

        // Page visibility - sync time when returning from background tab
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && this.isRunning && this.targetEndTime) {
                // Sync time with reality when tab becomes visible
                const now = Date.now();
                this.remainingSeconds = Math.max(0, Math.ceil((this.targetEndTime - now) / 1000));

                if (this.remainingSeconds <= 0) {
                    // Timer completed while in background - finish now
                    this.completePhase();
                } else {
                    this.updateDisplay();
                    this.updateTitle();
                }
            }
        });
    }

    setPreset(presetKey) {
        const preset = this.config.presets[presetKey];
        if (!preset) return;

        this.currentPreset = presetKey;
        this.isBreak = false;

        // Test mode: minutes become seconds for quick testing
        const multiplier = this.config.test_mode ? 1 : 60;
        this.totalSeconds = preset.work_minutes * multiplier;
        this.remainingSeconds = this.totalSeconds;

        // Update UI
        this.presetBtns.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.preset === presetKey);
        });

        // Update CSS variable for progress ring color
        document.documentElement.style.setProperty('--current-preset-color', preset.color);
        this.progressRing.style.stroke = preset.color;

        this.updateDisplay();
    }

    start() {
        if (this.isRunning) return;

        this.isRunning = true;
        this.btnStart.style.display = 'none';
        this.btnPause.style.display = 'flex';

        // Calculate target end time for accurate background tab tracking
        this.targetEndTime = Date.now() + (this.remainingSeconds * 1000);

        this.interval = setInterval(() => {
            this.tick();
        }, 1000);

        // Update title
        this.updateTitle();

        // Save state to localStorage for persistence across page navigation
        this.saveTimerState();
    }

    pause() {
        if (!this.isRunning) return;

        this.isRunning = false;
        this.btnStart.style.display = 'flex';
        this.btnPause.style.display = 'none';

        clearInterval(this.interval);
        this.interval = null;

        // Sync remaining seconds with actual time before pausing
        if (this.targetEndTime) {
            this.remainingSeconds = Math.max(0, Math.ceil((this.targetEndTime - Date.now()) / 1000));
            this.targetEndTime = null;
        }

        if (this.config.show_time_in_tab) {
            document.title = 'Paused - Pomodoro Timer';
        }

        // Save state to localStorage for persistence across page navigation
        this.saveTimerState();
    }

    reset() {
        this.pause();
        this.clearTimerState();  // Clear localStorage state on reset
        this.setPreset(this.currentPreset);
    }

    skip() {
        this.completePhase();
    }

    tick() {
        if (!this.isRunning || !this.targetEndTime) return;

        // Calculate remaining time based on actual time, not increments
        // This fixes background tab throttling issue
        const now = Date.now();
        this.remainingSeconds = Math.max(0, Math.ceil((this.targetEndTime - now) / 1000));

        if (this.remainingSeconds <= 0) {
            this.completePhase();
        } else {
            this.updateDisplay();
            this.updateTitle();

            // Save state every 10 seconds for persistence
            if (this.remainingSeconds % 10 === 0) {
                this.saveTimerState();
            }
        }
    }

    completePhase() {
        this.pause();
        this.clearTimerState();  // Clear localStorage state when phase completes

        if (!this.isBreak) {
            // Calculate actual worked time
            const preset = this.config.presets[this.currentPreset];
            const workedSeconds = this.totalSeconds - this.remainingSeconds;
            const actualMinutes = Math.round(workedSeconds / 60);

            // Store for proportional break calculation
            this.lastWorkMinutes = actualMinutes;

            // Determine if session was completed fully or skipped early
            const wasCompleted = this.remainingSeconds <= 0;

            // Work session completed - show rating modal
            this.playSound('work');
            const message = wasCompleted
                ? 'Time for a break.'
                : `Ukončeno po ${actualMinutes} min. Přestávka bude proporcionální.`;
            this.showNotification('Work session complete!', message);

            // Prepare session data for rating - use ACTUAL worked time
            this.pendingRating = {
                preset: this.currentPreset,
                category: this.categorySelect.value,
                task: this.taskInput.value,
                duration_minutes: actualMinutes,  // Actual time, not preset!
                completed: wasCompleted
            };

            // Show rating modal
            this.showRatingModal();
        } else {
            // Break completed
            this.playSound('break');
            this.showNotification('Break over!', 'Ready for the next session?');

            this.sessionCount++;
            this.isBreak = false;
            const preset = this.config.presets[this.currentPreset];
            this.totalSeconds = preset.work_minutes * 60;

            this.timerPhase.textContent = 'WORK';
            this.timerPhase.classList.remove('break');
            this.timerPhase.classList.add('work');
            this.progressRing.classList.remove('break');

            this.remainingSeconds = this.totalSeconds;
            this.updateDisplay();
            this.updateSessionDisplay();
        }
    }

    startBreak() {
        // Determine break length - proportional to actual work time
        const preset = this.config.presets[this.currentPreset];
        const workRatio = this.lastWorkMinutes / preset.work_minutes;

        let breakMinutes;
        let breakLabel;

        if (this.sessionCount % this.config.sessions_before_long_break === 0) {
            // Long break - also proportional
            breakMinutes = Math.round(this.config.long_break_minutes * workRatio);
            breakLabel = 'LONG BREAK';
        } else {
            // Short break - proportional
            breakMinutes = Math.round(preset.break_minutes * workRatio);
            breakLabel = 'BREAK';
        }

        // Minimum 1 minute break, maximum is the full preset break
        breakMinutes = Math.max(1, Math.min(breakMinutes,
            this.sessionCount % this.config.sessions_before_long_break === 0
                ? this.config.long_break_minutes
                : preset.break_minutes));

        this.totalSeconds = breakMinutes * 60;

        // Show proportional info if break was shortened
        const fullBreak = this.sessionCount % this.config.sessions_before_long_break === 0
            ? this.config.long_break_minutes
            : preset.break_minutes;

        if (breakMinutes < fullBreak) {
            this.timerPhase.textContent = `${breakLabel} (${breakMinutes}m)`;
        } else {
            this.timerPhase.textContent = breakLabel;
        }

        this.isBreak = true;
        this.timerPhase.classList.remove('work');
        this.timerPhase.classList.add('break');
        this.progressRing.classList.add('break');

        this.remainingSeconds = this.totalSeconds;
        this.updateDisplay();
        this.updateSessionDisplay();
    }

    sendSessionLog(data) {
        // Send via Socket.IO
        if (this.socket && this.socket.connected) {
            this.socket.emit('timer_complete', data);
        } else {
            // Fallback to HTTP
            fetch('/api/log', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        }

        // Update local stats
        this.updateStats();
    }

    updateDisplay() {
        const minutes = Math.floor(this.remainingSeconds / 60);
        const seconds = this.remainingSeconds % 60;
        this.timerTime.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;

        // Update progress ring
        const circumference = 2 * Math.PI * 90; // radius = 90
        const progress = this.remainingSeconds / this.totalSeconds;
        const offset = circumference * (1 - progress);
        this.progressRing.style.strokeDashoffset = offset;
    }

    updateSessionDisplay() {
        this.timerSession.textContent = `Session ${this.sessionCount}/${this.config.sessions_before_long_break}`;
    }

    updateTitle() {
        if (!this.config.show_time_in_tab) return;

        const minutes = Math.floor(this.remainingSeconds / 60);
        const seconds = this.remainingSeconds % 60;
        const time = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        const phase = this.isBreak ? 'Break' : 'Work';
        document.title = `${time} - ${phase} - Pomodoro`;
    }

    updateStats() {
        fetch('/api/stats/today')
            .then(res => res.json())
            .then(stats => {
                if (this.statSessions) {
                    this.statSessions.textContent = stats.sessions || stats.completed_sessions || 0;
                }
                if (this.statHours) {
                    this.statHours.textContent = stats.total_hours;
                }
                if (this.statRating) {
                    this.statRating.textContent = stats.avg_rating || '0';
                }
                if (this.progressFill) {
                    const sessions = stats.sessions || stats.completed_sessions || 0;
                    const percent = (sessions / this.config.daily_goal_sessions) * 100;
                    this.progressFill.style.width = `${Math.min(percent, 100)}%`;
                }
                if (this.navSessions) {
                    const sessions = stats.sessions || stats.completed_sessions || 0;
                    this.navSessions.textContent = `${sessions}/${this.config.daily_goal_sessions}`;
                }
            })
            .catch(err => console.log('Could not update stats:', err));

        // Also refresh today's focus stats
        this.loadTodayFocus();
    }

    // === Daily Focus Integration ===

    async loadTodayFocus() {
        try {
            const response = await fetch('/api/focus/today');
            const data = await response.json();

            if (data.success && data.focus) {
                this.todayFocus = data.focus;
                this.updateTodayFocusWidget();

                // Pre-select category if not already selected
                if (this.categorySelect && !this.categorySelect.value && data.focus.theme) {
                    this.categorySelect.value = data.focus.theme;
                }
            }
        } catch (error) {
            console.log('Could not load today focus:', error);
        }
    }

    updateTodayFocusWidget() {
        // Update Today's Focus widget if it exists
        const widget = document.getElementById('today-focus-widget');
        if (!widget || !this.todayFocus) return;

        const iconEl = widget.querySelector('.focus-widget-icon');
        const themeEl = widget.querySelector('.focus-widget-theme');
        const progressEl = widget.querySelector('.focus-widget-progress');
        const fillEl = widget.querySelector('.focus-widget-fill');

        if (iconEl && this.todayFocus.theme) {
            const icons = {
                'Coding': '💻', 'Learning': '📚', 'Writing': '✍️',
                'Planning': '📋', 'Communication': '💬', 'Research': '🔍',
                'Review': '👀', 'Meeting': '🤝', 'Admin': '📁', 'Other': '📌'
            };
            iconEl.textContent = icons[this.todayFocus.theme] || '🎯';
        }

        if (themeEl) {
            themeEl.textContent = this.todayFocus.theme || 'Nenastaveno';
        }

        if (progressEl) {
            const actual = this.todayFocus.actual_sessions || 0;
            const planned = this.todayFocus.planned_sessions || 6;
            progressEl.textContent = `${actual}/${planned}`;
        }

        if (fillEl) {
            const actual = this.todayFocus.actual_sessions || 0;
            const planned = this.todayFocus.planned_sessions || 6;
            const percent = Math.min((actual / planned) * 100, 100);
            fillEl.style.width = `${percent}%`;
        }
    }

    playSound(type) {
        if (!this.config.sound_enabled) return;

        try {
            const audio = type === 'work' ? this.audioWorkEnd : this.audioBreakEnd;
            if (audio) {
                audio.currentTime = 0;
                audio.play().catch(() => {});
            }
        } catch (e) {
            // Audio not available
        }
    }

    showNotification(title, body) {
        if (!this.config.notification_enabled) return;

        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(title, {
                body: body,
                icon: '/static/images/icon.png',
                tag: 'pomodoro'
            });
        } else if ('Notification' in window && Notification.permission !== 'denied') {
            Notification.requestPermission().then(permission => {
                if (permission === 'granted') {
                    new Notification(title, { body: body, tag: 'pomodoro' });
                }
            });
        }
    }
}

// Initialize timer when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Check if we have config (we're on the timer page)
    if (typeof CONFIG !== 'undefined') {
        window.pomodoroTimer = new PomodoroTimer(CONFIG);

        // Sync sessionCount with database (fixes long break timing after refresh)
        window.pomodoroTimer.syncSessionCount();

        // Request notification permission
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }
});
