# Validation Audit – Gesture Lab

## Already validated

| Area | What's checked |
|------|----------------|
| **Registration** | Username (max 25), email (@), password (has #/@/$), confirm match, conflict with admin |
| **Login** | Email, password; admin vs user |
| **Forgot password** | Email exists, new password rules, confirm match |
| **User profile** | Username, email, password; conflict with other users and admin; no-changes message |
| **Admin profile** | Username, email, password; conflict with User only when changing; no-changes message |
| **Admin update/delete user** | Admin-only; user exists; cannot delete admin account |
| **Contact form** | Email must contain @gmail.com; subject max 200 words |
| **Send notification** | Title ≤200 chars, message ≤1000 chars, all required |
| **Admin lesson/quiz images** | Type (JPG/PNG/GIF/WebP), size ≤5 MB; client + server |
| **Certificate download** | Level in allowed list; user has perfect score for that level |
| **predict-sign** | Content-Type is image/*; non-empty image |
| **Lesson/quiz CRUD** | lesson_id/quiz_id existence before update/delete |

---

## Gaps (recommended validation)

### 1. **Quiz result API** (`/api/quiz_result`) – **High**
- **Issue:** `score` and `total_questions` are not validated. A client could send e.g. `score=100`, `total_questions=10` and get unfair points/badges.
- **Recommendation:** Enforce `0 <= score <= total_questions`, `total_questions > 0`, and e.g. `total_questions <= 100` to avoid abuse.

### 2. **correct_option (add/update quiz)** – **Medium**
- **Issue:** `correct_option` must be 1–4 (per model). No check; invalid value could break quiz UI or logic.
- **Recommendation:** Reject if `correct_option` not in 1–4.

### 3. **predict-sign image size** – **Medium**
- **Issue:** No max file size. Very large images could cause high memory/CPU or DoS.
- **Recommendation:** Reject request if image size > e.g. 5 MB (same as admin uploads).

### 4. **Contact form** – **Low**
- **Issue:** `name` and `message` have no length limit; very long input is possible.
- **Recommendation:** Max length for name (e.g. 100) and message (e.g. 5000 chars or 500 words).

### 5. **Lesson/quiz text fields** – **Low**
- **Issue:** Lesson `name` (DB: 100), `heading` (200), `description` (Text); quiz option texts (255). No server-side length checks before save.
- **Recommendation:** Validate name ≤ 100, heading ≤ 200; optional max for description and option text to avoid huge payloads.

### 6. **Lesson sign_level / Quiz level** – **Low**
- **Issue:** Any string can be stored; app expects "Basic"/"Intermediate"/"Advance" and "Beginner"/"Intermediate"/"Advance".
- **Recommendation:** Allow-list values so invalid levels are rejected.

---

## Implemented in code (this session)

- Quiz result: validate `score` and `total_questions` (0 ≤ score ≤ total_questions, total_questions in 1–100).
- Quiz: validate `correct_option` in 1–4 for add and update.
- predict-sign: reject if image size > 5 MB.
