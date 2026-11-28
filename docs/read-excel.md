# Đọc nhiều file Excel cho A5

Cài thư viện từ thư mục gốc repo:

```powershell
python -m pip install -r requirements.txt
```

Đọc toàn bộ `.xlsx`/`.xlsm` trong một thư mục (không quét thư mục con):

```powershell
python -m codebase.excel_reader data-btc/training-ops
```

Đọc 3, 4 hoặc nhiều file bằng cách thêm đường dẫn, có dấu ngoặc kép khi có khoảng trắng:

```powershell
python -m codebase.excel_reader "data-btc/file1.xlsx" "data-btc/file2.xlsx" "data-btc/file3.xlsx"
```

Lưu dữ liệu đã đọc thành JSON trong thư mục được Git bỏ qua:

```powershell
python -m codebase.excel_reader data-btc/training-ops --output data-btc/import-a5.json
```

Không ghi đè file output đã tồn tại. Đổi tên output khi chạy lại.

## Dùng trong Python hoặc giao diện upload sau này

```python
from codebase.excel_reader import read_excel_files

result = read_excel_files(["data-btc/training-ops/teaching-schedule.xlsx",
                          "data-btc/training-ops/lab-coach-schedule.xlsx"])
print(result["summary"])
for error in result["errors"]:
    print(error)
```

Hàm cũng nhận danh sách đối tượng upload dạng file nhị phân (có `read`, `seek`,
`tell` hoặc `getvalue`), không cần lưu upload xuống đĩa. Giữ nguyên vị trí đọc
của stream. File trùng tên vẫn có `source_id` riêng theo vị trí trong lần nhập.

Kết quả gồm `files`, `errors`, `summary`. Mỗi file có các sheet; mỗi sheet có
danh sách dòng và ô. Mỗi ô giữ `coordinate`, `source_cell`, `inherited`, `value`,
`formula`, `hyperlink`. Ngày được chuyển sang chuỗi ISO; nội dung nhiều dòng được giữ nguyên.

Giá trị ô gộp được lặp đúng trong vùng gộp, có đánh dấu ô neo. Ô trống thông
thường không được tự điền. Công thức giữ nguyên và đọc kết quả cache nếu có;
không chạy công thức, không có cache thì trả `null` và cảnh báo trong sheet.
Cả sheet ẩn cũng được đọc và giữ trạng thái `state`. File lỗi có thông báo riêng,
các file hợp lệ vẫn được đọc; CLI trả mã 1 nếu có file lỗi.

Hỗ trợ `.xlsx` và `.xlsm`; `.xls` cũ cần chuyển sang `.xlsx`. Mặc định giới hạn
500.000 ô theo kích thước các sheet của mỗi workbook, phù hợp file demo nhỏ.
Đây chưa phải bộ đọc file lớn theo luồng.

Đây là tầng nhập dữ liệu, chưa tự suy luận tiêu đề, ghép lịch giữa các file,
phát hiện xung đột hoặc gọi AI. Nguồn BTC và JSON nhập giữ local trong `data-btc/`.
`python run.py` hiện vẫn dùng workflow mẫu; tầng nhập chưa được nối vào agent.
