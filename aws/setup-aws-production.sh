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

echo "======================================================================"
echo "🚀 Initializing AWS Infrastructure Setup for $GITHUB_REPO"
echo "Region: $AWS_REGION"
echo "======================================================================"

ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
echo "✔ Authenticated AWS Account ID: $ACCOUNT_ID"

# 1. Create ECR Repository (Free Tier: 500MB/month)
echo "📦 Setting up Amazon ECR Repository: $ECR_REPO_NAME..."
aws ecr create-repository \
  --repository-name "$ECR_REPO_NAME" \
  --image-scanning-configuration scanOnPush=true \
  --region "$AWS_REGION" 2>/dev/null || echo "  ℹ ECR Repository already exists."

# 2. Create CloudWatch Logs Log Group (Free Tier: 5GB ingestion/month)
echo "📝 Setting up CloudWatch Log Group: $LOG_GROUP_NAME..."
aws logs create-log-group \
  --log-group-name "$LOG_GROUP_NAME" \
  --region "$AWS_REGION" 2>/dev/null || echo "  ℹ Log group already exists."

aws logs put-retention-policy \
  --log-group-name "$LOG_GROUP_NAME" \
  --retention-in-days 30 \
  --region "$AWS_REGION"
echo "  ✔ Log retention set to 30 days."

# 3. Create or Verify GitHub Actions OIDC Provider
echo "🔐 Configuring GitHub OIDC Identity Provider in IAM..."
OIDC_EXISTS=$(aws iam list-open-id-connect-providers --query "OpenIDConnectProviderList[?contains(Arn, 'token.actions.githubusercontent.com')].Arn" --output text || true)

if [ -z "$OIDC_EXISTS" ]; then
  echo "  Creating OIDC provider for token.actions.githubusercontent.com..."
  aws iam create-open-id-connect-provider \
    --url "https://token.actions.githubusercontent.com" \
    --client-id-list "sts.amazonaws.com" \
    --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" "1c587612c62c2f1f417855018cf4b162f79f1874"
  echo "  ✔ OIDC Provider created."
else
  echo "  ✔ OIDC Provider already present."
fi

# 4. Create GitHub Actions IAM Role with OIDC Trust Policy
echo "🛡️ Creating GitHub Actions Deployment IAM Role: $OIDC_ROLE_NAME..."
TMP_DIR=$(mktemp -d)
sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" aws/iam/github-oidc-trust-policy.json > "$TMP_DIR/trust.json"
sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" aws/iam/github-actions-ecs-policy.json > "$TMP_DIR/perm.json"

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
echo "  ✔ GitHub Actions IAM Role ready."

# 5. Create ECS Task Execution Role & Task Role
echo "⚙️ Creating ECS Task Execution Role: $TASK_EXEC_ROLE_NAME..."
cat <<EOF > "$TMP_DIR/ecs-trust.json"
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
EOF

aws iam create-role \
  --role-name "$TASK_EXEC_ROLE_NAME" \
  --assume-role-policy-document "file://$TMP_DIR/ecs-trust.json" 2>/dev/null || true

aws iam attach-role-policy \
  --role-name "$TASK_EXEC_ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"

sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" aws/iam/ecs-task-execution-policy.json > "$TMP_DIR/task-exec-perm.json"
aws iam put-role-policy \
  --role-name "$TASK_EXEC_ROLE_NAME" \
  --policy-name "ECSTaskExecutionCustomPolicy" \
  --policy-document "file://$TMP_DIR/task-exec-perm.json"

echo "⚙️ Creating ECS Task Role: $TASK_ROLE_NAME..."
aws iam create-role \
  --role-name "$TASK_ROLE_NAME" \
  --assume-role-policy-document "file://$TMP_DIR/ecs-trust.json" 2>/dev/null || true

sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" aws/iam/ecs-task-role-policy.json > "$TMP_DIR/task-perm.json"
aws iam put-role-policy \
  --role-name "$TASK_ROLE_NAME" \
  --policy-name "ECSTaskRuntimePolicy" \
  --policy-document "file://$TMP_DIR/task-perm.json"

# 6. Create ECS Cluster
echo "🏗️ Creating Amazon ECS Cluster: $ECS_CLUSTER_NAME..."
aws ecs create-cluster \
  --cluster-name "$ECS_CLUSTER_NAME" \
  --region "$AWS_REGION" 2>/dev/null || echo "  ℹ Cluster already exists."

# 7. Output GitHub Secrets Configuration
echo ""
echo "======================================================================"
echo "✅ AWS INFRASTRUCTURE PREPARATION COMPLETE!"
echo "======================================================================"
echo "Add these 4 Secrets in GitHub: https://github.com/$GITHUB_REPO/settings/secrets/actions"
echo ""
echo "  1. AWS_ROLE_ARN:"
echo "     arn:aws:iam::$ACCOUNT_ID:role/$OIDC_ROLE_NAME"
echo ""
echo "  2. AWS_REGION:"
echo "     $AWS_REGION"
echo ""
echo "  3. ECR_REPOSITORY:"
echo "     $ECR_REPO_NAME"
echo ""
echo "  4. ECS_CLUSTER:"
echo "     $ECS_CLUSTER_NAME"
echo ""
echo "  5. ECS_SERVICE:"
echo "     marketintel-cms-service"
echo "======================================================================"
rm -rf "$TMP_DIR"
