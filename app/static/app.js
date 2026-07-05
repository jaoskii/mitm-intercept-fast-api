// Mitmproxy Intercept Dashboard Logic

document.addEventListener('DOMContentLoaded', () => {
    // API State and Cache
    let rules = [];
    let logs = [];
    let editingRuleId = null;

    // DOM Elements
    const rulesList = document.getElementById('rules-list');
    const logsList = document.getElementById('logs-list');
    const ruleCount = document.getElementById('rule-count');
    const addRuleBtn = document.getElementById('add-rule-btn');
    const clearLogsBtn = document.getElementById('clear-logs-btn');

    // Rule Modal Elements
    const ruleModal = document.getElementById('rule-modal');
    const ruleForm = document.getElementById('rule-form');
    const modalTitle = document.getElementById('modal-title');
    const ruleIdInput = document.getElementById('rule-id');
    const ruleNameInput = document.getElementById('rule-name');
    const ruleMethodSelect = document.getElementById('rule-method');
    const ruleUrlInput = document.getElementById('rule-url');
    const ruleActionSelect = document.getElementById('rule-action');
    const cancelModalBtn = document.getElementById('cancel-modal-btn');
    const closeModalBtn = document.getElementById('close-modal-btn');

    // Log Detail Modal Elements
    const logModal = document.getElementById('log-modal');
    const closeLogModalBtn = document.getElementById('close-log-modal-btn');
    const detailMethod = document.getElementById('detail-method');
    const detailUrl = document.getElementById('detail-url');
    const detailTime = document.getElementById('detail-time');
    const detailIntercepted = document.getElementById('detail-intercepted');
    const detailAction = document.getElementById('detail-action');
    const detailActionContainer = document.getElementById('detail-action-container');
    const detailReqHeaders = document.getElementById('detail-req-headers');
    const detailReqBody = document.getElementById('detail-req-body');
    const detailResStatus = document.getElementById('detail-res-status');
    const detailResHeaders = document.getElementById('detail-res-headers');
    const detailResBody = document.getElementById('detail-res-body');

    // Action Input Field Containers
    const fields = {
        mock_response: [
            document.getElementById('field-status-code'),
            document.getElementById('field-response-body'),
            document.getElementById('field-headers-json')
        ],
        modify_request_headers: [
            document.getElementById('field-headers-json')
        ],
        modify_response_headers: [
            document.getElementById('field-headers-json')
        ],
        modify_response_body: [
            document.getElementById('field-body-rewrite')
        ],
        delay: [
            document.getElementById('field-delay')
        ]
    };

    // --- Tab Switcher Logic ---
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            btn.classList.add('active');
            const tabId = btn.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
        });
    });

    // --- Action Dropdown Handler ---
    ruleActionSelect.addEventListener('change', () => {
        const selectedAction = ruleActionSelect.value;
        
        // Hide all fields first
        Object.values(fields).flat().forEach(field => {
            if (field) field.style.display = 'none';
        });

        // Show fields associated with selected action
        if (fields[selectedAction]) {
            fields[selectedAction].forEach(field => {
                if (field) field.style.display = 'block';
            });
        }
    });

    // --- WebSocket Manager (with Auto Reconnect) ---
    let ws;
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/ws`;
        
        console.log(`Connecting to WebSocket: ${wsUrl}`);
        ws = new WebSocket(wsUrl);

        ws.onmessage = (event) => {
            try {
                const logData = JSON.parse(event.data);
                addLogEntryToTable(logData, true); // prepend
                logs.unshift(logData);
                if (logs.length > 150) {
                    logs.pop();
                    logsList.lastElementChild.remove();
                }
            } catch (err) {
                console.error("Error reading WebSocket payload:", err);
            }
        };

        ws.onclose = () => {
            console.log("WebSocket connection closed. Retrying in 3 seconds...");
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = (err) => {
            console.error("WebSocket error:", err);
            ws.close();
        };
    }

    // --- API Calls ---

    // Fetch and render Rules
    async function loadRules() {
        try {
            const res = await fetch('/api/rules');
            rules = await res.json();
            renderRules();
        } catch (err) {
            console.error("Failed to load rules:", err);
            rulesList.innerHTML = `<div class="empty-state-list"><i class="fa-solid fa-triangle-exclamation"></i><p>Error loading rules</p></div>`;
        }
    }

    // Fetch and render Logs
    async function loadLogs() {
        try {
            const res = await fetch('/api/logs');
            logs = await res.json();
            renderLogs();
        } catch (err) {
            console.error("Failed to load logs:", err);
        }
    }

    // Save or update a rule
    ruleForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const action = ruleActionSelect.value;
        const ruleData = {
            name: ruleNameInput.value,
            method: ruleMethodSelect.value,
            url_pattern: ruleUrlInput.value,
            action: action,
            is_active: 1,
            status_code: null,
            response_body: null,
            headers_json: null,
            body_search: null,
            body_replace: null,
            delay_seconds: null
        };

        // Populate fields based on action
        if (action === 'mock_response') {
            ruleData.status_code = parseInt(document.getElementById('rule-status-code').value) || 200;
            ruleData.response_body = document.getElementById('rule-response-body').value;
            ruleData.headers_json = document.getElementById('rule-headers-json').value;
        } else if (action === 'modify_request_headers' || action === 'modify_response_headers') {
            ruleData.headers_json = document.getElementById('rule-headers-json').value;
        } else if (action === 'modify_response_body') {
            ruleData.body_search = document.getElementById('rule-body-search').value;
            ruleData.body_replace = document.getElementById('rule-body-replace').value;
        } else if (action === 'delay') {
            ruleData.delay_seconds = parseFloat(document.getElementById('rule-delay').value) || 1.0;
        }

        try {
            let res;
            if (editingRuleId) {
                res = await fetch(`/api/rules/${editingRuleId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(ruleData)
                });
            } else {
                res = await fetch('/api/rules', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(ruleData)
                });
            }

            if (res.ok) {
                closeRuleModal();
                loadRules();
            } else {
                const errData = await res.json();
                alert(`Error saving rule: ${errData.detail || 'Unknown error'}`);
            }
        } catch (err) {
            console.error("Error submitting rule:", err);
            alert("Network error saving rule.");
        }
    });

    // Toggle rule active status
    async function handleToggleRule(ruleId, isActive) {
        try {
            const res = await fetch(`/api/rules/${ruleId}/toggle`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_active: isActive ? 1 : 0 })
            });
            if (res.ok) {
                // Update local state
                const r = rules.find(x => x.id === ruleId);
                if (r) r.is_active = isActive ? 1 : 0;
                updateActiveCount();
                
                // Toggle active card class
                const card = document.querySelector(`.rule-card[data-id="${ruleId}"]`);
                if (card) {
                    if (isActive) card.classList.add('active');
                    else card.classList.remove('active');
                }
            } else {
                alert("Failed to toggle rule.");
                loadRules(); // reload fallback
            }
        } catch (err) {
            console.error("Toggle error:", err);
        }
    }

    // Delete rule
    async function handleDeleteRule(ruleId) {
        if (!confirm("Are you sure you want to delete this interception rule?")) return;
        try {
            const res = await fetch(`/api/rules/${ruleId}`, { method: 'DELETE' });
            if (res.ok) {
                loadRules();
            } else {
                alert("Failed to delete rule.");
            }
        } catch (err) {
            console.error("Delete error:", err);
        }
    }

    // Clear all logs
    clearLogsBtn.addEventListener('click', async () => {
        if (!confirm("Are you sure you want to clear all history traffic logs?")) return;
        try {
            const res = await fetch('/api/logs', { method: 'DELETE' });
            if (res.ok) {
                logs = [];
                renderLogs();
            }
        } catch (err) {
            console.error("Clear logs error:", err);
        }
    });

    // --- Rendering Functions ---

    function updateActiveCount() {
        const activeCount = rules.filter(r => r.is_active === 1).length;
        ruleCount.textContent = `${activeCount} Active`;
    }

    function renderRules() {
        if (rules.length === 0) {
            rulesList.innerHTML = `
                <div class="empty-state-list">
                    <i class="fa-solid fa-code-fork"></i>
                    <p>No rules created yet. Click "Add Intercept Rule" to start intercepting traffic.</p>
                </div>
            `;
            updateActiveCount();
            return;
        }

        rulesList.innerHTML = '';
        rules.forEach(rule => {
            const card = document.createElement('div');
            card.className = `rule-card ${rule.is_active ? 'active' : ''}`;
            card.setAttribute('data-id', rule.id);

            // Format Action String
            const actionLabels = {
                mock_response: '<i class="fa-solid fa-circle-stop"></i> Mock Response',
                modify_request_headers: '<i class="fa-solid fa-arrow-right-to-bracket"></i> Modify Request Headers',
                modify_response_headers: '<i class="fa-solid fa-arrow-right-from-bracket"></i> Modify Response Headers',
                modify_response_body: '<i class="fa-solid fa-file-signature"></i> Rewrite Response Body',
                delay: '<i class="fa-solid fa-clock"></i> Latency Delay'
            };
            const actionText = actionLabels[rule.action] || rule.action;

            card.innerHTML = `
                <div class="rule-card-header">
                    <div class="rule-name" title="${escapeHtml(rule.name)}">${escapeHtml(rule.name)}</div>
                    <label class="switch">
                        <input type="checkbox" ${rule.is_active ? 'checked' : ''}>
                        <span class="slider"></span>
                    </label>
                </div>
                <div class="rule-card-pattern">
                    <span class="badge-method ${rule.method.toLowerCase()}">${escapeHtml(rule.method)}</span>
                    <span class="pattern-text" title="${escapeHtml(rule.url_pattern)}">${escapeHtml(rule.url_pattern)}</span>
                </div>
                <div class="rule-card-footer">
                    <div class="rule-action-label">${actionText}</div>
                    <div class="rule-actions-btns">
                        <button class="action-icon-btn btn-edit" title="Edit Rule"><i class="fa-solid fa-pen-to-square"></i></button>
                        <button class="action-icon-btn btn-delete" title="Delete Rule"><i class="fa-solid fa-trash-can"></i></button>
                    </div>
                </div>
            `;

            // Event Listeners
            const toggleCheckbox = card.querySelector('input[type="checkbox"]');
            toggleCheckbox.addEventListener('change', (e) => {
                handleToggleRule(rule.id, e.target.checked);
            });

            card.querySelector('.btn-edit').addEventListener('click', () => {
                openEditRuleModal(rule);
            });

            card.querySelector('.btn-delete').addEventListener('click', () => {
                handleDeleteRule(rule.id);
            });

            rulesList.appendChild(card);
        });

        updateActiveCount();
    }

    function renderLogs() {
        if (logs.length === 0) {
            logsList.innerHTML = `
                <tr class="empty-state">
                    <td colspan="6">
                        <div class="empty-message">
                            <i class="fa-solid fa-network-wired"></i>
                            <p>No traffic intercepted yet. Send requests through the proxy (port 8080).</p>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        logsList.innerHTML = '';
        logs.forEach(log => addLogEntryToTable(log, false)); // append
    }

    function addLogEntryToTable(log, prepend = false) {
        // Remove empty state if present
        const emptyRow = logsList.querySelector('.empty-state');
        if (emptyRow) emptyRow.remove();

        const tr = document.createElement('tr');
        if (log.intercepted) {
            tr.className = 'intercepted';
        }

        // Parse method class
        const methodClass = log.method.toLowerCase();
        
        // Host & Path parsing
        let displayUrl = log.url;
        try {
            const parsedUrl = new URL(log.url);
            displayUrl = `<strong>${parsedUrl.host}</strong>${parsedUrl.pathname}${parsedUrl.search}`;
        } catch(e) {}

        // Status code class
        let statusClass = 'success';
        if (log.response_status) {
            if (log.response_status >= 500) statusClass = 'error';
            else if (log.response_status >= 400) statusClass = 'warning';
            else if (log.response_status >= 300) statusClass = 'redirect';
        }
        if (log.action_taken === 'mock_response') statusClass = 'mocked';

        const statusDisplay = log.response_status ? log.response_status : (log.intercepted ? 'MOCKED' : 'PENDING');
        const actionDisplay = log.intercepted 
            ? `<span class="intercept-badge" title="${escapeHtml(log.rule_name || 'Intercept Rule')}">${escapeHtml(log.action_taken)}</span>` 
            : '<span class="log-action-cell">Passed Through</span>';

        tr.innerHTML = `
            <td><span class="badge-method ${methodClass}">${escapeHtml(log.method)}</span></td>
            <td class="log-url-cell">${displayUrl}</td>
            <td class="log-status-cell ${statusClass}">${statusDisplay}</td>
            <td>${actionDisplay}</td>
            <td class="time-cell">${log.timestamp || 'Just now'}</td>
            <td>
                <button class="btn btn-secondary btn-inspect" style="padding: 0.35rem 0.65rem; font-size: 0.75rem;">
                    <i class="fa-solid fa-eye"></i> Inspect
                </button>
            </td>
        `;

        tr.querySelector('.btn-inspect').addEventListener('click', () => {
            openLogDetailModal(log);
        });

        if (prepend && logsList.firstChild) {
            logsList.insertBefore(tr, logsList.firstChild);
        } else {
            logsList.appendChild(tr);
        }
    }

    // --- Modal Controls ---

    function openRuleModal(title = "Create Intercept Rule") {
        editingRuleId = null;
        ruleForm.reset();
        modalTitle.textContent = title;
        ruleActionSelect.dispatchEvent(new Event('change'));
        ruleModal.style.display = 'flex';
    }

    function openEditRuleModal(rule) {
        editingRuleId = rule.id;
        modalTitle.textContent = "Edit Intercept Rule";
        
        ruleNameInput.value = rule.name;
        ruleMethodSelect.value = rule.method;
        ruleUrlInput.value = rule.url_pattern;
        ruleActionSelect.value = rule.action;

        // Trigger change to display relevant fields
        ruleActionSelect.dispatchEvent(new Event('change'));

        // Populate values in action-specific fields
        if (rule.status_code) document.getElementById('rule-status-code').value = rule.status_code;
        if (rule.response_body) document.getElementById('rule-response-body').value = rule.response_body;
        if (rule.headers_json) document.getElementById('rule-headers-json').value = rule.headers_json;
        if (rule.body_search) document.getElementById('rule-body-search').value = rule.body_search;
        if (rule.body_replace) document.getElementById('rule-body-replace').value = rule.body_replace;
        if (rule.delay_seconds) document.getElementById('rule-delay').value = rule.delay_seconds;

        ruleModal.style.display = 'flex';
    }

    function closeRuleModal() {
        ruleModal.style.display = 'none';
        editingRuleId = null;
    }

    function openLogDetailModal(log) {
        // Method and URL header
        detailMethod.textContent = log.method;
        detailMethod.className = `badge-method ${log.method.toLowerCase()}`;
        detailUrl.textContent = log.url;
        detailTime.textContent = log.timestamp || 'Just now';
        
        // Intercept Status
        detailIntercepted.textContent = log.intercepted ? "Yes" : "No";
        detailIntercepted.style.color = log.intercepted ? "var(--danger)" : "var(--success)";
        
        if (log.intercepted) {
            detailActionContainer.style.display = 'inline-flex';
            detailAction.textContent = `${log.action_taken} (${log.rule_name || 'Rule #' + log.matched_rule_id})`;
        } else {
            detailActionContainer.style.display = 'none';
        }

        // Request Tab
        detailReqHeaders.textContent = formatJSONOrText(log.request_headers);
        detailReqBody.textContent = log.request_body ? log.request_body : '(Empty)';

        // Response Tab
        detailResStatus.textContent = log.response_status ? log.response_status : (log.intercepted ? 'Mocked Response' : 'Pending');
        detailResHeaders.textContent = log.response_headers ? formatJSONOrText(log.response_headers) : '(Empty)';
        detailResBody.textContent = log.response_body ? log.response_body : '(Empty)';

        // Set default active tab to Request
        tabBtns[0].click();

        logModal.style.display = 'flex';
    }

    function closeLogDetailModal() {
        logModal.style.display = 'none';
    }

    // --- Helper Utilities ---

    function formatJSONOrText(str) {
        if (!str) return "(Empty)";
        try {
            const obj = typeof str === 'string' ? JSON.parse(str) : str;
            return JSON.stringify(obj, null, 2);
        } catch (e) {
            return str;
        }
    }

    function escapeHtml(unsafe) {
        if (!unsafe) return "";
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Event Bindings for Modals
    addRuleBtn.addEventListener('click', () => openRuleModal());
    cancelModalBtn.addEventListener('click', closeRuleModal);
    closeModalBtn.addEventListener('click', closeRuleModal);
    closeLogModalBtn.addEventListener('click', closeLogDetailModal);

    // Close on outside click
    window.addEventListener('click', (e) => {
        if (e.target === ruleModal) closeRuleModal();
        if (e.target === logModal) closeLogDetailModal();
    });

    // --- Initializer ---
    loadRules();
    loadLogs();
    connectWebSocket();
});
