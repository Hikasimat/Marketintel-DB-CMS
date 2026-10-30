# AWS Production Deployment Guide: Marketintel-DB-CMS

This guide details the complete production setup for the **Marketintel-DB-CMS Backend Service** running on **Amazon ECS (AWS Fargate)** with **GitHub Actions OIDC CI/CD** (zero static AWS keys) and the **MarketIntel DB Authentication Bridge**.

---

## 1. Architecture Overview

```mermaid
graph TD
    A[Developer Push to main] -->|OIDC JWT| B[GitHub Actions Runner]
    B -->|sts:AssumeRoleWithWebIdentity| C[AWS IAM Role: github-actions-marketintel-cms-role]
    B -->|Build & Push Docker Image| D[AWS ECR: marketintel-db-cms]
    B -->|Deploy Task Definition| E[AWS ECS Fargate Cluster]
    E -->|Pulls Image| D
    E -->|Retrieves Secrets| F[AWS SSM Parameter Store]
    E -->|Streams Logs| G[AWS CloudWatch Logs: /ecs/marketintel-cms-backend]
    E -->|Database Queries| H[(PostgreSQL Database: Supabase / AWS RDS)]
    E -->|Task Queue / Cache| I[(Redis Cache: Upstash / ElastiCache)]
    E -->|Login Verification| J[MarketIntel DB Auth API: /api/auth/login/]
```

### Key Principles
- **Backend Only**: Only the headless CMS API service and background workers are packaged and deployed. Frontend demo clients are omitted.
- **Zero Static AWS Secrets in GitHub**: Uses OpenID Connect (OIDC) between GitHub Actions and AWS STS. No AWS Access Key ID or Secret Access Key stored in GitHub.
- **MarketIntel DB Authentication Bridge**: CMS does not implement public user signup. Authentication delegates to MarketIntel DB's `POST /api/auth/login/` and profiles are retrieved from `/api/auth/me/`.

---

## 2. AWS Free Services & Free Tier Breakdown

| Component | Service | Free Tier / Cost Optimization Strategy |
| :--- | :--- | :--- |
| **Container Registry** | **Amazon ECR** | **500 MB/month** private storage included permanently in AWS Free Tier. |
| **Container Compute** | **AWS ECS (Fargate)** | Configured with `cpu: "256"` (0.25 vCPU) and `memory: "512"` (512 MB). Eligible for AWS Free Tier credits or low micro-cents consumption. |
| **Logging & Monitoring** | **AWS CloudWatch** | **5 GB/month** log ingestion and **5 GB** archive included permanently in Free Tier. Log retention capped at 30 days. |
| **Database** | **PostgreSQL** | Compatible with **Supabase Free Tier (500 MB)** (as used in MarketIntel DB) or **AWS RDS PostgreSQL (db.t4g.micro / 750 hours free/month)** in 12-month tier. |
| **Cache / Celery Broker** | **Redis** | Compatible with **Upstash Serverless Redis (Free 10k requests/day)** or **AWS ElastiCache (cache.t2.micro / 750 hours free/month)**. |
| **CI/CD** | **GitHub Actions** | **2,000 free minutes/month** on public & standard private repositories. |

---

## 3. Automated One-Command Provisioning

We provide automated setup scripts in [`aws/`](file:///c:/Users/mohan/OneDrive/Desktop/CMS/aws):

### Option A: Using PowerShell (Windows)
```powershell
.\aws\setup-aws-production.ps1 -AwsRegion "ap-south-1" -GitHubRepo "Hikasimat/Marketintel-DB-CMS"
```

### Option B: Using Bash (Linux / macOS / AWS CloudShell)
```bash
chmod +x aws/setup-aws-production.sh
./aws/setup-aws-production.sh
```

---

## 4. Manual Step-by-Step AWS Setup

If you prefer executing steps manually with the AWS CLI:

### Step 1: Create Amazon ECR Repository
```bash
aws ecr create-repository \
  --repository-name marketintel-db-cms \
  --image-scanning-configuration scanOnPush=true \
  --region ap-south-1
```

### Step 2: Create CloudWatch Log Group
```bash
aws logs create-log-group \
  --log-group-name /ecs/marketintel-cms-backend \
  --region ap-south-1

aws logs put-retention-policy \
  --log-group-name /ecs/marketintel-cms-backend \
  --retention-in-days 30 \
  --region ap-south-1
```

### Step 3: Configure GitHub OIDC Identity Provider in IAM
If you haven't already configured GitHub as an OIDC provider in your AWS account:
```bash
aws iam create-open-id-connect-provider \
  --url "https://token.actions.githubusercontent.com" \
  --client-id-list "sts.amazonaws.com" \
  --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" "1c587612c62c2f1f417855018cf4b162f79f1874"
```

### Step 4: Create GitHub Actions Deployment Role
1. Review the trust policy in [`aws/iam/github-oidc-trust-policy.json`](file:///c:/Users/mohan/OneDrive/Desktop/CMS/aws/iam/github-oidc-trust-policy.json).
2. Create the role:
```bash
aws iam create-role \
  --role-name github-actions-marketintel-cms-role \
  --assume-role-policy-document file://aws/iam/github-oidc-trust-policy.json

aws iam put-role-policy \
  --role-name github-actions-marketintel-cms-role \
  --policy-name GitHubActionsECSDeployPolicy \
  --policy-document file://aws/iam/github-actions-ecs-policy.json
```

### Step 5: Create ECS Task Execution & Task Roles
```bash
# Trust document for ECS Tasks
cat <<EOF > ecs-trust.json
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

# Task Execution Role
aws iam create-role --role-name marketintel-cms-task-execution-role --assume-role-policy-document file://ecs-trust.json
aws iam attach-role-policy --role-name marketintel-cms-task-execution-role --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam put-role-policy --role-name marketintel-cms-task-execution-role --policy-name ECSTaskExecutionCustomPolicy --policy-document file://aws/iam/ecs-task-execution-policy.json

# Task Role (Runtime)
aws iam create-role --role-name marketintel-cms-task-role --assume-role-policy-document file://ecs-trust.json
aws iam put-role-policy --role-name marketintel-cms-task-role --policy-name ECSTaskRuntimePolicy --policy-document file://aws/iam/ecs-task-role-policy.json
```

### Step 6: Create ECS Cluster
```bash
aws ecs create-cluster \
  --cluster-name marketintel-cms-cluster \
  --region ap-south-1
```

---

## 5. Setting up Secrets in AWS SSM Parameter Store

Store your production environment secrets securely in AWS SSM Parameter Store (Free Tier: 10,000 standard parameters free):

```bash
# Django Secret Key (min 50 characters)
aws ssm put-parameter --name "/marketintel-cms/DJANGO_SECRET_KEY" --type "SecureString" --value "CHANGE_ME_TO_SUPER_SECURE_KEY_OF_AT_LEAST_50_CHARS_LONG_12345" --overwrite

# PostgreSQL Database Connection URL (Supabase or AWS RDS)
aws ssm put-parameter --name "/marketintel-cms/DATABASE_URL" --type "SecureString" --value "postgresql://postgres:password@your-db-host:5432/postgres" --overwrite

# Redis Cache / Broker URL
aws ssm put-parameter --name "/marketintel-cms/REDIS_URL" --type "SecureString" --value "redis://default:password@your-redis-host:6379" --overwrite

# Field Encryption Key (32-byte urlsafe base64 key)
aws ssm put-parameter --name "/marketintel-cms/FIELD_ENCRYPTION_KEY" --type "SecureString" --value "fK_8g-3z4P...32_byte_base64_key..." --overwrite

# JWT Signing Key
aws ssm put-parameter --name "/marketintel-cms/JWT_SIGNING_KEY" --type "SecureString" --value "jwt_secret_signing_key_production_2026" --overwrite

# Allowed Hosts & Public URL
aws ssm put-parameter --name "/marketintel-cms/PUBLIC_BASE_URL" --type "String" --value "https://cms.hikasimat.com" --overwrite
aws ssm put-parameter --name "/marketintel-cms/DJANGO_ALLOWED_HOSTS" --type "String" --value "cms.hikasimat.com,localhost" --overwrite
```

---

## 6. Configure GitHub Repository Secrets

In your GitHub repository ([`https://github.com/Hikasimat/Marketintel-DB-CMS/settings/secrets/actions`](https://github.com/Hikasimat/Marketintel-DB-CMS/settings/secrets/actions)), add the following **Repository Secrets**:

| Secret Name | Example Value | Description |
| :--- | :--- | :--- |
| `AWS_ROLE_ARN` | `arn:aws:iam::123456789012:role/github-actions-marketintel-cms-role` | The ARN of the IAM role GitHub Actions assumes via OIDC. |
| `AWS_REGION` | `ap-south-1` | Your AWS region. |
| `ECR_REPOSITORY` | `marketintel-db-cms` | ECR repository name. |
| `ECS_CLUSTER` | `marketintel-cms-cluster` | ECS cluster name. |
| `ECS_SERVICE` | `marketintel-cms-service` | ECS service name. |

---

## 7. Push Repository to GitHub

Execute the following commands in your local repository to push to GitHub:

```bash
# 1. Add GitHub Remote
git remote add origin https://github.com/Hikasimat/Marketintel-DB-CMS.git

# 2. Rename branch to main
git branch -M main

# 3. Add and commit all production-ready files
git add .
git commit -m "feat: AWS production ready with GitHub OIDC, ECS, and MarketIntel DB Auth"

# 4. Push to GitHub
git push -u origin main
```

Once pushed, GitHub Actions will automatically trigger the [`deploy-ecs.yml`](file:///c:/Users/mohan/OneDrive/Desktop/CMS/.github/workflows/deploy-ecs.yml) workflow, build your Docker image, push it to Amazon ECR, and update your Amazon ECS service!
