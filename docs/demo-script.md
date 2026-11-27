# Kịch bản Demo 3 Phút (Thường & Tình huống khó)

## Chuẩn bị trước khi demo
1. Đã chạy `python -m alembic upgrade head`.
2. Đã tạo tài khoản Admin (`python -m backend.cli create-admin --username quantri`) và Viewer (`python -m backend.cli create-viewer --username hocvien`).
3. Đã nạp sẵn dữ liệu synthetic (`python -m backend.cli seed-synthetic`) hoặc chuẩn bị 2 file mẫu trong `.local_data/seed_workbooks/`.
4. Khởi động app bằng `.\scripts\dev.ps1` và mở `http://localhost:5173`.

---

## Kịch bản 1 — Luồng chuẩn từ Upload tới Viewer (90 giây)
1. **Đăng nhập Admin (`quantri`):** Tại **1. Dashboard**, chọn dự án `"Khoá 9 — Demo Synthetic"`, chỉ rõ banner `[CHẾ ĐỘ AI GIẢ LẬP — OFFLINE]` và `[DỮ LIỆU GIẢ LẬP / SYNTHETIC]`.
2. **Xem dữ liệu nguồn (Tab 3):** Chọn `synthetic_schedule_demo.xlsx` → sheet `Khoá 9 (GĐ1)`, chứng minh mọi ô giữ nguyên tọa độ `F6`, `F7`, `H7` và cờ nhạy cảm.
3. **Mapping & AI (Tab 4):** Chọn `synthetic_extra_sessions.xlsx` → bấm *"Chạy đề xuất AI (chỉ khi bấm)"* với checkbox *"Ẩn danh PII"* đang bật → chỉ ra nhãn `[Đề xuất giả lập (offline)]` và bấm **Chấp nhận / Từ chối** để Admin tự quyết định.
4. **Kiểm tra HC/SC (Tab 6):** Chỉ ra hệ thống phát hiện tự động bằng code:
   - `[LỖI CHẶN] HC-ROOM-STATUS`: `L3A LAB 2` đang `chờ xác nhận`.
   - `[LỖI CHẶN] HC-11`: `L2B LAB 2` trùng phòng `C201` hoặc mâu thuẫn với `Lịch lớp K9 (bản chép)`.
   - `[CẢNH BÁO] HC-INJECTION-CELL`: Ô `H7` chứa `SYSTEM OVERRIDE...` nhưng **bị bỏ qua hoàn toàn** như dữ liệu thô.
5. **Chặn công bố → Sửa lỗi → Công bố (Tab 5 → Tab 7):**
   - Sang **7. Duyệt công bố**: nút Công bố bị khoá vì còn lỗi chặn.
   - Quay lại **5. Lịch nháp**: sửa `L3A LAB 2` thành phòng trống đã xác nhận (`H210`, `confirmed`) và xử lý mục xung đột → hệ thống tự chạy lại validation (`0 lỗi chặn`).
   - Sang **7. Duyệt công bố**: tích xác nhận Admin → bấm **Công bố Phiên bản**.
6. **Chứng minh cô lập Viewer:** Đăng xuất → đăng nhập bằng tài khoản `hocvien` (`Viewer`) → chỉ nhìn thấy duy nhất bảng lịch công bố, lọc theo lớp/ngày, hoàn toàn không thấy draft, workbook gốc hay audit log.

---

## Kịch bản 2 — Tình huống khó & Bảo mật (60 giây)
1. **Upload file độc hại / sai định dạng:** Thử upload file `.csv` hoặc file giả lập chứa macro (`vbaProject.bin`) tại Tab 2 → hệ thống chặn ngay từ cổng kiểm tra an toàn và ghi vào `audit_log`.
2. **Rollback không mất lịch sử:** Đăng nhập lại Admin → vào **9. Lịch sử & Audit** → bấm **Tạo Draft từ bản này (Rollback)** ở phiên bản cũ → tạo draft mới mà không làm đổi bản đang công bố của Viewer cho đến khi Admin duyệt lại.
