const SensorModelsApp = (function() {
  // Private variables
  let csrfToken = '';
  let sensorModels = [];
  let urls = {};
  let formChanged = false;
  let searchTimeout = null;
  let activeModal = null;

  // Public methods
  return {
    init: function(config) {
      csrfToken = config.csrfToken;
      sensorModels = config.sensorModelsJson || [];
      urls = config.urls;
      
      this.setupFormValidation();
      this.setupKeyboardShortcuts();
      this.setupModalListeners();
      
      console.log("Sensor Models application initialized");
    },

    // ---------- Setup Functions ----------
    setupFormValidation: function() {
      // Add model form
      const addForm = document.getElementById('add-model-form');
      if (addForm) {
        addForm.addEventListener('submit', (e) => {
          if (!this.validateForm(this)) {
            e.preventDefault();
            return false;
          }
          this.showLoading('add');
        });
      }

      // Edit model form
      const editForm = document.getElementById('edit-model-form');
      if (editForm) {
        editForm.addEventListener('submit', (e) => {
          if (!this.validateForm(this)) {
            e.preventDefault();
            return false;
          }
          this.showLoading('edit');
        });
      }

      // Track form changes for unsaved changes warning
      document.querySelectorAll('#edit-model-form input, #edit-model-form textarea').forEach(input => {
        input.addEventListener('input', () => formChanged = true);
      });
    },

    setupKeyboardShortcuts: function() {
      document.addEventListener('keydown', (e) => {
        // Ctrl+S to save in edit modal
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
          e.preventDefault();
          const editSubmit = document.querySelector('#edit-model-form button[type="submit"]');
          if (editSubmit) editSubmit.click();
        }

        // Escape to close modals
        if (e.key === 'Escape') {
          const modals = document.querySelectorAll('.modal.show');
          modals.forEach(modal => {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
          });
        }
      });
    },

    setupModalListeners: function() {
      // Reset form when modal closes
      document.getElementById('addModelModal').addEventListener('hidden.bs.modal', () => {
        this.resetForm('add');
        this.hideMessages();
      });

      document.getElementById('editModelModal').addEventListener('hidden.bs.modal', () => {
        formChanged = false;
        this.hideMessages();
      });

      // Reset parameter library search when modal closes
      document.getElementById('paramLibraryModal').addEventListener('hidden.bs.modal', () => {
        document.getElementById('library-search').value = '';
        this.filterParamLibrary();
      });

      // Pack parameters before form submissions
      document.getElementById('add-model-form').addEventListener('submit', () => {
        activeModal = 'add';
        this.packParameters();
      });

      document.getElementById('edit-model-form').addEventListener('submit', () => {
        activeModal = 'edit';
        this.packParameters();
      });
    },

    // ---------- Row Click Handler ----------
    handleRowClick: function(modelId) {
      this.handleEditClick(modelId);
    },

    // ---------- Edit/Delete Handlers ----------
    handleEditClick: function(modelId) {
      const model = sensorModels.find(m => m.id === modelId);

      if (model) {
        this.openEditModal(modelId, model);
      } else {
        // Fallback: fetch from server
        this.fetchModelData(modelId).then(data => {
          this.openEditModal(modelId, data);
        }).catch(err => {
          console.error('Failed to load model:', err);
          this.showError('Failed to load model data');
        });
      }
    },

    handleDeleteClick: function(modelId, modelName) {
      if (!confirm(`Delete model "${modelName}"?\n\nThis action cannot be undone.`)) {
        return;
      }

      this.showGlobalLoading(true);

      const url = urls.deleteModel.replace('/0', '/' + modelId);
      
      fetch(url, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken
        }
      })
      .then(resp => resp.json())
      .then(data => {
        if (data.success) {
          // Remove row from table
          const row = document.getElementById('model-row-' + modelId);
          if (row) row.remove();

          // Show success message
          this.showSuccess(data.message || 'Model deleted successfully');

          // Refresh page after delay
          setTimeout(() => location.reload(), 1500);
        } else {
          throw new Error(data.message || 'Failed to delete model');
        }
      })
      .catch(err => {
        console.error('Delete error:', err);
        this.showError('Error: ' + err.message);
      })
      .finally(() => {
        this.showGlobalLoading(false);
      });
    },

    async fetchModelData(modelId) {
      const response = await fetch(`/sensor-models/${modelId}/parameters`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    },

    // ---------- Validation ----------
    validateForm: function(form) {
      let isValid = true;
      const requiredFields = form.querySelectorAll('[required]');

      requiredFields.forEach(field => {
        field.classList.remove('is-invalid');
        if (!field.value.trim()) {
          field.classList.add('is-invalid');
          isValid = false;
        }
      });

      // Validate parameter table
      const mode = form.id.includes('add') ? 'add' : 'edit';
      const paramRows = this.collectParamsFromTable(mode);
      if (paramRows.length === 0) {
        this.showError('At least one parameter is required');
        isValid = false;
      }

      return isValid;
    },

    // ---------- Parameter Table Functions ----------
    addParamRow: function(mode, param) {
      const tableId = mode === 'edit' ? 'edit-params-table' : 'add-params-table';
      const tbody = document.querySelector(`#${tableId} tbody`);
      
      if (!tbody) {
        console.error(`Table body not found for ID: ${tableId}`);
        return null;
      }
      
      // Ensure we have a valid parameter object
      const p = param || { 
        parameter_name: '', 
        parameter_type: '', 
        unit: '', 
        mqtt_field_name: '' 
      };
      
      // Normalize the parameter names
      const normalizedParam = {
        parameter_name: p.parameter_name || p.name || '',
        parameter_type: p.parameter_type || p.sensor_type || '',
        unit: p.unit || '',
        mqtt_field_name: p.mqtt_field_name || p.mqtt_field || ''
      };
      
      // Create new row
      const newRow = document.createElement('tr');
      const isFirstRow = tbody.children.length === 0;
      
      newRow.innerHTML = `
        <td>
          <input type="text" class="form-control form-control-sm param-name" 
                 value="${this.escapeHtml(normalizedParam.parameter_name)}" 
                 placeholder="Parameter name" required>
        </td>
        <td>
          <input type="text" class="form-control form-control-sm param-type" 
                 value="${this.escapeHtml(normalizedParam.parameter_type)}" 
                 placeholder="Type">
        </td>
        <td>
          <input type="text" class="form-control form-control-sm param-unit" 
                 value="${this.escapeHtml(normalizedParam.unit)}" 
                 placeholder="Unit">
        </td>
        <td>
          <input type="text" class="form-control form-control-sm param-mqtt" 
                 value="${this.escapeHtml(normalizedParam.mqtt_field_name)}" 
                 placeholder="MQTT field">
        </td>
        <td class="text-center">
          <button type="button" class="btn btn-sm btn-outline-danger" 
                  onclick="SensorModelsApp.removeRow(this)" 
                  ${isFirstRow ? 'disabled title="At least one parameter required"' : ''}>
            <i class="bi bi-x"></i>
          </button>
        </td>
      `;
      
      tbody.appendChild(newRow);
      
      // Update delete button states
      this.updateDeleteButtonStates(mode);
      
      // Add highlight class
      newRow.classList.add('param-newly-inserted');
      setTimeout(() => {
        newRow.classList.remove('param-newly-inserted');
      }, 2000);
      
      return newRow;
    },

    removeRow: function(btn) {
      const tr = btn.closest('tr');
      const table = tr.closest('table');
      const mode = table.id.includes('edit') ? 'edit' : 'add';

      if (tr) {
        tr.remove();
        this.updateDeleteButtonStates(mode);
      }
    },

    updateDeleteButtonStates: function(mode) {
      const tableId = mode === 'edit' ? 'edit-params-table' : 'add-params-table';
      const rows = document.querySelectorAll(`#${tableId} tbody tr`);

      rows.forEach((row, index) => {
        const deleteBtn = row.querySelector('.btn-outline-danger');
        if (deleteBtn) {
          deleteBtn.disabled = rows.length === 1;
        }
      });
    },

    collectParamsFromTable: function(mode) {
      const tableId = mode === 'edit' ? 'edit-params-table' : 'add-params-table';
      const rows = document.querySelectorAll(`#${tableId} tbody tr`);
      const out = [];

      rows.forEach(row => {
        const nameInput = row.querySelector('.param-name');
        const name = nameInput ? nameInput.value.trim() : '';

        if (!name) return; // Skip empty rows

        const param = {
          parameter_name: name,
          parameter_type: (row.querySelector('.param-type')?.value.trim() || ''),
          unit: (row.querySelector('.param-unit')?.value.trim() || ''),
          mqtt_field_name: (row.querySelector('.param-mqtt')?.value.trim() || '')
        };
        out.push(param);
      });

      return out;
    },

    packParameters: function() {
      if (activeModal === 'add') {
        const arr = this.collectParamsFromTable('add');
        document.getElementById('add-parameters-json').value = JSON.stringify(arr);
      } else if (activeModal === 'edit') {
        const arr = this.collectParamsFromTable('edit');
        document.getElementById('edit-parameters-json').value = JSON.stringify(arr);
      }
    },

    // ---------- Model CRUD Operations ----------
    openEditModal: function(id, model) {
      activeModal = 'edit';
      const modalEl = document.getElementById('editModelModal');
      const editModal = new bootstrap.Modal(modalEl);

      // Set form values
      document.getElementById('edit-model-id').value = id;
      document.getElementById('edit-name').value = model.name || '';
      document.getElementById('edit-manufacturer').value = model.manufacturer || '';
      document.getElementById('edit-description').value = model.description || '';

      // Clear and populate parameter table
      const tbody = document.querySelector('#edit-params-table tbody');
      tbody.innerHTML = '';

      const params = Array.isArray(model.parameters) ? model.parameters : [];
      if (params.length > 0) {
        params.forEach((p) => {
          const pnorm = {
            parameter_name: p.parameter_name || p.name || '',
            parameter_type: p.parameter_type || p.type || '',
            unit: p.unit || '',
            mqtt_field_name: p.mqtt_field_name || p.mqtt_field || ''
          };
          this.addParamRow('edit', pnorm);
        });
      } else {
        this.addParamRow('edit');
      }

      // Set form action
      const baseAction = urls.editModel;
      document.getElementById('edit-model-form').action = baseAction.replace('/0', '/' + id);

      editModal.show();
    },

    // ---------- Parameter Library Functions ----------
    openParamLibrary: function() {
      activeModal = 'library';
      const modalEl = document.getElementById('paramLibraryModal');
      const modal = new bootstrap.Modal(modalEl);
      this.loadParamLibrary();
      modal.show();
    },

    async loadParamLibrary() {
      const tbody = document.getElementById('library-tbody');
      if (!tbody) return;

      tbody.innerHTML = '<tr><td colspan="5" class="text-center py-3"><div class="spinner-border spinner-border-sm"></div> Loading...</td></tr>';

      try {
        const resp = await fetch(urls.getParameters);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

        const data = await resp.json();
        const params = data.parameters || [];

        if (params.length === 0) {
          tbody.innerHTML = '<tr><td colspan="5" class="text-center py-3 text-muted">No parameters found. Create one above.</td></tr>';
          return;
        }

        // Clear and populate table
        tbody.innerHTML = '';

        params.forEach(p => {
          const tr = document.createElement('tr');
          tr.dataset.param = JSON.stringify(p);

          // Add click handler for row selection
          tr.onclick = (e) => {
            if (e.target.type !== 'checkbox') {
              const checkbox = tr.querySelector('.param-choose');
              if (checkbox) {
                checkbox.checked = !checkbox.checked;
                this.updateRowSelection(tr, checkbox.checked);
              }
            }
          };

          tr.innerHTML = `
            <td class="text-center">
              <input type="checkbox" class="form-check-input param-choose" 
                     onchange="SensorModelsApp.updateRowSelection(this.closest('tr'), this.checked)">
            </td>
            <td>${this.escapeHtml(p.name)}</td>
            <td><span class="badge bg-secondary">${this.escapeHtml(p.sensor_type || '—')}</span></td>
            <td>${this.escapeHtml(p.unit || '—')}</td>
            <td><code class="text-muted">${this.escapeHtml(p.mqtt_field_name || '—')}</code></td>
          `;
          tbody.appendChild(tr);
        });

        // Update select all checkbox
        this.updateSelectAllCheckbox();

      } catch (err) {
        console.error('Library load error:', err);
        tbody.innerHTML = `
          <tr><td colspan="5" class="text-center py-3 text-danger">
            <i class="bi bi-exclamation-triangle"></i> Error loading parameters: ${this.escapeHtml(err.message)}
          </td></tr>
        `;
      }
    },

    updateRowSelection: function(row, isSelected) {
      if (isSelected) {
        row.classList.add('param-selected');
      } else {
        row.classList.remove('param-selected');
      }
      this.updateSelectAllCheckbox();
    },

    updateSelectAllCheckbox: function() {
      const checkboxes = document.querySelectorAll('.param-choose');
      const selectAllCheckbox = document.getElementById('select-all-checkbox');
      if (checkboxes.length > 0) {
        const allChecked = Array.from(checkboxes).every(cb => cb.checked);
        selectAllCheckbox.checked = allChecked;
        selectAllCheckbox.indeterminate = !allChecked && Array.from(checkboxes).some(cb => cb.checked);
      }
    },

    toggleAllParams: function(checked) {
      document.querySelectorAll('.param-choose').forEach(cb => {
        cb.checked = checked;
        this.updateRowSelection(cb.closest('tr'), checked);
      });
    },

    selectAllParams: function() {
      document.querySelectorAll('.param-choose').forEach(cb => {
        cb.checked = true;
        this.updateRowSelection(cb.closest('tr'), true);
      });
      this.updateSelectAllCheckbox();
    },

    deselectAllParams: function() {
      document.querySelectorAll('.param-choose').forEach(cb => {
        cb.checked = false;
        this.updateRowSelection(cb.closest('tr'), false);
      });
      this.updateSelectAllCheckbox();
    },

    async createParameter() {
      const nameInput = document.getElementById('new-param-name');
      const typeInput = document.getElementById('new-param-type');
      const unitInput = document.getElementById('new-param-unit');
      const mqttInput = document.getElementById('new-param-mqtt');
      const btn = document.getElementById('create-param-btn');

      const name = nameInput.value.trim();
      if (!name) {
        nameInput.focus();
        this.showError('Parameter name is required');
        return;
      }

      btn.disabled = true;
      btn.querySelector('.spinner-border').classList.remove('d-none');

      try {
        const resp = await fetch(urls.createParameter, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
          },
          body: JSON.stringify({
            name: name,
            sensor_type: typeInput.value.trim(),
            unit: unitInput.value.trim(),
            mqtt_field_name: mqttInput.value.trim()
          })
        });

        const data = await resp.json();

        if (resp.ok) {
          // Clear inputs
          nameInput.value = '';
          typeInput.value = '';
          unitInput.value = '';
          mqttInput.value = '';

          // Insert into active table if a modal is open
          if (data.parameter) {
            this.insertParamObjectToActiveTable(data.parameter);
          }

          // Reload library to include new parameter
          await this.loadParamLibrary();

          this.showSuccess('Parameter created successfully');
        } else {
          throw new Error(data.error || 'Failed to create parameter');
        }
      } catch (err) {
        console.error('Create parameter error:', err);
        this.showError(err.message);
      } finally {
        btn.disabled = false;
        btn.querySelector('.spinner-border').classList.add('d-none');
      }
    },

    filterParamLibrary: function() {
      const searchTerm = document.getElementById('library-search').value.toLowerCase();
      const rows = document.querySelectorAll('#library-tbody tr');
      let visibleCount = 0;

      rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        const isVisible = text.includes(searchTerm);
        row.style.display = isVisible ? '' : 'none';
        if (isVisible) visibleCount++;
      });

      // Update select all checkbox
      this.updateSelectAllCheckbox();
    },

    insertSelectedParameters: function() {
      const checkboxes = document.querySelectorAll('.param-choose:checked');
      if (checkboxes.length === 0) {
        this.showError('Select at least one parameter to insert');
        return;
      }

      const btn = document.getElementById('insert-params-btn');
      const spinner = btn.querySelector('.spinner-border');
      btn.disabled = true;
      spinner.classList.remove('d-none');

      // Determine which modal is active
      let targetModal = this.getActiveModal();

      if (!targetModal) {
        this.showError('Please open Add or Edit Model modal first');
        btn.disabled = false;
        spinner.classList.add('d-none');
        return;
      }

      // Insert each selected parameter
      let insertedCount = 0;
      checkboxes.forEach(cb => {
        const row = cb.closest('tr');
        if (row && row.dataset.param) {
          try {
            const param = JSON.parse(row.dataset.param);
            const newRow = this.addParamRow(targetModal, param);
            
            if (newRow) {
              insertedCount++;
            }
            
          } catch (e) {
            console.error('Error parsing parameter:', e);
          }
        }
      });

      // Update UI
      btn.disabled = false;
      spinner.classList.add('d-none');

      if (insertedCount > 0) {
        // Close modal after a short delay
        setTimeout(() => {
          const modal = bootstrap.Modal.getInstance(document.getElementById('paramLibraryModal'));
          if (modal) modal.hide();

          // Show success message
          this.showSuccess(`Inserted ${insertedCount} parameter(s) successfully`);
          
          // Force scroll to parameter table
          setTimeout(() => {
            const tableId = targetModal === 'add' ? 'add-params-table' : 'edit-params-table';
            const table = document.getElementById(tableId);
            if (table) {
              table.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
          }, 100);
        }, 500);
      } else {
        this.showError('Failed to insert any parameters');
      }
    },

    insertParamObjectToActiveTable: function(param) {
      const targetModal = this.getActiveModal();
      if (targetModal) {
        this.addParamRow(targetModal, param);
      }
    },

    getActiveModal: function() {
      // Check which modal is currently visible
      const modals = [
        { id: 'addModelModal', name: 'add' },
        { id: 'editModelModal', name: 'edit' }
      ];
      
      for (const modal of modals) {
        const modalElement = document.getElementById(modal.id);
        if (modalElement && modalElement.classList.contains('show')) {
          return modal.name;
        }
      }
      
      return null;
    },

    // ---------- Search Debouncing ----------
    debounceSearch: function() {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        document.getElementById('search-form').submit();
      }, 500);
    },

    // ---------- UI Helpers ----------
    showGlobalLoading: function(show) {
      const overlay = document.getElementById('global-loading');
      if (overlay) overlay.style.display = show ? 'block' : 'none';
    },

    showLoading: function(type) {
      const spinner = document.getElementById(`${type}-loading-spinner`);
      const btnText = document.getElementById(`${type}-btn-text`);
      const submitBtn = document.getElementById(`${type}-submit-btn`);

      if (spinner) spinner.classList.remove('d-none');
      if (btnText) btnText.textContent = type === 'add' ? 'Adding...' : 'Saving...';
      if (submitBtn) submitBtn.disabled = true;
    },

    hideLoading: function(type) {
      const spinner = document.getElementById(`${type}-loading-spinner`);
      const btnText = document.getElementById(`${type}-btn-text`);
      const submitBtn = document.getElementById(`${type}-submit-btn`);

      if (spinner) spinner.classList.add('d-none');
      if (btnText) btnText.textContent = type === 'add' ? 'Add model' : 'Save changes';
      if (submitBtn) submitBtn.disabled = false;
    },

    showError: function(message) {
      const errorDiv = document.getElementById('form-errors');
      if (errorDiv) {
        errorDiv.innerHTML = `<i class="bi bi-exclamation-triangle"></i> ${this.escapeHtml(message)}`;
        errorDiv.classList.remove('d-none');

        // Auto-hide after 5 seconds
        setTimeout(() => errorDiv.classList.add('d-none'), 5000);
      }
    },

    showSuccess: function(message) {
      const successDiv = document.getElementById('form-success');
      if (successDiv) {
        successDiv.innerHTML = `<i class="bi bi-check-circle"></i> ${this.escapeHtml(message)}`;
        successDiv.classList.remove('d-none');

        // Auto-hide after 3 seconds
        setTimeout(() => successDiv.classList.add('d-none'), 3000);
      }
    },

    hideMessages: function() {
      ['form-errors', 'form-success'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('d-none');
      });
    },

    resetForm: function(type) {
      const form = document.getElementById(`${type}-model-form`);
      if (form) {
        form.reset();
        const tbody = document.querySelector(`#${type}-params-table tbody`);
        if (tbody) {
          tbody.innerHTML = '';
          this.addParamRow(type);
        }
      }
    },

    // ---------- Utility Functions ----------
    escapeHtml: function(str) {
      if (str == null) return '';
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML;
    }
  };
})();

// Make functions available globally for inline event handlers
window.handleRowClick = (modelId) => SensorModelsApp.handleRowClick(modelId);
window.handleEditClick = (modelId) => SensorModelsApp.handleEditClick(modelId);
window.handleDeleteClick = (modelId, modelName) => SensorModelsApp.handleDeleteClick(modelId, modelName);
window.addParamRow = (mode, param) => SensorModelsApp.addParamRow(mode, param);
window.removeRow = (btn) => SensorModelsApp.removeRow(btn);
window.openParamLibrary = () => SensorModelsApp.openParamLibrary();
window.filterParamLibrary = () => SensorModelsApp.filterParamLibrary();
window.createParameter = () => SensorModelsApp.createParameter();
window.insertSelectedParameters = () => SensorModelsApp.insertSelectedParameters();
window.toggleAllParams = (checked) => SensorModelsApp.toggleAllParams(checked);
window.selectAllParams = () => SensorModelsApp.selectAllParams();
window.deselectAllParams = () => SensorModelsApp.deselectAllParams();
window.updateRowSelection = (row, checked) => SensorModelsApp.updateRowSelection(row, checked);
window.debounceSearch = () => SensorModelsApp.debounceSearch();