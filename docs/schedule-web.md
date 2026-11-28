# Ứng dụng xếp lịch đào tạo

## Chạy trên Windows

Chạy trong thư mục `K5-Day15-L3A-4people` bằng PowerShell.

```powershell
python -m pip install -r requirements.txt
$env:SCHEDULE_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:SCHEDULE_ADMIN_PASSWORD = python -c "import getpass; print(getpass.getpass('Mat khau quan tri (it nhat 16 ky tu): '))"
python run.py
```

Mở [trang lịch đào tạo](http://127.0.0.1:8080). Giữ `SCHEDULE_SECRET` trong cấu hình bí mật nếu dùng qua nhiều lần khởi động. Thay giá trị này sẽ vô hiệu hóa phiên và mã truy cập học viên cũ. Ban đào tạo, Key Coach và Day Lead dùng vai trò quản trị chung. Nếu phục vụ qua mạng, đặt sau HTTPS và bật `SCHEDULE_HTTPS=1` để cookie chỉ truyền qua HTTPS.

Upload được quét trên máy chủ bằng Microsoft Defender trên Windows hoặc ClamAV với cơ sở chữ ký hiện hành. Nếu cần, đặt `SCHEDULE_CLAMSCAN` thành đường dẫn đến `clamscan`. Ứng dụng dừng lần nhập nếu trình quét báo lỗi hoặc phát hiện tệp đáng ngờ. Mỗi tệp tối đa 8 MB. Các thành phần Excel như macro, ActiveX, workbook liên kết hoặc tệp nhúng bị từ chối. Trang tự động escape dữ liệu trước khi hiển thị và các thao tác POST có token CSRF.

## Từ lịch gốc đến lịch công bố

1. Trong trang quản trị, tải lên ba workbook trong `data/` và chọn **Nhập dữ liệu từ Excel**. Sau khi quét và đọc tệp, ứng dụng mở bảng nhập liệu trên web. Ba tệp gốc được lưu nguyên vẹn.
2. Dùng các tab để nhập nhóm học viên, năng lực, giờ rảnh, sức chứa và số coach cần có. Có thể nhập từng ô hoặc dán một vùng ô từ Excel. Bấm **Lưu bảng** trước khi chuyển tab. Mọi thay đổi được lưu vào workbook riêng `ClassesesData.xlsx`.
3. Dùng tab **Đối chiếu lịch gốc** để kiểm tra các chi tiết đã trích. Một số buổi có hai cột giảng song song cho cùng nhóm. Hãy tách nhóm theo phòng hoặc gộp phòng thành một phương án có sức chứa tổng đã xác nhận và một giảng viên phụ trách. Điền nhóm khai giảng và xác minh giờ học đặc biệt.
4. Quay về trang quản trị và chọn **Kiểm tra và xếp thử**. Solver đọc trực tiếp `ClassesesData.xlsx` đã lưu. `INFEASIBLE` nghĩa là các buổi không thể xếp đồng thời theo ràng buộc. `FEASIBLE` là lịch hợp lệ tìm được trong giới hạn 20 giây. `OPTIMAL` là lịch có điểm phạt thấp nhất đã được chứng minh.
5. Chọn **Xếp và công bố**. Ứng dụng chạy lại solver với lịch đã công bố mới nhất. Dùng bộ lọc để xem lịch từng người. Dùng **Lấy mã truy cập** và chuyển riêng mã cho đúng học viên.

Dữ liệu làm việc được giữ dưới `.schedule-data/` qua các lần khởi động. Khi công bố, ứng dụng lưu một bản của ba tệp gốc, `ClassesesData.xlsx` và lịch kết quả. Nút tải `ClassesesData.xlsx` dùng để lấy bản sao khi cần. Dùng `python run.py cli` để chạy luồng dòng lệnh hackathon.

## Các sheet và quy ước

Tất cả các sheet dưới đây nằm trong `ClassesesData.xlsx`.

| Nhóm dữ liệu | Sheet | Cách điền |
|---|---|---|
| Giảng dạy | Classes | `class_id` là mã ổn định của buổi. `subject` phải khớp với kỹ năng của nhân sự. `groups` chứa một hoặc nhiều nhóm phân cách bằng dấu chấm phẩy. `assistants` và `keys` là số Lab Coach và Key Coach bắt buộc, điền 0 nếu không cần. |
| Giảng dạy | Slots | Một dòng cho một phương án `slot_id` duy nhất của lớp. Điền `day`, `start`, `end`, `rooms` và `capacity`. Với nhiều phòng dùng đồng thời, phân cách mã phòng bằng dấu chấm phẩy và khai sức chứa tổng. |
| Giảng dạy | Teachers | `person`, `skills`, `daily_minutes`, `weekly_minutes`. Kỹ năng là danh sách tên chuyên đề phân cách bằng dấu chấm phẩy. |
| Giảng dạy | TeacherAvailability | `person`, `day`, `start`, `end`, `preferred`. |
| Coach | Coaches | Tương tự Teachers, thêm `role` với giá trị `lab`, `key` hoặc `lab;key`. Dùng cùng một tên cho cùng một người trên các sheet. |
| Coach | CoachAvailability | Cùng cấu trúc với TeacherAvailability. |
| Học viên | Learners | `student_id`, `full_name`, `group`. Mỗi học viên thuộc một nhóm. Một lớp có thể nhận nhiều nhóm. |
| Học viên | LearnerAvailability | Cùng cấu trúc với TeacherAvailability. Cột `person` là mã học viên hoặc `group:TênNhóm`. Nếu một học viên có dòng riêng trong ngày, dùng các dòng riêng cho ngày đó. |

Dùng ngày `YYYY-MM-DD`, giờ địa phương `HH:MM`. Khai khoảng rảnh đủ bao phủ toàn bộ thời lượng buổi. Điền `preferred=1` cho khung giờ mong muốn hoặc `0` cho khung giờ rảnh bình thường. Chỉ tính phạt sở thích nếu người đó có ít nhất một khung mong muốn.

Trong `Classes`, chọn `locked=0` để solver được xếp lại. Có thể điền `existing_slot`, `existing_teacher`, `existing_coaches` để mô tả phương án cũ lần đầu nhập. Dùng `locked=1` với một phương án cũ đầy đủ để giữ nguyên lịch. Sau khi công bố, ứng dụng lấy mốc so sánh từ lịch đã công bố theo `class_id`. Lớp đã khóa cần giữ nguyên giờ, phòng, chuyên đề, thành viên và phân công. Nếu dữ liệu mới mâu thuẫn, ứng dụng báo lỗi và giữ lịch hiện hành.

## Điểm phạt

Tất cả HC-02 đến HC-10 là ràng buộc cứng. Solver cũng tránh trùng phòng và trùng giờ giảng viên. Giới hạn giờ nhân sự tính theo ngày và tuần ISO, cộng gộp khi một người kiêm vai trò. Các điểm phạt SC-01 đến SC-07 lần lượt là 100, 30, 20, 20, 15, 10 và 5. SC-01 tính mỗi buổi thay đổi, SC-02/03/07 tính mỗi lượt phân công ngoài giờ mong muốn, SC-04/05 tính mỗi giờ làm tròn lên của chênh lệch tải cao nhất và thấp nhất trong từng đội, SC-06 tính mỗi giờ trống làm tròn lên trong ngày với từng nhân sự hoặc nhóm học viên.
