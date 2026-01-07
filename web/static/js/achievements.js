/**
 * Achievements Page JavaScript
 * Handles filtering, sorting, and toast notifications
 */

class AchievementsPage {
    constructor() {
        this.cards = document.querySelectorAll('.achievement-card');
        this.filterTabs = document.querySelectorAll('.filter-tab');
        this.rarityFilters = document.querySelectorAll('.rarity-filter');
        this.categorySelect = document.getElementById('category-filter');
        this.emptyState = document.querySelector('.empty-state');
        this.grid = document.querySelector('.achievements-grid');

        this.currentFilter = 'all';
        this.currentRarity = 'all';
        this.currentCategory = 'all';

        this.init();
    }

    init() {
        this.bindFilterEvents();
        this.bindRarityEvents();
        this.bindCategoryEvents();
        this.updateVisibleCount();
    }

    bindFilterEvents() {
        this.filterTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                this.filterTabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                this.currentFilter = tab.dataset.filter;
                this.applyFilters();
            });
        });
    }

    bindRarityEvents() {
        this.rarityFilters.forEach(btn => {
            btn.addEventListener('click', () => {
                this.rarityFilters.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.currentRarity = btn.dataset.rarity;
                this.applyFilters();
            });
        });
    }

    bindCategoryEvents() {
        if (this.categorySelect) {
            this.categorySelect.addEventListener('change', () => {
                this.currentCategory = this.categorySelect.value;
                this.applyFilters();
            });
        }
    }

    applyFilters() {
        let visibleCount = 0;

        this.cards.forEach(card => {
            const isUnlocked = card.dataset.unlocked === 'true';
            const rarity = card.dataset.rarity;
            const category = card.dataset.category;
            const progress = parseInt(card.dataset.progress) || 0;

            let showByFilter = true;
            let showByRarity = true;
            let showByCategory = true;

            // Filter by status
            switch (this.currentFilter) {
                case 'unlocked':
                    showByFilter = isUnlocked;
                    break;
                case 'locked':
                    showByFilter = !isUnlocked;
                    break;
                case 'in-progress':
                    showByFilter = !isUnlocked && progress >= 50;
                    break;
                case 'all':
                default:
                    showByFilter = true;
            }

            // Filter by rarity
            if (this.currentRarity !== 'all') {
                showByRarity = rarity === this.currentRarity;
            }

            // Filter by category
            if (this.currentCategory !== 'all') {
                showByCategory = category === this.currentCategory;
            }

            // Apply visibility
            const shouldShow = showByFilter && showByRarity && showByCategory;
            card.style.display = shouldShow ? '' : 'none';

            if (shouldShow) {
                visibleCount++;
            }
        });

        // Show/hide empty state
        if (this.emptyState) {
            this.emptyState.style.display = visibleCount === 0 ? 'block' : 'none';
        }
        if (this.grid) {
            this.grid.style.display = visibleCount === 0 ? 'none' : 'grid';
        }
    }

    updateVisibleCount() {
        // Update filter tab counts dynamically
        const allCount = this.cards.length;
        const unlockedCount = document.querySelectorAll('.achievement-card[data-unlocked="true"]').length;
        const lockedCount = allCount - unlockedCount;
        const inProgressCount = document.querySelectorAll('.achievement-card.in-progress').length;

        // Update tab text if needed
        // (counts are already in the HTML from server-side rendering)
    }
}

/**
 * Global function to show achievement unlock toast
 * Can be called from anywhere (timer.js, socket events, etc.)
 */
window.showAchievementUnlockToast = function(achievement) {
    const container = document.getElementById('achievement-toast-container');
    if (!container) {
        console.warn('Achievement toast container not found');
        return;
    }

    const toast = document.createElement('div');
    toast.className = `achievement-toast ${achievement.rarity || ''}`;

    toast.innerHTML = `
        <span class="toast-icon">${achievement.icon || '🏆'}</span>
        <div class="toast-content">
            <div class="toast-title">Achievement odemcen!</div>
            <div class="toast-subtitle">${achievement.name || 'Achievement'}</div>
        </div>
        <span class="toast-points">+${achievement.points || 0} pts</span>
    `;

    container.appendChild(toast);

    // Play unlock sound if available
    playAchievementSound(achievement.rarity);

    // Remove toast after animation
    setTimeout(() => {
        if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
        }
    }, 5000);
};

/**
 * Play sound effect for achievement unlock
 */
function playAchievementSound(rarity) {
    // Use existing notification sound or create achievement-specific ones
    try {
        const soundMap = {
            'legendary': 'legendary-unlock.mp3',
            'epic': 'epic-unlock.mp3',
            'rare': 'achievement-unlock.mp3',
            'common': 'achievement-unlock.mp3'
        };

        const soundFile = soundMap[rarity] || 'achievement-unlock.mp3';
        const audio = new Audio(`/static/sounds/${soundFile}`);
        audio.volume = 0.5;
        audio.play().catch(() => {
            // Fallback to notification sound if specific sound doesn't exist
            const fallback = new Audio('/static/sounds/notification.mp3');
            fallback.volume = 0.3;
            fallback.play().catch(() => {});
        });
    } catch (e) {
        // Silently fail if audio is not supported
    }
}

/**
 * Fetch and check for new achievements
 */
async function checkForNewAchievements() {
    try {
        const response = await fetch('/api/achievements/check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            const data = await response.json();
            if (data.newly_unlocked && data.newly_unlocked.length > 0) {
                data.newly_unlocked.forEach(achievement => {
                    window.showAchievementUnlockToast(achievement);
                });
            }
        }
    } catch (error) {
        console.error('Failed to check achievements:', error);
    }
}

/**
 * Refresh achievements data from server
 */
async function refreshAchievements() {
    try {
        const response = await fetch('/api/achievements');
        if (response.ok) {
            const data = await response.json();
            // Could update UI dynamically here if needed
            return data.achievements;
        }
    } catch (error) {
        console.error('Failed to refresh achievements:', error);
    }
    return null;
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize if we're on the achievements page
    if (document.querySelector('.achievements-container')) {
        window.achievementsPage = new AchievementsPage();
    }
});

// Listen for achievement unlocks via WebSocket
if (typeof io !== 'undefined') {
    document.addEventListener('DOMContentLoaded', () => {
        // Socket might be initialized by timer.js
        // We'll add listener there instead to avoid duplicate connections
    });
}
