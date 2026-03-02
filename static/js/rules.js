// rules.js - Complete alert rules management

// Function to get CSRF token
function getCSRFToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) {
        return metaTag.getAttribute('content');
    }
    const formToken = document.querySelector('input[name="csrf_token"]');
    if (formToken) {
        return formToken.value;
    }
    return '';
}

// Device selection handler
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.device-select').forEach(radio => {
        radio.addEventListener('change', function() {
            try {
                const params = JSON.parse(this.dataset.params || "[]");
                const select = document.getElementById('parameterSelect');
                const section = document.getElementById('parameterSection');

                if (!select || !section) return;

                select.innerHTML = '<option value="">Select a parameter</option>';

                if (params.length === 0) {
                    const opt = document.createElement('option');
                    opt.value = '';
                    opt.textContent = 'No parameters available';
                    opt.disabled = true;
                    select.appendChild(opt);
                    section.style.display = 'block';
                    return;
                }

                params.forEach(param => {
                    const option = document.createElement('option');
                    option.value = param.id || param.parameter_id || '';
                    option.textContent = `${param.name || 'Parameter'}${param.unit ? ' (' + param.unit + ')' : ''}`;
                    select.appendChild(option);
                });

                section.style.display = 'block';
            } catch (e) {
                console.error('Error parsing device parameters:', e);
            }
        });
    });

    // Action toggle handler - FIXED for phone numbers
    document.querySelectorAll('.action-toggle').forEach(toggle => {
        // Set initial state on page load
        const actionType = toggle.value;
        const configId = actionType + 'Config';
        const configDiv = document.getElementById(configId);
        
        if (configDiv) {
            configDiv.style.display = toggle.checked ? 'block' : 'none';
            
            // Check SMS availability on page load if SMS is checked
            if (actionType === 'sms' && toggle.checked) {
                setTimeout(() => checkSMSAvailability(), 100); // Small delay to ensure DOM is ready
            }
        }
        
        // Add change handler
        toggle.addEventListener('change', function() {
            const actionType = this.value;
            const configId = actionType + 'Config';
            const configDiv = document.getElementById(configId);
            
            if (configDiv) {
                configDiv.style.display = this.checked ? 'block' : 'none';
                
                // If showing SMS config, check for active phone numbers
                if (actionType === 'sms' && this.checked) {
                    checkSMSAvailability();
                }
            }
        });
    });

    // Toggle rule status
    document.querySelectorAll('.toggle-status').forEach(toggle => {
        toggle.addEventListener('change', function() {
            const ruleId = this.dataset.ruleId;
            const enabled = this.checked;
            const originalState = !enabled;
            
            fetch('/alerts/toggle_rule', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({
                    rule_id: ruleId,
                    enabled: enabled
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showToast('Rule status updated successfully', 'success');
                    const label = this.nextElementSibling;
                    if (label) {
                        if (enabled) {
                            label.innerHTML = '<span class="badge bg-success">Enabled</span>';
                        } else {
                            label.innerHTML = '<span class="badge bg-secondary">Disabled</span>';
                        }
                    }
                } else {
                    showToast(data.message || 'Failed to update rule', 'error');
                    this.checked = originalState;
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showToast('Network error occurred', 'error');
                this.checked = originalState;
            });
        });
    });


    // Form validation for create rule
    const createForm = document.querySelector('form[action*="create_rule"]');
    if (createForm) {
        createForm.addEventListener('submit', function(e) {
            const deviceSelected = document.querySelector('input[name="device_id"]:checked');
            const parameterSelected = document.getElementById('parameterSelect')?.value;
            const actionsSelected = document.querySelectorAll('input[name="actions[]"]:checked');
            const smsSelected = document.querySelector('input[name="actions[]"][value="sms"]:checked');
            
            if (!deviceSelected) {
                e.preventDefault();
                showToast('Please select a device', 'warning');
                return;
            }
            
            if (!parameterSelected || parameterSelected === 'Select a parameter') {
                e.preventDefault();
                showToast('Please select a parameter', 'warning');
                return;
            }
            
            if (actionsSelected.length === 0) {
                e.preventDefault();
                showToast('Please select at least one action', 'warning');
                return;
            }
            
            // Validate SMS recipients if SMS is selected
            if (smsSelected) {
                const smsSelect = document.querySelector('select[name="sms_recipients[]"]');
                if (smsSelect) {
                    const selectedOptions = Array.from(smsSelect.selectedOptions || []);
                    
                    // Check if there are any phone numbers available at all
                    const availableOptions = Array.from(smsSelect.options).filter(opt => !opt.disabled && opt.value);
                    
                    if (availableOptions.length === 0) {
                        e.preventDefault();
                        showToast('No active phone numbers available. Please add phone numbers first.', 'warning');
                        return;
                    }
                    
                    if (selectedOptions.length === 0) {
                        e.preventDefault();
                        showToast('Please select at least one phone number for SMS notification', 'warning');
                        return;
                    }
                }
            }
            
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Creating...';
                submitBtn.disabled = true;
            }
        });
    }
    
    // Form validation for edit rule
    const editForm = document.getElementById('editRuleForm');
    if (editForm) {
        editForm.addEventListener('submit', function(e) {
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Saving...';
                submitBtn.disabled = true;
            }
        });
    }
    
    // Initialize custom SMS message toggle
    const customSMS = document.getElementById('customSMSMessage');
    if (customSMS) {
        customSMS.addEventListener('change', function() {
            const customText = document.querySelector('textarea[name="sms_custom_text"]');
            if (customText) {
                customText.style.display = this.checked ? 'block' : 'none';
            }
        });
    }
    
    // Check SMS availability on page load if SMS is checked
    const smsToggle = document.getElementById('enableSMS');
    if (smsToggle && smsToggle.checked) {
        setTimeout(() => checkSMSAvailability(), 100);
    }
});

// FIXED: Function to check SMS availability
function checkSMSAvailability() {
    const smsConfig = document.getElementById('smsConfig');
    if (!smsConfig) return false;
    
    const smsSelect = smsConfig.querySelector('select[name="sms_recipients[]"]');
    if (!smsSelect) return false;
    
    // Get all non-disabled options with values
    const activeOptions = Array.from(smsSelect.options).filter(opt => !opt.disabled && opt.value);
    
    if (activeOptions.length === 0) {
        showToast('No active phone numbers available. Please add phone numbers first.', 'warning');
        return false;
    }
    
    // Log for debugging
    console.log(`Found ${activeOptions.length} active phone numbers`);
    return true;
}

// Show edit rule modal
function showEditRuleModal(ruleId) {
    const modalElement = document.getElementById('editRuleModal');
    if (!modalElement) return;
    
    const modal = new bootstrap.Modal(modalElement);
    const contentDiv = document.getElementById('editRuleContent');
    const form = document.getElementById('editRuleForm');
    
    if (!contentDiv || !form) return;
    
    form.action = `/alerts/edit_rule/${ruleId}`;
    const ruleIdInput = document.getElementById('editRuleId');
    if (ruleIdInput) ruleIdInput.value = ruleId;
    
    contentDiv.innerHTML = `
        <div class="text-center">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-2">Loading rule data...</p>
        </div>
    `;
    
    fetch(`/alerts/api/get_rule/${ruleId}`, {
        headers: {
            'X-CSRFToken': getCSRFToken()
        }
    })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(rule => {
            // Build edit form
            let html = `
                <div class="row">
                    <div class="col-md-6 mb-3">
                        <label for="editRuleName" class="form-label">Rule Name *</label>
                        <input type="text" class="form-control" id="editRuleName" 
                               name="name" value="${escapeHtml(rule.name)}" required>
                    </div>
                    <div class="col-md-6 mb-3">
                        <label for="editRuleDescription" class="form-label">Description</label>
                        <textarea class="form-control" id="editRuleDescription" 
                                  name="description" rows="2">${escapeHtml(rule.description || '')}</textarea>
                    </div>
                </div>
                
                <div class="row">
                    <div class="col-md-4 mb-3">
                        <label for="editOperator" class="form-label">Operator *</label>
                        <select class="form-select" id="editOperator" name="operator" required>
                            <option value=">" ${rule.operator === '>' ? 'selected' : ''}>Greater Than (>)</option>
                            <option value="<" ${rule.operator === '<' ? 'selected' : ''}>Less Than (<)</option>
                            <option value=">=" ${rule.operator === '>=' ? 'selected' : ''}>Greater Than or Equal (>=)</option>
                            <option value="<=" ${rule.operator === '<=' ? 'selected' : ''}>Less Than or Equal (<=)</option>
                            <option value="==" ${rule.operator === '==' ? 'selected' : ''}>Equals (==)</option>
                            <option value="!=" ${rule.operator === '!=' ? 'selected' : ''}>Not Equals (!=)</option>
                        </select>
                    </div>
                    <div class="col-md-4 mb-3">
                        <label for="editThreshold" class="form-label">Threshold Value *</label>
                        <input type="number" step="any" class="form-control" 
                               id="editThreshold" name="threshold" value="${escapeHtml(rule.threshold)}" required>
                    </div>
                    <div class="col-md-4 mb-3">
                        <label for="editCooldown" class="form-label">Cooldown (seconds)</label>
                        <input type="number" class="form-control" id="editCooldown" 
                               name="cooldown_seconds" value="${rule.cooldown_seconds || 300}" min="0">
                    </div>
                </div>
                
                <div class="mb-3">
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" 
                               name="enabled" id="editRuleEnabled" ${rule.enabled ? 'checked' : ''}>
                        <label class="form-check-label" for="editRuleEnabled">
                            Enable Rule
                        </label>
                    </div>
                </div>
                
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>
                    Device and parameter cannot be changed. Delete and recreate rule for different device/parameter.
                </div>
            `;
            
            contentDiv.innerHTML = html;
            modal.show();
        })
        .catch(error => {
            console.error('Error loading rule:', error);
            contentDiv.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    Failed to load rule data. Please try again.
                    <div class="mt-2 small">${error.message}</div>
                </div>
            `;
            modal.show();
        });
}

// Helper function to escape HTML
function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return String(unsafe)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Test rule function
function testRule(ruleId) {
    const modalElement = document.getElementById('testRuleModal');
    if (!modalElement) return;
    
    const modal = new bootstrap.Modal(modalElement);
    const resultDiv = document.getElementById('testResult');
    const spinner = document.getElementById('testSpinner');
    
    if (!resultDiv || !spinner) return;
    
    resultDiv.innerHTML = `
        <p>Testing rule #${ruleId}...</p>
        <p class="text-muted small">This will check if the rule would trigger with current conditions.</p>
    `;
    spinner.style.display = 'block';
    
    fetch(`/alerts/test_rule/${ruleId}`, {
        headers: {
            'X-CSRFToken': getCSRFToken()
        }
    })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            spinner.style.display = 'none';
            if (data.success) {
                if (data.should_trigger) {
                    resultDiv.innerHTML = `
                        <div class="alert alert-success">
                            <h6><i class="fas fa-check-circle me-2"></i>Test Successful</h6>
                            <p>Rule would trigger with current conditions.</p>
                            <hr>
                            <div class="mt-2">
                                <p><strong>Current Value:</strong> ${escapeHtml(data.current_value)}</p>
                                <p><strong>Threshold:</strong> ${escapeHtml(data.threshold)}</p>
                                <p><strong>Condition:</strong> ${escapeHtml(data.current_value)} ${escapeHtml(data.operator)} ${escapeHtml(data.threshold)}</p>
                                ${data.actions ? `<p><strong>Actions:</strong> ${escapeHtml(data.actions.join(', '))}</p>` : ''}
                            </div>
                        </div>
                    `;
                } else {
                    resultDiv.innerHTML = `
                        <div class="alert alert-warning">
                            <h6><i class="fas fa-info-circle me-2"></i>Test Result</h6>
                            <p>Rule would not trigger with current conditions.</p>
                            <hr>
                            <div class="mt-2">
                                <p><strong>Current Value:</strong> ${escapeHtml(data.current_value)}</p>
                                <p><strong>Threshold:</strong> ${escapeHtml(data.threshold)}</p>
                                <p><strong>Condition:</strong> ${escapeHtml(data.current_value)} ${escapeHtml(data.operator)} ${escapeHtml(data.threshold)}</p>
                                <p class="mb-0 small">${escapeHtml(data.message || '')}</p>
                            </div>
                        </div>
                    `;
                }
            } else {
                resultDiv.innerHTML = `
                    <div class="alert alert-danger">
                        <h6><i class="fas fa-times-circle me-2"></i>Test Failed</h6>
                        <p>${escapeHtml(data.message || 'Error testing rule')}</p>
                    </div>
                `;
            }
        })
        .catch(error => {
            spinner.style.display = 'none';
            resultDiv.innerHTML = `
                <div class="alert alert-danger">
                    <h6><i class="fas fa-times-circle me-2"></i>Test Failed</h6>
                    <p>Network error: ${escapeHtml(error.message)}</p>
                </div>
            `;
        });
    
    modal.show();
}

// View logs function
function viewLogs(ruleId) {
    window.location.href = `/alerts/logs?rule_id=${ruleId}`;
}

// Delete rule function
function deleteRule(ruleId) {
    if (confirm('Are you sure you want to delete this alert rule? This action cannot be undone.')) {
        fetch(`/alerts/delete_rule/${ruleId}`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCSRFToken()
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                showToast('Rule deleted successfully', 'success');
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
            } else {
                showToast(data.message || 'Failed to delete rule', 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Network error occurred', 'error');
        });
    }
}

// Toast notification function
function showToast(message, type = 'info') {
    let toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toastContainer';
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        toastContainer.style.zIndex = '9999';
        document.body.appendChild(toastContainer);
    }
    
    const toastId = 'toast-' + Date.now();
    const bgClass = type === 'success' ? 'bg-success' : 
                    type === 'error' ? 'bg-danger' : 
                    type === 'warning' ? 'bg-warning' : 'bg-info';
    
    const icon = type === 'success' ? 'check-circle' : 
                 type === 'error' ? 'exclamation-circle' : 
                 type === 'warning' ? 'exclamation-triangle' : 'info-circle';
    
    const toastHtml = `
        <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas fa-${icon} me-2"></i>
                    ${escapeHtml(message)}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" 
                        data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    const toastEl = document.getElementById(toastId);
    if (toastEl) {
        const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
        toast.show();
        
        toastEl.addEventListener('hidden.bs.toast', function() {
            this.remove();
        });
    }
}