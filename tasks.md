# Tasks — Day 08 LangGraph Lab

## Phase 1 — Core Graph (45 pts)

### T1 · `state.py` — Xác nhận schema (dễ, ~5 min)
- [x] Kiểm tra các field dùng `Annotated[list, add]` (append-only): `messages`, `tool_results`, `errors`, `events` — đã đúng, không cần sửa.
- [x] Thêm field `evaluation_result: str | None` nếu chưa có — đã có, OK.

### T2 · `nodes.py` — Implement classify_node (quan trọng nhất)
- [x] Bổ sung keyword đầy đủ theo bảng ưu tiên:
  - **risky** (ưu tiên cao nhất): `refund`, `delete`, `send`, `cancel`, `remove`, `revoke`
  - **tool**: `status`, `order`, `lookup`, `check`, `track`, `find`, `search`
  - **missing_info**: query < 5 từ có đại từ mơ hồ (`it`, `this`, `that`)
  - **error**: `timeout`, `fail`, `error`, `crash`, `unavailable`
  - **simple**: mặc định
- [x] Đảm bảo kiểm tra `risky` trước `tool` (tránh conflict "check order" vs "refund order").
- [x] Dùng word-boundary matching (strip punctuation trước khi so sánh).

### T3 · `nodes.py` — Các node còn lại
- [x] `evaluate_node`: logic hiện tại (check `"ERROR"` trong tool result) đã đủ — giữ nguyên.
- [x] `retry_or_fallback_node`: tăng `attempt` — đã đúng, giữ nguyên.
- [x] `dead_letter_node`: log rõ scenario_id và attempt — đã đủ.
- [x] `answer_node`: ground answer vào `tool_results[-1]` và `approval` nếu có — đã đủ cho lab.
- [x] `approval_node`: mock `approved=True` mặc định — đã đúng cho CI.

### T4 · `routing.py` — Kiểm tra logic
- [x] `route_after_classify`: mapping đầy đủ 5 route → node — đã đúng.
- [x] `route_after_retry`: `attempt >= max_attempts` → `dead_letter`, else → `tool` — đã đúng.
- [x] `route_after_evaluate`: `needs_retry` → `retry`, else → `answer` — đã đúng.
- [x] `route_after_approval`: `approved` → `tool`, else → `clarify` — đã đúng.

### T5 · `graph.py` — Kiểm tra wiring
- [x] Xác nhận tất cả path đều kết thúc tại `finalize → END`.
- [x] Kiểm tra path `error`: `classify → retry → tool → evaluate → [retry loop | answer] → finalize`.
- [x] Kiểm tra path `risky`: `classify → risky_action → approval → tool → evaluate → answer → finalize`.
- [x] Kiểm tra S07 (max_attempts=1): `retry → route_after_retry` phải trả về `dead_letter` ngay lần đầu.

### T6 · Chạy test
- [x] `make test` — tất cả test pass (11/11).
- [x] `make run-scenarios` — sinh ra `outputs/metrics.json` (7/7 success, 100%).

---

## Phase 2 — Persistence (15 pts)

### T7 · `persistence.py` — Fix SqliteSaver API
- [x] Sửa `SqliteSaver.from_conn_string(...)` → dùng `sqlite3.connect(...)` + `SqliteSaver(conn=...)` (API v3.x).
- [x] Bật WAL mode: `conn.execute("PRAGMA journal_mode=WAL")`.
- [x] Cập nhật `configs/lab.yaml` để dùng `checkpointer: sqlite` khi chạy demo.

### T8 · Bằng chứng persistence
- [x] Chạy một scenario, kill process, restart và resume từ checkpoint — ghi log/screenshot vào report.
- [x] Hoặc: in `thread_id` và gọi `graph.get_state_history(config)` để show state history (6 entries/run confirmed).

---

## Phase 3 — Metrics & Report (35 pts)

### T9 · Chạy và validate metrics
- [x] `make run-scenarios` → kiểm tra `outputs/metrics.json` có đủ 7 scenario.
- [x] `make grade-local` → pass validation (success_rate=100%, schema đúng).
- [x] Đảm bảo S04/S06 (risky) có `approval_observed: true`.
- [x] Đảm bảo S05/S07 (error) có `retry_count > 0`.

### T10 · `reports/lab_report.md`
- [x] Điền tên, repo, ngày.
- [x] Mô tả kiến trúc graph (nodes, edges, state fields).
- [x] Paste bảng metrics từ `outputs/metrics.json`.
- [x] Phân tích ít nhất 2 failure mode (retry exhaustion, missing approval).
- [x] Giải thích cách dùng checkpointer + thread_id.

---

## Phase 4 — Bonus Extensions (hướng tới 90+)

### T11 · SQLite crash-resume (dễ nhất, +điểm rõ)
- [x] Hoàn thành T7, chạy demo kill + restart, ghi evidence vào report.

### T12 · Graph diagram
- [x] Thêm vào `graph.py` hoặc script riêng:
  ```python
  print(graph.get_graph().draw_mermaid())
  ```
- [x] Paste diagram vào report.

### T13 · Real HITL với `interrupt()`
- [x] `approval_node` đã có code cho `LANGGRAPH_INTERRUPT=true` — test bằng cách set env var.
- [x] Ghi evidence (log output) vào report.

### T14 · Parallel fan-out với `Send()`
- [x] Dùng `fan_out_tools()` như conditional edge từ `tool` node, trả về list `Send()` tới 2 `tool_worker` song song.
- [x] Merge kết quả qua `add` reducer trên `tool_results` (confirmed: primary + secondary results).
- [x] Thêm `streamlit` vào `pyproject.toml` dependencies.
- [x] Tạo `src/langgraph_agent_lab/app.py` với các tính năng:
  - Dropdown chọn scenario từ `scenarios.jsonl` hoặc nhập query tự do
  - Nút "Run" → gọi `build_graph().invoke(state)` → hiển thị route, final answer
  - Timeline các events (node, event_type, message)
  - Bảng metrics tổng hợp khi chạy tất cả scenarios
- [x] Chạy bằng: `streamlit run src/langgraph_agent_lab/app.py`
- [x] Ghi screenshot vào report làm evidence bonus.

---

## Checklist nộp bài

- [x] `make test` pass (11/11)
- [x] `make run-scenarios` sinh `outputs/metrics.json` hợp lệ (7/7, 100%)
- [x] `make grade-local` pass
- [x] `reports/lab_report.md` đã điền đầy đủ
- [x] Có thể giải thích ít nhất 1 route và 1 failure mode khi demo

**Bonus (hướng tới 90+):**
- [x] SQLite persistence + WAL mode + state history evidence
- [x] Real HITL với `interrupt()` + resume via `Command`
- [x] Graph diagram (Mermaid) trong report
- [x] Streamlit UI với screenshots (`image_1.png`, `image_2.png`)
