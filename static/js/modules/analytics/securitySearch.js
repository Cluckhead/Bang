/**
 * Security Search Module
 * Handles security search and selection functionality
 */

class SecuritySearch {
    constructor(workstation) {
        this.workstation = workstation;
        this.searchTimeout = null;
        this.initializeSearch();
    }

    initializeSearch() {
        const searchInput = document.getElementById('security-search-input');
        const searchResults = document.getElementById('security-search-results');
        
        if (searchInput && searchResults) {
            searchInput.addEventListener('input', (e) => {
                const query = e.target.value.trim();
                
                // Clear previous timeout
                if (this.searchTimeout) {
                    clearTimeout(this.searchTimeout);
                }
                
                if (query.length < 2) {
                    searchResults.classList.add('hidden');
                    return;
                }
                
                // Debounce search
                this.searchTimeout = setTimeout(() => {
                    this.performSearch(query);
                }, 300);
            });

            // Hide results when clicking outside
            document.addEventListener('click', (e) => {
                if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
                    searchResults.classList.add('hidden');
                }
            });
        }
    }

    async performSearch(query) {
        try {
            const response = await fetch('/api/search-securities', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ query: query, limit: 10 })
            });

            if (response.ok) {
                const data = await response.json();
                this.displaySearchResults(data.results || []);
            }
        } catch (error) {
            console.error('Security search failed:', error);
        }
    }

    displaySearchResults(results) {
        const searchResults = document.getElementById('security-search-results');
        if (!searchResults) return;

        if (results.length === 0) {
            searchResults.innerHTML = '<div class="p-3 text-sm text-gray-500">No securities found</div>';
            searchResults.classList.remove('hidden');
            return;
        }

        const html = results.map(result => `
            <div class="p-2 hover:bg-gray-100 cursor-pointer border-b border-gray-100 last:border-b-0"
                 onclick="window.debugWorkstation.selectSecurityFromSearch('${result.isin}', '${result.security_name}', '${result.currency}')">
                <div class="font-medium text-sm">${result.isin}</div>
                <div class="text-xs text-gray-600">${result.security_name}</div>
                <div class="text-xs text-gray-500">${result.currency} • ${result.security_sub_type || 'N/A'}</div>
            </div>
        `).join('');

        searchResults.innerHTML = html;
        searchResults.classList.remove('hidden');
    }

    async loadSecurity() {
        const selectedIsin = document.getElementById('selected-security-isin');
        const valuationDate = document.getElementById('valuation-date');
        
        if (!selectedIsin || !selectedIsin.value.trim()) {
            this.workstation.showStatus('Please select a security first', false);
            return;
        }

        if (!valuationDate || !valuationDate.value) {
            this.workstation.showStatus('Please select a valuation date', false);
            return;
        }

        try {
            const data = await this.workstation.makeApiCall('/bond/api/debug/load_security', {
                isin: selectedIsin.value.trim(),
                valuation_date: valuationDate.value
            });

            if (data.success) {
                this.workstation.currentSecurity = data.security_data;
                this.workstation.currentDate = valuationDate.value;
                this.workstation.rawData = data.raw_data;
                this.workstation.calculationResults = data.calculation_results;
                this.workstation.vendorAnalytics = data.vendor_analytics;

                // Update UI
                this.updateSecurityInfo(data.security_data);
                this.updateAnalyticsComparison(data.calculation_results);
                this.workstation.updateHeaderInfo(
                    selectedIsin.value,
                    data.security_data?.name || '',
                    valuationDate.value
                );

                // Initialize other modules with loaded data
                if (this.workstation.dataInspector) {
                    this.workstation.dataInspector.updateData(data);
                }

                this.workstation.showStatus('Security loaded successfully', false);
                setTimeout(() => this.workstation.hideStatus(), 3000);

            } else {
                this.workstation.showStatus(`Error: ${data.message}`, false);
            }

        } catch (error) {
            console.error('Failed to load security:', error);
            this.workstation.showStatus('Failed to load security data', false);
        }
    }

    updateSecurityInfo(securityData) {
        const securityInfo = document.getElementById('security-info');
        const infoIsin = document.getElementById('info-isin');
        const infoCurrency = document.getElementById('info-currency');
        const infoName = document.getElementById('info-name');

        if (securityInfo && securityData) {
            if (infoIsin) infoIsin.textContent = securityData.isin || '-';
            if (infoCurrency) infoCurrency.textContent = securityData.currency || '-';
            if (infoName) infoName.textContent = securityData.name || '-';
            
            securityInfo.classList.remove('hidden');
        }
    }

    updateAnalyticsComparison(calculationResults) {
        const analyticsComparison = document.getElementById('analytics-comparison');
        const analyticsResults = document.getElementById('analytics-results');

        if (analyticsComparison && analyticsResults && calculationResults) {
            const html = this.formatAnalyticsResults(calculationResults);
            analyticsResults.innerHTML = html;
            analyticsComparison.classList.remove('hidden');
        }
    }

    formatAnalyticsResults(results) {
        const metrics = [
            { key: 'ytm_pct', label: 'YTM', unit: '%', decimals: 3 },
            { key: 'z_spread_bps', label: 'Z-Spread', unit: 'bps', decimals: 1 },
            { key: 'g_spread_bps', label: 'G-Spread', unit: 'bps', decimals: 1 },
            { key: 'effective_duration', label: 'Eff. Duration', unit: 'yrs', decimals: 2 },
            { key: 'modified_duration', label: 'Mod. Duration', unit: 'yrs', decimals: 2 },
            { key: 'convexity', label: 'Convexity', unit: '', decimals: 1 }
        ];

        return metrics.map(metric => {
            const ourValue = results.summary?.[metric.key];
            const vendorValue = results.vendor?.[metric.key];
            
            const ourFormatted = ourValue !== undefined ? 
                `${ourValue.toFixed(metric.decimals)}${metric.unit}` : '-';
            const vendorFormatted = vendorValue !== undefined ? 
                `${vendorValue.toFixed(metric.decimals)}${metric.unit}` : '-';

            return `
                <div class="flex justify-between items-center text-sm py-1">
                    <span class="font-medium">${metric.label}:</span>
                    <div class="flex space-x-4">
                        <span class="font-mono">${ourFormatted}</span>
                        <span class="text-gray-500 font-mono">(${vendorFormatted})</span>
                    </div>
                </div>
            `;
        }).join('');
    }
}

// Make SecuritySearch available globally
window.SecuritySearch = SecuritySearch;