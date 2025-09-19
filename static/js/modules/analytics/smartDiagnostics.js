/**
 * Smart Diagnostics Module
 * Handles diagnostic checks and automated issue detection
 */

class SmartDiagnostics {
    constructor(workstation) {
        this.workstation = workstation;
    }

    async runSmartDiagnosis() {
        if (!this.workstation.currentSecurity) {
            this.workstation.showStatus('Please load a security first', false);
            return;
        }

        try {
            const data = await this.workstation.makeApiCall('/bond/api/debug/smart_diagnosis', {
                isin: this.workstation.currentSecurity.isin,
                valuation_date: this.workstation.currentDate,
                raw_data: this.workstation.rawData,
                calculation_results: this.workstation.calculationResults
            });

            if (data.success) {
                this.displayDiagnosisResults(data.diagnosis);
                this.displayQuickFixes(data.suggested_fixes || []);
            } else {
                this.workstation.showStatus(`Diagnosis failed: ${data.message}`, false);
            }

        } catch (error) {
            console.error('Smart diagnosis failed:', error);
            this.workstation.showStatus('Smart diagnosis failed', false);
        }
    }

    async runQuickDiagnostic(checkType) {
        if (!this.workstation.currentSecurity) {
            this.workstation.showStatus('Please load a security first', false);
            return;
        }

        try {
            const data = await this.workstation.makeApiCall('/bond/api/debug/quick_diagnostic', {
                isin: this.workstation.currentSecurity.isin,
                valuation_date: this.workstation.currentDate,
                check_type: checkType
            });

            if (data.success) {
                this.displayQuickDiagnosticResult(checkType, data.result);
            } else {
                this.workstation.showStatus(`${checkType} check failed: ${data.message}`, false);
            }

        } catch (error) {
            console.error('Quick diagnostic failed:', error);
            this.workstation.showStatus(`${checkType} check failed`, false);
        }
    }

    displayDiagnosisResults(diagnosis) {
        const diagnosisResults = document.getElementById('diagnosis-results');
        const diagnosisContent = document.getElementById('diagnosis-content');

        if (diagnosisResults && diagnosisContent && diagnosis) {
            const html = this.formatDiagnosisResults(diagnosis);
            diagnosisContent.innerHTML = html;
            diagnosisResults.classList.remove('hidden');
        }
    }

    displayQuickFixes(fixes) {
        const quickFixes = document.getElementById('quick-fixes');
        const fixesContent = document.getElementById('fixes-content');

        if (quickFixes && fixesContent) {
            if (fixes.length > 0) {
                const html = fixes.map(fix => `
                    <button class="w-full text-left bg-yellow-50 hover:bg-yellow-100 border border-yellow-200 rounded p-2 text-sm"
                            onclick="window.debugWorkstation.applyQuickFix('${fix.fixId}')">
                        <div class="font-medium text-yellow-800">${fix.title}</div>
                        <div class="text-yellow-700 text-xs">${fix.description}</div>
                    </button>
                `).join('');
                fixesContent.innerHTML = html;
                quickFixes.classList.remove('hidden');
            } else {
                quickFixes.classList.add('hidden');
            }
        }
    }

    displayQuickDiagnosticResult(checkType, result) {
        const diagnosisResults = document.getElementById('diagnosis-results');
        const diagnosisContent = document.getElementById('diagnosis-content');

        if (diagnosisResults && diagnosisContent) {
            const html = this.formatQuickDiagnosticResult(checkType, result);
            diagnosisContent.innerHTML = html;
            diagnosisResults.classList.remove('hidden');
        }
    }

    formatDiagnosisResults(diagnosis) {
        const issues = diagnosis.issues || [];
        const warnings = diagnosis.warnings || [];
        const validations = diagnosis.validations || [];

        let html = '';

        if (issues.length > 0) {
            html += '<div class="mb-3"><h5 class="font-medium text-red-800 mb-1">Issues Found:</h5>';
            html += issues.map(issue => `
                <div class="text-red-700 text-xs mb-1">• ${issue}</div>
            `).join('');
            html += '</div>';
        }

        if (warnings.length > 0) {
            html += '<div class="mb-3"><h5 class="font-medium text-yellow-800 mb-1">Warnings:</h5>';
            html += warnings.map(warning => `
                <div class="text-yellow-700 text-xs mb-1">• ${warning}</div>
            `).join('');
            html += '</div>';
        }

        if (validations.length > 0) {
            html += '<div class="mb-3"><h5 class="font-medium text-green-800 mb-1">Validations Passed:</h5>';
            html += validations.map(validation => `
                <div class="text-green-700 text-xs mb-1">✓ ${validation}</div>
            `).join('');
            html += '</div>';
        }

        if (html === '') {
            html = '<div class="text-green-700 text-sm">All checks passed successfully!</div>';
        }

        return html;
    }

    formatQuickDiagnosticResult(checkType, result) {
        const checkNames = {
            'price_consistency': 'Price Consistency',
            'yield_validation': 'Yield Validation',
            'spread_analysis': 'Spread Analysis',
            'duration_check': 'Duration Check'
        };

        const checkName = checkNames[checkType] || checkType;
        
        let statusClass = 'text-green-700';
        let statusIcon = '✓';
        
        if (result.status === 'warning') {
            statusClass = 'text-yellow-700';
            statusIcon = '⚠';
        } else if (result.status === 'error') {
            statusClass = 'text-red-700';
            statusIcon = '✗';
        }

        let html = `
            <div class="mb-2">
                <h5 class="font-medium ${statusClass}">${statusIcon} ${checkName}</h5>
            </div>
        `;

        if (result.message) {
            html += `<div class="${statusClass} text-xs mb-2">${result.message}</div>`;
        }

        if (result.details && result.details.length > 0) {
            html += '<div class="text-xs space-y-1">';
            result.details.forEach(detail => {
                html += `<div class="text-gray-600">• ${detail}</div>`;
            });
            html += '</div>';
        }

        return html;
    }

    async applyQuickFix(fixId) {
        try {
            const data = await this.workstation.makeApiCall('/bond/api/debug/apply_fix', {
                isin: this.workstation.currentSecurity.isin,
                valuation_date: this.workstation.currentDate,
                fix_id: fixId
            });

            if (data.success) {
                this.workstation.showStatus('Quick fix applied successfully', false);
                // Refresh the security data
                if (this.workstation.securitySearch) {
                    await this.workstation.securitySearch.loadSecurity();
                }
            } else {
                this.workstation.showStatus(`Fix failed: ${data.message}`, false);
            }

        } catch (error) {
            console.error('Quick fix failed:', error);
            this.workstation.showStatus('Quick fix failed', false);
        }
    }
}

// Make SmartDiagnostics available globally
window.SmartDiagnostics = SmartDiagnostics;