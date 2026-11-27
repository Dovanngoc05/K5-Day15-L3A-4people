# Quản lý Chi phí AI, Token & Cache (`codebase/ai_service.py`)

## 1. Nguyên tắc kiểm soát chi phí
1. **Không gọi AI cho các tác vụ xác định:** Toàn bộ kiểm tra trùng phòng, trùng giảng viên, trùng lớp, trùng coach, thiếu trường và trạng thái phòng đều chạy bằng code thuần (`codebase/validator.py`), tiêu tốn **0 token**.
2. **Chỉ gửi ngữ cảnh tối thiểu:** Chỉ trích xuất tối đa 20 mục cột/ô mơ hồ cần phân tích (`prepare_minimal_mapping_payload`), cắt ngắn dưới `AI_MAX_CONTEXT_CHARS` (mặc định 6.000 ký tự) và ẩn danh PII trước khi gửi.
3. **Chỉ chạy khi Admin bấm nút:** Không có tác vụ nền tự động gọi LLM khi vừa upload hay khi load trang.
4. **Chế độ không tốn phí:** Đặt `AI_PROVIDER=fake` (mặc định) để chạy toàn bộ luồng offline hoặc `AI_PROVIDER=disabled` để tắt hoàn toàn lớp AI.

## 2. Cơ chế Cache & Ngân sách
- **Cache theo nội dung:** Tính `input_hash = SHA-256(payload_chuẩn_hoá + provider + model + prompt_version)`. Khi Admin bấm phân tích lại một dữ liệu không đổi, backend tìm bản ghi `status="ok"` trong bảng `ai_runs` và trả kết quả cache (`status="cached"`, `token_in=0`, `token_out=0`, `estimated_cost=0`).
- **Giới hạn ngân sách theo dự án:** Trường `ai_budget_usd` trong cấu hình dự án (mặc định `1.00 USD`, cấu hình từ `.env` qua `AI_BUDGET_USD_PER_PROJECT`) cộng dồn `estimated_cost` trong `ai_runs`. Khi tổng chi phí chạm hoặc vượt ngưỡng, lời gọi `openai` trả trạng thái `budget_exceeded` và giữ nguyên draft hiện tại.
- **Theo dõi minh bạch:** Mỗi lần gọi ghi lại `provider`, `model`, `prompt_version`, `input_hash`, `token_in`, `token_out`, `estimated_cost`, `latency_ms` trong `ai_runs` (xem tại tab **9. Lịch sử & Audit**).
