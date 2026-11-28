# Web xếp lịch local — 4people

## Cài và chạy

### Kho demo đã bổ sung cho bộ dữ liệu lớn

Nếu đã có thư mục `runtime/demo-ready`, chạy riêng bằng:

```powershell
.venv\Scripts\python.exe app.py --data-dir runtime/demo-ready --port 8001
```

Mở `http://127.0.0.1:8001`, dùng tài khoản hiện có được sao chép khi tạo kho. Kho này hiển thị banner giả lập và có lịch nháp 106 buổi chờ duyệt. Không sửa dữ liệu hoặc lịch khoá trong kho `runtime` gốc. Chỉ dùng để demo; các khai báo mới không phải thông tin đã xác minh.

Workbook đầy đủ nằm tại `data-btc/a5-input-demo-hoan-chinh.xlsx`: có `Assumptions`, bản `Source_Sessions`/`Source_Rooms` và ghi chú thay đổi. Không upload đè lên nguồn đang khoá để tránh vượt HC-10; dùng kho demo riêng hoặc kho trống. Bố trí ban đầu trong `Demo_Initial` là giả lập, được kiểm tra HC và dùng làm warm start; không phải lịch gốc đã duyệt.

Các cột tuỳ chọn `allowed_slots`, `allowed_rooms` trong Sessions giới hạn ứng viên bằng danh sách mã ngăn cách `|`; workbook cũ không có hai cột này vẫn đọc được. Bộ solver gộp chính xác các học viên có cùng đăng ký và availability/preferences để giảm kích thước mô hình, giữ trọng số theo số cá nhân và kiểm tra lịch cuối theo từng người.

Nếu tối ưu hết thời gian mà chưa có lời giải và baseline đầy đủ đã qua kiểm tra độc lập, CP-SAT có thể dành tối đa 5 giây để kiểm chứng baseline bằng mô hình cố định các biến gợi ý. Khi đó chỉ báo FEASIBLE, không tuyên bố tối ưu của mô hình gốc. Không dùng baseline không hợp lệ để bỏ qua HC.

Từ thư mục repo, dùng các lệnh ở README để tạo `.venv`, cài requirements, tạo admin rồi chạy `python run.py` bằng Python trong `.venv`. App dùng Flask + Waitress, chỉ lắng nghe `127.0.0.1:8000`. Có thể chạy `python app.py --port 8001` để đổi cổng. Không bật Flask debug server.

Tạo admin đầu tiên bằng `python app.py init-admin`; mật khẩu được hỏi qua terminal, tối thiểu 12 ký tự. Thêm admin bằng cùng lệnh với `--username tenkhac`. Không có tài khoản/mật khẩu mặc định. Tài khoản cá nhân do admin cấp trên web và gắn với một `person_id`; không tự đăng ký bằng mã sinh viên.

`A5_DATA_DIR` đổi thư mục dữ liệu, mặc định `runtime/`. Đây là biến môi trường của tiến trình; app không tự đọc `.env` dành cho model. `A5_HTTPS=1` bật Secure cookie nếu sau này chạy qua HTTPS; mặc định là local HTTP. Chưa cấu hình phục vụ Internet hay dùng nhiều tiến trình. Không mở trực tiếp thư mục runtime cho người dùng khác.

## Luồng admin

### Nhập file A5 khi kho hiện tại có lịch khoá

Chọn `a5-input-demo-hoan-chinh.xlsx` làm đầu vào. `a5-demo-solver-result.xlsx` là kết quả xếp lịch, không phải workbook đầu vào; app sẽ báo đúng loại file nếu chọn nhầm.

Sau khi quét virus, app luôn cho xem trước. Nếu HC-10 chặn ghi đè lịch khoá, chọn **Tạo kho riêng và nhập**: app tạo một kho Excel độc lập, giữ nguyên dữ liệu và lịch công bố của kho cũ, rồi chuyển trang admin sang kho mới. Ghi chú `Assumptions` được giữ và hiển thị banner khi dữ liệu có giả định. Muốn cập nhật tại chỗ thì vẫn phải thoả kiểm tra HC-10; thao tác tạo kho riêng không mở khoá hay sửa lịch gốc.

Nếu `runtime/demo-ready` đã tồn tại, nút **Mở bộ demo đã bổ sung** đưa admin thẳng đến bộ dữ liệu đầy đủ và lịch nháp đã tạo. Không cần đổi lệnh chạy hay cổng. Menu **Kho đã nhập** cho phép quay lại các kho riêng; **Về kho gốc** đưa admin về dữ liệu ban đầu.

Tài khoản và quyền truy cập quản lý tập trung ở kho gốc của app. Mỗi phiên admin giữ lựa chọn kho riêng, tránh thao tác nhầm khi admin khác chuyển kho. Học viên tiếp tục xem kho đã công bố trước đó; chỉ sau khi admin duyệt một phiên bản, trang cá nhân mới dùng kho vừa duyệt. Mọi thao tác chọn kho yêu cầu admin và CSRF; dữ liệu mỗi kho vẫn lưu bằng Excel trong `runtime/workspaces/<id>/`.

1. Upload 1–10 file `.xlsx`, tối đa 10 MB/file, tổng request 32 MB. Không nhận `.xls`, `.xlsm`, macro hoặc workbook có đối tượng nhúng/liên kết dữ liệu ngoài.
2. Kiểm tra ZIP/XML có giới hạn, quét virus bằng engine thật, đọc dữ liệu; xem bản tổng hợp trước khi xác nhận nhập. Nếu một file lỗi, cả batch không nhập vào dataset hiện tại. Bản file đã quét có thể được giữ để truy vết, không được tự công bố.
3. Xác nhận nhập: workbook chuẩn thay toàn bộ bảng cùng tên. Workbook BTC được adapter đọc bảo thủ; chưa hiểu thông tin thì báo cần làm rõ.
4. Xem mã lỗi và thông tin thiếu. Dùng **Bổ sung dữ liệu** để khai báo người/kỹ năng/giờ làm, đăng ký học viên, giờ rảnh hoặc yêu cầu coach; hoặc tải workbook bổ sung, sửa bằng Excel rồi upload lại. Mọi khai báo của admin được ghi nhật ký, không coi là dữ kiện tự suy ra từ file.
5. Đặt trọng số SC và chạy CP-SAT. Nếu thiếu dữ liệu, vô nghiệm hoặc hết thời gian chưa có lời giải, không tạo lịch công bố. `FEASIBLE` là lịch hợp lệ chưa chứng minh tối ưu; `OPTIMAL` là đã chứng minh tối ưu trong mô hình đã khai báo.
6. Xem lịch nháp và phân rã điểm. Admin bấm duyệt mới công bố; ngay trước đó code kiểm tra HC độc lập và kiểm tra fingerprint dữ liệu.
7. Dữ liệu/cấu hình đổi thì nháp cũ hết hiệu lực. Upload mới không thay lịch đang hiển thị. Khoá buổi theo lịch đã công bố; muốn thay phải chủ động mở khoá và ghi lý do. Không thay giờ của slot đang được lịch khoá sử dụng qua upload.

## Schema Excel chuẩn

Tải **Workbook dữ liệu** để có đúng cột và dữ liệu hiện tại. Sheet/cột phân biệt chữ hoa/thường. Dùng mã duy nhất và nhất quán, không dùng `|` trong một mã vì đó là dấu phân cách danh sách. Tên môn/kỹ năng phải khớp chính xác.

| Sheet | Các cột |
|---|---|
| People | person_id, name, role, subjects, skills, max_minutes_day, max_minutes_week |
| Sessions | session_id, class_id, subject, duration_minutes, required_skill, assistant_count, key_coach_required, locked, baseline_slot, baseline_teacher, baseline_assistants, baseline_key_coach, baseline_room |
| Slots | slot_id, date, start, end |
| Rooms | room_id, capacity |
| Enrollments | person_id, class_id |
| Availability | person_id, slot_id, available, preferred |
| Weights | constraint_id, weight |

- `role`: `teacher`, `assistant`, `key_coach`, `student`. Người nhận một vai chính trong bản đầu. Key coach được xếp và kiểm tra giờ như một coach; chưa mô hình hoá một người kiêm nhiều vai.
- `subjects`, `skills`, `required_skill`, `baseline_assistants` là danh sách phân cách `|`. Giảng viên phải có môn của buổi; mỗi coach phải có đủ kỹ năng yêu cầu.
- Mỗi session là một lớp/nhóm học trong một phòng với một giảng viên. Nếu chia lớp nhiều phòng hoặc cần nhiều giảng viên đồng thời, admin phải tách thành nhóm/buổi và khai báo đăng ký tương ứng; adapter không tự phân học viên vào phòng. Buổi online từ nguồn cần được chuẩn hoá thành cấu hình phù hợp trước khi giải; bản đầu tối ưu các buổi có phòng và sức chứa khai báo.
- `date`: `YYYY-MM-DD`; `start`, `end`: `HH:MM` dạng text (giờ Việt Nam). Mỗi slot trong cùng ngày. Session bắt đầu đúng đầu slot, thời lượng không vượt độ dài slot; solver không tự tạo giờ ngoài bảng Slots.
- `assistant_count`: 0–10; `key_coach_required`, `locked`, `available`, `preferred`: 0 hoặc 1.
- `Availability` cần khai báo rõ từng cặp người liên quan–slot: 1 là rảnh toàn bộ slot, 0 là không rảnh. Thiếu dòng là thiếu dữ liệu, không phải rảnh mặc định. `preferred=0` chỉ là ưu tiên mềm, khác `available=0`.
- `max_minutes_day` và `max_minutes_week` bắt buộc cho đội giảng dạy; giới hạn tuần theo ISO year/week, tính phút thực. Cần đưa đầy đủ nghĩa vụ liên quan vào đầu vào để kiểm tra xung đột và giờ làm có ý nghĩa.
- Mỗi lớp phải có đăng ký học viên. Cùng học viên có thể đăng ký nhiều lớp, nhờ đó phát hiện trùng lịch cá nhân. Không dùng tên để nối người.
- `baseline_*` ghi lịch hiện có. Khi `locked=1`, phải có baseline đầy đủ và solver giữ nguyên. Sau duyệt, lịch đã công bố trở thành baseline cho lần giải kế tiếp, trạng thái khoá chỉ đổi khi admin yêu cầu.
- Mỗi lần nhập có thể chỉ chứa một vài sheet chuẩn: People/Enrollments/Availability trong một file, Sessions/Slots/Weights file khác và Rooms file thứ ba. Chọn tất cả cùng lúc để xem trước bản kết hợp. Khi upload nhiều sheet chuẩn cùng tên, bảng ở file sau thay thế bảng trước; nên tránh trùng sheet nếu không có chủ đích.
- Không dùng công thức trong workbook chuẩn; chuyển thành giá trị trước khi upload. Text bắt đầu `=` được xuất lại dưới dạng chuỗi literal, không thực thi.

Tạo bộ **ba file mẫu hoàn toàn giả lập** bằng:

```powershell
.venv\Scripts\python.exe app.py demo-workbooks
```

File nằm trong `runtime/demo-inputs/`. Hoặc bấm **Nạp bộ mẫu** vào kho trống để thử không cần upload. Bộ mẫu không phải bằng chứng pain.

## Ba workbook hiện tại

Adapter nhận diện `Learners`, `Khoá 9 (GĐ1)`, và các sheet lịch lab coach. Danh sách học viên chỉ cung cấp danh tính; chưa có lớp đăng ký. Tên giảng viên/coach được lấy từ lịch nhưng chuyên môn/kỹ năng/giờ rảnh không được tự suy đoán. Phòng có thể có mã nhưng chưa có sức chứa; nhiều phòng/chưa xác nhận cần admin làm rõ.

Lịch nguồn được nhập ở trạng thái khoá để tránh vô tình xếp lại trước khi admin xác nhận. Có thể thiếu baseline coach/phòng; báo cáo sẽ yêu cầu bổ sung. Trong **Bổ sung dữ liệu**, admin có thể chủ động mở khoá theo lớp và khai báo yêu cầu coach, có ghi lý do; hoặc mở từng buổi trên trang điều phối. Không bấm các xác nhận hàng loạt nếu chưa kiểm tra chúng đúng với dữ liệu.

Adapter hiện đọc một mục lịch cho mỗi mã buổi, không tự giải quyết buổi nhiều phòng/nhiều giảng viên, buổi gộp hoặc form đổi ca đang chờ xử lý. Các trường hợp này phải được xác nhận trong workbook chuẩn trước khi dùng solver. Đây là giới hạn nhập dữ liệu, không phải kết luận về chất lượng lịch nguồn.

## Ràng buộc và điểm phạt

HC-01/02/03: dùng `add_no_overlap` trên khoảng thời gian thực cho từng người. HC-04: lọc theo availability của mọi người được chọn. HC-05/06: lọc chuyên môn/kỹ năng và vai trò. HC-07: sức chứa phòng đủ số học viên đăng ký. HC-08: tổng phút làm ngày/tuần không vượt giới hạn. HC-09: mỗi session chọn đúng một giảng viên. HC-10: khoá baseline. HC-11: không trùng phòng. Có bước kiểm tra độc lập trước công bố; không bỏ HC để lấy lời giải.

| SC | Trọng số mặc định, minh hoạ | Đơn vị vi phạm |
|---|---:|---|
| SC-01 | 100 | Mỗi buổi khác baseline về slot/giảng viên/phòng/coach tính một lần |
| SC-02 | 30 | Mỗi học viên-buổi ngoài giờ ưu tiên |
| SC-03 | 20 | Mỗi giảng viên-buổi ngoài giờ ưu tiên |
| SC-04 | 20 | Chênh lệch tổng giờ làm lớn nhất–nhỏ nhất giữa giảng viên |
| SC-05 | 15 | Chênh lệch tổng giờ làm lớn nhất–nhỏ nhất giữa lab coach |
| SC-06 | 10 | Tổng giờ trống giữa các buổi trong ngày của từng người, bao gồm giờ nghỉ giữa ca |
| SC-07 | 5 | Mỗi lab coach/key coach-buổi ngoài giờ ưu tiên |

CP-SAT dùng số nguyên: số vi phạm nhân 60 và thời gian tính theo phút; khi hiển thị chia 60. Trọng số admin chỉnh 0–10.000; tổng điểm là tổng trọng số nhân mức vi phạm. SC-04/05 tính trên toàn khoảng lập lịch và gồm cả người có tải 0. Chưa có cấu hình loại giờ nghỉ khỏi SC-06.

Giới hạn app local: 200 session, 100 slot, 2.000 người; tối đa 100.000 tổ hợp person-duty trong mô hình. Thời gian giải 15 giây, seed 42, một worker. Nếu vượt giới hạn, chia đầu vào thành phạm vi nhỏ nhưng phải giữ các nghĩa vụ liên quan để kiểm tra trùng lịch. Không khẳng định tối ưu nếu solver chỉ trả FEASIBLE/UNKNOWN.

## Quét virus và bảo vệ truy cập

- Windows tự tìm `MpCmdRun.exe` của Microsoft Defender, custom scan với `-DisableRemediation`. Chỉ tiếp tục khi exit code 0. Máy khác cài ClamAV, cập nhật signatures bằng `freshclam`, cấu hình đường dẫn executable trong biến `CLAMSCAN_PATH`; cũng nhận `clamscan` trên PATH. Không có engine, timeout hoặc mã trả về khác 0 thì từ chối nhập, không có nút bỏ qua.
- Chặn file quá lớn, ZIP quá nhiều entry, tổng giải nén lớn, đường dẫn ZIP nguy hiểm, entry trùng, macro, embedded object và external data link. XML dùng `defusedxml`; giới hạn kích thước sheet. Kiểm tra cấu trúc không được gọi là quét virus.
- Tên file dùng `secure_filename`; file lưu dưới ID ngẫu nhiên trong runtime, không dùng đường dẫn người nhập. Không thực thi công thức hoặc shell command từ dữ liệu.
- HTML dùng Jinja autoescape, CSP không cho script, CSRF cho mọi POST, cookie HttpOnly/SameSite, giới hạn đăng nhập sai. Password dùng hash Werkzeug; không lưu plaintext trong workbook. Mã người xem lịch lấy từ tài khoản server, không từ URL/form.
- Tất cả route upload, template, cấu hình, xem phiên bản, tạo tài khoản, công bố đều bắt buộc admin ở server. Trang cá nhân chỉ tải những buổi liên kết với người đăng nhập trong snapshot công bố; không trả toàn bộ lịch rồi lọc bằng trình duyệt.
- Dữ liệu lưu Excel với atomic replace và filelock. `dataset.xlsx` chứa dữ liệu đang sửa; `state.xlsx` chứa tài khoản hash, con trỏ lịch công bố và audit; `versions/*.xlsx` chứa snapshot lịch và người tham dự; `pending/*.xlsx` chứa nhập chờ xác nhận; `uploads/*.xlsx` chứa bản gốc đã quét. `session.key` là bí mật local để ký cookie.
- Đây là app local, chưa có HTTPS, email khôi phục mật khẩu hay mô hình triển khai nhiều máy. Người có quyền đọc filesystem runtime có thể đọc dữ liệu Excel; quyền web không thay thế quyền truy cập ổ đĩa.

## Phạm vi AI và đánh giá hackathon

Bộ xếp lịch dùng OR-Tools CP-SAT chạy thật trên máy, không gọi model LLM. Web không cần API key. `codebase/agent.py`/`ai.py` vẫn là luồng mẫu của khung; eval/simulate hiện chưa đo luồng web mới. Không dùng kết quả unit/integration test để tuyên bố đạt benchmark sản phẩm hay đã có lời gọi AI thật ở CP3. Giữ nguyên `run.py`, `tracing.py`, các bộ chạy eval/simulate, §7 và metric hiện tại.

Tài liệu chính thức: [CP-SAT](https://developers.google.com/optimization/cp/cp_solver/), [employee scheduling](https://developers.google.com/optimization/scheduling/employee_scheduling), [Flask security](https://flask.palletsprojects.com/en/stable/web-security/), [ClamAV](https://docs.clamav.net/manual/Usage/Scanning.html), [Microsoft Defender CLI](https://learn.microsoft.com/en-us/defender-endpoint/command-line-arguments-microsoft-defender-antivirus).
