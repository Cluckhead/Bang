/**
 * Analytics Debug Workstation - Main Controller
 * Handles the 6-panel functionality and API communication
 */

class DebugWorkstation {
    constructor() {
        this.currentSecurity = null;
        this.currentDate = null;
        this.rawData = null;
        this.calculationResults = null;
        this.vendorAnalytics = null;
        
        this.initializeEventListeners();
    }

    initializeEventListeners() {
        // Panel 1: Security Loading
        const loadBtn = document.getElementById('load-security-btn');
        if (loadBtn) {
            loadBtn.addEventListener('click', () => this.loadSecurity());
        }
        
        // Security Search
        this.initializeSecuritySearch();
        
        // Panel 2: Enhanced Data Tabs
        document.querySelectorAll('.data-tab').forEach(tab => {
            tab.addEventListener('click', (e) => this.switchDataTab(e.target.dataset.tab));
        });
        
        // Panel 3: Quick Diagnostics
        const smartDiagBtn = document.getElementById('smart-diagnosis-btn');
        if (smartDiagBtn) {
            smartDiagBtn.addEventListener('click', () => this.runSmartDiagnosis());
        }
        
        document.querySelectorAll('.quick-diag-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.runQuickDiagnostic(e.target.dataset.check));
        });
        
        // Panel 4: Sensitivity Analysis
        this.initializeSensitivityControls();
        
        // Panel 5: Goal Seek
        const targetAnalytic = document.getElementById('target-analytic');
        const goalSeekBtn = document.getElementById('run-goal-seek-btn');
        if (targetAnalytic) targetAnalytic.addEventListener('change', () => this.updateVendorValue());
        if (goalSeekBtn) goalSeekBtn.addEventListener('click', () => this.runEnhancedGoalSeek());
        
        const inputToChange = document.getElementById('input-to-change');
        if (inputToChange) {
            inputToChange.addEventListener('change', () => this.adjustInputRanges());
        }
        
        // Panel 6: Scenario Tabs  
        document.querySelectorAll('.scenario-tab').forEach(tab => {
            tab.addEventListener('click', (e) => this.switchScenarioTab(e.target.dataset.scenario));
        });
        
        // Scenario Builder
        document.querySelectorAll('.scenario-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.runScenario(e.target.dataset.scenarioType));
        });
        
        // Curve Tools
        const curveCheckboxes = ['show-our-curve', 'show-vendor-curve', 'show-shocked-curve'];
        curveCheckboxes.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('change', () => this.updateCurveChart());
            }
        });

        // Curve Analysis
        const curveAnalysisBtn = document.getElementById('run-curve-analysis-btn');
        if (curveAnalysisBtn) {
            curveAnalysisBtn.addEventListener('click', () => this.runCurveAnalysis());
        }
    }

    showStatus(message, isLoading = false) {
        const statusBar = document.getElementById('status-bar');
        const statusMessage = document.getElementById('status-message');
        const spinner = document.getElementById('loading-spinner');
        
        if (statusBar && statusMessage) {
            statusMessage.textContent = message;
            statusBar.classList.remove('hidden');
            
            if (spinner) {
                if (isLoading) {
                    spinner.classList.remove('hidden');
                } else {
                    spinner.classList.add('hidden');
                }
            }
        }
    }

    hideStatus() {
        const statusBar = document.getElementById('status-bar');
        if (statusBar) {
            statusBar.classList.add('hidden');
        }
    }

    updateHeaderInfo(isin, name, date) {
        const headerInfo = document.getElementById('header-security-info');
        const headerIsin = document.getElementById('header-isin');
        const headerName = document.getElementById('header-name');
        const headerDate = document.getElementById('header-date');
        
        if (headerInfo && headerIsin && headerName && headerDate) {
            headerIsin.textContent = isin || '-';
            headerName.textContent = name || '-';
            headerDate.textContent = date || '-';
            
            if (isin) {
                headerInfo.classList.remove('hidden');
            } else {
                headerInfo.classList.add('hidden');
            }
        }
    }

    // Methods to be implemented by specific modules
    initializeSecuritySearch() {
        // Import and initialize security search module
        if (window.SecuritySearch) {
            this.securitySearch = new window.SecuritySearch(this);
        }
    }

    initializeSensitivityControls() {
        // Import and initialize sensitivity analysis module
        if (window.SensitivityAnalysis) {
            this.sensitivityAnalysis = new window.SensitivityAnalysis(this);
        }
    }

    // Delegate to specific modules
    async loadSecurity() {
        if (this.securitySearch) {
            return await this.securitySearch.loadSecurity();
        }
    }

    switchDataTab(tabName) {
        if (this.dataInspector) {
            this.dataInspector.switchTab(tabName);
        }
    }

    async runSmartDiagnosis() {
        if (this.smartDiagnostics) {
            return await this.smartDiagnostics.runSmartDiagnosis();
        }
    }

    async runQuickDiagnostic(checkType) {
        if (this.smartDiagnostics) {
            return await this.smartDiagnostics.runQuickDiagnostic(checkType);
        }
    }

    updateVendorValue() {
        if (this.goalSeek) {
            this.goalSeek.updateVendorValue();
        }
    }

    adjustInputRanges() {
        if (this.goalSeek) {
            this.goalSeek.adjustInputRanges();
        }
    }

    async runEnhancedGoalSeek() {
        if (this.goalSeek) {
            return await this.goalSeek.runEnhancedGoalSeek();
        }
    }

    switchScenarioTab(scenarioName) {
        if (this.advancedTools) {
            this.advancedTools.switchTab(scenarioName);
        }
    }

    async runScenario(scenarioType) {
        if (this.advancedTools) {
            return await this.advancedTools.runScenario(scenarioType);
        }
    }

    updateCurveChart() {
        if (this.advancedTools) {
            this.advancedTools.updateCurveChart();
        }
    }

    async runCurveAnalysis() {
        if (this.advancedTools) {
            return await this.advancedTools.runCurveAnalysis();
        }
    }

    // Utility method for API calls
    async makeApiCall(endpoint, data = {}) {
        try {
            this.showStatus(`Calling ${endpoint}...`, true);
            
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            this.hideStatus();
            return result;

        } catch (error) {
            console.error('API call failed:', error);
            this.showStatus(`Error: ${error.message}`, false);
            throw error;
        }
    }

    // Method to select security from search (called by security search module)
    selectSecurityFromSearch(isin, name, currency) {
        const selectedIsin = document.getElementById('selected-security-isin');
        const searchInput = document.getElementById('security-search-input');
        const searchResults = document.getElementById('security-search-results');
        
        if (selectedIsin) selectedIsin.value = isin;
        if (searchInput) searchInput.value = `${isin} - ${name}`;
        if (searchResults) searchResults.classList.add('hidden');
        
        this.updateHeaderInfo(isin, name, null);
    }
}

// Make DebugWorkstation available globally
window.DebugWorkstation = DebugWorkstation;