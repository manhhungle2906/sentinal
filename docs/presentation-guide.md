# API Sentinel — Hướng dẫn trình bày & demo sản phẩm

> Tài liệu này dành cho buổi trình bày trước giảng viên. Nó gồm ba phần:
> **Phần A** giới thiệu sản phẩm (để nói), **Phần B** hướng dẫn demo từng
> bước trên môi trường thật, **Phần C** phần hỏi đáp dự kiến.
>
> **Trạng thái đã kiểm chứng:** sản phẩm đang chạy trực tiếp tại
> **https://sentinel-web-ryxl.onrender.com** (Render Free Tier + Neon
> PostgreSQL 16). Mọi con số trong tài liệu này đều lấy từ dữ liệu thật
> trên Neon, đối chiếu với giao diện và với log của detector.

---

## Mục lục

| Phần | Nội dung | Dùng khi |
|---|---|---|
| [0. Chuẩn bị](#0-chuẩn-bị-15-phút-trước-khi-trình-bày) | Đưa hệ thống về trạng thái sẵn sàng | Trước buổi demo |
| [1. Bảng tóm tắt để nói trong 60 giây](#1-bảng-tóm-tắt-để-nói-trong-60-giây) | Pitch ngắn | Mở đầu |
| [2. Vấn đề và giải pháp](#2-vấn-đề-và-giải-pháp) | Bối cảnh | Phần đầu |
| [3. Kiến trúc](#3-kiến-trúc) | Cách hệ thống hoạt động | Khi giảng viên hỏi |
| [4. Quy tắc phát hiện](#4-quy-tắc-phát-hiện) | Ba rule và ngữ nghĩa cửa sổ | Khi hỏi về logic |
| [5. Mô hình dữ liệu](#5-mô-hình-dữ-liệu) | Các bảng và ràng buộc | Khi hỏi về DB |
| [6. Bảo mật](#6-bảo-mật) | Xác thực, phân quyền, CSRF | Khi hỏi về security |
| [7. Giao diện](#7-giao-diện) | Các màn hình và hành vi | Khi giảng viên hỏi về UX |
| [8. Demo từng bước](#8-demo-từng-bước) | Kịch bản demo ~19 phút | **Phần chính** |
| [9. Kịch bản dự phòng](#9-kịch-bản-dự-phòng-khi-có-sự-cố) | Xử lý sự cố | Khi mạng lỗi |
| [10. Bằng chứng đã kiểm chứng](#10-bằng-chứng-đã-kiểm-chứng) | Test, CI, số liệu | Khi giảng viên yêu cầu chứng minh |
| [11. Giới hạn đã biết](#11-giới-hạn-đã-biết) | Trung thực về phạm vi | Câu hỏi khó |
| [12. Hỏi đáp dự kiến](#12-hỏi-đáp-dự-kiến) | 12 câu hỏi khó | Chuẩn bị |

---

## 0. Chuẩn bị (15 phút trước khi trình bày)

### 0.1 Kiểm tra hệ thống còn sống

Render Free Tier **tắt máy sau 15 phút không hoạt động**. Lần mở đầu tiên
phải chờ "cold start" khoảng 1 phút. Hãy làm việc này **trước** khi bắt đầu
trình bày.

```sh
cd /Users/hungle/Desktop/Sentinal_AI

# Chạm vào ứng dụng để đánh thức máy (chờ ~60 giây nếu đang ngủ)
curl -s https://sentinel-web-ryxl.onrender.com/health/ready
```

Kết quả mong đợi:

```json
{"status":"ok","service":"core","checked_at":"...","database":"ok"}
```

### 0.2 Chạy smoke check đầy đủ

```sh
backend/.venv/bin/python scripts/smoke.py \
  --base-url https://sentinel-web-ryxl.onrender.com \
  --core-url https://sentinel-web-ryxl.onrender.com \
  --ingest-url https://sentinel-web-ryxl.onrender.com
```

Kết quả mong đợi (8/8):

```
PASS  browser url: status 200
PASS  proxy /health/live: status 200
PASS  proxy /health/ready: status 200 (database: ok)
PASS  core /health/live: status 200
PASS  core /health/ready: status 200
PASS  ingest /health/live: status 200
PASS  ingest /health/ready: status 200
PASS  detector heartbeat: {"status": "ok", "service": "detector"}
smoke check passed
```

### 0.3 Nạp sẵn dữ liệu demo (nếu muốn có dữ liệu mới)

Script này tạo workspace, 3 API source và nạp đủ 3 kịch bản phát hiện. **Chạy
một lần trước buổi demo**, không chạy trong lúc trình bày (mất ~2 phút).

```sh
backend/.venv/bin/python scripts/seed_live.py \
  --base-url https://sentinel-web-ryxl.onrender.com
```

> **Lưu ý quan trọng:** script dùng tài khoản `demo@apisentinel.dev`. Nếu
> tài khoản này đã tồn tại, script đăng nhập lại thay vì tạo mới. Kịch bản
> `high_request_volume` dùng **thread pool** để 120 event nằm gọn trong cửa
> sổ 60 giây — nếu gửi tuần tự, event sẽ rải trên ~2 phút và rule sẽ
> **không** fire. Đây là hành vi đúng: rule đếm theo **server receipt
> timestamp**, không theo timestamp do client gửi lên.

### 0.4 Tài khoản dùng trong demo

| Email | Mật khẩu | Vai trò | Dùng để |
|---|---|---|---|
| `demo@apisentinel.dev` | `Sentinel-demo-password-2026!` | owner | Tạo source, thêm thành viên, assign |
| `analyst@apisentinel.dev` | `Sentinel-analyst-2026!` | analyst | Phiên thứ hai: comment, đổi status |
| `outsider@apisentinel.dev` | `Sentinel-outsider-2026!` | không thuộc workspace | Chứng minh chặn truy cập |

> Hãy **mở sẵn 2 trình duyệt** (một normal window, một incognito) để demo
> cộng tác 2 phiên mà không phải đăng xuất/đăng nhập lại.

### 0.5 Danh sách kiểm tra trước khi bắt đầu

- [ ] `curl /health/ready` trả về `"database":"ok"`
- [ ] Smoke check 8/8 PASS
- [ ] Mở <https://sentinel-web-ryxl.onrender.com> — trang login hiện ra
- [ ] Incognito window sẵn sàng cho phiên analyst
- [ ] Terminal mở sẵn tại `/Users/hungle/Desktop/Sentinal_AI`
- [ ] Không có tab nào hiển thị thông tin nhạy cảm (URL Neon có mật khẩu)

---

## 1. Bảng tóm tắt để nói trong 60 giây

> Kịch bản mở đầu. Nói chậm, đủ 60 giây, không đọc nguyên văn.

> "API Sentinel là hệ thống giám sát an ninh API cho các nhóm phát triển nhỏ.
>
> Nó thu thập **metadata của request** từ những API bạn giám sát — không
> lưu body, không lưu header nhạy cảm, không lưu mật khẩu — rồi áp dụng
> **ba quy tắc phát hiện có thể giải thích được**. Mỗi cảnh báo đều trả lời
> được ba câu hỏi: *vì sao rule này fire*, *bằng chứng nào đã được đếm*, và
> *ai đang điều tra nó*.
>
> Phần quan trọng nhất: đây là công cụ **quan sát và điều tra**, không phải
> công cụ chặn. Nó không scan mạng, không đoán mật khẩu, và không bao giờ
> khẳng định một alert là exploit thành công — một IP chỉ là *telemetry*, không
> phải bằng chứng danh tính.
>
> Sản phẩm đang chạy thật trên Render Free Tier với Neon PostgreSQL, tôi sẽ
> demo toàn bộ luồng ngay bây giờ."

---

## 2. Vấn đề và giải pháp

### 2.1 Vấn đề

Một nhóm nhỏ có 3–5 API. Họ cần biết:

1. **API của tôi có bị tấn công không?** — và câu trả lời phải có bằng chứng,
   không phải "có vẻ lạ".
2. **Alert này có thật sự nghiêm trọng không?** — cần nhìn được rule, ngưỡng,
   cửa sổ thời gian và danh sách event cụ thể đã bị đếm.
3. **Team đang xử lý cái gì?** — cần phân công, bình luận, lịch sử, và ai
   đã làm gì.

Các giải pháp thương mại (Datadog Security, Snyk, WAF) giải quyết một phần,
nhưng: nặng, tốn tiền, và **không giải thích được** vì sao rule fire.

### 2.2 Giải pháp của API Sentinel

| Yêu cầu của người dùng | Cách API Sentinel đáp ứng |
|---|---|
| Biết có bị tấn công không | 3 rule tự động, cảnh báo có bằng chứng |
| Hiểu vì sao fire | Alert đóng băng snapshot: rule, count, threshold, window, interval |
| Thấy bằng chứng | Bảng evidence nối tới từng event cụ thể (IP, route, method, status, thời điểm nhận) |
| Điều tra cùng nhau | Assign, comment, history ghi actor + timestamp |
| Không tốn tiền | Postgres + React + FastAPI, chạy trên free tier |
| Tự tin về dữ liệu | Không lưu body/header/password; IP là telemetry, không phải danh tính |

### 2.3 Ranh giới rõ ràng (nói ra để giảng viên thấy bạn hiểu phạm vi)

**Có:** giám sát, phát hiện, giải thích, điều tra, cộng tác.

**Không có (có chủ đích):**
- ❌ Chặn traffic — ngoài phạm vi, sản phẩm giám sát chứ không can thiệp
- ❌ Offensive tooling / network scanner / credential guessing
- ❌ Replay attack vào API thật
- ❌ Thông báo ngoài (email, chat) — chưa có trong release này
- ❌ SSO, machine-learning detection
- ❌ Sửa rule từ UI — threshold đến từ biến môi trường

---

## 3. Kiến trúc

### 3.1 Sơ đồ tổng quan

```
                      trình duyệt
                          │  (cùng origin, session cookie + CSRF)
                          ▼
              ┌───────────────────────┐
              │  web (nginx)          │──▶ phục vụ SPA + proxy
              │  reverse proxy        │    /api/  /ingest/  /health/
              └───────────┬───────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
  ┌────────────┐  ┌─────────────┐   ┌──────────────┐
  │  core API  │  │ ingest API  │   │  detector    │
  │  FastAPI   │  │  FastAPI    │   │  worker      │
  │            │  │             │   │              │
  │ auth       │  │ xác thực    │   │ đánh giá     │
  │ workspaces │  │ source      │   │ rule         │
  │ sources    │  │ validate    │   │ ghi alert +  │
  │ monitoring │  │ lưu event   │   │ evidence     │
  │ điều tra    │  │             │   │              │
  └─────┬──────┘  └──────┬──────┘   └──────┬───────┘
        │                │                 │
        └────────────────┴─────────────────┘
                         ▼
              ┌────────────────────┐
              │  PostgreSQL 16     │  một migration owner
              │  (một instance)     │
              └────────────────────┘
```

### 3.2 Vì sao tách service nhưng dùng chung database?

Đây là câu hỏi giảng viên **rất hay hỏi**. Trả lời thẳng:

> "Ingestion và detection là **hai workload tách biệt**: hai process riêng, hai
> container riêng ở bản Compose, vòng đời restart riêng, health check riêng.
> API ingest có thể restart mà detector không bị ảnh hưởng, detector chậm
> cũng không chặn việc ingest. **Ingestion trả 202 nghĩa là 'đã lưu', không
> phải 'đã phân tích xong'.**
>
> Nhưng chúng **dùng chung một schema**, nên đổi bảng `security_events` là
> phải migrate đồng thời cả hai. Đây là một **đánh đổi có chủ đích** cho dự
> án một người:
>
> - **Nếu database-per-service**: mỗi thay đổi schema là một pipeline
>   migration riêng, phải thiết kế cơ chế giữ alert và evidence nhất quán
>   giữa hai DB, dashboard phải join qua service, và thêm một bề mặt vận
>   hành nữa. Với một team và một schema, đó là rất nhiều máy móc để đổi lấy
>   rất ít cô lập.
> - **Nếu shared persistence**: schema là nguồn sự thật duy nhất, alert và
>   evidence nằm trong **cùng transaction** với event, dashboard aggregate là
>   SQL join thuần. Sự cô lập thực sự cần — process chết, restart, scale
>   độc lập — đã đạt được bằng việc tách workload và entry point.
>
> Nếu sau này cần vòng đời schema độc lập, đường nâng cấp đã rõ: tách bảng
> do ingestion sở hữu ra database riêng trước, rồi publish event qua contract."

### 3.3 Bốn runtime, một entry point

Ở bản local (`compose.yaml`) có **7 service**: `db`, `migrate`, `core`, `ingest`,
`detector`, `web`, `demo`.

Ở bản cloud (Render Free Tier) không có background worker, không có private
service, không có one-off job, nên 4 runtime chạy chung **một container** dưới
dạng **4 OS process riêng**:

| Process | Port trong container |
|---|---|
| `uvicorn sentinel.core.app` | 8000 |
| `uvicorn sentinel.ingest.app` | 8001 |
| `python -m sentinel.detector.worker` | không có |
| `nginx` (SPA + proxy) | `$PORT` |

Migration chạy **trước tiên** trong entrypoint, nên schema owner vẫn là duy
nhất. `alembic upgrade head` là idempotent → restart an toàn.

```bash
# deploy/entrypoint.sh
echo "==> applying the database migrations"
alembic upgrade head

echo "==> starting the Core API on ${CORE_PORT}"
uvicorn sentinel.core.app:create_app --factory --host 0.0.0.0 --port "${CORE_PORT}" &
...
wait -n   # container chết khi bất kỳ process nào chết
```

### 3.4 Những gì **không** nằm trong `common/`

`backend/sentinel/common/` chỉ chứa: contract (DTO Pydantic), persistence
(SQLAlchemy models), session factory, config, clock, security helper. **Không
route logic, không rule logic.** Đây là ranh giới đã được giữ và review được.

---

## 4. Quy tắc phát hiện

### 4.1 Ba rule mặc định

| Rule key | Event được đếm | Ngưỡng | Cửa sổ | Severity |
|---|---|---:|---:|---|
| `failed_login_burst` | event `login_failed` tường minh | 5 | 2 phút | High |
| `high_request_volume` | mọi request event hợp lệ (kể cả login) | 101 | 1 phút | Medium |
| `repeated_access_denial` | HTTP 401/403 **ngoài** luồng login thất bại | 10 | 5 phút | Medium |

Tất cả đều cấu hình được qua biến môi trường
(`SENTINEL_FAILED_LOGIN_BURST_THRESHOLD`, `SENTINEL_HIGH_REQUEST_VOLUME_WINDOW_SECONDS`, …).

### 4.2 Ngữ nghĩa cửa sổ — điểm dễ bị hỏi nhất

```python
def in_detection_window(received_at: datetime, as_of: datetime, window: timedelta) -> bool:
    return as_of - window < received_at <= as_of
```

- Khoảng đếm là **`(t - window, t]`** — nửa mở bên trái, đóng bên phải.
- `t` là **server receipt timestamp** của event đang được đánh giá.
- Đầu bị loại, cuối được tính.

**Đếm tách theo source VÀ theo source IP.** Một burst từ IP này không
bao giờ làm tăng count của IP khác; API thứ hai không bao giờ làm tăng count
của API thứ nhất.

### 4.3 Phát hiện điểm vượt ngưỡng (crossing)

```text
count_before = count_after - 1        (khi trigger đủ điều kiện)
triggered    = count_before < threshold <= count_after
```

Alert **chỉ** được tạo khi count đi từ *dưới* ngưỡng lên *bằng hoặc trên*
ngưỡng. Đây là điểm khác biệt quan trọng so với "gửi alert mỗi khi count
>= ngưỡng" — không spam alert.

### 4.4 Khoảng suppression

Khi tạo alert, `suppressed_until` = receipt time của trigger + 1 cửa sổ rule.
Trong khoảng đó, mọi crossing tiếp theo cho cùng `(rule_key, source_id, source_ip)`
bị bỏ qua.

- Crossing **trong** khoảng suppression bị **loại**, không được xếp hàng giao
  sau.
- Sau khi hết khoảng suppression, cần một **crossing mới** mới sinh alert.
- **Việc con người resolve alert không reset suppression** — detection và
  investigation độc lập.

### 4.5 Timestamp receipt vs timestamp client

Quyết định dùng **server receipt timestamp**, còn timestamp client được giữ
lại làm **evidence**.

Hệ quả: một batch đến trễ được đánh giá như một burst **đến cùng lúc**, nên
alert phản ánh **tốc độ đến**, không phải tốc độ lịch sử. Đây là hành vi được
tài liệu hoá, không phải bug.

> **Chứng minh trong demo:** kịch bản `high_request_volume` gửi 120 event
> **song song**. Nếu gửi tuần tự, chúng rải trên ~2 phút → **không** đủ 101
> event trong 60 giây → rule không fire. Tôi đã gặp đúng lỗi này và đã sửa
> script (xem `docs/implementation-status.md`, Milestone 6).

### 4.6 Độ tin cậy của worker

- Worker claim job bằng `SELECT … FOR UPDATE SKIP LOCKED`, xử lý theo thứ tự
  receipt ổn định.
- Quyết định rule + alert + evidence + hoàn tất job ghi trong **một transaction**.
- Lỗi tạm thời → rollback, job giữ `pending`, tăng attempt, retry **bounded
  backoff** (tối đa 30s).
- Sau `SENTINEL_DETECTOR_MAX_ATTEMPTS` (mặc định 5) → job `failed` với thông
  báo **sanitized** (`TypeName: processing failed`), không bao giờ chứa payload
  hay credential.
- **Khôi phục thủ công** (không tạo alert trùng, nhờ unique constraint
  `(rule_key, trigger_event_id)`):

```sql
UPDATE detector_jobs
SET status = 'pending', attempts = 0, last_error = NULL
WHERE id = '<job id>';
```

---

## 5. Mô hình dữ liệu

### 5.1 Các bảng

| Bảng | Vai trò |
|---|---|
| `users` | Tài khoản, mật khẩu hash Argon2id |
| `sessions` | Session token (chỉ digest), CSRF digest, hạn dùng, revoke |
| `workspaces` | Ranh giới tenant cho source, event, alert |
| `memberships` | User ↔ workspace với role `owner` / `analyst` / `viewer` |
| `api_sources` | API được giám sát, label, key digest, key prefix, trạng thái revoke |
| `security_events` | Metadata request đã lưu, `ingest_seq` là tie-breaker ổn định |
| `detector_jobs` | Một job pending/done/failed cho mỗi event |
| `alerts` | Phát hiện, snapshot trigger đã đóng băng, cửa sổ suppression |
| `alert_evidence` | Liên kết alert ↔ event đã được đếm |
| `alert_comments` | Bình luận điều tra |
| `alert_history` | Thay đổi status/assignee kèm actor và timestamp |
| `detector_heartbeat` | Một dòng, heartbeat cuối cùng của detector |

### 5.2 Invariant quan trọng (đã có test)

| Invariant | Cơ chế |
|---|---|
| Retry event không tạo event/job thứ hai | UNIQUE `(source_id, event_uuid)` |
| Event và job cùng tồn tại | Ghi trong **một transaction** |
| Retry worker không tạo alert trùng | UNIQUE `(rule_key, trigger_event_id)` |
| Evidence không vượt biên workspace/source | Lọc theo `source_id` của chính alert khi đọc |
| Truy vấn event nhanh | Index theo source, source IP, receipt time |
| Phân trang có giới hạn | `limit` nằm trong `[1, 200]`, sort ổn định + ID tie-breaker |

---

## 6. Bảo mật

### 6.1 Xác thực

- Mật khẩu hash bằng **Argon2id** (`argon2-cffi`).
- **Session opaque**, entropy cao, sinh server-side. Chỉ **digest SHA-256**
  được lưu trong DB. Raw token nằm trong cookie `sentinel_session`
  (`HttpOnly`, `SameSite=Lax`, `Secure` khi production).
- Logout **revoke** dòng session. Session hết hạn hoặc bị revoke → từ chối.

### 6.2 CSRF

Double-submit cookie: cookie đọc được `sentinel_csrf` phải được echo lại
trong header `X-CSRF-Token`, và digest lưu trong DB phải khớp. Route đổi
trạng thái còn kiểm tra **same-origin** trên header `Origin`.

### 6.3 Phân quyền — "deny by default"

| Tình huống | HTTP status |
|---|---|
| Không có session / session hỏng | **401** |
| Đã đăng nhập nhưng sai role trong workspace | **403** |
| Đã đăng nhập nhưng **không thuộc** workspace | **404** |

> **404 chứ không phải 403** cho người ngoài workspace: người dùng ngoài
> workspace **không được biết object đó tồn tại**. Đây là chống enumeration.

| Role | Đọc | Comment / Assign / Đổi status | Quản lý member & source |
|---|---|---|---|
| `owner` | ✅ | ✅ | ✅ |
| `analyst` | ✅ | ✅ | ❌ |
| `viewer` | ✅ | ❌ | ❌ |

Chỉ owner hoặc analyst **trong cùng workspace** mới được assign.

### 6.4 Dữ liệu nhạy cảm — không bao giờ lưu

❌ Request/response body · ❌ Header `Authorization`/`Cookie` · ❌ Mật khẩu
thô · ❌ Token · ❌ Ingestion key (chỉ digest)

Contract ingestion dùng `extra="forbid"` → field lạ bị **từ chối**, không bị
bỏ qua âm thầm.

**Route template** phải đến từ router được instrument, không phải raw URL.
Query string và fragment bị từ chối. Body bị giới hạn kích thước **trước khi
parse** (Core 64 KiB, Ingest 32 KiB).

### 6.5 Rate limit

| Endpoint | Mặc định | Biến |
|---|---:|---|
| Login | 10 lần/phút/client | `SENTINEL_LOGIN_RATE_LIMIT_PER_MINUTE` |
| Ingestion | 600 event/phút/source | `SENTINEL_INGESTION_RATE_LIMIT_PER_MINUTE` |

**Không trust forwarding header.** `source_ip` trong event là telemetry do
source xác thực cung cấp, **không phải** đầu vào phân quyền.

---

## 7. Giao diện

### 7.1 Các màn hình

| Màn hình | Đường dẫn | Nội dung |
|---|---|---|
| Login/Register | `/login` | Đăng nhập, đăng ký, đăng xuất |
| Overview | `/` | 4 metric + biểu đồ traffic |
| Event explorer | `/events` | Lọc theo 7 tiêu chí + phân trang |
| Alerts | `/alerts` | Lọc theo status/severity/source |
| Alert detail | `/alerts/{id}` | Evidence, comment, assign, history |
| Sources | `/sources` | Tạo/rotate/revoke key |
| Team | `/team` | Thêm thành viên theo email, đổi role |

### 7.2 Hành vi quan trọng

- **Polling**: Overview 30s, Alerts 15s, cộng nút refresh thủ công.
- **Bucket** biểu đồ: cố định **60 giây**, zero-fill toàn bộ khoảng → khoảng
  im lặng hiện thành khoảng trống, không phải thiếu cột.
- **Alert không phải request.** Evidence chồng lấn **không** được cộng lại
  thành số request. UI ghi rõ điều này ngay dưới biểu đồ.
- **State tách bạch**: loading / error / empty là 3 state khác nhau, state lỗi
  luôn hiện lý do. Refresh hỏng hiện banner thay vì giữ dữ liệu cũ trong im
  lặng.
- **Accessibility**: mọi control có label, bảng dùng `scope` cho header, trạng
  thái hiện bằng **chữ** chứ không chỉ bằng màu, layout responsive.

---

## 8. Demo từng bước

> **Tổng thời gian: ~19 phút.** Mỗi bước có **câu nói** để bạn dùng và
> **điều cần chứng minh** để giảng viên tự kiểm.

---

### BƯỚC 1 — Mở đầu & kiến trúc (2 phút)

**Câu nói:**
> "Trước khi vào giao diện, tôi xin nói về kiến trúc. Có bốn runtime tách
> biệt: một reverse proxy phục vụ React, Core API xử lý tài khoản và điều
> tra, Ingestion API xác thực source rồi lưu event, và detector worker chạy
> rule. Tất cả dùng chung một PostgreSQL. Ở bản local chúng là 7 container
> riêng trong Compose; ở bản cloud Render Free Tier không có background
> worker nên 4 runtime chạy chung một container dưới dạng 4 process riêng —
> logic tách service vẫn nguyên."

**Mở file để giảng viên xem:** `deploy/entrypoint.sh` (4 process), `compose.yaml` (7 service).

---

### BƯỚC 2 — Đăng nhập & tạo workspace (1 phút)

**Thao tác:**
1. Mở <https://sentinel-web-ryxl.onrender.com>
2. Đăng nhập `demo@apisentinel.dev` / `Sentinel-demo-password-2026!`

**Cần chứng minh:** thanh header hiện đúng email + tên workspace. Chọn
workspace khác trong dropdown sẽ đổi toàn bộ dữ liệu — đó là ranh giới
tenant.

**Nói thêm nếu giảng viên hỏi về đăng ký:**
> "Đăng ký cũng dùng chính API đó — `POST /api/auth/register`. Mật khẩu hash
> Argon2id, session opaque chỉ lưu digest."

---

### BƯỚC 3 — Overview: metric thật từ PostgreSQL (2 phút)

**Thao tác:** Bấm **Overview**.

**Cần chứng minh:**

| Metric | Giá trị (đo lúc 19/11/2026, 18:44) |
|---|---|
| Total requests | 470 |
| Failed logins | 6 |
| Access denials | 12 |
| Open alerts | 3 (tổng 4 alert) |

> Con số tăng theo mỗi lần chạy demo — đó là **đúng**, vì mọi lần nạp dữ
> liệu đều tạo event thật trong PostgreSQL. Nếu bạn muốn con số đúng như
> tài liệu này, chạy `scripts/seed_live.py` **một lần** ngay trước buổi demo
> và dùng đúng các số đó. Nếu không, chỉ cần nói *"con số này tăng dần theo
> mỗi lần demo vì dữ liệu là thật"* — đó là một điểm cộng.

**Điểm cần nói (quan trọng):**
> "Những con số này là aggregate thật từ PostgreSQL, không hard-code. Và
> chú ý dòng ghi chú dưới biểu đồ: *'Alerts are investigation findings, not
> requests, and overlapping alert evidence is not summed into a request count.'*
> Đây là một lỗi rất dễ mắc — đếm alert thành request, hoặc cộng evidence
> chồng lấn thành số request duy nhất. Sản phẩm này tách hai khái niệm đó
> rõ ràng."

**Thử thêm:** đổi Time range (15 phút → 24 giờ → 7 ngày), đổi Source. Biểu đồ
và metric cập nhật. Bấm **Refresh** thủ công.

---

### BƯỚC 4 — Event explorer: dữ liệu thật đi qua pipeline (2 phút)

**Thao tác:**
1. Bấm **Events** → thấy bảng event (IP, route, method, status, duration, type).
2. Lọc **Source IP** = `198.51.100.50` → bấm **Apply filters**.

**Cần chứng minh:** còn đúng **6/6** event, tất cả `login_failed` từ
`Login Gateway`, route `/api/auth/login`.

**Nói:**
> "Những event này đi qua đúng đường production: HTTP POST `/ingest/v1/events`
> với `X-Source-Key` → validate → ghi vào `security_events` **cùng transaction**
> với `detector_jobs`. Tôi đã query trực tiếp Neon để đối chiếu — count
> trong DB khớp chính xác với những gì UI hiển thị."

**Thử thêm:** lọc theo Route, Method, Status, Event Type; bấm **Reset filters**.

---

### BƯỚC 5 — Ba rule đã fire (2 phút)

**Thao tác:** Bấm **Alerts**.

**Cần chứng minh:**

| Rule | Count / Threshold | Window | Severity | IP |
|---|---|---:|---|---|
| `high_request_volume` | 101 / 101 | 60s | Medium | 198.51.100.99 |
| `repeated_access_denial` | 10 / 10 | 300s | Medium | 198.51.100.88 |
| `failed_login_burst` | 5 / 5 | 120s | High | 198.51.100.50 |

> Danh sách có thể có **4 alert** nếu bạn đã chạy phép kiểm chứng ngưỡng ở
> [Bước 5b](#bước-5b--đối-chứng-dưới-ngưỡng-không-fire-1-phút--bằng-chứng-rule-đúng)
> (thêm một `high_request_volume` từ IP `198.51.100.199`). Đó là bình
> thường — mỗi lần chạy kiểm chứng dùng IP mới để không bị suppression.

**Nói:**
> "Cả ba rule đều fire đúng **ngưỡng**, không phải vượt ngưỡng — vì rule chỉ
> tạo alert tại điểm vượt ngưỡng, tức count trước < ngưỡng ≤ count sau.
> Ba kịch bản dùng **source IP khác nhau** để mỗi alert là không nhập nhằng."

---

### BƯỚC 5b — Đối chứng: dưới ngưỡng KHÔNG fire (1 phút) ⭐ *bằng chứng rule đúng*

> Đây là bước phân biệt sản phẩm này với một hệ thống cảnh báo "có event là
> báo động". Chạy trước khi demo, dùng IP riêng cho từng ca.

**Thao tác (Terminal):**

```sh
backend/.venv/bin/python - <<'PY'
import sys, uuid, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "scripts")
from seed_live import Client

BASE = "https://sentinel-web-ryxl.onrender.com"
c = Client(BASE)
c.post("/api/auth/login", body={
    "email": "demo@apisentinel.dev",
    "password": "Sentinel-demo-password-2026!"})
ws = c.get("/api/workspaces")[1][0]["id"]
h = {"X-Workspace-Id": ws}
partner = [s for s in c.get("/api/sources", headers=h)[1]
           if s["label"] == "Partner API"][0]
key = c.post_csrf(f"/api/sources/{partner['id']}/rotate", headers=h)[1]["ingestion_key"]

def burst(ip, n, route):
    def send(i):
        Client(BASE).post("/ingest/v1/events", body={
            "event_id": str(uuid.uuid4()), "event_type": "request",
            "occurred_at": "2026-01-01T00:00:00Z", "source_ip": ip,
            "route_template": route, "method": "GET", "status_code": 200,
            "duration_ms": 3}, headers={"X-Source-Key": key})
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(send, range(n)))

burst("198.51.100.201", 100, "/api/under-volume")   # 100 < 101
burst("198.51.100.202",   4, "/api/under-login")    #   4 <   5
burst("198.51.100.203",   9, "/api/under-denial")   #   9 <  10

print("submitted, waiting 25s for the detector...")
time.sleep(25)
alerts = c.get("/api/alerts?limit=200", headers=h)[1]
for ip, label in [("198.51.100.201", "volume 100/101"),
                  ("198.51.100.202", "login   4/5"),
                  ("198.51.100.203", "denial  9/10")]:
    hit = [a for a in alerts if a["source_ip"] == ip]
    print(f"  {label:14} -> {'ALERT FIRED (WRONG)' if hit else 'no alert (correct)'}")
PY
```

**Kết quả thật đã đo:**

```
  volume 100/101 -> no alert (correct)
  login    4/5   -> no alert (correct)
  denial   9/10  -> no alert (correct)
```

**Nói:**
> "Đây là phần tôi muốn giảng viên chú ý nhất. 100 event dưới ngưỡng 101,
> 4 dưới ngưỡng 5, 9 dưới ngưỡng 10 — **không cái nào sinh alert**. Rule so
> sánh ngưỡng thật, không phải 'có event là báo động'. Và nhớ lại ở trên:
> 101 event trong cửa sổ 60 giây **mới** fire. Vậy ngưỡng được áp dụng đúng
> ở cả hai chiều."

**Sau bước này:** quay lại tab **Alerts** và bấm **Refresh** — danh sách vẫn
chỉ có 3 alert (cộng các alert từ kịch bản khác). Đó chính là bằng chứng
trực quan cho điều trên.

---

### BƯỚC 6 — Evidence: vì sao rule fire (3 phút) ⭐ *phần quan trọng nhất*

**Thao tác:** Bấm vào alert `failed_login_burst`.

**Cần chứng minh — "Why this fired":**

| Trường | Giá trị |
|---|---|
| RULE CONDITION | `failed_login_burst` |
| ACTUAL COUNT | 5 |
| THRESHOLD | 5 |
| WINDOW | 120 seconds |
| INTERVAL START | 18:13:46 19/11/2026 |
| INTERVAL END | 18:15:46 19/11/2026 |
| SOURCE | `e31ded00-1d36-4355-9bee-d048f64b6b42` |

**Và bảng Evidence (5)** — mỗi dòng là một event cụ thể:

```
Received              IP              Route            Method  Status  Type
18:15:42 19/11/2026   198.51.100.50   /api/auth/login  POST    401     login_failed
18:15:43 19/11/2026   198.51.100.50   /api/auth/login  POST    401     login_failed
18:15:44 19/11/2026   198.51.100.50   /api/auth/login  POST    401     login_failed
18:15:45 19/11/2026   198.51.100.50   /api/auth/login  POST    401     login_failed
18:15:46 19/11/2026   198.51.100.50   /api/auth/login  POST    401     login_failed
```

**Nói (đây là điểm bán hàng chính):**
> "Đây là phần phân biệt sản phẩm này với một hệ thống cảnh báo thông thường.
> Alert **đóng băng snapshot** tại thời điểm trigger: count, threshold, window,
> interval, source. Tôi có thể trả lời chính xác *vì sao* rule này fire, và
> chỉ ra **từng event** đã được đếm. Nếu traffic tiếp tục, count trong DB sẽ
> tăng, nhưng count trên alert vẫn là 5 — vì nó là snapshot của thời điểm
> phát hiện.
>
> Và lưu ý mốc thời gian: `Received` là **server receipt time** (18:15:42 →
> 18:15:46, cách nhau ~1 giây), còn `request_at` trong API là timestamp
> client. Cửa sổ 120 giây được tính trên receipt time."

---

### BƯỚC 7 — Điều tra: assign + comment + đổi status (2 phút)

**Thao tác (trên cùng alert):**
1. Bấm **Move to investigating** → badge đổi sang `Investigating`.
2. Chọn **ASSIGN TO** → `Demo Owner (owner)`.
3. Gõ vào ô comment: *"Xác nhận burst đăng nhập thất bại từ IP 198.51.100.50 trên Login Gateway."*
   → bấm **Post comment**.
4. Bấm **Move to resolved**.

**Cần chứng minh — History:**

```
status changed      new → investigating        Demo Owner · 18:24:00
commented                                 Demo Owner · 18:24:11
assignee changed     — → 1da704b1-…            Demo Owner · 18:24:18
status changed      investigating → resolved  Demo Owner · 18:24:23
```

**Và sau khi resolve:**
> "This alert is in a terminal status and can no longer change."

**Nói:**
> "Mọi thay đổi đều ghi **actor** và **timestamp**. Người khác đăng nhập vào sẽ
> thấy đúng lịch sử này. Và lưu ý: resolve alert **không** reset khoảng
> suppression của detector — việc con người điều tra độc lập với việc phát
> hiện."

---

### BƯỚC 8 — Cộng tác 2 phiên (2 phút) ⭐ *phần khác biệt nhất*

**Thao tác:**
1. Chuyển sang **cửa sổ incognito** → đăng nhập `analyst@apisentinel.dev` /
   `Sentinel-analyst-2026!`.
2. Mở alert `repeated_access_denial`.
3. Bấm **Move to investigating**.
4. Post một comment khác.

**Cần chứng minh:**
- Analyst thấy **đầy đủ** alert, evidence, và dropdown **ASSIGN TO** liệt kê cả
  owner lẫn analyst.
- Comment của owner vẫn còn (dữ liệu chung workspace).
- History bây giờ hiện **cả hai actor**:
  ```
  status changed   new → investigating     Ana Analyst · 18:25:50
  commented                               Ana Analyst · 18:25:48
  ```

**Nói:**
> "Đây là workflow điều tra **dùng chung**, không phải chat của từng người.
> Hai phiên, hai người khác nhau, cùng một alert, lịch sử gộp lại."

---

### BƯỚC 9 — Chặn truy cập: outsider & anonymous (2 phút) ⭐ *chứng minh security*

**Thao tác:** mở Terminal.

**Cần chứng minh — outsider (không thuộc workspace):**

```sh
backend/.venv/bin/python - <<'PY'
import sys; sys.path.insert(0,"scripts")
from seed_live import Client
c = Client("https://sentinel-web-ryxl.onrender.com")
c.post("/api/auth/register", body={
    "email":"outsider@apisentinel.dev",
    "password":"Sentinel-outsider-2026!",
    "display_name":"Otto Outsider"})
c.post("/api/auth/login", body={
    "email":"outsider@apisentinel.dev",
    "password":"Sentinel-outsider-2026!"})
ws = "234abda7-82a7-4ade-80ee-5983ac9ef6b1"
h = {"X-Workspace-Id": ws}
print("alerts       :", c.get("/api/alerts", headers=h)[0])
print("alert detail :", c.get("/api/alerts/9a0bcff1-…", headers=h)[0])
print("comments     :", c.post_csrf("/api/alerts/9a0bcff1-…/comments",
                                    body={"body":"x"}, headers=h)[0])
print("sources      :", c.get("/api/sources", headers=h)[0])
print("events       :", c.get("/api/events", headers=h)[0])
PY
```

**Kết quả thật đã đo:**

```
alerts       : 404
alert detail : 404
comments     : 404
sources      : 404
events       : 404
```

**Và anonymous (không đăng nhập):**

```sh
backend/.venv/bin/python - <<'PY'
import sys; sys.path.insert(0,"scripts")
from seed_live import Client
c = Client("https://sentinel-web-ryxl.onrender.com")
ws = "234abda7-82a7-4ade-80ee-5983ac9ef6b1"
print("alerts :", c.get("/api/alerts", headers={"X-Workspace-Id": ws})[0])
print("me     :", c.get("/api/auth/me")[0])
PY
```

```
alerts : 401
me     : 401
```

**Nói:**
> "Người ngoài workspace nhận **404**, không phải 403 — vì họ không được biết
> object đó tồn tại. Không có session thì **401**. Tất cả scope áp dụng đồng
> đều cho metrics, evidence, comment và history."

---

### BƯỚC 10 — Sources: key hiển thị đúng 1 lần (1 phút)

**Thao tác:** Bấm **Sources**.

**Cần chứng minh:**

| Label | Key prefix | State |
|---|---|---|
| Demo API | `sn_cbec86` | Active |
| Login Gateway | `sn_a660d7` | Active |
| Partner API | `sn_4236cc` | Active |

**Nói:**
> "Chỉ có **prefix** được hiển thị. Raw key chỉ hiện **một lần** khi tạo hoặc
> rotate. Server chỉ lưu digest của key — dù lộ database cũng không dựng lại
> được key để giả mạo source. Rotate là **atomic**: key cũ chết ngay lập tức."

---

### BƯỚC 11 — Team & phân quyền (1 phút)

**Thao tác:** Bấm **Team**.

**Cần chứng minh:** 2 thành viên — `Demo Owner` (owner), `Ana Analyst`
(analyst). Có form thêm thành viên theo email có sẵn với role chọn được.

**Nói:**
> "Owner quản lý member và source, và có thể điều tra. Analyst đọc và điều tra
> được nhưng không quản lý được. Viewer chỉ đọc — không comment, không assign,
> không đổi status. Chỉ owner hoặc analyst **trong cùng workspace** mới được
> assign."

---

### BƯỚC 12 — Đóng lại: bằng chứng kiểm thử (2 phút)

**Câu nói chuyển mood:**
> "Trước khi kết thúc, đây là bằng chứng rằng đây không phải một prototype."

**Mở file `docs/implementation-status.md`** và chỉ vào bảng kết quả.

**Số liệu:**

| Hạng mục | Kết quả |
|---|---|
| Test backend (pytest) | **73 test** trong 6 file — 21 core API, 14 rule, 12 ingest, 10 detector, 9 DB, 5 investigation (+2 test được parametrized) |
| Test frontend (Vitest) | 6 test |
| Test trình duyệt (Playwright) | **6/6** scenario |
| CI jobs | **5/5 xanh** trên GitHub Actions |
| LOC | Backend 3.331 · Frontend 2.628 · Test 1.722 · Script 1.592 |

**6 scenario Playwright** (mở `frontend/e2e/app.spec.ts`):
1. registration, workspace and source setup
2. an ordinary ingested event appears in the event explorer
3. event filters narrow the result set
4. the three detection rules raise alerts with evidence
5. two members investigate an alert together and the history persists
6. a signed-in non-member cannot reach the workspace data

**Nói:**
> "Scenario 4 và 5 chính là những gì tôi vừa demo thủ công — nhưng bằng
> Playwright, chạy tự động, trên một stack test biệt lập với database rỗng."

---

## 9. Kịch bản dự phòng (khi có sự cố)

| Sự cố | Dấu hiệu | Xử lý |
|---|---|---|
| Render đang ngủ | Trang trắng, chờ > 30s | `curl /health/ready` để đánh thức, đợi ~60s, thử lại |
| Neon autoscale | API trả 503 lúc đầu | Đợi 10s, thử lại — Neon tự resume |
| Detector chậm | Alert chưa xuất hiện | Đợi 5–15s rồi bấm **Refresh**; kiểm tra `GET /health/detector` |
| Muốn dữ liệu mới | Alert cũ đã resolve | Chạy lại `scripts/seed_live.py` (tạo thêm scenario với IP khác) |
| Muốn demo offline | Mạng yếu | Dùng bản local: `docker compose --profile demo up --build --wait` → <http://localhost:8080> |

**Lệnh kiểm tra nhanh từng thành phần:**

```sh
curl -s https://sentinel-web-ryxl.onrender.com/health/live
curl -s https://sentinel-web-ryxl.onrender.com/health/ready
curl -s https://sentinel-web-ryxl.onrender.com/health/detector
```

**Nếu cần dựng lại stack local hoàn toàn:**

```sh
cp .env.example .env
docker compose --profile demo up --build --wait --wait-timeout 120
python3 scripts/demo.py --scenario all
python3 scripts/smoke.py
```

---

## 10. Bằng chứng đã kiểm chứng

### 10.1 Smoke check trên production (8/8)

```
PASS  browser url: status 200
PASS  proxy /health/live: status 200
PASS  proxy /health/ready: status 200 (database: ok)
PASS  core /health/live: status 200
PASS  core /health/ready: status 200
PASS  ingest /health/live: status 200
PASS  ingest /health/ready: status 200
PASS  detector heartbeat: {"status": "ok", "service": "detector"}
smoke check passed
```

### 10.2 Kết quả demo trên production (đo ngày 2026-11-19)

```
PASS  register demo@apisentinel.dev (201)
PASS  workspace "Demo Workspace"
PASS  three sources created (Demo API, Login Gateway, Partner API)
PASS  ordinary traffic persisted and listed in the event explorer
PASS  failed_login_burst     count 5/5     window 120s  severity high
PASS  high_request_volume    count 101/101 window 60s   severity medium
PASS  repeated_access_denial count 10/10   window 300s  severity medium
PASS  alert detail shows the rule condition, the frozen count, the interval
      and the linked evidence rows
PASS  status new -> investigating -> resolved recorded with the actor
PASS  assignment to a workspace owner persisted
PASS  comment persisted and visible after reload
PASS  a second session (analyst@apisentinel.dev, role analyst) saw the same
      alert, commented and moved it to investigating
PASS  outsider@apisentinel.dev received 404 for alerts, alert detail,
      comments, sources and events
PASS  anonymous requests received 401
```

### 10.3 Kiểm chứng ngưỡng trên production (đo ngày 2026-11-19)

Đã chạy trực tiếp trên `https://sentinel-web-ryxl.onrender.com`, dùng **IP
hoàn toàn mới** cho mỗi lần để loại trừ ảnh hưởng của suppression:

**Vượt ngưỡng — crossing chính xác tại ngưỡng:**

```
110 event song song từ IP 198.51.100.199
FRESH CROSSING OK: count=101/101 window=60s
```

**Dưới ngưỡng — phải KHÔNG fire:**

| Kịch bản | Số event | Ngưỡng | Kết quả |
|---|---:|---:|---|
| Volume | 100 | 101 | ✅ không có alert |
| Login burst | 4 | 5 | ✅ không có alert |
| Access denial | 9 | 10 | ✅ không có alert |

Đây là bằng chứng quan trọng nhất về tính đúng đắn của rule: **rule so sánh
ngưỡng thật**, không phải "có event là sinh alert". Một hệ thống cảnh báo
naive sẽ fire ở cả 3 trường hợp dưới ngưỡng.

### 10.4 CI pipeline

<https://github.com/manhhungle2906/sentinal/actions/runs/44507587620>

```
PASS  Compose validation
PASS  Browser checks
PASS  Frontend checks
PASS  Backend checks
PASS  Full verification gate
```

### 10.5 Một lỗi thật đã tìm và sửa trong quá trình deploy

> **Đây là câu chuyện đáng kể — nên kể nếu giảng viên hỏi về kinh nghiệm
> thực tế.**

**Triệu chứng:** deploy fail ở bước `alembic upgrade head`:

```
OperationalError: connection to server at "2600:1f16:555:9621:c1fd:73cf:753e:5e0",
port 5432 failed: Network is unreachable
```

**Phân tích:** Neon publish **cả IPv4 và IPv6** cho pooled endpoint. Render Free
Tier **không có IPv6 route**, nên hostname resolve ra IPv6 và connect fail.

**Sửa:** resolve hostname ra IPv4 một lần lúc start-up, truyền vào libpq qua
`hostaddr`, **nhưng vẫn giữ `host` là domain** để TLS SNI và kiểm tra
certificate vẫn hoạt động:

```python
# backend/sentinel/common/db.py
def ipv4_connect_args(database_url: str) -> dict[str, str]:
    """Pin the IPv4 address when the host also publishes an IPv6 record."""
    ...
    return {"hostaddr": address}
```

Áp dụng cùng cách cho `backend/alembic/env.py`. Có **9 test hồi quy** trong
`tests/test_db.py`.

**Sau đó** deploy fail tiếp ở credential → đã reset mật khẩu Neon và cập
nhật `SENTINEL_DATABASE_URL` trong Render Environment.

### 10.6 Vì sao `high_request_volume` ban đầu không fire

> Cũng là một câu chuyện hay — cho thấy hiểu đúng ngữ nghĩa rule.

**Triệu chứng:** script seed gửi 104 event, alert không bao giờ xuất hiện.

**Phân tích:** rule đếm theo **server receipt timestamp**. 104 HTTP round-trip
tuần tự rải trên ~2 phút → chỉ 68 event nằm trong cửa sổ 60 giây → không đủ
101.

**Sửa:** `scripts/seed_live.py` dùng thread pool có giới hạn để event nằm gọn
trong cửa sổ. **Đây không phải bug của sản phẩm** — đây là hành vi đúng đắn
đã được tài liệu hoá: rule phản ánh **tốc độ đến**, không phải lịch sử.

---

## 11. Giới hạn đã biết

Nói thẳng, không giấu. Giảng viên sẽ tôn trọng sự trung thực hơn là bị phát
hiện sau.

| Giới hạn | Ảnh hưởng | Hướng xử lý |
|---|---|---|
| Detector là **một** worker | Không scale ngang được đường detect | Cần test thứ tự + concurrency cho multi-replica |
| Không có rule editor trên UI | Threshold đến từ biến môi trường | Config-as-code là chuẩn; có thể thêm UI sau |
| Không có notification ngoài | Team phải mở dashboard | Tích hợp email/webhook là bước tiếp theo tự nhiên |
| Render free tier spin-down 15 phút | Cold start ~1 phút | Nâng cấp paid là đủ |
| Neon autoscale khi rảnh | Query đầu tiên có thì chậm | Tự resume, không cần code |
| Không có SSO / ML detection | Đúng phạm vi bài toán | Ngoài release này |
| **Không chặn traffic** | Chỉ quan sát | Đúng phạm vi — giám sát ≠ can thiệp |

---

## 12. Hỏi đáp dự kiến

### Q1. "Vì sao dùng chung database mà không tách database cho từng service?"

Trả lời ở [mục 3.2](#32-vì-sao-tách-service-nhưng-dùng-chung-database). Tóm
tắt: ingestion và detection là workload tách biệt thật sự (restart độc lập,
health riêng, `202` = đã lưu chứ không phải đã phân tích). Shared
persistence là **đánh đổi có chủ đích**: schema là nguồn sự thật duy nhất,
alert + evidence nằm cùng transaction với event, dashboard là SQL join thuần.
Database-per-service sẽ đòi hỏi pipeline migration, cross-service consistency
và thêm một bề mặt vận hành — quá nhiều máy móc cho một schema, một team.

### Q2. "Alert có nghĩa là bị tấn công không?"

**Không.** Alert nghĩa là "một mẫu hành vi đã vượt ngưỡng cấu hình". `source_ip`
là telemetry do chính API được giám sát cung cấp — nó có thể bị giả mạo nếu
API đó proxy lại traffic. Vì vậy tài liệu ghi rõ: *một IP không bao giờ là bằng
chứng danh tính*, và sản phẩm không bao giờ khẳng định exploit thành công.

### Q3. "Xử lý race condition thế nào khi nhiều event đến cùng lúc?"

Ba lớp:
1. **Đếm ổn định** — event cùng receipt time được sắp theo `ingest_seq` tăng
   dần; khi đầu cửa sổ bằng receipt time của trigger, chỉ những row có seq ≤
   trigger được đếm. Worker và event query luôn thống nhất.
2. **Idempotent write** — UNIQUE `(rule_key, trigger_event_id)` chặn alert trùng.
   UNIQUE `(source_id, event_uuid)` chặn event trùng.
3. **Claim job** — `SELECT … FOR UPDATE SKIP LOCKED` để nhiều worker không giật
   cùng một job (dù release này chỉ chạy 1 worker, cơ chế đã có sẵn).

### Q4. "Nếu detector chết giữa chừng thì sao?"

- Job và event nằm cùng transaction → không bao giờ có job trỏ tới event không
  tồn tại, cũng không có event accepted mà mất job.
- Lỗi tạm → rollback, job giữ `pending`, retry với backoff.
- Vượt số lần retry → `failed` + thông báo sanitized, kèm câu SQL khôi phục
  thủ công đã ghi trong tài liệu.
- Vì alert creation idempotent, requeue job **không** tạo alert trùng.
- Khi container restart, job `pending` được claim lại — **không event accepted
  nào bị mất**.

### Q5. "CSRF và CORS khác nhau thế nào?"

CORS kiểm soát **trình duyệt ở domain khác** có được đọc response hay không.
CSRF bảo vệ **request gửi từ domain đã tin cậy** — trình duyệt tự gửi cookie
kèm theo. Ở đây frontend và API cùng origin nên CORS không cần, nhưng CSRF
**vẫn cần**: nếu không có nó, một trang độc hại ở domain khác có thể gửi
`POST` vào API Sentinel bằng cookie của người dùng. Đây là lý do sản phẩm
dùng double-submit cookie **kèm** kiểm tra same-origin.

### Q6. "Vì sao dùng opaque session thay vì JWT?"

JWT không thu hồi được — token đã ký vẫn hợp lệ đến khi hết hạn. Với hệ
thống điều tra nội bộ, cần **thu hồi ngay lập tức** khi người dùng bị
disable hoặc khi phát hiện session bị lộ. Vì vậy token lưu server-side (chỉ
digest trong DB), revoke được bằng một `UPDATE`.

### Q7. "Dashboard lấy số liệu thế nào, có phải hard-code không?"

Không. Aggregate thật từ PostgreSQL: tổng request, số login thất bại, số
access denial, số alert mở, và bucket traffic cố định 60 giây có zero-fill
toàn bộ khoảng. Alert **không** được tính vào request, và evidence chồng lấn
**không** được cộng lại thành số request duy nhất.

### Q8. "Sản phẩm này có chặn được tấn công không?"

Không, và đó là ranh giới có chủ đích. Nó giám sát và giải thích. Để chặn
traffic bạn cần một WAF ở đường vào, và alert của Sentinel là thứ giúp bạn
**quyết định** có nên bật chặn hay không.

### Q9. "Đọc được dữ liệu của khách hàng thật không?"

Không. Chỉ metadata từ allowlist: source id, event uuid, receipt time, request
time, source IP, route template, method, status, duration, event type. **Không**
body, **không** `Authorization`/`Cookie`, **không** mật khẩu, **không** token.
Contract ingestion `extra="forbid"` nên field lạ bị từ chối. IP được lưu để
đếm theo IP và để điều tra; nó là telemetry, và tài liệu mô tả cách xoá theo
chính sách retention mà không làm orphan evidence.

### Q10. "Chạy được trên hạ tầng của tôi không?"

Có. `compose.yaml` dựng đủ 7 service. Yêu cầu: Docker Compose v2 + PostgreSQL
16. Nếu muốn lên cloud, `render.yaml` là Blueprint cho Render; hướng dẫn
chi tiết (HTTPS, biến môi trường, managed DB, migration, health, smoke) ở
`docs/deployment.md`.

### Q11. "Bao lâu để dựng lại từ đầu?"

- Local: `cp .env.example .env && docker compose --profile demo up --build --wait`
  → khoảng 3–5 phút (build ảnh lần đầu).
- Cloud: push + Render Blueprint → khoảng 5–8 phút (build + migrate + start).
- Verify: `python3 scripts/smoke.py` → dưới 10 giây.

### Q12. "Điều gì sẽ làm tiếp nếu có thêm thời gian?"

Theo thứ tự ưu tiên:
1. **Notification** (email/webhook) — khoảng trống lớn nhất trong trải nghiệm
   hiện tại: alert mới không tự đến với team.
2. **Multi-replica detector** — cần test thứ tự và concurrency, đã là khoảng
   trống đã biết.
3. **Rule editor trên UI** — hiện threshold là config-as-code.
4. **Read replica** cho các truy vấn monitoring khi database thành nút thắt.

---

## Phụ lục A — Lệnh đầy đủ để dựng lại từ số 0

```sh
# ---------- LOCAL ----------
cd /Users/hungle/Desktop/Sentinal_AI
cp .env.example .env                              # không ghi đè .env cũ
docker compose --profile demo config --quiet      # validate
docker compose --profile demo up --build --wait --wait-timeout 120
python3 scripts/smoke.py                          # 8/8
python3 scripts/demo.py --scenario all            # nạp dữ liệu demo
# mở http://localhost:8080  →  demo-owner@example.com / demo-owner-password

# ---------- VERIFY ----------
python3 scripts/verify.py --suite backend        # ruff + pytest
python3 scripts/verify.py --suite frontend       # lint + typecheck + vitest + build
python3 scripts/verify.py --suite e2e            # playwright
python3 scripts/verify.py --suite all            # full gate

# ---------- CLOUD ----------
git push -u origin main
# Render Dashboard → New → Blueprint → chọn repo → path render.yaml
#   SENTINEL_DATABASE_URL = postgresql+psycopg://…
#   SENTINEL_SECRET_KEY   = python3 -c "import secrets; print(secrets.token_urlsafe(48))"

backend/.venv/bin/python scripts/smoke.py \
  --base-url https://sentinel-web-ryxl.onrender.com \
  --core-url https://sentinel-web-ryxl.onrender.com \
  --ingest-url https://sentinel-web-ryxl.onrender.com

backend/.venv/bin/python scripts/live_check.py \
  --base-url https://sentinel-web-ryxl.onrender.com
```

## Phụ lục B — Danh sách file quan trọng khi giảng viên yêu cầu mở code

| Chủ đề | File |
|---|---|
| Quy tắc phát hiện & ngữ nghĩa cửa sổ | `backend/sentinel/detector/rules.py` |
| Worker, transaction, suppression, retry | `backend/sentinel/detector/worker.py` |
| Ingestion contract & validate | `backend/sentinel/ingest/routers/events.py` |
| Auth, session, Argon2id | `backend/sentinel/core/routers/auth.py`, `backend/sentinel/common/security.py` |
| Phân quyền theo workspace | `backend/sentinel/core/deps.py` |
| Điều tra alert (status/assign/comment/history) | `backend/sentinel/core/routers/investigation.py` |
| Model & constraint DB | `backend/sentinel/common/models.py` |
| Migration (duy nhất) | `backend/alembic/versions/e00bbf48a74e_initial_schema.py` |
| Sửa IPv6 (bài học deploy) | `backend/sentinel/common/db.py` |
| Frontend HTTP client | `frontend/src/api/client.ts` |
| Trang alert (evidence/comment/history) | `frontend/src/pages/AlertDetailPage.tsx` |
| Test trình duyệt | `frontend/e2e/app.spec.ts` |
| CI | `.github/workflows/ci.yml` |
| Entry point cloud | `deploy/entrypoint.sh` |

## Phụ lục C — Tài liệu trong repo

| File | Nội dung |
|---|---|
| `README.md` | Tổng quan, quick start, lệnh, security model |
| `docs/architecture.md` | Service, data model, **ngữ nghĩa rule**, config, data handling |
| `docs/deployment.md` | HTTPS, biến môi trường, managed DB, migration, health, smoke |
| `docs/implementation-status.md` | **Milestone + kết quả thực tế của từng lệnh** |
| `docs/presentation-guide.md` | File này |

---

*Tài liệu này được cập nhật ngày 2026-11-19. Mọi số liệu đã kiểm chứng trên
production tại `https://sentinel-web-ryxl.onrender.com` và đối chiếu trực tiếp
với dữ liệu trong Neon PostgreSQL.*
