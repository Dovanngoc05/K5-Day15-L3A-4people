# Bảo mật & An toàn Dữ liệu Local (Threat Model Ngắn)

## 1. Tài sản cần bảo vệ
- Tài khoản quản trị và phiên làm việc (`users`, `user_sessions`).
- Dữ liệu gốc trong các workbook Excel (có thể chứa email, SĐT, mã học viên, họ tên).
- Tính toàn vẹn của phiên bản lịch đã công bố cho người xem (`published`).
- API key của nhà cung cấp AI (chỉ đọc từ `.env`).

## 2. Các mối đe doạ và biện pháp phòng thủ đã triển khai

| Mối đe doạ | Biện pháp bảo vệ trong code |
|---|---|
| **Lộ mật khẩu / dò mật khẩu** | Băm mật khẩu bằng **Argon2** (`argon2-cffi`); không hard-code mật khẩu Admin mặc định; tạo Admin qua CLI (`backend/cli.py`); giới hạn tối đa 5 lần đăng nhập sai / 5 phút (`429`); thông báo lỗi đăng nhập đồng nhất và thực hiện dummy verify khi user không tồn tại. |
| **Chiếm phiên / CSRF / CORS rộng** | Cookie `a5_sid` có `HttpOnly`, `SameSite=Lax`, hỗ trợ `Secure`; mọi request `POST/PATCH/PUT/DELETE` bắt buộc header `X-CSRF-Token` khớp `user_sessions.csrf_token`; CORS chỉ mở cho `FRONTEND_ORIGIN`. |
| **Leo thang đặc quyền (Viewer xem dữ liệu Admin)** | Kiểm tra vai trò ở mọi endpoint backend (`require_admin` vs `require_authenticated`); `/api/public/schedule` chỉ truy vấn `status='published'` và loại bỏ hoàn toàn `provenance`, `source_cells`, `audit_log`, đường dẫn file gốc. |
| **File Excel độc hại (Macro, ActiveX, XXE, ZIP bomb, Path Traversal)** | Kiểm tra trong `codebase/file_safety.py`: từ chối sai đuôi, quá dung lượng, sai chữ ký `PK\x03\x04`, `vbaProject.bin`, `xl/activeX/`, `xl/embeddings/`, tệp thực thi nhúng, `<!DOCTYPE`/`<!ENTITY`, công thức `=CMD\|`, `=WEBSERVICE(`, tỷ lệ nén > 100x. Lưu đĩa bằng UUID4 ngoài thư mục static/public. |
| **Prompt Injection trong ô Excel** | Quét phát hiện mẫu `SYSTEM OVERRIDE` / `ignore previous instructions` gắn cờ `prompt_injection_suspect` + cảnh báo `HC-INJECTION-CELL`; khi gửi sang model bọc dữ liệu trong `<untrusted_excel_data>` và dùng system prompt cấm thực thi lệnh từ dữ liệu. |
| **Lộ dữ liệu cá nhân (PII) / API key** | Gắn cờ email, SĐT, mã học viên, họ tên trong `source_cells`; mặc định bật ẩn danh (`redact_pii=True`) trước khi gửi sang AI; `.env`, `.local_data/`, `*.db`, `data-btc/` đều nằm trong `.gitignore`; bảng `ai_runs` và `audit_log` không lưu API key hay nội dung nhạy cảm. |
