/**
 * Pomodoro Calendar - JavaScript Logic
 * Handles month/week views, daily focus, weekly planning, and weekly review
 */

class PomodoroCalendar {
    constructor() {
        this.currentDate = new Date();
        this.currentView = 'month'; // 'month' or 'week'
        this.selectedDate = null;
        this.calendarData = {};
        this.weeklyGoals = [];
        this.nextWeekGoals = [];
        this.focusThemes = []; // Current themes for the focus modal

        // Czech month names
        this.monthNames = [
            'Leden', 'Únor', 'Březen', 'Duben', 'Květen', 'Červen',
            'Červenec', 'Srpen', 'Září', 'Říjen', 'Listopad', 'Prosinec'
        ];

        // Czech day names
        this.dayNames = ['Ne', 'Po', 'Út', 'St', 'Čt', 'Pá', 'So'];
        this.dayNamesFull = ['Neděle', 'Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota'];

        this.init();
    }

    async init() {
        this.bindEvents();
        this.renderLegend();
        await this.loadTodayFocus();
        await this.loadCalendarData();
        this.render();
    }

    bindEvents() {
        // Navigation
        document.getElementById('prev-btn').addEventListener('click', () => this.navigate(-1));
        document.getElementById('next-btn').addEventListener('click', () => this.navigate(1));
        document.getElementById('today-btn').addEventListener('click', () => this.goToToday());

        // View toggle
        document.querySelectorAll('.view-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.switchView(e.target.dataset.view));
        });

        // Action buttons
        document.getElementById('plan-week-btn').addEventListener('click', () => this.openWeeklyPlanning());
        document.getElementById('review-btn').addEventListener('click', () => this.openWeeklyReview());
        document.getElementById('edit-today-focus').addEventListener('click', () => this.openFocusModal(this.formatDate(new Date())));

        // Focus Modal
        document.getElementById('close-focus-modal').addEventListener('click', () => this.closeFocusModal());
        document.getElementById('cancel-focus').addEventListener('click', () => this.closeFocusModal());
        document.getElementById('save-focus').addEventListener('click', () => this.saveFocus());
        document.getElementById('focus-notes').addEventListener('input', (e) => {
            document.getElementById('notes-count').textContent = e.target.value.length;
        });
        document.getElementById('add-theme-btn').addEventListener('click', () => this.addFocusTheme());
        document.getElementById('new-theme-select').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.addFocusTheme();
        });

        // Planning Modal
        document.getElementById('close-planning-modal').addEventListener('click', () => this.closePlanningModal());
        document.getElementById('cancel-planning').addEventListener('click', () => this.closePlanningModal());
        document.getElementById('save-planning').addEventListener('click', () => this.saveWeeklyPlan());
        document.getElementById('add-goal-btn').addEventListener('click', () => this.addWeeklyGoal());
        document.getElementById('new-goal-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.addWeeklyGoal();
        });

        // Review Modal
        document.getElementById('close-review-modal').addEventListener('click', () => this.closeReviewModal());
        document.getElementById('cancel-review').addEventListener('click', () => this.closeReviewModal());
        document.getElementById('save-review').addEventListener('click', () => this.saveWeeklyReview());
        document.getElementById('add-next-goal-btn').addEventListener('click', () => this.addNextWeekGoal());
        document.getElementById('new-next-goal-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.addNextWeekGoal();
        });

        // Close modals on overlay click
        document.querySelectorAll('.modal-overlay').forEach(overlay => {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    overlay.classList.add('hidden');
                }
            });
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                document.querySelectorAll('.modal-overlay').forEach(m => m.classList.add('hidden'));
                document.getElementById('confirm-dialog')?.classList.add('hidden');
            }
        });
    }

    // === Toast Notification System ===

    showToast(message, type = 'info', duration = 4000) {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || icons.info}</span>
            <span class="toast-message">${message}</span>
            <button class="toast-close">&times;</button>
        `;

        // Close button handler
        toast.querySelector('.toast-close').addEventListener('click', () => {
            this.dismissToast(toast);
        });

        container.appendChild(toast);

        // Auto-dismiss after duration
        if (duration > 0) {
            setTimeout(() => this.dismissToast(toast), duration);
        }

        return toast;
    }

    dismissToast(toast) {
        if (!toast || !toast.parentElement) return;

        toast.style.animation = 'toastSlideOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }

    // === Confirmation Dialog ===

    showConfirmDialog(options = {}) {
        return new Promise((resolve) => {
            const dialog = document.getElementById('confirm-dialog');
            const iconEl = document.getElementById('confirm-dialog-icon');
            const titleEl = document.getElementById('confirm-dialog-title');
            const messageEl = document.getElementById('confirm-dialog-message');
            const cancelBtn = document.getElementById('confirm-dialog-cancel');
            const confirmBtn = document.getElementById('confirm-dialog-confirm');

            // Set content
            iconEl.textContent = options.icon || '⚠️';
            titleEl.textContent = options.title || 'Potvrdit akci';
            messageEl.textContent = options.message || 'Opravdu chcete pokračovat?';
            cancelBtn.textContent = options.cancelText || 'Zrušit';
            confirmBtn.textContent = options.confirmText || 'Potvrdit';

            // Set button style
            confirmBtn.className = `btn ${options.danger ? 'btn-danger' : 'btn-primary'}`;

            const cleanup = () => {
                dialog.classList.add('hidden');
                cancelBtn.removeEventListener('click', handleCancel);
                confirmBtn.removeEventListener('click', handleConfirm);
                dialog.removeEventListener('click', handleOverlay);
            };

            const handleCancel = () => {
                cleanup();
                resolve(false);
            };

            const handleConfirm = () => {
                cleanup();
                resolve(true);
            };

            const handleOverlay = (e) => {
                if (e.target === dialog) {
                    handleCancel();
                }
            };

            cancelBtn.addEventListener('click', handleCancel);
            confirmBtn.addEventListener('click', handleConfirm);
            dialog.addEventListener('click', handleOverlay);

            dialog.classList.remove('hidden');
        });
    }

    // === Loading State Helpers ===

    setButtonLoading(button, isLoading) {
        if (!button) return;
        if (isLoading) {
            button.classList.add('loading');
            button.disabled = true;
        } else {
            button.classList.remove('loading');
            button.disabled = false;
        }
    }

    setModalLoading(modalBody, isLoading) {
        if (!modalBody) return;
        if (isLoading) {
            modalBody.classList.add('modal-loading');
        } else {
            modalBody.classList.remove('modal-loading');
        }
    }

    setCalendarLoading(isLoading) {
        const monthGrid = document.getElementById('calendar-grid');
        const weekGrid = document.getElementById('week-grid');

        if (isLoading) {
            monthGrid?.classList.add('loading');
            weekGrid?.classList.add('loading');
        } else {
            monthGrid?.classList.remove('loading');
            weekGrid?.classList.remove('loading');
        }
    }

    // === ML Insights Integration ===

    async fetchMLInsights(weekStart) {
        try {
            const response = await fetch(`/api/weekly-insights/${weekStart}`, {
                method: 'GET',
                headers: { 'Accept': 'application/json' }
            });

            if (!response.ok) {
                throw new Error(`ML service responded with ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.warn('ML insights unavailable:', error.message);
            // Return fallback data when ML service is unavailable
            return {
                predicted_sessions: null,
                recommended_focus: null,
                tip: 'ML service není dostupný.',
                productivity_trend: null
            };
        }
    }

    populateMLInsights(mlData) {
        const predictionEl = document.getElementById('ml-prediction');
        const recommendationEl = document.getElementById('ml-recommendation');
        const tipEl = document.getElementById('ml-tip');

        if (!mlData) {
            predictionEl.textContent = '-';
            recommendationEl.textContent = '-';
            tipEl.textContent = 'ML insights budou dostupné po nasbírání více dat.';
            return;
        }

        // Prediction
        if (mlData.predicted_sessions !== null && mlData.predicted_sessions !== undefined) {
            predictionEl.textContent = `${mlData.predicted_sessions} sessions`;
        } else {
            predictionEl.textContent = '-';
        }

        // Recommended focus
        if (mlData.recommended_focus) {
            const icon = window.APP_CONFIG.categoryIcons[mlData.recommended_focus] || '🎯';
            recommendationEl.innerHTML = `${icon} ${mlData.recommended_focus}`;
        } else {
            recommendationEl.textContent = '-';
        }

        // Tip
        if (mlData.tip) {
            tipEl.textContent = mlData.tip;
        } else {
            tipEl.textContent = 'Pokračuj ve sbírání dat pro personalizované insights.';
        }

        // Add trend indicator if available
        if (mlData.productivity_trend !== null && mlData.productivity_trend !== undefined) {
            const trendEl = document.querySelector('.ml-insights-section .insight-item:last-child .insight-text');
            if (trendEl && mlData.productivity_trend !== 0) {
                const trendIcon = mlData.productivity_trend > 0 ? '📈' : '📉';
                const trendText = mlData.productivity_trend > 0
                    ? `+${mlData.productivity_trend}%`
                    : `${mlData.productivity_trend}%`;
                tipEl.innerHTML = `${mlData.tip} <span class="ml-trend">${trendIcon} ${trendText}</span>`;
            }
        }
    }

    // === Navigation ===

    navigate(direction) {
        if (this.currentView === 'month') {
            this.currentDate.setMonth(this.currentDate.getMonth() + direction);
        } else {
            this.currentDate.setDate(this.currentDate.getDate() + (direction * 7));
        }
        this.loadCalendarData().then(() => this.render());
    }

    goToToday() {
        this.currentDate = new Date();
        this.loadCalendarData().then(() => {
            this.render();
            // Scroll to and highlight today's cell
            setTimeout(() => {
                const todayCell = document.querySelector('.day-cell.today');
                if (todayCell) {
                    todayCell.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    // Flash animation
                    todayCell.style.animation = 'pulse 0.5s ease';
                    setTimeout(() => todayCell.style.animation = '', 500);
                }
            }, 100);
        });
    }

    switchView(view) {
        this.currentView = view;
        document.querySelectorAll('.view-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.view === view);
        });
        this.render();
    }

    // === Data Loading ===

    async loadCalendarData() {
        this.setCalendarLoading(true);

        try {
            const year = this.currentDate.getFullYear();
            const month = this.currentDate.getMonth() + 1;

            // Load current month
            const response = await fetch(`/api/calendar/month/${year}/${month}`);
            const data = await response.json();

            this.calendarData = {};
            if (data.success) {
                data.days.forEach(day => {
                    this.calendarData[day.date] = day;
                });
            }

            // For week view, also load adjacent months if needed
            if (this.currentView === 'week') {
                const weekStart = this.getWeekStart(this.currentDate);
                const weekEnd = new Date(weekStart);
                weekEnd.setDate(weekEnd.getDate() + 6);

                // Check if week spans into previous month
                if (weekStart.getMonth() !== this.currentDate.getMonth()) {
                    const prevYear = weekStart.getFullYear();
                    const prevMonth = weekStart.getMonth() + 1;
                    const prevResponse = await fetch(`/api/calendar/month/${prevYear}/${prevMonth}`);
                    const prevData = await prevResponse.json();
                    if (prevData.success) {
                        prevData.days.forEach(day => {
                            this.calendarData[day.date] = day;
                        });
                    }
                }

                // Check if week spans into next month
                if (weekEnd.getMonth() !== this.currentDate.getMonth()) {
                    const nextYear = weekEnd.getFullYear();
                    const nextMonth = weekEnd.getMonth() + 1;
                    const nextResponse = await fetch(`/api/calendar/month/${nextYear}/${nextMonth}`);
                    const nextData = await nextResponse.json();
                    if (nextData.success) {
                        nextData.days.forEach(day => {
                            this.calendarData[day.date] = day;
                        });
                    }
                }
            }
        } catch (error) {
            console.error('Failed to load calendar data:', error);
            this.showToast('Chyba při načítání kalendáře', 'error');
        } finally {
            this.setCalendarLoading(false);
        }
    }

    async loadTodayFocus() {
        try {
            const response = await fetch('/api/focus/today');
            const data = await response.json();

            if (data.success && data.focus) {
                this.updateTodayBanner(data.focus);
            }
        } catch (error) {
            console.error('Failed to load today focus:', error);
        }
    }

    updateTodayBanner(focus) {
        const icon = document.getElementById('focus-icon');
        const theme = document.getElementById('focus-theme');
        const progress = document.getElementById('focus-progress');
        const fill = document.getElementById('focus-progress-fill');

        // Handle multiple themes
        const themes = focus.themes || [];
        if (themes.length > 0) {
            // Show first theme icon and combine names
            const firstTheme = themes[0].theme;
            icon.textContent = window.APP_CONFIG.categoryIcons[firstTheme] || '🎯';
            if (themes.length === 1) {
                theme.textContent = firstTheme;
            } else {
                const themeNames = themes.map(t => t.theme).join(', ');
                theme.textContent = themeNames;
            }
        } else if (focus.theme) {
            // Backward compatibility for old single theme
            icon.textContent = window.APP_CONFIG.categoryIcons[focus.theme] || '🎯';
            theme.textContent = focus.theme;
        } else {
            icon.textContent = '🎯';
            theme.textContent = 'Nenastaveno';
        }

        const actual = focus.actual_sessions || 0;
        const planned = focus.total_planned || focus.planned_sessions || 6;
        progress.textContent = `${actual}/${planned} sessions`;
        fill.style.width = `${Math.min((actual / planned) * 100, 100)}%`;
    }

    // === Rendering ===

    render() {
        this.updateTitle();

        if (this.currentView === 'month') {
            document.getElementById('month-view').classList.remove('hidden');
            document.getElementById('week-view').classList.add('hidden');
            this.renderMonthView();
        } else {
            document.getElementById('month-view').classList.add('hidden');
            document.getElementById('week-view').classList.remove('hidden');
            this.renderWeekView();
        }
    }

    updateTitle() {
        const title = document.getElementById('calendar-title');
        if (this.currentView === 'month') {
            title.textContent = `${this.monthNames[this.currentDate.getMonth()]} ${this.currentDate.getFullYear()}`;
        } else {
            const weekStart = this.getWeekStart(this.currentDate);
            const weekEnd = new Date(weekStart);
            weekEnd.setDate(weekEnd.getDate() + 6);
            title.textContent = `${weekStart.getDate()}. ${this.monthNames[weekStart.getMonth()]} - ${weekEnd.getDate()}. ${this.monthNames[weekEnd.getMonth()]} ${weekEnd.getFullYear()}`;
        }
    }

    renderMonthView() {
        const grid = document.getElementById('calendar-grid');
        grid.innerHTML = '';

        const year = this.currentDate.getFullYear();
        const month = this.currentDate.getMonth();

        // First day of month
        const firstDay = new Date(year, month, 1);
        // Last day of month
        const lastDay = new Date(year, month + 1, 0);

        // Start from Monday (adjust if first day is Sunday)
        let startDate = new Date(firstDay);
        const dayOfWeek = firstDay.getDay();
        const daysToSubtract = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
        startDate.setDate(startDate.getDate() - daysToSubtract);

        // Render 6 weeks (42 days)
        const today = this.formatDate(new Date());

        for (let i = 0; i < 42; i++) {
            const date = new Date(startDate);
            date.setDate(startDate.getDate() + i);

            const dateStr = this.formatDate(date);
            const dayData = this.calendarData[dateStr] || {};
            const isOtherMonth = date.getMonth() !== month;
            const isToday = dateStr === today;
            const hasFocus = (dayData.themes && dayData.themes.length > 0) || !!dayData.theme;

            const cell = document.createElement('div');
            cell.className = 'day-cell';
            if (isOtherMonth) cell.classList.add('other-month');
            if (isToday) cell.classList.add('today');
            if (hasFocus) cell.classList.add('has-focus');

            cell.innerHTML = this.renderDayCell(date.getDate(), dayData, isToday);
            cell.addEventListener('click', () => this.openFocusModal(dateStr));

            grid.appendChild(cell);
        }
    }

    renderDayCell(dayNum, data, isToday) {
        let html = `<span class="day-number">${dayNum}</span>`;

        // Handle multiple themes
        const themes = data.themes || [];
        const hasThemes = themes.length > 0 || data.theme;

        if (hasThemes) {
            // Show multiple theme icons
            if (themes.length > 0) {
                const icons = themes.slice(0, 3).map(t =>
                    window.APP_CONFIG.categoryIcons[t.theme] || '📌'
                ).join('');
                const names = themes.map(t => t.theme).join(', ');
                const displayName = themes.length > 1
                    ? `${themes.length} témata`
                    : themes[0].theme;
                html += `
                    <div class="day-theme">
                        <span class="theme-icon">${icons}</span>
                        <span class="theme-name" title="${names}">${displayName}</span>
                    </div>
                `;
            } else if (data.theme) {
                // Backward compatibility
                const icon = window.APP_CONFIG.categoryIcons[data.theme] || '📌';
                html += `
                    <div class="day-theme">
                        <span class="theme-icon">${icon}</span>
                        <span class="theme-name">${data.theme}</span>
                    </div>
                `;
            }

            const actual = data.actual_sessions || 0;
            const planned = data.total_planned || data.planned_sessions || 0;
            if (planned > 0) {
                const completed = actual >= planned;
                html += `<span class="day-sessions ${completed ? 'completed' : ''}">${actual}/${planned}</span>`;
            }

            if (data.productivity_score !== undefined && data.productivity_score > 0) {
                let level = 'low';
                if (data.productivity_score >= 70) level = 'high';
                else if (data.productivity_score >= 40) level = 'medium';
                html += `<span class="productivity-dot ${level}"></span>`;
            }
        }

        return html;
    }

    renderWeekView() {
        const grid = document.getElementById('week-grid');
        grid.innerHTML = '';

        const weekStart = this.getWeekStart(this.currentDate);
        const today = this.formatDate(new Date());

        for (let i = 0; i < 7; i++) {
            const date = new Date(weekStart);
            date.setDate(weekStart.getDate() + i);

            const dateStr = this.formatDate(date);
            const dayData = this.calendarData[dateStr] || {};
            const isToday = dateStr === today;

            const card = document.createElement('div');
            card.className = 'week-day-card';
            if (isToday) card.classList.add('today');

            card.innerHTML = this.renderWeekDayCard(date, dayData);
            card.addEventListener('click', () => this.openFocusModal(dateStr));

            grid.appendChild(card);
        }
    }

    renderWeekDayCard(date, data) {
        const dayName = this.dayNames[date.getDay()];
        const themes = data.themes || [];
        const actual = data.actual_sessions || 0;
        const planned = data.total_planned || data.planned_sessions || 6;
        const progress = Math.min((actual / planned) * 100, 100);

        // Get icons and names for themes
        let icon = '';
        let themeName = '';
        if (themes.length > 0) {
            icon = themes.slice(0, 3).map(t =>
                window.APP_CONFIG.categoryIcons[t.theme] || '📌'
            ).join('');
            themeName = themes.length > 1
                ? themes.map(t => t.theme).join(', ')
                : themes[0].theme;
        } else if (data.theme) {
            // Backward compatibility
            icon = window.APP_CONFIG.categoryIcons[data.theme] || '📌';
            themeName = data.theme;
        }

        const hasTheme = themes.length > 0 || data.theme;

        return `
            <div class="week-day-header">
                <div>
                    <div class="week-day-name">${dayName}</div>
                    <div class="week-day-date">${date.getDate()}</div>
                </div>
                <span class="week-theme-icon">${icon}</span>
            </div>
            <div class="week-day-content">
                ${hasTheme ? `<div class="week-theme-name">${themeName}</div>` : '<div class="week-theme-name" style="color: var(--text-muted)">Bez tématu</div>'}
                <div class="week-sessions-info">
                    <span class="week-sessions-text">${actual}/${planned} sessions</span>
                    <div class="week-progress-bar">
                        <div class="week-progress-fill" style="width: ${progress}%"></div>
                    </div>
                </div>
                ${data.notes ? `<div class="week-notes">${data.notes}</div>` : ''}
            </div>
        `;
    }

    renderLegend() {
        const container = document.getElementById('legend-items');
        container.innerHTML = '';

        window.APP_CONFIG.categories.forEach(category => {
            const icon = window.APP_CONFIG.categoryIcons[category] || '📌';
            const color = window.APP_CONFIG.categoryColors[category] || '#94a3b8';

            const item = document.createElement('div');
            item.className = 'legend-item';
            item.innerHTML = `
                <span class="legend-color" style="background: ${color}"></span>
                <span>${icon} ${category}</span>
            `;
            container.appendChild(item);
        });
    }

    // === Daily Focus Modal ===

    async openFocusModal(dateStr) {
        this.selectedDate = dateStr;
        this.focusThemes = [];
        const modal = document.getElementById('focus-modal');

        // Update title
        const date = new Date(dateStr);
        const dayName = this.dayNamesFull[date.getDay()];
        const monthName = this.monthNames[date.getMonth()];
        document.getElementById('modal-date-title').textContent =
            `${dayName}, ${date.getDate()}. ${monthName.toLowerCase()} ${date.getFullYear()}`;

        // Load data
        try {
            const response = await fetch(`/api/focus/${dateStr}`);
            const data = await response.json();

            if (data.success && data.focus) {
                // Load themes array
                this.focusThemes = data.focus.themes || [];
                // Backward compatibility: convert old theme to themes array
                if (this.focusThemes.length === 0 && data.focus.theme) {
                    this.focusThemes = [{
                        theme: data.focus.theme,
                        planned_sessions: data.focus.planned_sessions || 6,
                        notes: ''
                    }];
                }

                document.getElementById('focus-notes').value = data.focus.notes || '';
                document.getElementById('notes-count').textContent = (data.focus.notes || '').length;

                // Show stats for past days
                const statsSection = document.getElementById('day-stats');
                if (dateStr < this.formatDate(new Date()) && data.focus.actual_sessions !== undefined) {
                    document.getElementById('stat-actual').textContent = data.focus.actual_sessions;
                    document.getElementById('stat-productivity').textContent =
                        `${data.focus.productivity_score || 0}%`;
                    statsSection.classList.remove('hidden');
                } else {
                    statsSection.classList.add('hidden');
                }
            } else {
                // Reset form
                this.focusThemes = [];
                document.getElementById('focus-notes').value = '';
                document.getElementById('notes-count').textContent = '0';
                document.getElementById('day-stats').classList.add('hidden');
            }
        } catch (error) {
            console.error('Failed to load focus data:', error);
            this.focusThemes = [];
        }

        // Reset add theme form
        document.getElementById('new-theme-select').value = '';
        document.getElementById('new-theme-sessions').value = 1;

        this.renderFocusThemes();
        modal.classList.remove('hidden');
    }

    renderFocusThemes() {
        const container = document.getElementById('focus-themes-list');
        container.innerHTML = '';

        if (this.focusThemes.length === 0) {
            container.innerHTML = '<div class="themes-empty">Zatím žádná témata. Přidej téma níže.</div>';
            return;
        }

        this.focusThemes.forEach((themeData, index) => {
            const icon = window.APP_CONFIG.categoryIcons[themeData.theme] || '📌';
            const item = document.createElement('div');
            item.className = 'theme-item';
            item.innerHTML = `
                <span class="theme-item-icon">${icon}</span>
                <div class="theme-item-info">
                    <div class="theme-item-name">${themeData.theme}</div>
                    <div class="theme-item-sessions">${themeData.planned_sessions} sessions</div>
                </div>
                <button class="theme-item-delete" data-index="${index}" title="Odebrat">&times;</button>
            `;
            item.querySelector('.theme-item-delete').addEventListener('click', () => {
                this.removeFocusTheme(index);
            });
            container.appendChild(item);
        });
    }

    addFocusTheme() {
        const select = document.getElementById('new-theme-select');
        const sessionsInput = document.getElementById('new-theme-sessions');

        const theme = select.value;
        const sessions = parseInt(sessionsInput.value) || 1;

        if (!theme) {
            return;
        }

        // Check if theme already exists
        const exists = this.focusThemes.some(t => t.theme === theme);
        if (exists) {
            this.showToast(`Téma "${theme}" už je přidané.`, 'warning');
            return;
        }

        this.focusThemes.push({
            theme: theme,
            planned_sessions: sessions,
            notes: ''
        });

        // Reset form
        select.value = '';
        sessionsInput.value = 1;

        this.renderFocusThemes();
    }

    async removeFocusTheme(index) {
        const theme = this.focusThemes[index];
        const confirmed = await this.showConfirmDialog({
            icon: '🗑️',
            title: 'Odebrat téma',
            message: `Opravdu chcete odebrat téma "${theme.theme}"?`,
            confirmText: 'Odebrat',
            danger: true
        });

        if (confirmed) {
            this.focusThemes.splice(index, 1);
            this.renderFocusThemes();
        }
    }

    closeFocusModal() {
        document.getElementById('focus-modal').classList.add('hidden');
        this.selectedDate = null;
        this.focusThemes = [];
    }

    async saveFocus() {
        if (!this.selectedDate) return;

        const saveBtn = document.getElementById('save-focus');
        this.setButtonLoading(saveBtn, true);

        const data = {
            date: this.selectedDate,
            themes: this.focusThemes,
            notes: document.getElementById('focus-notes').value
        };

        try {
            const response = await fetch('/api/focus', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (result.success) {
                this.closeFocusModal();
                this.showToast('Zaměření dne uloženo', 'success');
                await this.loadCalendarData();
                await this.loadTodayFocus();
                this.render();
            } else {
                this.showToast('Chyba při ukládání: ' + result.error, 'error');
            }
        } catch (error) {
            console.error('Failed to save focus:', error);
            this.showToast('Chyba při ukládání', 'error');
        } finally {
            this.setButtonLoading(saveBtn, false);
        }
    }

    // === Weekly Planning Modal ===

    async openWeeklyPlanning() {
        const modal = document.getElementById('planning-modal');
        const weekStart = this.getWeekStart(this.currentDate);
        const weekEnd = new Date(weekStart);
        weekEnd.setDate(weekEnd.getDate() + 6);

        // Update title
        document.getElementById('planning-week-title').textContent =
            `Plánování týdne: ${weekStart.getDate()}.-${weekEnd.getDate()}. ${this.monthNames[weekEnd.getMonth()].toLowerCase()} ${weekEnd.getFullYear()}`;

        // Load existing plan
        try {
            const response = await fetch(`/api/planning/week/${this.formatDate(weekStart)}`);
            const data = await response.json();

            this.weeklyGoals = (data.success && data.plan?.goals) ? [...data.plan.goals] : [];

            this.renderPlanningGrid(weekStart, data.success ? data.plan : null);
            this.renderWeeklyGoals();
        } catch (error) {
            console.error('Failed to load weekly plan:', error);
            this.weeklyGoals = [];
            this.renderPlanningGrid(weekStart, null);
            this.renderWeeklyGoals();
        }

        modal.classList.remove('hidden');
    }

    renderPlanningGrid(weekStart, plan) {
        const grid = document.getElementById('planning-week-grid');
        grid.innerHTML = '';

        const planDays = {};
        if (plan?.days) {
            plan.days.forEach(d => planDays[d.date] = d);
        }

        for (let i = 0; i < 7; i++) {
            const date = new Date(weekStart);
            date.setDate(weekStart.getDate() + i);
            const dateStr = this.formatDate(date);
            const dayPlan = planDays[dateStr] || {};

            const day = document.createElement('div');
            day.className = 'planning-day';
            day.innerHTML = `
                <div class="planning-day-name">${this.dayNames[date.getDay()]}</div>
                <div class="planning-day-date">${date.getDate()}</div>
                <select class="planning-theme-select" data-date="${dateStr}">
                    <option value="">-</option>
                    ${window.APP_CONFIG.categories.map(c =>
                        `<option value="${c}" ${dayPlan.theme === c ? 'selected' : ''}>${c}</option>`
                    ).join('')}
                </select>
                <input type="number" class="planning-sessions-input" data-date="${dateStr}"
                       min="1" max="20" value="${dayPlan.planned_sessions || 6}" placeholder="6">
            `;
            grid.appendChild(day);
        }
    }

    renderWeeklyGoals() {
        const container = document.getElementById('weekly-goals');
        container.innerHTML = '';

        this.weeklyGoals.forEach((goal, index) => {
            const item = document.createElement('div');
            item.className = 'goal-item';
            item.innerHTML = `
                <input type="checkbox" class="goal-checkbox">
                <span class="goal-text">${goal}</span>
                <button class="goal-delete" data-index="${index}">&times;</button>
            `;
            item.querySelector('.goal-delete').addEventListener('click', async () => {
                const confirmed = await this.showConfirmDialog({
                    icon: '🗑️',
                    title: 'Odebrat cíl',
                    message: `Opravdu chcete odebrat cíl "${goal}"?`,
                    confirmText: 'Odebrat',
                    danger: true
                });
                if (confirmed) {
                    this.weeklyGoals.splice(index, 1);
                    this.renderWeeklyGoals();
                }
            });
            container.appendChild(item);
        });
    }

    addWeeklyGoal() {
        const input = document.getElementById('new-goal-input');
        const goal = input.value.trim();
        if (goal) {
            this.weeklyGoals.push(goal);
            this.renderWeeklyGoals();
            input.value = '';
        }
    }

    closePlanningModal() {
        document.getElementById('planning-modal').classList.add('hidden');
    }

    async saveWeeklyPlan() {
        const saveBtn = document.getElementById('save-planning');
        this.setButtonLoading(saveBtn, true);

        const weekStart = this.getWeekStart(this.currentDate);

        // Collect days data
        const days = [];
        document.querySelectorAll('.planning-day').forEach(dayEl => {
            const select = dayEl.querySelector('.planning-theme-select');
            const input = dayEl.querySelector('.planning-sessions-input');

            days.push({
                date: select.dataset.date,
                theme: select.value,
                planned_sessions: parseInt(input.value) || 6
            });
        });

        const data = {
            week_start: this.formatDate(weekStart),
            days: days,
            goals: this.weeklyGoals
        };

        try {
            const response = await fetch('/api/planning/week', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (result.success) {
                this.closePlanningModal();
                this.showToast('Týdenní plán uložen', 'success');
                await this.loadCalendarData();
                await this.loadTodayFocus();
                this.render();
            } else {
                this.showToast('Chyba při ukládání: ' + result.error, 'error');
            }
        } catch (error) {
            console.error('Failed to save weekly plan:', error);
            this.showToast('Chyba při ukládání', 'error');
        } finally {
            this.setButtonLoading(saveBtn, false);
        }
    }

    // === Weekly Review Modal ===

    async openWeeklyReview() {
        const modal = document.getElementById('review-modal');
        const modalBody = modal.querySelector('.modal-body');

        // Get last completed week
        const today = new Date();
        const lastWeekStart = this.getWeekStart(today);
        lastWeekStart.setDate(lastWeekStart.getDate() - 7);
        const lastWeekEnd = new Date(lastWeekStart);
        lastWeekEnd.setDate(lastWeekEnd.getDate() + 6);

        const weekStartStr = this.formatDate(lastWeekStart);

        // Update title
        document.getElementById('review-week-title').textContent =
            `Weekly Review: ${lastWeekStart.getDate()}.${lastWeekStart.getMonth() + 1}. - ${lastWeekEnd.getDate()}.${lastWeekEnd.getMonth() + 1}.${lastWeekEnd.getFullYear()}`;

        // Show modal immediately with loading state
        modal.classList.remove('hidden');
        this.setModalLoading(modalBody, true);

        // Load review data and ML insights in parallel
        try {
            const [reviewResponse, mlData] = await Promise.all([
                fetch(`/api/review/week/${weekStartStr}`),
                this.fetchMLInsights(weekStartStr)
            ]);

            const reviewData = await reviewResponse.json();

            if (reviewData.success) {
                this.populateReviewData(reviewData.review, reviewData.stats);
            }

            // Populate ML insights (overrides any existing ml_insights from backend)
            this.populateMLInsights(mlData);

        } catch (error) {
            console.error('Failed to load weekly review:', error);
            this.showToast('Chyba při načítání review dat', 'error');
        } finally {
            this.setModalLoading(modalBody, false);
        }
    }

    populateReviewData(review, stats) {
        // Stats
        if (stats) {
            document.getElementById('review-total-sessions').textContent = stats.total_sessions || 0;
            document.getElementById('review-total-hours').textContent =
                `${(stats.total_hours || 0).toFixed(1)}h`;
            document.getElementById('review-completed').textContent =
                `${Math.round(stats.completed_ratio || 0)}%`;
            document.getElementById('review-productivity').textContent =
                `${Math.round(stats.avg_productivity || 0)}%`;

            document.getElementById('best-day').textContent = stats.best_day || '-';
            document.getElementById('week-trend').textContent = this.getTrendText(stats.trend);

            // Theme breakdown
            this.renderThemeBreakdown(stats.theme_breakdown || []);
        }

        // Reflections
        if (review?.reflections) {
            document.getElementById('what-worked').value = review.reflections.what_worked || '';
            document.getElementById('what-to-improve').value = review.reflections.what_to_improve || '';
            document.getElementById('lessons-learned').value = review.reflections.lessons_learned || '';
        } else {
            document.getElementById('what-worked').value = '';
            document.getElementById('what-to-improve').value = '';
            document.getElementById('lessons-learned').value = '';
        }

        // ML Insights
        if (review?.ml_insights) {
            document.getElementById('ml-prediction').textContent =
                `${review.ml_insights.predicted_sessions || '-'} sessions`;
            document.getElementById('ml-recommendation').textContent =
                review.ml_insights.recommended_focus || '-';
            document.getElementById('ml-tip').textContent =
                review.ml_insights.tip || 'Analyzuji data...';
        } else {
            document.getElementById('ml-prediction').textContent = '-';
            document.getElementById('ml-recommendation').textContent = '-';
            document.getElementById('ml-tip').textContent = 'ML insights budou dostupné po nasbírání více dat.';
        }

        // Next week goals
        this.nextWeekGoals = (review?.next_week_goals) ? [...review.next_week_goals] : [];
        this.renderNextWeekGoals();
    }

    getTrendText(trend) {
        if (!trend) return '-';
        if (trend > 0) return `↗️ Nahoru (+${trend}%)`;
        if (trend < 0) return `↘️ Dolů (${trend}%)`;
        return '→ Stabilní';
    }

    renderThemeBreakdown(breakdown) {
        const container = document.getElementById('theme-breakdown');
        container.innerHTML = '';

        if (breakdown.length === 0) {
            container.innerHTML = '<p style="color: var(--text-muted)">Žádná data pro tento týden</p>';
            return;
        }

        const maxSessions = Math.max(...breakdown.map(t => t.sessions));

        breakdown.forEach(theme => {
            const color = window.APP_CONFIG.categoryColors[theme.theme] || '#94a3b8';
            const width = (theme.sessions / maxSessions) * 100;

            const item = document.createElement('div');
            item.className = 'theme-bar-item';
            item.innerHTML = `
                <span class="theme-bar-name">${theme.theme}</span>
                <div class="theme-bar-container">
                    <div class="theme-bar-fill" style="width: ${width}%; background: ${color}"></div>
                </div>
                <span class="theme-bar-stats">${theme.sessions} ses. (${Math.round(theme.avg_rating || 0)}%)</span>
            `;
            container.appendChild(item);
        });
    }

    renderNextWeekGoals() {
        const container = document.getElementById('next-week-goals');
        container.innerHTML = '';

        this.nextWeekGoals.forEach((goal, index) => {
            const item = document.createElement('div');
            item.className = 'goal-item';
            item.innerHTML = `
                <input type="checkbox" class="goal-checkbox">
                <span class="goal-text">${goal}</span>
                <button class="goal-delete" data-index="${index}">&times;</button>
            `;
            item.querySelector('.goal-delete').addEventListener('click', async () => {
                const confirmed = await this.showConfirmDialog({
                    icon: '🗑️',
                    title: 'Odebrat cíl',
                    message: `Opravdu chcete odebrat cíl "${goal}"?`,
                    confirmText: 'Odebrat',
                    danger: true
                });
                if (confirmed) {
                    this.nextWeekGoals.splice(index, 1);
                    this.renderNextWeekGoals();
                }
            });
            container.appendChild(item);
        });
    }

    addNextWeekGoal() {
        const input = document.getElementById('new-next-goal-input');
        const goal = input.value.trim();
        if (goal) {
            this.nextWeekGoals.push(goal);
            this.renderNextWeekGoals();
            input.value = '';
        }
    }

    closeReviewModal() {
        document.getElementById('review-modal').classList.add('hidden');
    }

    async saveWeeklyReview() {
        const saveBtn = document.getElementById('save-review');
        this.setButtonLoading(saveBtn, true);

        const today = new Date();
        const lastWeekStart = this.getWeekStart(today);
        lastWeekStart.setDate(lastWeekStart.getDate() - 7);

        const data = {
            week_start: this.formatDate(lastWeekStart),
            reflections: {
                what_worked: document.getElementById('what-worked').value,
                what_to_improve: document.getElementById('what-to-improve').value,
                lessons_learned: document.getElementById('lessons-learned').value
            },
            next_week_goals: this.nextWeekGoals
        };

        try {
            const response = await fetch('/api/review/week', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (result.success) {
                this.closeReviewModal();
                this.showToast('Weekly Review úspěšně uložen', 'success');
            } else {
                this.showToast('Chyba při ukládání: ' + result.error, 'error');
            }
        } catch (error) {
            console.error('Failed to save weekly review:', error);
            this.showToast('Chyba při ukládání', 'error');
        } finally {
            this.setButtonLoading(saveBtn, false);
        }
    }

    // === Utilities ===

    formatDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    getWeekStart(date) {
        const d = new Date(date);
        const day = d.getDay();
        const diff = d.getDate() - day + (day === 0 ? -6 : 1); // Monday
        return new Date(d.setDate(diff));
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.calendar = new PomodoroCalendar();
});
