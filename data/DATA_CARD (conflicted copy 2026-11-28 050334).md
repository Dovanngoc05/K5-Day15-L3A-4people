# Data card — dữ liệu bản chạy thử dùng

> Điền ở guide bước 2.4 (bản đầu ở CP2, đủ ở CP3). Ôn lại: ngày 6 · lab ngày 6. Chấm ở rubric R4.
> Một trang. Mỗi dataset một mục. Dữ liệu chạy thử (bài mẫu, thông báo mẫu, đoạn transcript…) để trong thư mục `data/` này.
> Không commit nguyên tài liệu khoá, dữ liệu cá nhân thật hay nguyên file data BTC cấp — chỉ đoạn trích ngắn, bản viết lại, hoặc số đã tổng hợp.

## Dataset 1 · learners.xlsx

|                           |                                                                                                                             |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Dùng để làm gì       | Danh sách học viên phục vụ chạy thử ứng dụng                                                                       |
| Từ đâu                 | mock data do AI gen ra không phải dữ liệu thật                                                                         |
| Xử lý những bước gì | Thêm hv, ngày tạo, tên và mã sinh viên giả lập cho toàn bộ danh sách bằng `generate_learners.py`            |
| Số dòng / số đoạn    | 1.000 dòng dữ liệu, 5 cột; file Excel `learners.xlsx`                                                                 |
| Phiên bản / ngày lấy  | 2026-11-27                                                                                                                  |
| Nhãn                     | Toàn bộ 1.000 dòng trong `learners.xlsx` có `record_source=synthetic`. Nhãn áp dụng cho bộ dữ liệu chạy thử |
| Giới hạn                | Dữ liệu thử, không phải danh sách đăng ký thật hoặc bằng chứng khảo sát/pain                                 |

**Cột dữ liệu:** `hv`, `created_date`, `student_id`, `full_name`, `record_source`.

**Mã sinh viên:** `2A202700001`–`2A202701000`, duy nhất, theo mẫu `2A20270` + 4 chữ số.

**Ngày tạo:** giữ ngày nguồn `2026-11-05`; các dòng bổ sung dùng `2026-11-27`.

**Data `synthetic`:** ghép họ, tên đệm và tên tiếng Việt theo thứ tự cố định, không dùng ngẫu nhiên nên không cần seed. Tên không đại diện cho danh tính thật. Kiểm tra tự động số dòng, mã duy nhất, định dạng mã, ngày ISO và bảo toàn các dòng nguồn; chưa có người kiểm tay. Data tự dựng **không phải bằng chứng pain**.
