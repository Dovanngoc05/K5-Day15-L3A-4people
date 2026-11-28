# Tổng hợp bằng chứng pain

> Cập nhật từ các tệp hiện có trong repo. Chỉ ghi nhận dữ liệu đã thu thập; không dùng bộ `training-ops` giả lập làm bằng chứng pain.
> Trạng thái CP3 hiện tại: **chưa đạt ngưỡng bằng chứng**. Khảo sát có 4 phản hồi (cần ≥20 người đúng vai); chưa có hồ sơ phỏng vấn; dữ liệu đào tạo trong repo là dữ liệu giả lập.

## 1. Nguồn đã dùng

| Nguồn | Kết quả hiện có | Đạt ngưỡng? | Hồ sơ |
|---|---|---|---|
| Đào data người dùng thật | Chưa thực hiện. `evidence/data-mining.md` còn là mẫu trống; các workbook `training-ops` là dữ liệu giả lập. | **Không** | `evidence/data-mining.md` |
| Phỏng vấn đúng người dùng, ngoài nhóm | Chưa có hồ sơ phỏng vấn; thư mục chỉ có `TEMPLATE.md`, không có `P1.md`, `P2.md`, `P3.md`. | **Không** | `evidence/interviews/` |
| Khảo sát đúng người dùng, ngoài nhóm | 4 phản hồi trong CSV: 3 Học viên, 1 Lab Coach. Ngưỡng yêu cầu ≥20 người đúng vai. | **Không** | `evidence/survey/questions.md`, `evidence/survey/results.csv` |

### Kết quả khảo sát hiện có

Đếm theo 4 dòng dữ liệu đã ẩn danh trong `evidence/survey/results.csv` (R1–R4). Mẫu nhỏ nên chỉ ghi số đếm, không ghi tỷ lệ phần trăm.

- **Học viên (R1–R3, n=3):** cả 3 cho biết tra lịch/phòng qua email hoặc danh sách nhóm; tần suất là 2 người trên 10 lần/tháng và 1 người 6–10 lần/tháng; cả 3 chọn “Chưa gặp tình huống nào ở trên”; thời gian lần gần nhất đều dưới 5 phút.
- **Lab Coach (R4, n=1):** báo tra lịch/phòng 1–2 lần/tháng qua bảng phân công giảng dạy (Google Sheets / Excel), lần gần nhất dưới 5 phút. Người trả lời ghi nhận tình huống phòng còn “chờ xác nhận” hoặc “dự kiến (dk:)” sát giờ học, gây thêm thời gian kiểm tra và hỏi qua lại.
- **Key Coach / Day Lead:** chưa có phản hồi được ghi nhận trong CSV hiện tại. Đây là vai trò chính trong giả thuyết ở `evidence/hypothesis.md`, vì vậy khảo sát hiện tại chưa kiểm chứng được giả thuyết đó.
- Form khảo sát: https://docs.google.com/forms/d/1WnyFE3oAB9c6tT7-6Q9UYDxRnY-uH0RmSDHto4qlm7w/viewform. Bản CSV trong repo đã bỏ cột liên hệ; không suy đoán danh tính người trả lời.

## 2. Số chính

- **Đào data:** chưa thực hiện trên dữ liệu người dùng thật; không tính workbook giả lập.
- **Phỏng vấn:** chưa có hồ sơ nên chưa thể báo số người gặp pain, tần suất hoặc thời gian xử lý.
- **Khảo sát:** tổng `n=4`; Học viên `3`, Lab Coach `1`, Key Coach/Day Lead `0` được ghi nhận. Trong nhóm Học viên, `3/3` chọn chưa gặp tình huống nêu trong câu hỏi. Lab Coach có `1/1` phản hồi về phòng chưa xác nhận/dự kiến sát giờ học và việc phải kiểm tra, hỏi lại. Tổng mẫu vẫn dưới ngưỡng `≥20`; không kết luận đại diện cho người dùng mục tiêu.

| Mã ẩn danh | Vai | Gặp pain theo câu trả lời? | Số lần/tháng | Thời gian lần gần nhất | Cách hiện tại |
|---|---|---|---|---|---|
| R1 | Học viên | Không ghi nhận pain trong lựa chọn khảo sát | Trên 10 lần tra lịch | Dưới 5 phút | Outlook / danh sách nhóm học viên |
| R2 | Học viên | Không ghi nhận pain trong lựa chọn khảo sát | Trên 10 lần tra lịch | Dưới 5 phút | Outlook / danh sách nhóm học viên |
| R3 | Học viên | Không ghi nhận pain trong lựa chọn khảo sát | 6–10 lần tra lịch | Dưới 5 phút | Outlook / danh sách nhóm học viên |
| R4 | Lab Coach | Có nêu tình huống phòng chờ xác nhận/dự kiến sát giờ học | 1–2 lần tra lịch | Dưới 5 phút | Bảng phân công giảng dạy (Google Sheets / Excel) |

## 3. Trích dẫn / câu trả lời nguyên văn đã ẩn danh

Các câu dưới đây được chép nguyên văn từ những trường trả lời trong CSV. R1–R3 là lựa chọn có sẵn trong câu hỏi (không phải phát biểu tự do); hai câu của R4 là câu trả lời về tình huống và tác động. Những câu này chưa thay thế yêu cầu phỏng vấn hoặc ngưỡng mẫu khảo sát CP3.

1. “Chưa gặp tình huống nào ở trên” — R1, câu `issues_encountered` trong `evidence/survey/results.csv` (lựa chọn khảo sát).
2. “Chưa gặp tình huống nào ở trên” — R2, câu `issues_encountered` trong `evidence/survey/results.csv` (lựa chọn khảo sát).
3. “Chưa gặp tình huống nào ở trên” — R3, câu `issues_encountered` trong `evidence/survey/results.csv` (lựa chọn khảo sát).
4. “Phòng vẫn "chờ xác nhận" hoặc "dự kiến (dk:)" sát giờ học” — R4, câu `issues_encountered` trong `evidence/survey/results.csv`.
5. “Mất thêm thời gian kiểm tra lại và hỏi qua lại nhiều bên” — R4, câu `actual_impact` trong `evidence/survey/results.csv`.

## 4. Các nguồn có khớp nhau không?

Chưa đủ nguồn độc lập để đối chiếu: hiện chỉ có một khảo sát nhỏ, chưa có phỏng vấn và chưa có đào data người dùng thật. Trong CSV, ba học viên không báo tình huống vướng được hỏi; một Lab Coach nêu vấn đề phòng chưa được xác nhận/dự kiến sát giờ học và phải kiểm tra, hỏi lại. Kết quả này gợi ý cần tập trung hỏi đúng vai vận hành, nhưng `n=1` Lab Coach không đủ để khái quát.

## 5. Kết luận so với giả thuyết

**Chưa kiểm chứng / chưa thể kết luận đúng hay sai.** Giả thuyết trong `evidence/hypothesis.md` nhắm tới Key Coach / Day Lead chuẩn bị thông báo; hiện chưa có phản hồi nào của vai này. Câu trả lời của một Lab Coach là tín hiệu liên quan đến việc xác nhận phòng, nhưng khác vai và không chứng minh khâu đối chiếu/soạn thông báo là nguyên nhân chính.

Điều còn chưa biết: Key Coach / Day Lead có thực sự phải đối chiếu nhiều nguồn không, tình huống xảy ra bao nhiêu lần, mỗi lần mất bao lâu, và pain chủ yếu nằm ở đối chiếu lịch hay chờ xác nhận phòng/cập nhật. Cần thu thập phỏng vấn ít nhất 3 người ngoài nhóm đúng vai hoặc khảo sát đạt ít nhất 20 người đúng vai; sau đó cập nhật bằng chứng và giữ nguyên cả kết quả trái chiều.

