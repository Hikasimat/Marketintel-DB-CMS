#!/usr/bin/env bash
# ==============================================================================
# AWS Production Infrastructure Provisioning Script for Marketintel-DB-CMS
# Uses AWS Free Services & Free-Tier Eligible Defaults
# Configures GitHub Actions OIDC (Zero static credentials)
# ==============================================================================

set -euo pipefail

# Configuration
AWS_REGION="${AWS_REGION:-ap-south-1}"
GITHUB_REPO="Hikasimat/Marketintel-DB-CMS"
ECR_REPO_NAME="marketintel-db-cms"
ECS_CLUSTER_NAME="marketintel-cms-cluster"
LOG_GROUP_NAME="/ecs/marketintel-cms-backend"
OIDC_ROLE_NAME="github-actions-marketintel-cms-role"
TASK_EXEC_ROLE_NAME="marketintel-cms-task-execution-role"
TASK_ROLE_NAME="marketintel-cms-task-role"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IAM_DIR="$SCRIPT_DIR/iam"

echo "======================================================================"
echo "[*] Initializing AWS Infrastructure Setup for $GITHUB_REPO"
echo "    Region: $AWS_REGION"
echo "======================================================================"

# Step 0: Check Authentication / Prompt for Login
echo "[*] Checking AWS authentication status..."
if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo ""
  echo "[!] AWS CLI is not authenticated or credentials were not found."
  echo "Please choose an authentication method:"
  echo "  [1] Enter AWS Access Key & Secret Key interactively"
  echo "  [2] Run 'aws configure' setup wizard"
  echo "  [3] Run AWS SSO login ('aws sso login')"
  echo "  [4] Exit"
  echo ""
  read -p "Select option (1-4) [default: 1]: " CHOICE
  CHOICE="${CHOICE:-1}"

  if [ "$CHOICE" = "1" ]; then
    read -p "Enter AWS Access Key ID: " ENTERED_KEY_ID
    read -sp "Enter AWS Secret Access Key: " ENTERED_SEC_KEY
    echo ""
    read -p "Enter AWS Session Token (Optional - press Enter to skip): " ENTERED_TOKEN

    export AWS_ACCESS_KEY_ID="$ENTERED_KEY_ID"
    export AWS_SECRET_ACCESS_KEY="$ENTERED_SEC_KEY"
    if [ -n "$ENTERED_TOKEN" ]; then
      export AWS_SESSION_TOKEN="$ENTERED_TOKEN"
    fi
    export AWS_DEFAULT_REGION="$AWS_REGION"
  elif [ "$CHOICE" = "2" ]; then
    aws configure
  elif [ "$CHOICE" = "3" ]; then
    aws login || aws sso login
  else
    echo "[!] Setup aborted by user."
    exit 1
  fi
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
echo "[OK] Authenticated AWS Account ID: $ACCOUNT_ID"

# 1. Create ECR Repository (Free Tier: 500MB/month)
echo "[*] Setting up Amazon ECR Repository: $ECR_REPO_NAME..."
aws ecr create-repository \
  --repository-name "$ECR_REPO_NAME" \
  --image-scanning-configuration scanOnPush=true \
  --region "$AWS_REGION" 2>/dev/null || echo "    [INFO] ECR Repository already exists."

# 2. Create CloudWatch Logs Log Group (Free Tier: 5GB ingestion/month)
echo "[*] Setting up CloudWatch Log Group: $LOG_GROUP_NAME..."
aws logs create-log-group \
  --log-group-name "$LOG_GROUP_NAME" \
  --region "$AWS_REGION" 2>/dev/null || echo "    [INFO] Log group already exists."

aws logs put-retention-policy \
  --log-group-name "$LOG_GROUP_NAME" \
  --retention-in-days 30 \
  --region "$AWS_REGION"
echo "    [OK] Log retention set to 30 days."

# 3. Create or Verify GitHub Actions OIDC Provider
echo "[*] Configuring GitHub OIDC Identity Provider in IAM..."
OIDC_EXISTS=$(aws iam list-open-id-connect-providers --query "OpenIDConnectProviderList[?contains(Arn, 'token.actions.githubusercontent.com')].Arn" --output text || true)

if [ -z "$OIDC_EXISTS" ] || [ "$OIDC_EXISTS" = "None" ]; then
  echo "    Creating OIDC provider for token.actions.githubusercontent.com..."
  aws iam create-open-id-connect-provider \
    --url "https://token.actions.githubusercontent.com" \
    --client-id-list "sts.amazonaws.com" \
    --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" "1c587612c62c2f1f417855018cf4b162f79f1874"
  echo "    [OK] OIDC Provider created."
else
  echo "    [OK] OIDC Provider already present."
fi

# 4. Create GitHub Actions IAM Role with OIDC Trust Policy
echo "[*] Creating GitHub Actions Deployment IAM Role: $OIDC_ROLE_NAME..."
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" "$IAM_DIR/github-oidc-trust-policy.json" > "$TMP_DIR/trust.json"
sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" "$IAM_DIR/github-actions-ecs-policy.json" > "$TMP_DIR/perm.json"

aws iam create-role \
  --role-name "$OIDC_ROLE_NAME" \
  --assume-role-policy-document "file://$TMP_DIR/trust.json" \
  --description "Role for GitHub Actions to deploy Marketintel-DB-CMS to ECS" 2>/dev/null || \
aws iam update-assume-role-policy \
  --role-name "$OIDC_ROLE_NAME" \
  --policy-document "file://$TMP_DIR/trust.json"

aws iam put-role-policy \
  --role-name "$OIDC_ROLE_NAME" \
  --policy-name "GitHubActionsECSDeployPolicy" \
  --policy-document "file://$TMP_DIR/perm.json"
echo "    [OK] GitHub Actions IAM Role ready."

# 5. Create ECS Task Execution Role & Task Role
echo "[*] Creating ECS Task Execution Role: $TASK_EXEC_ROLE_NAME..."

aws iam create-role \
  --role-name "$TASK_EXEC_ROLE_NAME" \
  --assume-role-policy-document "file://$IAM_DIR/ecs-tasks-trust-policy.json" 2>/dev/null || true

aws iam attach-role-policy \
  --role-name "$TASK_EXEC_ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"

sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" "$IAM_DIR/ecs-task-execution-policy.json" > "$TMP_DIR/task-exec-perm.json"
aws iam put-role-policy \
  --role-name "$TASK_EXEC_ROLE_NAME" \
  --policy-name "ECSTaskExecutionCustomPolicy" \
  --policy-document "file://$TMP_DIR/task-exec-perm.json"

echo "[*] Creating ECS Task Role: $TASK_ROLE_NAME..."
aws iam create-role \
  --role-name "$TASK_ROLE_NAME" \
  --assume-role-policy-document "file://$IAM_DIR/ecs-tasks-trust-policy.json" 2>/dev/null || true

sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" "$IAM_DIR/ecs-task-role-policy.json" > "$TMP_DIR/task-perm.json"
aws iam put-role-policy \
  --role-name "$TASK_ROLE_NAME" \
  --policy-name "ECSTaskRuntimePolicy" \
  --policy-document "file://$TMP_DIR/task-perm.json"

# 6. Create ECS Cluster
echo "[*] Creating Amazon ECS Cluster: $ECS_CLUSTER_NAME..."
aws ecs create-cluster --cluster-name "$ECS_CLUSTER_NAME" --region "$AWS_REGION" 2>/dev/null || echo "    [INFO] Cluster already exists."

echo ""
echo "======================================================================"
echo "[OK] AWS INFRASTRUCTURE PREPARATION COMPLETE!"
echo "======================================================================"
echo "Add these Secrets & Variables in GitHub:"
echo "https://github.com/$GITHUB_REPO/settings/secrets/actions"
echo ""
echo "  Secret Name:       AWS_ROLE_ARN"
echo "  Secret Value:      arn:aws:iam::$ACCOUNT_ID:role/$OIDC_ROLE_NAME"
echo ""
echo "  Variables:"
echo "    AWS_REGION:      $AWS_REGION"
echo "    ECR_REPOSITORY:  $ECR_REPO_NAME"
echo "    ECS_CLUSTER:     $ECS_CLUSTER_NAME"
echo "    ECS_SERVICE:     marketintel-cms-service"
echo "======================================================================"
