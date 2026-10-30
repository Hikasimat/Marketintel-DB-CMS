# ==============================================================================
# AWS Production Infrastructure Setup for PowerShell
# Repository: Hikasimat/Marketintel-DB-CMS
# ==============================================================================

param(
    [string]$AwsRegion = "ap-south-1",
    [string]$GitHubRepo = "Hikasimat/Marketintel-DB-CMS"
)

$ErrorActionPreference = "Stop"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "🚀 Initializing AWS Infrastructure for $GitHubRepo" -ForegroundColor Cyan
Write-Host "Region: $AwsRegion" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

$accountId = (aws sts get-caller-identity --query "Account" --output text).Trim()
Write-Host "✔ Authenticated AWS Account ID: $accountId" -ForegroundColor Green

# 1. ECR Repository
$ecrRepoName = "marketintel-db-cms"
Write-Host "📦 Setting up Amazon ECR Repository: $ecrRepoName..." -ForegroundColor Yellow
try {
    aws ecr create-repository --repository-name $ecrRepoName --image-scanning-configuration scanOnPush=true --region $AwsRegion | Out-Null
} catch {
    Write-Host "  ℹ ECR Repository already exists."
}

# 2. CloudWatch Log Group
$logGroupName = "/ecs/marketintel-cms-backend"
Write-Host "📝 Setting up CloudWatch Log Group: $logGroupName..." -ForegroundColor Yellow
try {
    aws logs create-log-group --log-group-name $logGroupName --region $AwsRegion | Out-Null
} catch {
    Write-Host "  ℹ Log group already exists."
}
aws logs put-retention-policy --log-group-name $logGroupName --retention-in-days 30 --region $AwsRegion | Out-Null

# 3. GitHub OIDC Provider in IAM
Write-Host "🔐 Configuring GitHub OIDC Identity Provider in IAM..." -ForegroundColor Yellow
$oidcExists = aws iam list-open-id-connect-providers --query "OpenIDConnectProviderList[?contains(Arn, 'token.actions.githubusercontent.com')].Arn" --output text
if (-not $oidcExists -or $oidcExists -eq "None") {
    aws iam create-open-id-connect-provider `
        --url "https://token.actions.githubusercontent.com" `
        --client-id-list "sts.amazonaws.com" `
        --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" "1c587612c62c2f1f417855018cf4b162f79f1874" | Out-Null
    Write-Host "  ✔ OIDC Provider created." -ForegroundColor Green
} else {
    Write-Host "  ✔ OIDC Provider already exists." -ForegroundColor Green
}

# 4. GitHub Actions Role
$oidcRoleName = "github-actions-marketintel-cms-role"
Write-Host "🛡️ Creating GitHub Actions IAM Role: $oidcRoleName..." -ForegroundColor Yellow

$trustPolicy = (Get-Content "aws/iam/github-oidc-trust-policy.json" -Raw).Replace("ACCOUNT_ID", $accountId)
$permPolicy = (Get-Content "aws/iam/github-actions-ecs-policy.json" -Raw).Replace("ACCOUNT_ID", $accountId)

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
Write-Host "  ✔ GitHub Actions IAM Role ready." -ForegroundColor Green

# 5. ECS Task Execution Role & Task Role
$taskExecRole = "marketintel-cms-task-execution-role"
$taskRole = "marketintel-cms-task-role"
Write-Host "⚙️ Creating ECS Task Roles..." -ForegroundColor Yellow

$ecsTrust = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ecs-tasks.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
"@
$tmpEcsTrust = [System.IO.Path]::GetTempFileName()
Set-Content -Path $tmpEcsTrust -Value $ecsTrust

try { aws iam create-role --role-name $taskExecRole --assume-role-policy-document "file://$tmpEcsTrust" | Out-Null } catch {}
aws iam attach-role-policy --role-name $taskExecRole --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" | Out-Null

$taskExecPolicy = (Get-Content "aws/iam/ecs-task-execution-policy.json" -Raw).Replace("ACCOUNT_ID", $accountId)
$tmpExec = [System.IO.Path]::GetTempFileName()
Set-Content -Path $tmpExec -Value $taskExecPolicy
aws iam put-role-policy --role-name $taskExecRole --policy-name "ECSTaskExecutionCustomPolicy" --policy-document "file://$tmpExec" | Out-Null
Remove-Item $tmpExec -Force

try { aws iam create-role --role-name $taskRole --assume-role-policy-document "file://$tmpEcsTrust" | Out-Null } catch {}
$taskRolePolicy = (Get-Content "aws/iam/ecs-task-role-policy.json" -Raw).Replace("ACCOUNT_ID", $accountId)
$tmpTask = [System.IO.Path]::GetTempFileName()
Set-Content -Path $tmpTask -Value $taskRolePolicy
aws iam put-role-policy --role-name $taskRole --policy-name "ECSTaskRuntimePolicy" --policy-document "file://$tmpTask" | Out-Null
Remove-Item $tmpTask, $tmpEcsTrust -Force

# 6. ECS Cluster
$clusterName = "marketintel-cms-cluster"
Write-Host "🏗️ Creating Amazon ECS Cluster: $clusterName..." -ForegroundColor Yellow
try {
    aws ecs create-cluster --cluster-name $clusterName --region $AwsRegion | Out-Null
} catch {
    Write-Host "  ℹ Cluster already exists."
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "✅ AWS INFRASTRUCTURE PREPARATION COMPLETE!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Add these Secrets in GitHub: https://github.com/$GitHubRepo/settings/secrets/actions"
Write-Host "  1. AWS_ROLE_ARN:       arn:aws:iam::$accountId:role/$oidcRoleName" -ForegroundColor Yellow
Write-Host "  2. AWS_REGION:         $AwsRegion" -ForegroundColor Yellow
Write-Host "  3. ECR_REPOSITORY:      $ecrRepoName" -ForegroundColor Yellow
Write-Host "  4. ECS_CLUSTER:        $clusterName" -ForegroundColor Yellow
Write-Host "  5. ECS_SERVICE:        marketintel-cms-service" -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Cyan
