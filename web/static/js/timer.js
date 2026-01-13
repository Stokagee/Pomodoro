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
        this.burnoutRisk = typeof BURNOUT_RISK !== 'undefined' ? BURNOUT_RISK : null;
        this.burnoutCheckedToday = false;  // Track if we showed warning today

        this.initializeSocket();
        this.initializeElements();
        this.bindEvents();
        this.initializeRatingModal();
        this.initializeBurnoutModal();  // Initialize burnout warning modal
        this.initializeQualityPrediction();  // Initialize quality prediction widget
        this.setPreset(this.currentPreset);
        this.loadTodayFocus();  // Load daily focus
        this.loadTimerState();  // Restore timer state from localStorage
        this.checkBurnoutOnLoad();  // Check if we need to warn on page load
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
            this.socket.on('achievement_unlocked', (achievement) => {
                console.log('Achievement unlocked:', achievement);
                this.showAchievementToast(achievement);
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

    async start() {
        if (this.isRunning) return;

        // Check burnout risk before starting (only for work sessions)
        if (!this.isBreak) {
            const canStart = await this.checkBurnoutBeforeStart();
            if (!canStart) {
                return; // Burnout warning modal is shown, wait for user decision
            }
        }

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

    // === Achievement Toast ===

    showAchievementToast(achievement) {
        // Try to use the global function from achievements.js if available
        if (typeof window.showAchievementUnlockToast === 'function') {
            window.showAchievementUnlockToast(achievement);
            return;
        }

        // Fallback: Create toast container if it doesn't exist
        let container = document.getElementById('achievement-toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'achievement-toast-container';
            container.style.cssText = 'position:fixed;top:80px;right:20px;z-index:1000;display:flex;flex-direction:column;gap:0.75rem;';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.style.cssText = `
            display:flex;align-items:center;gap:1rem;padding:1rem 1.5rem;
            background:#1a1a1a;border:2px solid #22c55e;border-radius:12px;
            box-shadow:0 4px 20px rgba(0,0,0,0.5);min-width:300px;
            animation:toast-slide-in 0.5s ease;
        `;

        // Add legendary glow for legendary achievements
        if (achievement.rarity === 'legendary') {
            toast.style.borderColor = '#f59e0b';
            toast.style.boxShadow = '0 0 30px rgba(245, 158, 11, 0.5)';
        }

        toast.innerHTML = `
            <span style="font-size:2rem;">${achievement.icon || '🏆'}</span>
            <div style="flex:1;">
                <div style="font-weight:600;font-size:0.875rem;">Achievement odemcen!</div>
                <div style="font-size:0.75rem;color:#a0a0a0;">${achievement.name || 'Achievement'}</div>
            </div>
            <span style="font-family:'JetBrains Mono',monospace;color:#f59e0b;font-size:0.875rem;">+${achievement.points || 0} pts</span>
        `;

        container.appendChild(toast);

        // Play notification sound
        try {
            const audio = new Audio('/static/sounds/notification.mp3');
            audio.volume = 0.3;
            audio.play().catch(() => {});
        } catch (e) {}

        // Remove toast after 5 seconds
        setTimeout(() => {
            toast.style.animation = 'toast-fade-out 0.5s ease forwards';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 500);
        }, 4500);
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
        // Sound is ALWAYS enabled - hardcoded, cannot be disabled
        try {
            let audio;
            if (type === 'work') {
                audio = this.audioWorkEnd;
            } else if (type === 'break') {
                audio = this.audioBreakEnd;
            } else if (type === 'burnout') {
                audio = this.audioBurnoutWarning;
            }

            if (audio) {
                audio.currentTime = 0;
                audio.play().catch(() => {});
            }
        } catch (e) {
            // Audio not available
        }
    }

    // === Burnout Risk Warning System ===

    initializeBurnoutModal() {
        // Burnout modal elements
        this.burnoutModal = document.getElementById('burnout-warning-modal');
        this.burnoutIgnoreBtn = document.getElementById('burnout-ignore');
        this.burnoutTakeBreakBtn = document.getElementById('burnout-take-break');
        this.audioBurnoutWarning = document.getElementById('audio-burnout-warning');

        if (this.burnoutIgnoreBtn) {
            this.burnoutIgnoreBtn.addEventListener('click', () => {
                this.hideBurnoutModal();
                this.burnoutCheckedToday = true;
                this.saveBurnoutCheckState();
                // Continue with starting the timer
                this.startTimerAfterBurnoutCheck();
            });
        }

        if (this.burnoutTakeBreakBtn) {
            this.burnoutTakeBreakBtn.addEventListener('click', () => {
                this.hideBurnoutModal();
                this.burnoutCheckedToday = true;
                this.saveBurnoutCheckState();
                // Don't start timer, user chose to take a break
            });
        }

        // Load burnout check state from localStorage
        this.loadBurnoutCheckState();
    }

    saveBurnoutCheckState() {
        const today = new Date().toDateString();
        localStorage.setItem('burnoutCheckedDate', today);
    }

    loadBurnoutCheckState() {
        const savedDate = localStorage.getItem('burnoutCheckedDate');
        const today = new Date().toDateString();
        this.burnoutCheckedToday = (savedDate === today);
    }

    checkBurnoutOnLoad() {
        // If burnout risk is high/critical, show browser notification on page load
        if (this.burnoutRisk &&
            ['high', 'critical'].includes(this.burnoutRisk.risk_level) &&
            !this.burnoutCheckedToday) {
            this.showBurnoutBrowserNotification();
        }
    }

    async checkBurnoutBeforeStart() {
        // Skip if already checked today or during break
        if (this.burnoutCheckedToday || this.isBreak) {
            return true; // OK to proceed
        }

        // Use preloaded data or fetch fresh
        let risk = this.burnoutRisk;
        if (!risk) {
            risk = await this.fetchBurnoutRisk();
            this.burnoutRisk = risk;
        }

        if (risk && ['high', 'critical'].includes(risk.risk_level)) {
            this.showBurnoutWarningModal(risk);
            return false; // Don't start yet
        }

        return true; // OK to proceed
    }

    async fetchBurnoutRisk() {
        try {
            const response = await fetch('/api/burnout-risk');
            if (response.ok) {
                return await response.json();
            }
        } catch (e) {
            console.log('Could not fetch burnout risk:', e);
        }
        return null;
    }

    showBurnoutWarningModal(risk) {
        if (!this.burnoutModal) return;

        // Play warning sound
        this.playSound('burnout');

        // Populate modal with risk data
        const scoreEl = document.getElementById('modal-risk-score');
        const badgeEl = document.getElementById('modal-risk-badge');
        const gaugeEl = document.getElementById('modal-risk-gauge');
        const factorsEl = document.getElementById('modal-burnout-factors');
        const recsEl = document.getElementById('modal-recommendations');

        if (scoreEl) {
            scoreEl.textContent = risk.risk_score;
        }

        if (badgeEl) {
            badgeEl.textContent = risk.risk_level.toUpperCase();
            badgeEl.className = `risk-badge risk-badge-${risk.risk_level}`;
        }

        if (gaugeEl) {
            gaugeEl.style.setProperty('--risk-percent', risk.risk_score);
        }

        // Populate risk factors
        if (factorsEl && risk.risk_factors) {
            factorsEl.innerHTML = '<h4>Hlavni faktory:</h4>';
            const topFactors = risk.risk_factors.slice(0, 3);
            topFactors.forEach(factor => {
                const item = document.createElement('div');
                item.className = 'burnout-factor-item';
                item.innerHTML = `
                    <span class="factor-severity-dot ${factor.severity}"></span>
                    <span>${factor.message}</span>
                `;
                factorsEl.appendChild(item);
            });
        }

        // Populate recommendations
        if (recsEl && risk.recommendations) {
            recsEl.innerHTML = '<h4>Doporuceni:</h4><ul>';
            const topRecs = risk.recommendations.slice(0, 2);
            topRecs.forEach(rec => {
                recsEl.innerHTML += `<li>${rec}</li>`;
            });
            recsEl.innerHTML += '</ul>';
        }

        // Show modal
        this.burnoutModal.style.display = 'flex';
    }

    hideBurnoutModal() {
        if (this.burnoutModal) {
            this.burnoutModal.style.display = 'none';
        }
    }

    showBurnoutBrowserNotification() {
        if (!('Notification' in window) || Notification.permission !== 'granted') {
            return;
        }

        const risk = this.burnoutRisk;
        if (!risk) return;

        const topFactor = risk.risk_factors && risk.risk_factors[0]
            ? risk.risk_factors[0].message
            : 'Doporucujeme odpocinek';

        const notification = new Notification('Pomodoro - Riziko vyhoreni', {
            body: `Risk: ${risk.risk_level.toUpperCase()} (${risk.risk_score}/100)\n${topFactor}`,
            icon: '/static/images/icon.png',
            tag: 'burnout-warning',
            requireInteraction: true
        });

        notification.onclick = () => {
            window.focus();
            window.location.href = '/insights#burnout';
        };
    }

    startTimerAfterBurnoutCheck() {
        // Actually start the timer (bypassing burnout check)
        this.isRunning = true;
        this.btnStart.style.display = 'none';
        this.btnPause.style.display = 'flex';

        this.targetEndTime = Date.now() + (this.remainingSeconds * 1000);

        this.interval = setInterval(() => {
            this.tick();
        }, 1000);

        this.updateTitle();
        this.saveTimerState();
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

    // === Session Quality Prediction ===

    initializeQualityPrediction() {
        this.qualityWidget = document.getElementById('quality-prediction-widget');
        this.qualityScore = document.getElementById('prediction-score');
        this.qualityRingProgress = document.getElementById('prediction-ring-progress');
        this.qualityFactors = document.getElementById('prediction-factors');
        this.qualityRecommendation = document.getElementById('prediction-recommendation');

        if (!this.qualityWidget) return;

        // Initial fetch
        this.fetchQualityPrediction();

        // Live update on preset change
        this.presetBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                // Small delay to let preset change complete
                setTimeout(() => this.fetchQualityPrediction(), 100);
            });
        });

        // Live update on category change
        if (this.categorySelect) {
            this.categorySelect.addEventListener('change', () => {
                this.fetchQualityPrediction();
            });
        }
    }

    async fetchQualityPrediction() {
        if (!this.qualityWidget) return;

        const preset = this.currentPreset;
        const category = this.categorySelect ? this.categorySelect.value : null;

        try {
            const params = new URLSearchParams({ preset });
            if (category) params.append('category', category);

            const response = await fetch(`/api/quality-prediction?${params}`);
            const data = await response.json();

            if (!data.error) {
                this.updateQualityWidget(data);
            } else {
                this.showQualityError();
            }
        } catch (e) {
            console.log('Could not fetch quality prediction:', e);
            this.showQualityError();
        }
    }

    updateQualityWidget(data) {
        if (!this.qualityWidget) return;

        const score = Math.round(data.predicted_productivity || 70);

        // Update score display
        if (this.qualityScore) {
            this.qualityScore.textContent = `${score}%`;
        }

        // Update ring progress (circumference = 2 * PI * 35 = 219.91)
        if (this.qualityRingProgress) {
            const circumference = 219.91;
            const offset = circumference * (1 - score / 100);
            this.qualityRingProgress.style.strokeDashoffset = offset;

            // Color based on score
            let color = '#22c55e'; // green
            if (score < 60) {
                color = '#ef4444'; // red
            } else if (score < 75) {
                color = '#f59e0b'; // orange
            }
            this.qualityRingProgress.style.stroke = color;
        }

        // Update factors
        if (this.qualityFactors && data.factors) {
            const topFactors = data.factors.slice(0, 2);
            if (topFactors.length > 0) {
                this.qualityFactors.innerHTML = topFactors.map(f => `
                    <span class="factor-tag factor-${f.type}">
                        ${f.type === 'positive' ? '✓' : '✗'} ${f.name}
                    </span>
                `).join('');
            } else {
                this.qualityFactors.innerHTML = '';
            }
        }

        // Update recommendation
        if (this.qualityRecommendation && data.recommendation) {
            const rec = data.recommendation;
            this.qualityRecommendation.innerHTML = `
                <span class="rec-icon">${rec.icon || '💡'}</span>
                <span class="rec-text">${rec.message}</span>
            `;
            this.qualityRecommendation.className = `prediction-recommendation rec-${rec.type}`;
        }

        // Update widget class based on score
        this.qualityWidget.classList.remove('score-high', 'score-medium', 'score-low');
        if (score >= 75) {
            this.qualityWidget.classList.add('score-high');
        } else if (score >= 60) {
            this.qualityWidget.classList.add('score-medium');
        } else {
            this.qualityWidget.classList.add('score-low');
        }
    }

    showQualityError() {
        if (this.qualityScore) {
            this.qualityScore.textContent = '--';
        }
        if (this.qualityRecommendation) {
            this.qualityRecommendation.innerHTML = `
                <span class="rec-icon">⚠️</span>
                <span class="rec-text">ML sluzba nedostupna</span>
            `;
        }
    }
}

// =============================================================================
// FOCUSAI LEARNING RECOMMENDER - Client-side Functions
// =============================================================================

// Global state for AI suggestions
let currentAISuggestion = null;
let aiSuggestionVisible = true;

/**
 * Load AI suggestion for next session
 * @param {string} excludeTopic - Topic to exclude (for "Jiný nápad" functionality)
 * @param {boolean} bypassCache - Force refresh without cache (default: false)
 */
async function loadAISuggestion(excludeTopic = '', bypassCache = false) {
    const panel = document.getElementById('ai-suggestion-panel');
    const idle = document.getElementById('ai-idle');
    const loading = document.getElementById('ai-loading');
    const result = document.getElementById('ai-result');
    const error = document.getElementById('ai-error');

    if (!panel) return;

    // Hide idle state, show loading state
    if (idle) idle.classList.add('hidden');
    loading.classList.remove('hidden');
    result.classList.add('hidden');
    error.classList.add('hidden');

    try {
        // Build URL with optional exclude_topic and bypass_cache parameters
        let url = '/api/ai/next-session';
        const params = [];
        if (excludeTopic) {
            params.push(`exclude_topic=${encodeURIComponent(excludeTopic)}`);
        }
        if (bypassCache) {
            params.push(`bypass_cache=true`);
        }
        if (params.length > 0) {
            url += '?' + params.join('&');
        }

        const response = await fetch(url);
        const data = await response.json();

        if (data && data.topic) {
            currentAISuggestion = data;
            displayAISuggestion(data);
        } else {
            showAIError();
        }
    } catch (err) {
        console.error('AI suggestion failed:', err);
        showAIError();
    }
}

/**
 * Force refresh AI suggestion (bypasses all caches)
 */
async function forceRefreshAISuggestion() {
    await loadAISuggestion('', true); // bypassCache = true
}

/**
 * Display AI suggestion in the panel
 */
function displayAISuggestion(data) {
    const loading = document.getElementById('ai-loading');
    const result = document.getElementById('ai-result');
    const error = document.getElementById('ai-error');

    // Update UI elements
    const categoryEl = document.getElementById('ai-category');
    const topicEl = document.getElementById('ai-topic');
    const reasonEl = document.getElementById('ai-reason');
    const confidenceBar = document.getElementById('ai-confidence-bar');
    const confidenceValue = document.getElementById('ai-confidence-value');
    const cacheStatus = document.getElementById('ai-cache-status');

    if (categoryEl) categoryEl.textContent = data.category || 'Learning';
    if (topicEl) topicEl.textContent = data.topic || 'Osobní rozvoj';
    if (reasonEl) reasonEl.textContent = data.reason || 'Zkoušej nové věci každý den';

    // Display confidence
    const confidence = Math.round((data.confidence || 0.5) * 100);
    if (confidenceBar) confidenceBar.style.width = `${confidence}%`;
    if (confidenceValue) confidenceValue.textContent = `${confidence}%`;

    // Cache status
    if (cacheStatus) {
        cacheStatus.textContent = data.from_cache ? '📦 Z cache' : '🧠 Čerstvá analýza';
    }

    // Show result, hide loading
    loading.classList.add('hidden');
    result.classList.remove('hidden');
    error.classList.add('hidden');
}

/**
 * Show error state in AI panel
 */
function showAIError() {
    const loading = document.getElementById('ai-loading');
    const result = document.getElementById('ai-result');
    const error = document.getElementById('ai-error');

    loading.classList.add('hidden');
    result.classList.add('hidden');
    error.classList.remove('hidden');
}

/**
 * Hide AI suggestion panel
 */
function hideAISuggestion() {
    const panel = document.getElementById('ai-suggestion-panel');
    if (panel) {
        panel.classList.add('hidden');
        aiSuggestionVisible = false;
    }
}

/**
 * Show AI suggestion panel
 */
function showAISuggestionPanel() {
    const panel = document.getElementById('ai-suggestion-panel');
    if (panel) {
        panel.classList.remove('hidden');
        aiSuggestionVisible = true;
    }
}

/**
 * Refresh AI suggestion (invalidate cache and reload with different topic)
 */
async function refreshAISuggestion() {
    // Get current topic to exclude from next suggestion
    const currentTopic = currentAISuggestion?.topic || '';

    // First invalidate the cache
    try {
        await fetch('/api/ai/invalidate-cache?type=next_session', { method: 'POST' });
    } catch (err) {
        console.warn('Cache invalidation failed:', err);
    }

    // Then reload suggestion, excluding the current topic
    await loadAISuggestion(currentTopic);
}

/**
 * Use the AI suggestion - fill in the task input
 */
function useSuggestion() {
    if (!currentAISuggestion) return;

    const taskInput = document.getElementById('task-input');
    const categorySelect = document.getElementById('category-select');

    if (taskInput && currentAISuggestion.topic) {
        taskInput.value = currentAISuggestion.topic;
    }

    if (categorySelect && currentAISuggestion.category) {
        // Check if the category exists in the select
        const options = Array.from(categorySelect.options);
        const matchingOption = options.find(opt =>
            opt.value.toLowerCase() === currentAISuggestion.category.toLowerCase()
        );

        if (matchingOption) {
            categorySelect.value = matchingOption.value;
        }
    }

    // Also update preset if suggested
    if (currentAISuggestion.preset && window.pomodoroTimer) {
        const presetBtn = document.querySelector(`[data-preset="${currentAISuggestion.preset}"]`);
        if (presetBtn) {
            presetBtn.click();
        }
    }

    // Hide the panel after using suggestion
    hideAISuggestion();

    // Show feedback toast
    showToast('AI doporučení použito!', 'success');
}

/**
 * Load more/different suggestions
 */
async function loadMoreSuggestions() {
    await refreshAISuggestion();
}

/**
 * Simple toast notification for feedback
 */
function showToast(message, type = 'info') {
    // Check if toast container exists, if not create it
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${type === 'success' ? '✓' : 'ℹ️'}</span>
        <span class="toast-message">${message}</span>
    `;

    container.appendChild(toast);

    // Animate in
    setTimeout(() => toast.classList.add('show'), 10);

    // Remove after 3 seconds
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// =============================================================================
// EXPAND SUGGESTION FUNCTIONS - Follow-up questions for AI recommendations
// =============================================================================

let expandSectionOpen = false;

/**
 * Toggle the expand section visibility
 */
function toggleExpandSection() {
    const buttons = document.getElementById('expand-buttons');
    const icon = document.getElementById('expand-icon');
    const answer = document.getElementById('expand-answer');

    if (!buttons || !icon) return;

    expandSectionOpen = !expandSectionOpen;

    if (expandSectionOpen) {
        buttons.classList.remove('hidden');
        icon.textContent = '▼';
    } else {
        buttons.classList.add('hidden');
        answer.classList.add('hidden');
        icon.textContent = '▶';
    }
}

/**
 * Expand the current AI suggestion with more details
 * @param {string} questionType - Type of question: resources, steps, time_estimate, connection
 */
async function expandSuggestion(questionType) {
    if (!currentAISuggestion) {
        showToast('Nejdříve získej doporučení', 'info');
        return;
    }

    const answerDiv = document.getElementById('expand-answer');
    const loadingDiv = document.getElementById('expand-loading');
    const contentDiv = document.getElementById('expand-content');

    if (!answerDiv || !loadingDiv || !contentDiv) return;

    // Show loading state
    answerDiv.classList.remove('hidden');
    loadingDiv.classList.remove('hidden');
    contentDiv.classList.add('hidden');

    try {
        const response = await fetch('/api/ai/expand-suggestion', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                suggestion: {
                    category: currentAISuggestion.category,
                    topic: currentAISuggestion.topic,
                    reason: currentAISuggestion.reason
                },
                question_type: questionType
            })
        });

        const data = await response.json();

        if (data && data.answer) {
            displayExpandedAnswer(data, questionType);
        } else {
            showExpandError();
        }
    } catch (err) {
        console.error('Expand suggestion failed:', err);
        showExpandError();
    }
}

/**
 * Display the expanded answer from AI
 * @param {Object} data - Response from AI
 * @param {string} questionType - Type of question asked
 */
function displayExpandedAnswer(data, questionType) {
    const loadingDiv = document.getElementById('expand-loading');
    const contentDiv = document.getElementById('expand-content');
    const iconEl = document.getElementById('expand-icon-result');
    const typeEl = document.getElementById('expand-type');
    const textEl = document.getElementById('expand-text');
    const confidenceEl = document.getElementById('expand-confidence');

    if (!loadingDiv || !contentDiv) return;

    // Question type labels
    const typeLabels = {
        'resources': 'Zdroje',
        'steps': 'Kroky',
        'time_estimate': 'Časový odhad',
        'connection': 'Souvislost s cíli'
    };

    // Set icon
    if (iconEl) iconEl.textContent = data.icon || '💡';

    // Set type label
    if (typeEl) typeEl.textContent = typeLabels[questionType] || 'Odpověď';

    // Format and set answer text
    if (textEl) {
        // Convert bullet points to HTML
        let formattedAnswer = data.answer || 'Žádná odpověď';
        formattedAnswer = formattedAnswer
            .replace(/•/g, '<br>•')
            .replace(/\n/g, '<br>')
            .replace(/^<br>/, ''); // Remove leading br
        textEl.innerHTML = formattedAnswer;
    }

    // Show confidence if available
    if (confidenceEl) {
        if (data.confidence) {
            const confidence = Math.round(data.confidence * 100);
            confidenceEl.innerHTML = `
                <span class="expand-confidence-label">Jistota: ${confidence}%</span>
                ${data.ai_generated ? '<span class="ai-badge">🧠 AI</span>' : '<span class="fallback-badge">📦 Fallback</span>'}
            `;
        } else {
            confidenceEl.innerHTML = '';
        }
    }

    // Hide loading, show content
    loadingDiv.classList.add('hidden');
    contentDiv.classList.remove('hidden');
}

/**
 * Show error state in expand section
 */
function showExpandError() {
    const loadingDiv = document.getElementById('expand-loading');
    const contentDiv = document.getElementById('expand-content');
    const textEl = document.getElementById('expand-text');
    const iconEl = document.getElementById('expand-icon-result');
    const typeEl = document.getElementById('expand-type');
    const confidenceEl = document.getElementById('expand-confidence');

    if (loadingDiv) loadingDiv.classList.add('hidden');
    if (contentDiv) contentDiv.classList.remove('hidden');
    if (iconEl) iconEl.textContent = '⚠️';
    if (typeEl) typeEl.textContent = 'Chyba';
    if (textEl) textEl.innerHTML = 'AI dočasně nedostupná. Zkus to později.';
    if (confidenceEl) confidenceEl.innerHTML = '';
}

/**
 * Reset expand section when new suggestion is loaded
 */
function resetExpandSection() {
    const buttons = document.getElementById('expand-buttons');
    const answer = document.getElementById('expand-answer');
    const icon = document.getElementById('expand-icon');

    if (buttons) buttons.classList.add('hidden');
    if (answer) answer.classList.add('hidden');
    if (icon) icon.textContent = '▶';
    expandSectionOpen = false;
}

// =============================================================================
// START DAY WORKFLOW FUNCTIONS
// =============================================================================

let startDayData = null;
let startDayCurrentStep = 1;
let categoryPlannerData = {};

// Wellness check-in data
let wellnessData = {
    sleep_quality: null,
    energy_level: null,
    mood: null,
    stress_level: null,
    motivation: null,
    focus_ability: null
};

// Wellness metric configurations
const WELLNESS_METRICS = {
    sleep_quality: { id: 'sleep', color: 'var(--accent-blue)', label: 'Spánek' },
    energy_level: { id: 'energy', color: 'var(--accent-green)', label: 'Energie' },
    mood: { id: 'mood', color: 'var(--accent-orange)', label: 'Nálada' },
    stress_level: { id: 'stress', color: 'var(--accent-red)', label: 'Stres', inverse: true },
    motivation: { id: 'motivation', color: 'var(--accent-purple)', label: 'Motivace' },
    focus_ability: { id: 'focus', color: 'var(--accent-cyan)', label: 'Soustředění' }
};

// Track wellness dragging state per metric
let wellnessDragging = {};

/**
 * Initialize wellness rating handlers for all 6 metrics
 */
function initWellnessRatings() {
    for (const [metricKey, config] of Object.entries(WELLNESS_METRICS)) {
        const container = document.getElementById(`wellness-${config.id}`);
        if (!container) continue;

        const starsContainer = container.querySelector('.wellness-stars-svg');
        if (!starsContainer) continue;

        wellnessDragging[metricKey] = false;

        // Mouse events
        starsContainer.addEventListener('mousedown', (e) => {
            wellnessDragging[metricKey] = true;
            setWellnessRatingFromPosition(metricKey, e, starsContainer);
        });

        starsContainer.addEventListener('mousemove', (e) => {
            if (wellnessDragging[metricKey]) {
                setWellnessRatingFromPosition(metricKey, e, starsContainer);
            }
        });

        starsContainer.addEventListener('mouseup', () => {
            wellnessDragging[metricKey] = false;
        });

        starsContainer.addEventListener('mouseleave', () => {
            wellnessDragging[metricKey] = false;
        });

        starsContainer.addEventListener('click', (e) => {
            setWellnessRatingFromPosition(metricKey, e, starsContainer);
        });

        // Touch events for mobile
        starsContainer.addEventListener('touchstart', (e) => {
            e.preventDefault();
            wellnessDragging[metricKey] = true;
            setWellnessRatingFromPosition(metricKey, e.touches[0], starsContainer);
        });

        starsContainer.addEventListener('touchmove', (e) => {
            e.preventDefault();
            if (wellnessDragging[metricKey]) {
                setWellnessRatingFromPosition(metricKey, e.touches[0], starsContainer);
            }
        });

        starsContainer.addEventListener('touchend', () => {
            wellnessDragging[metricKey] = false;
        });
    }

    // Reset overall preview
    updateWellnessOverall();
}

/**
 * Calculate percentage from click/touch position
 */
function setWellnessRatingFromPosition(metricKey, event, container) {
    const rect = container.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const width = rect.width;

    // Calculate percentage (0-100) rounded to 5%
    let percentage = (x / width) * 100;
    percentage = Math.round(percentage / 5) * 5;
    percentage = Math.max(0, Math.min(100, percentage));

    setWellnessRating(metricKey, percentage);
}

/**
 * Set wellness rating for a specific metric
 */
function setWellnessRating(metricKey, percentage) {
    const config = WELLNESS_METRICS[metricKey];
    if (!config) return;

    // Store the value
    wellnessData[metricKey] = percentage;

    // Update star fills
    updateWellnessStarsFill(config.id, percentage);

    // Update percentage display
    const percentEl = document.getElementById(`wellness-${config.id}-percentage`);
    if (percentEl) {
        percentEl.textContent = `${percentage}%`;
    }

    // Update overall wellness score
    updateWellnessOverall();
}

/**
 * Update star gradient fills for a wellness metric
 */
function updateWellnessStarsFill(metricId, percentage) {
    const percentPerStar = 20;

    for (let i = 0; i < 5; i++) {
        const starStart = i * percentPerStar;
        const starEnd = (i + 1) * percentPerStar;

        let fillPercent;
        if (percentage >= starEnd) {
            fillPercent = 100;
        } else if (percentage <= starStart) {
            fillPercent = 0;
        } else {
            fillPercent = ((percentage - starStart) / percentPerStar) * 100;
        }

        // Update gradient stops
        const gradient = document.getElementById(`wellness-${metricId}-grad-${i}`);
        if (gradient) {
            const fillStop = gradient.querySelector('.fill-stop');
            const emptyStop = gradient.querySelector('.empty-stop');
            if (fillStop && emptyStop) {
                fillStop.setAttribute('offset', `${fillPercent}%`);
                emptyStop.setAttribute('offset', `${fillPercent}%`);
            }
        }
    }
}

/**
 * Calculate and display overall wellness score
 */
function updateWellnessOverall() {
    const weights = {
        sleep_quality: 0.20,
        energy_level: 0.20,
        mood: 0.15,
        stress_level: 0.15,  // Inverse: lower stress = better
        motivation: 0.15,
        focus_ability: 0.15
    };

    let totalWeight = 0;
    let weightedSum = 0;
    let filledCount = 0;

    for (const [key, weight] of Object.entries(weights)) {
        const value = wellnessData[key];
        if (value !== null) {
            filledCount++;
            totalWeight += weight;
            // Stress is inverse: low stress = good, so we use (100 - stress)
            const effectiveValue = (key === 'stress_level') ? (100 - value) : value;
            weightedSum += effectiveValue * weight;
        }
    }

    // Calculate overall score
    let overall = 0;
    if (totalWeight > 0) {
        overall = Math.round(weightedSum / totalWeight);
    }

    // Update overall display
    const overallValueEl = document.getElementById('wellness-overall-value');
    const overallBarEl = document.getElementById('wellness-overall-bar');
    const overallLabelEl = document.getElementById('wellness-overall-label');

    if (overallValueEl) {
        overallValueEl.textContent = filledCount > 0 ? `${overall}%` : '--%';
    }

    if (overallBarEl) {
        overallBarEl.style.width = `${overall}%`;

        // Color based on score
        if (overall >= 70) {
            overallBarEl.style.backgroundColor = 'var(--accent-green)';
        } else if (overall >= 40) {
            overallBarEl.style.backgroundColor = 'var(--accent-orange)';
        } else {
            overallBarEl.style.backgroundColor = 'var(--accent-red)';
        }
    }

    if (overallLabelEl) {
        if (overall >= 80) {
            overallLabelEl.textContent = 'Výborný stav';
        } else if (overall >= 60) {
            overallLabelEl.textContent = 'Dobrý stav';
        } else if (overall >= 40) {
            overallLabelEl.textContent = 'Průměrný stav';
        } else if (filledCount > 0) {
            overallLabelEl.textContent = 'Nízký stav';
        } else {
            overallLabelEl.textContent = 'Vyplňte hodnocení';
        }
    }

    return overall;
}

/**
 * Validate wellness step - at least 3 metrics should be filled
 */
function validateWellnessStep() {
    const filledCount = Object.values(wellnessData).filter(v => v !== null).length;
    return filledCount >= 3;
}

/**
 * Pre-fill wellness data if already completed today
 */
function prefillWellnessData(checkin) {
    if (!checkin) return;

    for (const [metricKey, config] of Object.entries(WELLNESS_METRICS)) {
        const value = checkin[metricKey];
        if (value !== null && value !== undefined) {
            setWellnessRating(metricKey, Math.round(value));
        }
    }
}

/**
 * Open the Start Day modal and load data
 */
async function openStartDayModal() {
    const modal = document.getElementById('start-day-modal');
    if (!modal) return;

    // Reset state
    startDayCurrentStep = 1;
    categoryPlannerData = {};
    wellnessData = {
        sleep_quality: null,
        energy_level: null,
        mood: null,
        stress_level: null,
        motivation: null,
        focus_ability: null
    };

    // Show modal
    modal.style.display = 'flex';

    // Initialize wellness rating handlers
    initWellnessRatings();

    // Reset to step 1
    goToStartDayStep(1);

    // Load data
    await loadStartDayData();
}

/**
 * Close the Start Day modal
 */
function closeStartDayModal() {
    const modal = document.getElementById('start-day-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

/**
 * Navigate to a specific step
 */
function goToStartDayStep(stepNumber) {
    startDayCurrentStep = stepNumber;

    // Hide all steps
    document.querySelectorAll('.start-day-step').forEach(step => {
        step.classList.add('hidden');
    });

    // Show current step
    const currentStep = document.getElementById(`start-day-step-${stepNumber}`);
    if (currentStep) {
        currentStep.classList.remove('hidden');
    }

    // Update step indicators
    document.querySelectorAll('.start-day-steps .step').forEach(stepEl => {
        const num = parseInt(stepEl.dataset.step);
        stepEl.classList.toggle('active', num === stepNumber);
        stepEl.classList.toggle('completed', num < stepNumber);
    });
}

/**
 * Load all Start Day data from API
 */
async function loadStartDayData() {
    const loadingEl = document.getElementById('briefing-loading');
    const contentEl = document.getElementById('briefing-content');
    const errorEl = document.getElementById('briefing-error');

    // Show loading
    if (loadingEl) loadingEl.classList.remove('hidden');
    if (contentEl) contentEl.classList.add('hidden');
    if (errorEl) errorEl.classList.add('hidden');

    try {
        const response = await fetch('/api/start-day');
        const data = await response.json();

        if (data.success) {
            startDayData = data;

            // Pre-fill wellness data if already completed today
            if (data.wellness_checkin) {
                prefillWellnessData(data.wellness_checkin);
            }

            // Render morning briefing
            renderMorningBriefing(data.morning_briefing);

            // Render category planner
            renderCategoryPlanner(data.categories);

            // Render challenge
            renderDailyChallenge(data.daily_challenge);

            // Update summary info
            updateStartDaySummary(data);

            // Hide loading, show content
            if (loadingEl) loadingEl.classList.add('hidden');
            if (contentEl) contentEl.classList.remove('hidden');
        } else {
            showStartDayError();
        }
    } catch (err) {
        console.error('Failed to load Start Day data:', err);
        showStartDayError();
    }
}

/**
 * Show error state
 */
function showStartDayError() {
    const loadingEl = document.getElementById('briefing-loading');
    const contentEl = document.getElementById('briefing-content');
    const errorEl = document.getElementById('briefing-error');

    if (loadingEl) loadingEl.classList.add('hidden');
    if (contentEl) contentEl.classList.add('hidden');
    if (errorEl) errorEl.classList.remove('hidden');
}

/**
 * Format briefing value - handles both strings and objects
 * @param {*} value - The value to format (string or object)
 * @param {string} type - Type of value: 'yesterday', 'prediction', 'recommendation', 'wellbeing', 'generic'
 * @param {string} fallback - Fallback text if value is empty
 * @returns {string} Formatted text
 */
function formatBriefingValue(value, type = 'generic', fallback = '-') {
    if (!value) return fallback;
    if (typeof value === 'string') return value;

    // yesterday_summary: { sessions, rating, highlight }
    if (type === 'yesterday' && typeof value === 'object') {
        const parts = [];
        if (value.sessions !== undefined) parts.push(`${value.sessions} sessions`);
        if (value.rating !== undefined) parts.push(`${value.rating}%`);
        if (value.highlight) parts.push(value.highlight);
        return parts.length > 0 ? parts.join(' - ') : fallback;
    }

    // today_prediction: { expected_sessions, expected_productivity, confidence, reasoning }
    if (type === 'prediction' && typeof value === 'object') {
        const parts = [];
        if (value.expected_sessions !== undefined) {
            parts.push(`Očekáváno ${value.expected_sessions} sessions`);
        }
        if (value.expected_productivity !== undefined) {
            parts.push(`${value.expected_productivity}% produktivita`);
        }
        if (value.reasoning) parts.push(value.reasoning);
        return parts.length > 0 ? parts.join(' - ') : fallback;
    }

    // recommendation/focus
    if (type === 'recommendation' && typeof value === 'object') {
        return value.focus || value.message || value.text || value.suggestion || fallback;
    }

    // wellbeing: { status, tip, score }
    if (type === 'wellbeing' && typeof value === 'object') {
        const parts = [];
        if (value.status) parts.push(value.status);
        if (value.tip) parts.push(value.tip);
        if (value.score !== undefined) parts.push(`Score: ${value.score}`);
        return parts.length > 0 ? parts.join(' - ') : fallback;
    }

    // Generic fallback - try common properties
    if (typeof value === 'object') {
        return value.message || value.text || value.highlight || value.summary || fallback;
    }

    return fallback;
}

/**
 * Render the morning briefing from AI
 */
function renderMorningBriefing(briefing) {
    const yesterdayEl = document.getElementById('briefing-yesterday');
    const predictionEl = document.getElementById('briefing-prediction');
    const recommendationEl = document.getElementById('briefing-recommendation');
    const wellbeingEl = document.getElementById('briefing-wellbeing');

    if (!briefing) {
        // Fallback when AI is completely unavailable
        if (yesterdayEl) yesterdayEl.textContent = 'AI analýza není dostupná. Pokračuj na plánování.';
        if (predictionEl) predictionEl.textContent = '-';
        if (recommendationEl) recommendationEl.textContent = 'Doporučuji začít s Deep Work presetem.';
        if (wellbeingEl) wellbeingEl.textContent = 'Nezapomeň na pravidelné přestávky!';
        return;
    }

    // Parse AI response - handle both structured and text responses
    if (typeof briefing === 'string') {
        // Simple text response
        if (yesterdayEl) yesterdayEl.textContent = briefing;
        return;
    }

    // Show fallback indicator if using PresetRecommender
    if (briefing.fallback && briefing.using_preset_recommender) {
        // Add visual indicator for fallback mode
        if (recommendationEl) {
            recommendationEl.innerHTML = '';
            const indicator = document.createElement('span');
            indicator.className = 'fallback-indicator';
            indicator.textContent = '📊 ';
            recommendationEl.appendChild(indicator);

            const text = document.createElement('span');
            text.textContent = briefing.recommendation || 'Doporučuji začít s Deep Work presetem.';
            recommendationEl.appendChild(text);
        }
    }

    // Structured response from AIAnalyzer - use formatBriefingValue to handle objects
    if (yesterdayEl) {
        yesterdayEl.textContent = formatBriefingValue(
            briefing.yesterday_summary || briefing.analysis?.yesterday,
            'yesterday',
            'Včerejší analýza není dostupná'
        );
    }
    if (predictionEl) {
        // Handle both string and object prediction formats
        let predictionText;
        if (briefing.prediction && typeof briefing.prediction === 'object') {
            const pred = briefing.prediction;
            predictionText = `Očekávám ${pred.predicted_sessions || 4} sessions, produktivita ~${pred.productivity_prediction || 75}%`;
        } else {
            predictionText = formatBriefingValue(
                briefing.today_prediction || briefing.analysis?.prediction,
                'prediction',
                'Predikce není k dispozici'
            );
        }
        predictionEl.textContent = predictionText;
    }
    if (recommendationEl && !briefing.fallback) {
        // Only set recommendation text if not already set by fallback handler above
        let recText;
        // Handle both old format (recommendation) and new format (optimal_schedule)
        if (briefing.recommendation) {
            recText = formatBriefingValue(briefing.recommendation, 'recommendation', null);
        } else if (briefing.optimal_schedule && briefing.optimal_schedule.length > 0) {
            // Use first item from optimal_schedule as recommendation
            const first = briefing.optimal_schedule[0];
            recText = `${first.activity} (${first.preset} preset) - ${first.reason}`;
        } else if (briefing.analysis?.focus) {
            recText = formatBriefingValue(briefing.analysis.focus, 'recommendation', null);
        }

        if (recText) {
            recommendationEl.textContent = recText;
        } else {
            recommendationEl.textContent = 'Doporučuji začít s Deep Work presetem.';
        }
    }
    if (wellbeingEl) {
        // Handle both old format (wellbeing) and new format (wellbeing_check)
        let wellbeingText;
        if (briefing.wellbeing) {
            wellbeingText = formatBriefingValue(briefing.wellbeing, 'wellbeing', null);
        } else if (briefing.wellbeing_check?.suggestion) {
            wellbeingText = briefing.wellbeing_check.suggestion;
        } else if (briefing.analysis?.wellbeing) {
            wellbeingText = formatBriefingValue(briefing.analysis.wellbeing, 'wellbeing', null);
        }

        if (wellbeingText) {
            wellbeingEl.textContent = wellbeingText;
        } else {
            wellbeingEl.textContent = 'Držím ti palce!';
        }
    }
}

/**
 * Render the category planner with all user categories
 */
function renderCategoryPlanner(categories) {
    const planner = document.getElementById('category-planner');
    if (!planner || !categories) return;

    planner.innerHTML = '';
    categoryPlannerData = {};

    categories.forEach(category => {
        categoryPlannerData[category] = 0;

        const row = document.createElement('div');
        row.className = 'category-row';
        row.innerHTML = `
            <span class="category-name">${category}</span>
            <div class="category-counter">
                <button class="counter-btn minus" onclick="adjustCategorySessions('${category}', -1)">-</button>
                <span class="counter-value" id="counter-${category.replace(/\s+/g, '-')}">0</span>
                <button class="counter-btn plus" onclick="adjustCategorySessions('${category}', 1)">+</button>
            </div>
        `;
        planner.appendChild(row);
    });
}

/**
 * Adjust session count for a category
 */
function adjustCategorySessions(category, delta) {
    const current = categoryPlannerData[category] || 0;
    const newValue = Math.max(0, Math.min(20, current + delta));
    categoryPlannerData[category] = newValue;

    // Update display
    const counterId = `counter-${category.replace(/\s+/g, '-')}`;
    const counterEl = document.getElementById(counterId);
    if (counterEl) {
        counterEl.textContent = newValue;
    }

    // Update total
    updatePlanningTotal();
}

/**
 * Update the total planned sessions display
 */
function updatePlanningTotal() {
    const total = Object.values(categoryPlannerData).reduce((sum, val) => sum + val, 0);
    const totalEl = document.getElementById('total-planned-sessions');
    if (totalEl) {
        totalEl.textContent = `${total} sessions`;
    }
}

/**
 * Render the daily challenge
 */
function renderDailyChallenge(challenge) {
    const titleEl = document.getElementById('challenge-title');
    const descEl = document.getElementById('challenge-description');
    const xpEl = document.getElementById('challenge-xp');

    if (!challenge) {
        if (titleEl) titleEl.textContent = 'Žádná výzva';
        if (descEl) descEl.textContent = 'Výzva není k dispozici.';
        if (xpEl) xpEl.textContent = '+0 XP';
        return;
    }

    if (titleEl) titleEl.textContent = challenge.title || 'Denní výzva';
    if (descEl) descEl.textContent = challenge.description || 'Splň dnešní cíl!';
    if (xpEl) xpEl.textContent = `+${challenge.xp_reward || 50} XP`;
}

/**
 * Update summary section with streak and level
 */
function updateStartDaySummary(data) {
    const streakEl = document.getElementById('summary-streak');
    const levelEl = document.getElementById('summary-level');

    if (streakEl && data.streak_status) {
        streakEl.textContent = data.streak_status.current_streak || 0;
    }
    if (levelEl && data.user_profile) {
        levelEl.textContent = data.user_profile.level || 1;
    }
}

/**
 * Complete the Start Day workflow - save and close
 */
async function completeStartDay() {
    // Prepare themes data
    const themes = [];
    for (const [category, sessions] of Object.entries(categoryPlannerData)) {
        if (sessions > 0) {
            themes.push({
                theme: category,
                planned_sessions: sessions,
                notes: ''
            });
        }
    }

    // Get notes
    const notesEl = document.getElementById('day-notes');
    const notes = notesEl ? notesEl.value : '';

    // Get challenge acceptance
    const acceptChallengeEl = document.getElementById('accept-challenge');
    const challengeAccepted = acceptChallengeEl ? acceptChallengeEl.checked : false;

    // Prepare wellness data - only include filled metrics
    const wellnessPayload = {};
    let hasWellnessData = false;
    for (const [key, value] of Object.entries(wellnessData)) {
        if (value !== null) {
            wellnessPayload[key] = value;
            hasWellnessData = true;
        }
    }

    // Capture wellness notes (if provided)
    const wellnessNotesEl = document.getElementById('wellness-notes');
    if (wellnessNotesEl && wellnessNotesEl.value.trim()) {
        wellnessPayload.notes = wellnessNotesEl.value.trim();
        hasWellnessData = true;  // Ensure wellness is sent even if only notes filled
    }

    try {
        const requestBody = {
            themes: themes,
            notes: notes,
            challenge_accepted: challengeAccepted
        };

        // Include wellness data if any metrics were filled
        if (hasWellnessData) {
            requestBody.wellness = wellnessPayload;
        }

        const response = await fetch('/api/start-day', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

        const result = await response.json();

        if (result.success) {
            closeStartDayModal();
            showToast('Den naplánován!', 'success');

            // Refresh the page to update widgets
            setTimeout(() => {
                window.location.reload();
            }, 500);
        } else {
            showToast('Chyba při ukládání plánu.', 'error');
        }
    } catch (err) {
        console.error('Failed to save Start Day:', err);
        showToast('Chyba při ukládání plánu.', 'error');
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

        // Wellness notes character counter
        const wellnessNotesEl = document.getElementById('wellness-notes');
        const wellnessCountEl = document.getElementById('wellness-notes-count');
        if (wellnessNotesEl && wellnessCountEl) {
            wellnessNotesEl.addEventListener('input', () => {
                wellnessCountEl.textContent = wellnessNotesEl.value.length;
            });
        }

        // FocusAI suggestion is now loaded on-demand via button click
    }
});
