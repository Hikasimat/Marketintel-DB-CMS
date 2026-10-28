# Authentication, Tenancy & RBAC API Reference

## 1. Authentication Endpoints

### Register User
```http
POST /api/v1/auth/register/
```
**Request:**
```json
{
  "email": "owner@example.com",
  "password": "SecurePassword123!"
}
```
**Response (201 Created):**
```json
{
  "id": "e9634d0b-0442-4dc9-9801-447cf0810ff8",
  "email": "owner@example.com",
  "created_at": "2026-10-28T12:00:00Z"
}
```

### Obtain JWT Token Pair
```http
POST /api/v1/auth/token/
```
**Request:**
```json
{
  "email": "owner@example.com",
  "password": "SecurePassword123!"
}
```
**Response (200 OK):**
```json
{
  "access": "<jwt_access_token>",
  "refresh": "<jwt_refresh_token>",
  "token_type": "Bearer",
  "expires_in": 900
}
```

### Refresh Access Token (Token Rotation)
```http
POST /api/v1/auth/token/refresh/
```
**Request:**
```json
{
  "refresh": "<current_refresh_token>"
}
```
**Response (200 OK):**
```json
{
  "access": "<new_jwt_access_token>",
  "refresh": "<new_jwt_refresh_token>",
  "token_type": "Bearer",
  "expires_in": 900
}
```
> [!NOTE]
> Attempting to reuse an already-rotated refresh token triggers instant revocation of the entire token family.

---

## 2. Workspace & Membership Management

### Create Workspace
```http
POST /api/v1/workspaces/
Authorization: Bearer <access_token>
```
**Request:**
```json
{
  "name": "Acme Media",
  "slug": "acme-media"
}
```
**Response (201 Created):**
```json
{
  "id": "7b58c732-45e0-496e-bc3d-f2e30c4923f1",
  "name": "Acme Media",
  "slug": "acme-media",
  "created_at": "2026-10-28T12:00:00Z"
}
```

### List Workspace Members
```http
GET /api/v1/workspaces/{workspace_id}/members/
Authorization: Bearer <access_token>
```

### Add / Update Member Role
```http
POST /api/v1/workspaces/{workspace_id}/members/
Authorization: Bearer <access_token>
```
**Request:**
```json
{
  "user_email": "editor@example.com",
  "role": "EDITOR"
}
```
Allowed roles: `OWNER`, `ADMIN`, `EDITOR`, `ANALYST`.

---

## 3. Immutable Audit Trail

### Query Workspace Audit Events
```http
GET /api/v1/workspaces/{workspace_id}/audit-events/?limit=50
Authorization: Bearer <access_token>
```
**Response (200 OK):**
```json
{
  "count": 1,
  "results": [
    {
      "id": "9f27d549-b528-444a-9937-56e6d1ce967e",
      "action": "CONTENT_PUBLISHED",
      "actor_email": "editor@example.com",
      "resource_type": "Article",
      "resource_id": "c1f7b882-628d-426b-8c65-27f7f035616e",
      "timestamp": "2026-10-28T12:30:00Z"
    }
  ]
}
```
Audit records are strictly append-only; database update and delete operations throw runtime exceptions.
