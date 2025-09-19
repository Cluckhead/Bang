# PowerShell script to update imports in test files

# Get all Python files in the current directory
$files = Get-ChildItem -Path . -Filter "*.py" -File

Write-Host "Found $($files.Count) Python files to update"

$updatedFiles = @()

foreach ($file in $files) {
    Write-Host "Processing: $($file.Name)"
    
    $content = Get-Content $file.FullName -Raw
    $originalContent = $content
    
    # 1. Replace 'from config import' with 'from core.config import'
    $content = $content -replace 'from config import', 'from core.config import'
    
    # 2. Replace 'import config' with 'from core import config'
    $content = $content -replace '^import config$', 'from core import config'
    $content = $content -replace '\nimport config$', "`nfrom core import config"
    
    # 3. Replace imports from core modules
    $content = $content -replace 'from utils import', 'from core.utils import'
    $content = $content -replace '^import utils$', 'from core import utils'
    $content = $content -replace '\nimport utils$', "`nfrom core import utils"
    
    $content = $content -replace 'from data_utils import', 'from core.data_utils import'
    $content = $content -replace '^import data_utils$', 'from core import data_utils'
    $content = $content -replace '\nimport data_utils$', "`nfrom core import data_utils"
    
    $content = $content -replace 'from data_loader import', 'from core.data_loader import'
    $content = $content -replace '^import data_loader$', 'from core import data_loader'
    $content = $content -replace '\nimport data_loader$', "`nfrom core import data_loader"
    
    $content = $content -replace 'from settings_loader import', 'from core.settings_loader import'
    $content = $content -replace '^import settings_loader$', 'from core import settings_loader'
    $content = $content -replace '\nimport settings_loader$', "`nfrom core import settings_loader"
    
    $content = $content -replace 'from io_lock import', 'from core.io_lock import'
    $content = $content -replace '^import io_lock$', 'from core import io_lock'
    $content = $content -replace '\nimport io_lock$', "`nfrom core import io_lock"
    
    $content = $content -replace 'from navigation_config import', 'from core.navigation_config import'
    $content = $content -replace '^import navigation_config$', 'from core import navigation_config'
    $content = $content -replace '\nimport navigation_config$', "`nfrom core import navigation_config"
    
    # 4. Replace imports from data_processing modules
    $content = $content -replace 'from preprocessing import', 'from data_processing.preprocessing import'
    $content = $content -replace '^import preprocessing$', 'from data_processing import preprocessing'
    $content = $content -replace '\nimport preprocessing$', "`nfrom data_processing import preprocessing"
    
    $content = $content -replace 'from data_validation import', 'from data_processing.data_validation import'
    $content = $content -replace '^import data_validation$', 'from data_processing import data_validation'
    $content = $content -replace '\nimport data_validation$', "`nfrom data_processing import data_validation"
    
    $content = $content -replace 'from data_audit import', 'from data_processing.data_audit import'
    $content = $content -replace '^import data_audit$', 'from data_processing import data_audit'
    $content = $content -replace '\nimport data_audit$', "`nfrom data_processing import data_audit"
    
    $content = $content -replace 'from curve_processing import', 'from data_processing.curve_processing import'
    $content = $content -replace '^import curve_processing$', 'from data_processing import curve_processing'
    $content = $content -replace '\nimport curve_processing$', "`nfrom data_processing import curve_processing"
    
    $content = $content -replace 'from price_matching_processing import', 'from data_processing.price_matching_processing import'
    $content = $content -replace '^import price_matching_processing$', 'from data_processing import price_matching_processing'
    $content = $content -replace '\nimport price_matching_processing$', "`nfrom data_processing import price_matching_processing"
    
    # 5. Replace imports from analytics modules
    $content = $content -replace 'from metric_calculator import', 'from analytics.metric_calculator import'
    $content = $content -replace '^import metric_calculator$', 'from analytics import metric_calculator'
    $content = $content -replace '\nimport metric_calculator$', "`nfrom analytics import metric_calculator"
    
    $content = $content -replace 'from security_processing import', 'from analytics.security_processing import'
    $content = $content -replace '^import security_processing$', 'from analytics import security_processing'
    $content = $content -replace '\nimport security_processing$', "`nfrom analytics import security_processing"
    
    $content = $content -replace 'from staleness_processing import', 'from analytics.staleness_processing import'
    $content = $content -replace '^import staleness_processing$', 'from analytics import staleness_processing'
    $content = $content -replace '\nimport staleness_processing$', "`nfrom analytics import staleness_processing"
    
    $content = $content -replace 'from maxmin_processing import', 'from analytics.maxmin_processing import'
    $content = $content -replace '^import maxmin_processing$', 'from analytics import maxmin_processing'
    $content = $content -replace '\nimport maxmin_processing$', "`nfrom analytics import maxmin_processing"
    
    $content = $content -replace 'from file_delivery_processing import', 'from analytics.file_delivery_processing import'
    $content = $content -replace '^import file_delivery_processing$', 'from analytics import file_delivery_processing'
    $content = $content -replace '\nimport file_delivery_processing$', "`nfrom analytics import file_delivery_processing"
    
    $content = $content -replace 'from issue_processing import', 'from analytics.issue_processing import'
    $content = $content -replace '^import issue_processing$', 'from analytics import issue_processing'
    $content = $content -replace '\nimport issue_processing$', "`nfrom analytics import issue_processing"
    
    $content = $content -replace 'from ticket_processing import', 'from analytics.ticket_processing import'
    $content = $content -replace '^import ticket_processing$', 'from analytics import ticket_processing'
    $content = $content -replace '\nimport ticket_processing$', "`nfrom analytics import ticket_processing"
    
    # Only write if content changed
    if ($content -ne $originalContent) {
        Set-Content -Path $file.FullName -Value $content -NoNewline
        Write-Host "  Updated: $($file.Name)"
        $updatedFiles += $file.Name
    } else {
        Write-Host "  No changes needed: $($file.Name)"
    }
}

Write-Host ""
Write-Host "Summary:"
Write-Host "  Total files processed: $($files.Count)"
Write-Host "  Files updated: $($updatedFiles.Count)"

if ($updatedFiles.Count -gt 0) {
    Write-Host "  Updated files:"
    foreach ($fileName in $updatedFiles) {
        Write-Host "    - $fileName"
    }
}