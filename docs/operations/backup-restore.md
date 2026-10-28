# Database Backup, Disaster Recovery & Restore Guide

## 1. Objectives & Recovery Targets

- **Recovery Point Objective (RPO):** < 5 minutes (via automated WAL archiving and continuous transaction logging).
- **Recovery Time Objective (RTO):** < 30 minutes (time required to provision an active database replica and restore service readiness).

---

## 2. Backup Strategy

### A. Continuous WAL Archiving & Point-In-Time Recovery (PITR)
In production, PostgreSQL should be hosted on a managed database platform (AWS RDS, GCP Cloud SQL) with:
1. Automated daily physical snapshots with 35-day retention.
2. Continuous Write-Ahead Log (WAL) archiving to encrypted multi-region object storage (S3 / GCS).
3. Encryption at rest enabled using customer-managed KMS keys.

### B. Daily Logical Backups (`pg_dump`)
In addition to physical snapshots, generate nightly logical dumps for offsite disaster recovery and version migration validation:
```bash
pg_dump \
  --format=custom \
  --compress=9 \
  --no-owner \
  --no-privileges \
  --file="/backups/cms_$(date +%Y%m%d_%H%M%S).dump" \
  -h $POSTGRES_HOST \
  -U $POSTGRES_USER \
  -d $POSTGRES_DB
```

---

## 3. Restoration Procedures

### Scenario A: Restoring from Managed Snapshot (Point-in-Time Recovery)
1. In the cloud console or CLI, initiate a point-in-time restore to a target timestamp prior to the incident:
   ```bash
   aws rds restore-db-instance-to-point-in-time \
     --source-db-instance-identifier cms-prod-primary \
     --target-db-instance-identifier cms-prod-restored \
     --restore-time "2026-10-28T12:00:00Z"
   ```
2. Update the application's `POSTGRES_HOST` secret to point to the restored instance.
3. Validate readiness probe:
   ```bash
   curl -f http://localhost:8000/health/ready
   ```

---

### Scenario B: Restoring from Logical Dump (`pg_restore`)
1. Create a clean database target:
   ```sql
   DROP DATABASE IF EXISTS cms_recovery;
   CREATE DATABASE cms_recovery OWNER cms_app;
   ```
2. Restore using custom format dump:
   ```bash
   pg_restore \
     --clean \
     --if-exists \
     --no-owner \
     --no-privileges \
     -h $POSTGRES_HOST \
     -U $POSTGRES_USER \
     -d cms_recovery \
     /backups/cms_target.dump
   ```
3. Run post-restore schema and migration verification:
   ```bash
   python manage.py migrate --check
   ```

---

## 4. Cryptographic Key Recovery Invariant
All encrypted credentials stored in the `search_provider_credential` table are encrypted with AES-256-GCM using per-record Data Encryption Keys (DEKs) wrapped by the Master Key (`ENCRYPTION_MASTER_KEY`).

> [!CRITICAL]
> Restoring a database backup requires the exact `ENCRYPTION_MASTER_KEY` (or one of the `ENCRYPTION_FALLBACK_KEYS`) that was active when the backup was taken. Store production encryption master keys in a high-availability secrets manager (AWS Secrets Manager, HashiCorp Vault) with independent backup policies.
