/**
 * Settings Page - Category Management
 */

let categories = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadCategories();
});

async function loadCategories() {
    try {
        const response = await fetch('/api/config');
        const config = await response.json();
        categories = config.categories || [];
        renderCategories();
    } catch (err) {
        console.error('Failed to load categories:', err);
        showToast('Chyba pri nacitani kategorii', 'error');
    }
}

function renderCategories() {
    const list = document.getElementById('category-list');
    if (!list) return;

    list.innerHTML = categories.map(cat => `
        <div class="category-item" data-category="${escapeHtml(cat)}">
            <span class="category-name">${escapeHtml(cat)}</span>
            <div class="category-actions">
                <button onclick="editCategory('${escapeHtml(cat)}')" class="btn-edit" title="Upravit">&#9998;</button>
                <button onclick="deleteCategory('${escapeHtml(cat)}')" class="btn-delete" title="Smazat"
                        ${cat === 'Other' ? 'disabled' : ''}>&#10005;</button>
            </div>
        </div>
    `).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function addCategory() {
    const input = document.getElementById('new-category-input');
    const name = input.value.trim();

    if (!name) {
        showToast('Zadej nazev kategorie', 'warning');
        input.focus();
        return;
    }

    if (name.length > 50) {
        showToast('Nazev je prilis dlouhy (max 50 znaku)', 'warning');
        return;
    }

    if (categories.includes(name)) {
        showToast('Kategorie jiz existuje', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/categories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'add', name })
        });

        const result = await response.json();
        if (result.success) {
            categories = result.categories;
            renderCategories();
            input.value = '';
            showToast('Kategorie pridana', 'success');
        } else {
            showToast(result.error || 'Chyba pri pridavani', 'error');
        }
    } catch (err) {
        console.error('Add category failed:', err);
        showToast('Chyba pri pridavani kategorie', 'error');
    }
}

function editCategory(name) {
    document.getElementById('edit-original-name').value = name;
    document.getElementById('edit-category-input').value = name;
    document.getElementById('edit-category-modal').style.display = 'flex';
    document.getElementById('edit-category-input').focus();
    document.getElementById('edit-category-input').select();
}

function closeEditModal() {
    document.getElementById('edit-category-modal').style.display = 'none';
}

async function saveCategory() {
    const originalName = document.getElementById('edit-original-name').value;
    const newName = document.getElementById('edit-category-input').value.trim();

    if (!newName) {
        showToast('Nazev nesmi byt prazdny', 'warning');
        return;
    }

    if (newName.length > 50) {
        showToast('Nazev je prilis dlouhy (max 50 znaku)', 'warning');
        return;
    }

    if (newName === originalName) {
        closeEditModal();
        return;
    }

    if (categories.includes(newName)) {
        showToast('Kategorie s timto nazvem jiz existuje', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/categories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'rename',
                oldName: originalName,
                newName
            })
        });

        const result = await response.json();
        if (result.success) {
            categories = result.categories;
            renderCategories();
            closeEditModal();
            const msg = result.sessions_updated > 0
                ? `Kategorie prejmenovana (${result.sessions_updated} sessions aktualizovano)`
                : 'Kategorie prejmenovana';
            showToast(msg, 'success');
        } else {
            showToast(result.error || 'Chyba pri prejmenovani', 'error');
        }
    } catch (err) {
        console.error('Rename category failed:', err);
        showToast('Chyba pri prejmenovani kategorie', 'error');
    }
}

function deleteCategory(name) {
    if (name === 'Other') {
        showToast('Kategorii "Other" nelze smazat', 'warning');
        return;
    }

    document.getElementById('delete-category-name').textContent = name;

    // Populate reassign dropdown
    const select = document.getElementById('reassign-category');
    select.innerHTML = categories
        .filter(c => c !== name)
        .map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`)
        .join('');

    // Default to 'Other' if available
    if (categories.includes('Other')) {
        select.value = 'Other';
    }

    document.getElementById('delete-category-modal').style.display = 'flex';
}

function closeDeleteModal() {
    document.getElementById('delete-category-modal').style.display = 'none';
}

async function confirmDeleteCategory() {
    const name = document.getElementById('delete-category-name').textContent;
    const actionRadio = document.querySelector('input[name="delete-action"]:checked');
    const action = actionRadio ? actionRadio.value : 'reassign';
    const reassignTo = action === 'reassign'
        ? document.getElementById('reassign-category').value
        : null;

    try {
        const response = await fetch('/api/categories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'delete',
                name,
                reassignTo
            })
        });

        const result = await response.json();
        if (result.success) {
            categories = result.categories;
            renderCategories();
            closeDeleteModal();
            const msg = result.sessions_updated > 0
                ? `Kategorie smazana (${result.sessions_updated} sessions presunuto)`
                : 'Kategorie smazana';
            showToast(msg, 'success');
        } else {
            showToast(result.error || 'Chyba pri mazani', 'error');
        }
    } catch (err) {
        console.error('Delete category failed:', err);
        showToast('Chyba pri mazani kategorie', 'error');
    }
}

// Toast notification
function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
        success: '&#10003;',
        error: '&#10005;',
        warning: '&#9888;',
        info: '&#8505;'
    };

    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span class="toast-message">${escapeHtml(message)}</span>
    `;

    container.appendChild(toast);

    // Trigger animation
    setTimeout(() => toast.classList.add('show'), 10);

    // Remove after delay
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Close modals on escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeEditModal();
        closeDeleteModal();
    }
});

// Close modals when clicking outside
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        closeEditModal();
        closeDeleteModal();
    }
});
