/**
 * Data Inspector Module
 * Handles raw data display and tab switching
 */

class DataInspector {
    constructor(workstation) {
        this.workstation = workstation;
        this.currentTab = 'market';
        this.initializeTabs();
    }

    initializeTabs() {
        document.querySelectorAll('.data-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                this.switchTab(e.target.dataset.tab);
            });
        });
    }

    switchTab(tabName) {
        // Update tab styling
        document.querySelectorAll('.data-tab').forEach(tab => {
            if (tab.dataset.tab === tabName) {
                tab.classList.add('border-blue-500', 'text-blue-600');
                tab.classList.remove('border-transparent', 'text-gray-500');
            } else {
                tab.classList.remove('border-blue-500', 'text-blue-600');
                tab.classList.add('border-transparent', 'text-gray-500');
            }
        });

        // Show/hide tab content
        document.querySelectorAll('.data-tab-content').forEach(content => {
            content.classList.add('hidden');
        });

        const targetContent = document.getElementById(`${tabName}-data-tab`);
        if (targetContent) {
            targetContent.classList.remove('hidden');
        }

        this.currentTab = tabName;

        // Load tab-specific data if needed
        this.loadTabData(tabName);
    }

    updateData(apiData) {
        this.rawData = apiData.raw_data;
        this.calculationResults = apiData.calculation_results;
        this.vendorAnalytics = apiData.vendor_analytics;

        // Update all tabs with new data
        this.updateMarketDataTab();
        this.updateCalculationsTab();
        this.updateVendorTab();
    }

    loadTabData(tabName) {
        switch (tabName) {
            case 'market':
                this.updateMarketDataTab();
                break;
            case 'calculations':
                this.updateCalculationsTab();
                break;
            case 'vendor':
                this.updateVendorTab();
                break;
        }
    }

    updateMarketDataTab() {
        if (!this.rawData) return;

        // Update summary fields
        this.updateMarketSummary();
        
        // Update market data table
        this.updateMarketDataTable();
    }

    updateMarketSummary() {
        const fields = [
            { id: 'market-clean-price', key: 'clean_price', format: this.formatPrice },
            { id: 'market-accrued', key: 'accrued_interest', format: this.formatPrice },
            { id: 'market-dirty-price', key: 'dirty_price', format: this.formatPrice },
            { id: 'market-coupon-rate', key: 'coupon_rate_pct', format: this.formatPercent }
        ];

        fields.forEach(field => {
            const element = document.getElementById(field.id);
            if (element && this.rawData) {
                const value = this.rawData[field.key];
                element.textContent = value !== undefined ? field.format(value) : '-';
            }
        });
    }

    updateMarketDataTable() {
        const tbody = document.getElementById('market-data-tbody');
        if (!tbody || !this.rawData) return;

        const marketFields = [
            { field: 'ISIN', value: this.rawData.isin, source: 'Static' },
            { field: 'Issue Date', value: this.rawData.issue_date, source: 'Static' },
            { field: 'Maturity Date', value: this.rawData.maturity_date, source: 'Static' },
            { field: 'First Coupon', value: this.rawData.first_coupon, source: 'Static' },
            { field: 'Day Basis', value: this.rawData.day_basis, source: 'Static' },
            { field: 'Coupon Frequency', value: this.rawData.coupon_frequency, source: 'Static' },
            { field: 'Clean Price', value: this.formatPrice(this.rawData.clean_price), source: 'Market' },
            { field: 'Accrued Interest', value: this.formatPrice(this.rawData.accrued_interest), source: 'Calculated' }
        ];

        const html = marketFields.map(item => `
            <tr class="hover:bg-gray-50">
                <td class="px-2 py-1 border-b text-sm">${item.field}</td>
                <td class="px-2 py-1 border-b text-sm font-mono">${item.value || '-'}</td>
                <td class="px-2 py-1 border-b text-xs text-gray-500">${item.source}</td>
            </tr>
        `).join('');

        tbody.innerHTML = html;
    }

    updateCalculationsTab() {
        const tbody = document.getElementById('calculations-tbody');
        if (!tbody || !this.calculationResults) return;

        const metrics = [
            { key: 'ytm_pct', label: 'YTM (%)', format: this.formatPercent },
            { key: 'z_spread_bps', label: 'Z-Spread (bps)', format: this.formatBps },
            { key: 'g_spread_bps', label: 'G-Spread (bps)', format: this.formatBps },
            { key: 'effective_duration', label: 'Effective Duration', format: this.formatDuration },
            { key: 'modified_duration', label: 'Modified Duration', format: this.formatDuration },
            { key: 'convexity', label: 'Convexity', format: this.formatNumber },
            { key: 'spread_duration', label: 'Spread Duration', format: this.formatDuration }
        ];

        const html = metrics.map(metric => {
            const ourValue = this.calculationResults.summary?.[metric.key];
            const vendorValue = this.vendorAnalytics?.[metric.key];
            
            const ourFormatted = ourValue !== undefined ? metric.format(ourValue) : '-';
            const vendorFormatted = vendorValue !== undefined ? metric.format(vendorValue) : '-';
            
            let difference = '-';
            let diffClass = '';
            
            if (ourValue !== undefined && vendorValue !== undefined) {
                const diff = ourValue - vendorValue;
                difference = metric.format(Math.abs(diff));
                if (diff > 0.001) diffClass = 'text-red-600';
                else if (diff < -0.001) diffClass = 'text-blue-600';
                else diffClass = 'text-green-600';
            }

            return `
                <tr class="hover:bg-gray-50">
                    <td class="px-2 py-1 border-b text-sm">${metric.label}</td>
                    <td class="px-2 py-1 border-b text-sm font-mono text-right">${ourFormatted}</td>
                    <td class="px-2 py-1 border-b text-sm font-mono text-right">${vendorFormatted}</td>
                    <td class="px-2 py-1 border-b text-sm font-mono text-right ${diffClass}">${difference}</td>
                </tr>
            `;
        }).join('');

        tbody.innerHTML = html;
    }

    updateVendorTab() {
        const tbody = document.getElementById('vendor-tbody');
        if (!tbody || !this.vendorAnalytics) return;

        const vendorData = Object.entries(this.vendorAnalytics).map(([key, value]) => {
            let unit = '';
            let formattedValue = value;
            
            if (key.includes('pct') || key.includes('yield')) {
                unit = '%';
                formattedValue = this.formatPercent(value);
            } else if (key.includes('bps') || key.includes('spread')) {
                unit = 'bps';
                formattedValue = this.formatBps(value);
            } else if (key.includes('duration')) {
                unit = 'years';
                formattedValue = this.formatDuration(value);
            } else if (typeof value === 'number') {
                formattedValue = this.formatNumber(value);
            }

            return {
                analytic: key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                value: formattedValue,
                unit: unit,
                source: 'Vendor'
            };
        });

        const html = vendorData.map(item => `
            <tr class="hover:bg-gray-50">
                <td class="px-2 py-1 border-b text-sm">${item.analytic}</td>
                <td class="px-2 py-1 border-b text-sm font-mono text-right">${item.value}</td>
                <td class="px-2 py-1 border-b text-xs text-gray-500">${item.unit}</td>
                <td class="px-2 py-1 border-b text-xs text-gray-500">${item.source}</td>
            </tr>
        `).join('');

        tbody.innerHTML = html;
    }

    // Formatting helpers
    formatPrice(value) {
        return typeof value === 'number' ? value.toFixed(4) : '-';
    }

    formatPercent(value) {
        return typeof value === 'number' ? value.toFixed(3) + '%' : '-';
    }

    formatBps(value) {
        return typeof value === 'number' ? value.toFixed(1) + ' bps' : '-';
    }

    formatDuration(value) {
        return typeof value === 'number' ? value.toFixed(2) : '-';
    }

    formatNumber(value) {
        return typeof value === 'number' ? value.toFixed(2) : '-';
    }
}

// Make DataInspector available globally
window.DataInspector = DataInspector;