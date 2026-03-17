# AI Agent Architecture & Development Guide (AGENTS.md)

## 1. Project Overview & Architecture

This project implements a **Telegram Bot** with a "Xianxia/Cultivation" (修仙) theme, providing AI-powered image and video generation services. The architecture follows a layered design, separating interface handling, business logic, and infrastructure integration.

### 1.1 Architecture Diagram

```mermaid
graph TD
    User((User/Daoist)) <-->|Telegram API| TG[Telegram Bot Interface]
    
    subgraph "Application Layer (src)"
        TG -->|Updates| H[Handler Layer]
        H -->|Commands/Messages| R[Router/Dispatcher]
        
        subgraph "Service Layer"
            R -->|Auth & Quota| PS[Permission Service]
            R -->|Task Orchestration| TS[Task Service]
            TS -->|Queue/Status| IS[Image Service]
        end
        
        subgraph "Infrastructure Layer"
            IS -->|HTTP/REST| API[Backend API Client]
            PS -->|SQLAlchemy| DB[Database (PostgreSQL)]
            TS -->|File I/O| S[Storage/MinIO]
        end
    end
    
    subgraph "External Systems"
        API <-->|Generation Tasks| AI_Backend[AI Inference Server]
        S <-->|Assets| MinIO[MinIO Object Storage]
        DB <-->|Persistance| PG[PostgreSQL DB]
    end
```

### 1.2 Core Components

The system is modularized into several key "Agents" (logical components):

1.  **Interface Agent (Gateway)**: Handles Telegram updates, session management, and user interaction.
2.  **Permission Agent (Sect Elder)**: Manages user authentication, "Spirit Stone" (credit) economy, and "Cultivation Levels" (tiers).
3.  **Generation Agent (Alchemist)**: Orchestrates AI tasks (Image-to-Image, Face Swap, Video Generation).
4.  **Backend Connector Agent (Transmission)**: Manages reliable communication with the AI backend.
5.  **Data Steward Agent**: Handles data persistence and logging.

---

## 2. Agent Responsibilities & Contracts

### 2.1 Interface Agent (Gateway)
-   **Codebase**: `bot_test.py`, `src/handlers/*`
-   **Role**: Entry point for all user interactions.
-   **Responsibilities**:
    -   Initialize the Telegram Application and Register Handlers.
    -   Parse incoming `Update` objects (Text, Photo, Video, Document).
    -   Manage User Session State (`context.user_data['mode']`).
    -   Route requests to appropriate services based on current Mode (e.g., `MODE_FACESWAP`, `MODE_UNDRESS`).
    -   Render UI (Reply Keyboards, Inline Buttons).
-   **Inputs**: Telegram `Update` objects.
-   **Outputs**: User feedback (Messages, Menus) or calls to Service Layer.

### 2.2 Permission Agent (Sect Elder)
-   **Codebase**: `src/services/permission_service.py`, `src/quota.py`
-   **Role**: Gatekeeper and Economy Manager.
-   **Responsibilities**:
    -   **Authentication**: Verify if user is a member of the required Telegram Channel (`REQUIRED_CHANNEL_ID`).
    -   **Economy**: Manage "Spirit Stones" (Credits). Deduct costs for tasks, award credits for Check-ins/Referrals.
    -   **Tier Management**: Calculate User Group (凡人 -> 练气期 -> 筑基期 -> 金丹期) based on activity.
    -   **Referral System**: Track invites and distribute rewards.
-   **Key Algorithms**:
    -   `calculate_user_priority`: Dynamic priority based on User Group and Daily Usage.
    -   `refresh_user_group`: Automates tier promotion based on thresholds (Invites, Check-ins, Generations).

### 2.3 Generation Agent (Alchemist)
-   **Codebase**: `src/services/task_service.py`
-   **Role**: Task Orchestrator.
-   **Responsibilities**:
    -   **Preprocessing**: Save uploaded files to `TMP_DIR`, validate inputs.
    -   **Task Submission**: Construct payloads for different tasks (Img2Img, FaceSwap, Video).
    -   **Monitoring**: Poll task status via `ImageService`.
    -   **Post-processing**: Download results, save to local/cloud, send to user.
    -   **Cleanup**: Remove temporary files.
-   **Modes**:
    -   **Quick Tasks**: Undress, Masturbation (Single Image + Preset Prompt).
    -   **Face Swap**: 2-Step (Face + Body) or Random Template.
    -   **Video**: Custom Text-to-Video or Template-based (e.g., "Doggy Style", "Blowjob").

### 2.4 Backend Connector Agent (Transmission)
-   **Codebase**: `src/services/image_service.py`, `src/api_client.py`
-   **Role**: Reliable Transport Layer.
-   **Responsibilities**:
    -   **Protocol**: HTTP/1.1 REST.
    -   **Resilience**: Implements **Circuit Breaker** (fail fast if backend is down) and **Async Retries**.
    -   **Storage Integration**: Fetches assets from MinIO before sending to Backend.
    -   **Endpoints**: `img2img`, `face_swap`, `perfect_video_edit`, `perfect_video_insert`.

### 2.5 Data Steward Agent
-   **Codebase**: `src/database/*`
-   **Role**: Persistence Manager.
-   **Responsibilities**:
    -   Manage SQLAlchemy sessions (`AsyncSessionLocal`).
    -   Define Schema (`User`, `History`, `Referral`, `UserLog`).
    -   Record detailed transaction logs for every credit change.

---

## 3. Inter-Agent Communication

-   **Pattern**: Direct Asynchronous Function Calls (`await service.method()`).
-   **State Sharing**:
    -   **Transient**: `context.user_data` (Telegram Bot Context) for multi-step flows (e.g., FaceSwap Step 1 -> Step 2).
    -   **Persistent**: PostgreSQL for User Profile, Credits, and History.
-   **External**:
    -   **Bot <-> Backend**: HTTP Polling (Status Check).
    -   **Bot <-> MinIO**: S3-compatible API.

---

## 4. Configuration & Environment

The system is configured via `config.py` using `.env` variables.

### 4.1 Key Environment Variables

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `BOT_TOKEN_TEST` | Telegram Bot Token | `123456:ABC...` |
| `DATABASE_URL` | PostgreSQL Connection String | `postgresql+asyncpg://...` |
| `API_BASE` | AI Backend Base URL | `http://192.168.1.226:8003` |
| `API_TOKEN` | Backend Auth Token | `your_secure_token` |
| `MINIO_ENDPOINT` | MinIO Address | `192.168.1.115:9000` |
| `REQUIRED_CHANNEL_ID` | Channel ID for Mandatory Join | `-1001234567890` |
| `PROXY_URL` | Network Proxy (Optional) | `socks5://127.0.0.1:7890` |

---

## 5. Testing Strategy

### 5.1 Unit Testing Template
Use `pytest` and `unittest.mock`.

```python
import pytest
from unittest.mock import AsyncMock, patch
from src.services.permission_service import PermissionService

@pytest.mark.asyncio
async def test_check_quota_sufficient():
    # Setup
    service = PermissionService()
    service.quota_manager.check_credits = AsyncMock(return_value=True)
    
    # Execute
    update = AsyncMock()
    context = AsyncMock()
    result = await service.check_quota(update, context, cost=2)
    
    # Assert
    assert result is True
```

### 5.2 Integration Testing
-   **Database**: Use a separate test database or transaction rollback.
-   **API**: Mock `httpx.AsyncClient` to simulate Backend responses.

---

## 6. Deployment & Observability

### 6.1 Deployment Steps

#### Local Deployment
1.  **Prerequisites**: Python 3.10+, PostgreSQL, MinIO, AI Backend.
2.  **Install Dependencies**: `pip install -r requirements.txt`.
3.  **Setup DB**: Run migration scripts (e.g., `alembic` or `init_db` in `post_init`).
4.  **Run**: `python src/bot_test.py`.

#### Docker Deployment & Restart
To properly restart the bot service and apply the latest code changes, you must remove the old container and rebuild it.

```bash
cd deploy

# 1. Stop and remove the old container
docker-compose down
# (Alternatively, just for the bot service: docker-compose rm -fs bot)

# 2. Rebuild the image and start the new container in the background
docker-compose up -d --build
```

### 6.2 Observability
-   **Logging**:
    -   `UserLogger` (`src/logger.py`) records user-centric actions to files.
    -   Standard `logging` for system errors.
-   **Metrics**:
    -   Queue Size (via `/queue` command).
    -   User Stats (via `/profile` or `个人中心`).

---

## 7. Security & Compliance

### 7.1 Access Control
-   **Role-Based**: Regular Users vs. Admins (implied by configuration/code access).
-   **Gatekeeper**: `check_access` enforces Channel Membership.

### 7.2 Data Safety
-   **Input Validation**: `_handle_template_contribution` validates file types.
-   **Privacy**: Private generation mode available (Inline Button "私密").
-   **Traceability**: All generations are logged in `History` table and `UserLog`.

### 7.3 Operational Security
-   **Secrets**: All sensitive keys in `.env` (not committed).
-   **Circuit Breaker**: Prevents cascading failures when Backend is overloaded.

---

## 8. Maintenance

**Maintainer**: Dev Team
**Last Updated**: 2025-03-05

### Changelog
-   **Initial Draft**: Architecture reverse-engineered from source code.
