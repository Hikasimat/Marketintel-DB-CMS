# ==============================================================================
# AWS Production Infrastructure Setup for PowerShell
# Repository: Hikasimat/Marketintel-DB-CMS
# ==============================================================================

param(
    [string]$AwsRegion = "ap-south-1",
    [string]$GitHubRepo = "Hikasimat/Marketintel-DB-CMS",
    [string]$AwsAccessKeyId = "",
    [string]$AwsSecretAccessKey = "",
    [string]$AwsSessionToken = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $scriptDir) {
    $scriptDir = Join-Path (Get-Location).Path "aws"
}
$iamDir = Join-Path $scriptDir "iam"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "[*] Initializing AWS Infrastructure for $GitHubRepo" -ForegroundColor Cyan
Write-Host "    Region: $AwsRegion" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# Step 0: Handle Credentials / Login
if (-not [string]::IsNullOrWhiteSpace($AwsAccessKeyId) -and -not [string]::IsNullOrWhiteSpace($AwsSecretAccessKey)) {
    $env:AWS_ACCESS_KEY_ID = $AwsAccessKeyId.Trim()
    $env:AWS_SECRET_ACCESS_KEY = $AwsSecretAccessKey.Trim()
    if (-not [string]::IsNullOrWhiteSpace($AwsSessionToken)) {
        $env:AWS_SESSION_TOKEN = $AwsSessionToken.Trim()
    }
    $env:AWS_DEFAULT_REGION = $AwsRegion
}

Write-Host "[*] Checking AWS authentication status..." -ForegroundColor Yellow

$isAuthenticated = $false
try {
    $testId = aws sts get-caller-identity --query "Account" --output text 2>$null
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($testId)) {
        $isAuthenticated = $true
    }
} catch {
    $isAuthenticated = $false
}

if (-not $isAuthenticated) {
    Write-Host ""
    Write-Host "[!] AWS CLI is not authenticated or credentials were not found." -ForegroundColor Yellow
    Write-Host "Please choose an authentication method:" -ForegroundColor Cyan
    Write-Host "  [1] Enter AWS Access Key & Secret Key interactively"
    Write-Host "  [2] Run 'aws configure' interactive setup"
    Write-Host "  [3] Run AWS SSO login ('aws sso login')"
    Write-Host "  [4] Exit"
    Write-Host ""
    
    $choice = Read-Host "Select option (1-4) [default: 1]"
    if ([string]::IsNullOrWhiteSpace($choice)) { $choice = "1" }

    if ($choice -eq "1") {
        $enteredKeyId = Read-Host "Enter AWS Access Key ID"
        $enteredSecKey = Read-Host "Enter AWS Secret Access Key"
        $enteredToken = Read-Host "Enter AWS Session Token (Optional - press Enter to skip)"
        
        if ([string]::IsNullOrWhiteSpace($enteredKeyId) -or [string]::IsNullOrWhiteSpace($enteredSecKey)) {
            Write-Host "[X] Access Key and Secret Key are required." -ForegroundColor Red
            exit 1
        }
        
        $env:AWS_ACCESS_KEY_ID = $enteredKeyId.Trim()
        $env:AWS_SECRET_ACCESS_KEY = $enteredSecKey.Trim()
        if (-not [string]::IsNullOrWhiteSpace($enteredToken)) {
            $env:AWS_SESSION_TOKEN = $enteredToken.Trim()
        }
        $env:AWS_DEFAULT_REGION = $AwsRegion
    } elseif ($choice -eq "2") {
        aws configure
    } elseif ($choice -eq "3") {
        try {
            aws login
        } catch {
            aws sso login
        }
    } else {
        Write-Host "[!] Setup aborted by user." -ForegroundColor Red
        exit 1
    }
}

# Verify authentication after login step
try {
    $accountId = (aws sts get-caller-identity --query "Account" --output text).Trim()
    if (-not $accountId -or $accountId -eq "None") {
        throw "Account ID is empty"
    }
    Write-Host "[OK] Authenticated AWS Account ID: $accountId" -ForegroundColor Green
} catch {
    Write-Host "[X] ERROR: Unable to verify AWS credentials via 'aws sts get-caller-identity'." -ForegroundColor Red
    Write-Host "    Please ensure your AWS credentials and permissions are valid." -ForegroundColor Red
    exit 1
}

# 1. ECR Repository
$ecrRepoName = "marketintel-db-cms"
Write-Host "[*] Setting up Amazon ECR Repository: $ecrRepoName..." -ForegroundColor Yellow
try {
    aws ecr create-repository --repository-name $ecrRepoName --image-scanning-configuration scanOnPush=true --region $AwsRegion | Out-Null
} catch {
    Write-Host "    [INFO] ECR Repository already exists."
}

# 2. CloudWatch Log Group
$logGroupName = "/ecs/marketintel-cms-backend"
Write-Host "[*] Setting up CloudWatch Log Group: $logGroupName..." -ForegroundColor Yellow
try {
    aws logs create-log-group --log-group-name $logGroupName --region $AwsRegion | Out-Null
} catch {
    Write-Host "    [INFO] Log group already exists."
}
aws logs put-retention-policy --log-group-name $logGroupName --retention-in-days 30 --region $AwsRegion | Out-Null

# 3. GitHub OIDC Provider in IAM
Write-Host "[*] Configuring GitHub OIDC Identity Provider in IAM..." -ForegroundColor Yellow
$oidcExists = aws iam list-open-id-connect-providers --query "OpenIDConnectProviderList[?contains(Arn, 'token.actions.githubusercontent.com')].Arn" --output text
if (-not $oidcExists -or $oidcExists -eq "None") {
    aws iam create-open-id-connect-provider `
        --url "https://token.actions.githubusercontent.com" `
        --client-id-list "sts.amazonaws.com" `
        --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" "1c587612c62c2f1f417855018cf4b162f79f1874" | Out-Null
    Write-Host "    [OK] OIDC Provider created." -ForegroundColor Green
} else {
    Write-Host "    [OK] OIDC Provider already exists." -ForegroundColor Green
}

# 4. GitHub Actions Role
$oidcRoleName = "github-actions-marketintel-cms-role"
Write-Host "[*] Creating GitHub Actions IAM Role: $oidcRoleName..." -ForegroundColor Yellow

$trustPolicyPath = Join-Path $iamDir "github-oidc-trust-policy.json"
$permPolicyPath = Join-Path $iamDir "github-actions-ecs-policy.json"

$trustPolicy = (Get-Content $trustPolicyPath -Raw).Replace("ACCOUNT_ID", $accountId)
$permPolicy = (Get-Content $permPolicyPath -Raw).Replace("ACCOUNT_ID", $accountId)

$tmpTrust = [System.IO.Path]::GetTempFileName()
$tmpPerm = [System.IO.Path]::GetTempFileName()
Set-Content -Path $tmpTrust -Value $trustPolicy
Set-Content -Path $tmpPerm -Value $permPolicy

try {
    aws iam create-role --role-name $oidcRoleName --assume-role-policy-document "file://$tmpTrust" --description "Role for GitHub Actions to deploy Marketintel-DB-CMS to ECS" | Out-Null
} catch {
    aws iam update-assume-role-policy --role-name $oidcRoleName --policy-document "file://$tmpTrust" | Out-Null
}
aws iam put-role-policy --role-name $oidcRoleName --policy-name "GitHubActionsECSDeployPolicy" --policy-document "file://$tmpPerm" | Out-Null
Remove-Item $tmpTrust, $tmpPerm -Force
Write-Host "    [OK] GitHub Actions IAM Role ready." -ForegroundColor Green

# 5. ECS Task Execution Role & Task Role
$taskExecRole = "marketintel-cms-task-execution-role"
$taskRole = "marketintel-cms-task-role"
Write-Host "[*] Creating ECS Task Roles..." -ForegroundColor Yellow

$ecsTrustPath = Join-Path $iamDir "ecs-tasks-trust-policy.json"

try {
    aws iam create-role --role-name $taskExecRole --assume-role-policy-document "file://$ecsTrustPath" | Out-Null
} catch {
    # Role already exists
}
aws iam attach-role-policy --role-name $taskExecRole --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" | Out-Null

$taskExecPolicyPath = Join-Path $iamDir "ecs-task-execution-policy.json"
$taskExecPolicy = (Get-Content $taskExecPolicyPath -Raw).Replace("ACCOUNT_ID", $accountId)
$tmpExec = [System.IO.Path]::GetTempFileName()
Set-Content -Path $tmpExec -Value $taskExecPolicy
aws iam put-role-policy --role-name $taskExecRole --policy-name "ECSTaskExecutionCustomPolicy" --policy-document "file://$tmpExec" | Out-Null
Remove-Item $tmpExec -Force

try {
    aws iam create-role --role-name $taskRole --assume-role-policy-document "file://$ecsTrustPath" | Out-Null
} catch {
    # Role already exists
}
$taskRolePolicyPath = Join-Path $iamDir "ecs-task-role-policy.json"
$taskRolePolicy = (Get-Content $taskRolePolicyPath -Raw).Replace("ACCOUNT_ID", $accountId)
$tmpTask = [System.IO.Path]::GetTempFileName()
Set-Content -Path $tmpTask -Value $taskRolePolicy
aws iam put-role-policy --role-name $taskRole --policy-name "ECSTaskRuntimePolicy" --policy-document "file://$tmpTask" | Out-Null
Remove-Item $tmpTask -Force

# 6. ECS Cluster
$clusterName = "marketintel-cms-cluster"
Write-Host "[*] Creating Amazon ECS Cluster: $clusterName..." -ForegroundColor Yellow
try {
    aws ecs create-cluster --cluster-name $clusterName --region $AwsRegion | Out-Null
} catch {
    Write-Host "    [INFO] Cluster already exists."
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "[OK] AWS INFRASTRUCTURE PREPARATION COMPLETE!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Add these Secrets & Variables in GitHub:" -ForegroundColor White
Write-Host "https://github.com/$GitHubRepo/settings/secrets/actions" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Secret Name:       AWS_ROLE_ARN" -ForegroundColor Yellow
Write-Host "  Secret Value:      arn:aws:iam::$accountId:role/$oidcRoleName" -ForegroundColor White
Write-Host ""
Write-Host "  Variables:" -ForegroundColor Yellow
Write-Host "    AWS_REGION:      $AwsRegion" -ForegroundColor White
Write-Host "    ECR_REPOSITORY:  $ecrRepoName" -ForegroundColor White
Write-Host "    ECS_CLUSTER:     $clusterName" -ForegroundColor White
Write-Host "    ECS_SERVICE:     marketintel-cms-service" -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan
