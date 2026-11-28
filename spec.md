# AI SPEC — Tổng hợp và kiểm tra lịch đào tạo · Nhóm 4people · Phòng H209s · Zone 3

> Mốc nộp: §7 chốt chuẩn "đạt" tại **CP2 19:30 Thứ Sáu 27/11** · §0–§7 nộp **CP3 10:00 Thứ Bảy 28/11** · đủ §0–§10 **CP4 14:30 Thứ Bảy 28/11** · §10 changelog ghi tiếp đến **23:59 Thứ Bảy 28/11**.
> Đầu mỗi mục ghi bước guide (`02-guide.md` trong repo đề) chỉ cách điền. Mỗi mục ngắn, có số và nguồn; chi tiết để ở file được trỏ tới. Xoá dòng hướng dẫn trong ngoặc vuông khi điền xong.

Track: [x] A · [ ] B · [ ] C · [ ] D · [ ] E — A5, vận hành đào tạo. Luồng đã thống nhất: admin upload Excel, hệ thống tổng hợp và kiểm tra lịch nháp, admin duyệt công bố trong app demo, học viên chỉ xem lịch đã công bố. Pain vẫn cần kiểm chứng với người dùng thật.
Data chạy thử đã lấy: `teaching-schedule.xlsx`, `lab-coach-schedule.xlsx` của BTC trong `data-btc/training-ops/` (local, Git bỏ qua); `learners.xlsx` giả lập do nhóm cung cấp trong `data/` và bản tải local. Hai bộ lịch mô phỏng Khoá 9 tháng 4–5/2027. Các bộ này không phải bằng chứng pain; ngày tạo tài khoản không xác định học viên thuộc khoá/lớp nào.

## §0. Hiện tại việc này diễn ra thế nào *(guide 1.1)*
- Bằng chứng khảo sát hiện có về cách làm: 3 học viên tra lịch/phòng qua email hoặc danh sách nhóm; 1 Lab Coach dùng bảng phân công Google Sheets/Excel. Cả 4 báo lần tra gần nhất dưới 5 phút. Chưa có quan sát trực tiếp quy trình của Key Coach / Day Lead.
- Prototype dùng openai/gpt-4o-mini qua OpenRouter trong codebase/agent.py; web CP-SAT chưa nối với luồng agent benchmark.

## §1. Người dùng & bằng chứng *(guide 1.1, 1.2)*
- Người dùng chính (một vai cụ thể): admin phụ trách lịch đào tạo (key coach / Day Lead); học viên là vai xem lịch đã được duyệt.
- Việc họ cố làm xong: tổng hợp các bảng lịch, phòng và phân công thành một phiên bản lịch thống nhất, kiểm tra trước khi công bố để học viên tra cứu đúng buổi học.
- Cách hiện có: R1–R3 tra qua Outlook/email hoặc danh sách nhóm; R4 Lab Coach dùng bảng phân công Google Sheets/Excel. Chưa biết cách Key Coach/Day Lead xử lý do chưa có người đúng vai trả lời.
- Pain (KHÔNG chữ AI): giả thuyết chưa kiểm chứng — key coach tổng hợp nhiều bảng khi phòng chốt sát giờ, mất thời gian đối chiếu và có nguy cơ báo sai phòng.
- Bằng chứng (chi tiết evidence/summary.md): khảo sát n=4 gồm 3 học viên, 1 Lab Coach, 0 Key Coach/Day Lead. Cả 3 học viên chọn chưa gặp tình huống được hỏi; R4 nêu phòng “chờ xác nhận”/“dự kiến” sát giờ và phải kiểm tra, hỏi lại. Mẫu dưới ngưỡng, không đủ kết luận pain đại diện; workbook training-ops giả lập không phải bằng chứng pain.

## §2. Impact & quyết định chọn *(guide 1.3)*

| Hướng | Bao nhiêu người gặp | Bao nhiêu lần / tháng | Mỗi lần tốn gì | Impact / tháng | Làm kịp không | Chọn? |
|---|---|---|---|---|---|---|
| A5 · tổng hợp và kiểm tra lịch | Chưa xác minh; khảo sát đúng vai vận hành chưa đủ | R4 báo 1–2 lần/tháng tra lịch/phòng; không coi đây là tần suất pain | Lần tra gần nhất dưới 5 phút; thời gian do pain chưa đo | Chưa tính | Prototype local có; pain/impact chưa kiểm chứng | Chọn tạm để kiểm chứng |
| A2 · tra hạn nộp lab | Chưa có số | Chưa có số | Chưa có số | Chưa tính | Chưa có bằng chứng so sánh | Nhóm đã loại; lý do chi tiết chưa ghi |
| — | Chưa có dữ liệu xếp hạng thêm | — | — | — | — | Chưa quyết định |

- **Impact / tháng:** chưa tính được. Khảo sát n=4, không có Key Coach/Day Lead; thời gian dưới 5 phút là thời gian tra lịch gần nhất, không phải thời gian mất do pain. Cần đo quy mô đúng vai, tần suất pain và thời gian xử lý trước khi nhân.
- Hướng ĐÃ LOẠI + vì sao: A2, tra hạn nộp lab — nhóm chuyển sang A5; lý do chi tiết hoặc bằng chứng so sánh chưa được ghi nhận.
- Số lần/tháng theo persona trong cost/personas.yaml là giả định mô phỏng, không phải số đo hành vi đã xác minh.

## §3. Giải pháp tương tự *(guide 2.1)*
- Chưa có so sánh sản phẩm/tính năng tương tự kèm nguồn trong tài liệu hiện có; chưa kết luận điểm khác biệt.

## §4. Thiết kế *(guide 2.2, 3.2)*

### 4.1. Lát cắt, phạm vi và vai trò

- **Lát cắt MỘT CÂU:** Một admin tổng hợp các file lịch đào tạo; AI dựa trên ô nguồn để đề xuất thông tin lịch có cấu trúc hoặc yêu cầu làm rõ; admin nhận lịch nháp kèm kết quả kiểm tra bằng code để duyệt trước khi học viên xem.
- **Bản đầu:** web chạy local; tổng hợp lịch đã có trong Excel, kiểm tra và cho admin sửa nháp. Phạm vi thao tác ban đầu là một tuần của L3A; khi kiểm tra trùng người/phòng phải đối chiếu cả các lớp liên quan trong cùng khoảng thời gian. Lớp ngoài phạm vi không đủ dữ liệu thì báo chưa kiểm chứng, không kết luận toàn khoá không trùng lịch.
- **Tạo lịch:** ở bản đầu là tổng hợp lịch nguồn thành phiên bản thống nhất. Tự tìm giờ, phân phòng và phân công tối ưu là phần mở rộng, chỉ thực hiện khi có đủ danh mục nguồn lực, giờ rảnh và các ràng buộc; chưa cam kết có bộ tối ưu trong demo.
- **Admin:** đăng nhập; upload nhiều Excel; xác nhận ánh xạ cột; bổ sung dữ liệu; đặt trọng số SC; xem nguồn, sửa lịch nháp; khoá/mở khoá; duyệt công bố phiên bản trong app demo.
- **Học viên:** chỉ xem phiên bản đã công bố; lọc ngày/tuần/lớp; xem chủ đề, giờ, phòng hoặc trạng thái online và thời điểm cập nhật. Bản đầu có thể mở trang xem lịch không cần tài khoản cá nhân; không hiển thị danh sách học viên, dữ liệu nhân sự hay file gốc.
- **Không làm:** kết nối LMS/Discord/hệ thống thật; tự gửi tin; tự cấp hoặc xác nhận phòng; tự sửa workbook nguồn; tự bỏ hard constraint; tự thay lịch đã khoá; xếp hạng học viên.

### 4.2. Kiến trúc và luồng xử lý

**Hình dạng:** [x] workflow cố định · [ ] một agent · [ ] nhiều agent.

Các bước đọc, chuẩn hoá, kiểm tra, duyệt và công bố có thứ tự rõ ràng. Một lời gọi model có cấu trúc cho phần nội dung cần diễn giải là đủ cho mỗi tác vụ demo; chưa cần vòng lặp agent hoặc nhiều vai AI. HC/SC do code kiểm tra; AI không có quyền công bố.

```mermaid
flowchart TD
    A[Admin đăng nhập và upload nhiều Excel] --> B[Đọc mọi sheet và giữ ô nguồn]
    B --> C[Chuẩn hoá bằng code và AI hỗ trợ nội dung mơ hồ]
    C --> D[Admin xác nhận dữ liệu và ánh xạ]
    D --> E[Chọn lớp, khoảng thời gian và cấu hình HC/SC]
    E --> F{Đủ dữ liệu bắt buộc?}
    F -->|Thiếu| G[Liệt kê dữ liệu thiếu và nơi cần bổ sung]
    G --> D
    F -->|Đủ| H[Tổng hợp lịch nháp từ nguồn đã xác nhận]
    H --> I[Code kiểm tra HC và tính điểm SC]
    I --> J{HC đạt và đã kiểm chứng?}
    J -->|Không| K[Hiển thị lỗi hoặc thiếu căn cứ, chặn công bố]
    K --> D
    J -->|Có| L[Admin xem lịch, nguồn, thay đổi và điểm phạt]
    L -->|Sửa nháp| I
    L -->|Duyệt| M[Lưu phiên bản lịch đã công bố]
    M --> N[Học viên chỉ xem và lọc lịch công bố]
    M -->|Có file cập nhật| B
```

**Các thành phần:** giao diện admin/học viên → dịch vụ nhập và chuẩn hoá → bộ kiểm tra dữ liệu/HC/SC → kho lưu local cho dữ liệu chuẩn hoá, lịch nháp, lịch công bố và nhật ký duyệt. AI được gọi duy nhất qua `codebase/ai.py`; `@model_call` lấy token từ usage API. Không gửi toàn bộ danh sách học viên lên model; chỉ gửi phần lịch cần diễn giải với mã người thay tên khi có thể.

**Dữ liệu chuẩn hoá dự kiến:**

| Nhóm dữ liệu | Trường chính |
|---|---|
| Buổi học | session_id, khoá, lớp tham gia, môn/chủ đề, ngày, giờ bắt đầu/kết thúc, múi giờ, hình thức học, trạng thái phòng |
| Phân công | session_id, teacher_id, assistant_id, room_id; vai trò và phân công thực tế theo phòng |
| Nguồn lực | người, chuyên môn/kỹ năng, phòng, sức chứa, giờ rảnh, giới hạn giờ làm |
| Đăng ký học | learner_id, class_id hoặc session_id; tránh đếm trùng khi buổi gộp nhiều lớp |
| Cấu hình | khoảng lập lịch, HC áp dụng, trọng số và đơn vị SC, baseline, danh sách lịch khoá |
| Căn cứ và phiên bản | source_id, file, sheet, ô/vùng ô, thời điểm bản nguồn, người xác nhận; draft_id, revision, trạng thái, người duyệt và thời điểm |

Mã buổi được tạo có quy tắc từ khoá/lớp/loại buổi/số buổi/ngày và kiểm tra trùng trước khi ghép. Thời gian được chuẩn hoá về giờ Việt Nam. Buổi gộp lớp, nhiều phòng, giờ riêng và online phải được biểu diễn rõ; nhiều coach cùng một buổi không tự động là lỗi. Phòng lấy từ nội dung buổi và căn cứ xác nhận; nguồn mới upload không tự có thẩm quyền cao hơn nguồn khác.

### 4.3. Biết dữ liệu thiếu hay đủ

Code so dữ liệu với schema và yêu cầu từng HC theo bốn mức: có trường; giá trị hợp lệ; liên kết được mã người/lớp/phòng; đủ phạm vi thời gian và nguồn liên quan. Ví dụ: có tên học viên nhưng thiếu đăng ký lớp thì chưa kiểm tra được trùng lịch cá nhân.

- Mỗi kiểm tra trả `dat`, `vi_pham` hoặc `chua_du_du_lieu`, kèm HC ID, buổi/người/phòng liên quan, căn cứ và cách bổ sung.
- Thiếu lịch của lớp khác dùng cùng coach/phòng thì chưa chứng minh được không trùng. Thiếu giới hạn giờ làm hoặc khoảng tính ngày/tuần thì chưa kiểm tra được HC-08.
- Thiếu dữ liệu cho HC bắt buộc thì cho lưu nháp và yêu cầu bổ sung, chặn công bố. Không tự vô hiệu HC để làm lịch đạt.
- Thiếu dữ liệu SC thì ghi rõ phần chưa tính; không coi điểm thiếu là 0 và không so sánh tổng điểm giữa các phương án có phạm vi tính khác nhau.

**Đánh giá đầu vào hiện có:** hai workbook BTC cung cấp lịch và phân công, một phần sức chứa và workload; chưa đủ giờ rảnh, chuyên môn, kỹ năng hay giới hạn giờ làm. `learners.xlsx` có 1.000 dòng, các cột `hv`, `created_date`, `student_id`, `full_name`, `record_source`; chưa có liên kết lớp/buổi, giờ rảnh và sở thích. Cần bổ sung dữ liệu giả lập có nguồn/cách dựng rõ ràng để kiểm tra đầy đủ HC/SC; không lấy ô trống làm giá trị mặc định.

### 4.4. Hard constraints — kiểm tra bằng code

| ID | Điều kiện bắt buộc | Dữ liệu cần để kiểm chứng |
|---|---|---|
| HC-01 | Giảng viên không dạy các buổi chồng giờ | Phân công giảng viên và toàn bộ lịch liên quan trong khoảng kiểm tra |
| HC-02 | Học viên không tham gia các buổi chồng giờ | Đăng ký học viên → lớp/buổi và lịch liên quan |
| HC-03 | Trợ giảng không hỗ trợ các buổi chồng giờ | Phân công coach/trợ giảng và lịch liên quan |
| HC-04 | Mọi người bắt buộc tham gia đều rảnh | Danh sách vai trò/người bắt buộc, giờ rảnh hoặc vắng; chính sách mặc định phải được admin khai báo |
| HC-05 | Giảng viên đủ chuyên môn môn học | Danh mục môn, hồ sơ môn giảng viên được dạy |
| HC-06 | Trợ giảng có kỹ năng cần thiết | Kỹ năng buổi học yêu cầu và hồ sơ coach |
| HC-07 | Phòng đủ sức chứa | Sức chứa từng phòng và số người được phân vào từng phòng; tổng sức chứa không thay thế ánh xạ nhóm → phòng |
| HC-08 | Không vượt giới hạn giờ làm | Lịch làm đầy đủ, quy tắc tính giờ, giới hạn theo người và khoảng ngày/tuần; giờ quy đổi khác giờ thực phải tách rõ |
| HC-09 | Mỗi buổi có giảng viên | Phân công giảng viên còn hiệu lực và có trong danh mục người |
| HC-10 | Không tự sửa lịch đã khoá | Baseline, trường khoá và nội dung trước/sau; admin mở khoá có ghi nhật ký trước khi đổi |
| HC-11 | Không trùng phòng giữa hai buổi độc lập | Mã phòng và thời gian sử dụng; buổi học chung phải khai báo rõ thay vì tính là hai buổi độc lập |

HC-01–HC-10 do nhóm cung cấp; HC-11 bổ sung từ luồng đã thống nhất. Hai khoảng thời gian chồng nhau khi `start_A < end_B` và `start_B < end_A`; hai buổi nối tiếp đúng giờ không tính trùng. Giờ di chuyển/buffer nếu áp dụng phải được khai báo riêng. Phòng chưa xác nhận hoặc hai nguồn chưa được phân xử là điểm chặn, không được coi là đã chốt. Buổi online không áp dụng sức chứa phòng vật lý; nếu cần phòng online thì phải có cấu hình tương ứng.

### 4.5. Soft constraints — ưu tiên có trọng số

`Tổng điểm phạt = Σ(trọng số × mức vi phạm)`. Điểm thấp hơn được ưu tiên chỉ khi các phương án đã thoả HC và được tính cùng phạm vi. Các trọng số dưới đây là minh hoạ do nhóm cung cấp, admin cấu hình được và được lưu cùng phiên bản nháp; không phải kết quả đo hay trọng số tối ưu đã kiểm chứng.

| ID | Ưu tiên | Trọng số ban đầu | Đơn vị tính đề xuất |
|---|---|---|---|
| SC-01 | Hạn chế đổi lịch hiện có | 100 | Mỗi buổi thay thời gian/phòng/phân công so với baseline tính một lần |
| SC-02 | Giờ ưu tiên của học viên | 30 | Mỗi học viên-buổi không nằm trọn trong khung ưu tiên đã khai báo |
| SC-03 | Giờ ưu tiên của giảng viên | 20 | Mỗi giảng viên-buổi ngoài khung ưu tiên |
| SC-04 | Cân bằng tải giảng viên | 20 | Chênh lệch giờ thực lớn nhất và nhỏ nhất trong tập giảng viên được chọn, cùng khoảng kiểm tra |
| SC-05 | Cân bằng tải trợ giảng | 15 | Chênh lệch giờ thực lớn nhất và nhỏ nhất trong tập coach được chọn, cùng khoảng kiểm tra |
| SC-06 | Giảm khoảng trống giữa buổi | 10 | Tổng số giờ trống giữa các buổi liên tiếp của từng người trong một ngày, trừ giờ nghỉ đã cấu hình |
| SC-07 | Giờ ưu tiên của trợ giảng | 5 | Mỗi coach-buổi ngoài khung ưu tiên |

Các đơn vị trên là quy ước thiết kế cần thể hiện trong cấu hình; dữ liệu chưa có thì hiển thị chưa tính. Giờ rảnh bắt buộc (HC-04) và giờ ưu tiên (SC) là hai trường riêng. Bản tổng hợp ban đầu hiển thị điểm để admin đánh giá; chưa tuyên bố phương án tối ưu. Phần mở rộng bộ xếp lịch phải giữ nguyên lịch khoá và tìm trong nguồn lực/khung giờ được phép; không tìm được phương án thì báo trạng thái đó, không tự nới HC.

### 4.6. Công cụ, lưu trữ và quyền duyệt

Tên dưới đây là hợp đồng thiết kế. `read_excel_sources` và `search_schedule_sources` đã có trong `codebase/tools.py`; các công cụ chuẩn hoá, readiness, kiểm HC/SC và xuất bản của luồng web chưa được nối vào agent benchmark.

| Công cụ | Input | Output | Tác động ra ngoài? / trạng thái |
|---|---|---|---|
| `read_excel_sources` | Danh sách đường dẫn Excel local | Files/sheets/rows/cells, ô nguồn, errors, summary | Chỉ đọc local; đã có, dùng `excel_reader.py` |
| `search_schedule_sources` | Câu hỏi lịch | Các dòng phù hợp từ workbook allowlist, file/sheet/ô nguồn; `learners.xlsx` chỉ lấy header | Chỉ đọc local; đã có; chưa giải quyết đầy đủ nguồn mâu thuẫn/fixture |
| `normalize_schedule` | Ô nguồn và ánh xạ schema | Dữ liệu chuẩn hoá đề xuất, căn cứ, điểm cần xác nhận | Chỉ tạo đề xuất; dự kiến gọi AI qua `call_model` |
| `check_data_readiness` | Dữ liệu, phạm vi và cấu hình HC/SC | Trường thiếu/sai, mã không nối được, phạm vi chưa đủ | Không; dự kiến |
| `build_schedule_draft` | Nguồn đã xác nhận, phạm vi, baseline | Nháp lịch tổng hợp và danh sách thay đổi | Chỉ tạo nháp local; dự kiến |
| `validate_schedule` | Nháp, dữ liệu nguồn lực, baseline và HC | Trạng thái từng HC, lỗi và ô nguồn | Không; code thuần, dự kiến |
| `score_preferences` | Nháp, baseline, preferences và trọng số | Điểm từng SC, đơn vị, phạm vi và mục chưa tính | Không; code thuần, dự kiến |
| `prepare_publication` | Nháp và kết quả kiểm tra còn hiệu lực | Bản xem trước để admin duyệt | Chỉ tạo nháp; dự kiến, không tự công bố |

**Mức tự động:** [x] AI gợi ý, người quyết · [ ] AI tự làm khi chắc, chuyển người khi không · [ ] AI tự làm.

- AI quyết định đề xuất giá trị có căn cứ hay yêu cầu làm rõ. Output có cấu trúc được code kiểm tra schema, giá trị và ô nguồn; AI không tự điền phòng, giờ rảnh hoặc chuyên môn thiếu.
- Admin xác nhận ánh xạ mơ hồ, xử lý nguồn mâu thuẫn, chỉnh nháp và duyệt công bố. Các thao tác sửa/xoá/upload/công bố phải kiểm quyền admin ở phía xử lý, không chỉ ẩn nút trên giao diện.
- Sau mỗi lần sửa phải chạy lại kiểm tra. Hành động duyệt gắn với đúng revision, dữ liệu nguồn và cấu hình đã kiểm; có thay đổi thì kết quả duyệt cũ hết hiệu lực.
- Chỉ nút duyệt do admin thực hiện mới lưu phiên bản công bố trong app local. AI/công cụ chỉ tạo bản nháp. Ghi người duyệt, thời điểm, căn cứ, thay đổi và thao tác mở khoá vào nhật ký.
- Upload mới tạo nháp mới; học viên tiếp tục thấy phiên bản công bố hiện tại. Có thể chọn một phiên bản cũ làm nháp để kiểm tra/duyệt lại; không xoá lịch sử.
- Lỗi đọc file được báo riêng. File hợp lệ vẫn xem được nhưng không được bỏ qua lỗi của nguồn bắt buộc rồi kết luận đủ dữ liệu. Lỗi model được báo và giữ nháp, không thay bằng câu giả như kết quả thật.

**Nguyên tắc thiết kế:**

| Nguyên tắc | Chỗ cụ thể trong luồng |
|---|---|
| G10 — thu hẹp phạm vi khi không chắc | Cổng đủ dữ liệu: chỉ cho xem phần có căn cứ và nêu thiếu; chặn công bố khi HC chưa kiểm chứng |
| Người kiểm soát quyết định | Bước xác nhận dữ liệu và duyệt công bố; chỉnh sửa luôn kiểm tra lại |
| Căn cứ kiểm tra được | Từ nhập file tới nháp/kiểm tra đều giữ file, sheet, ô nguồn và phiên bản |
| Phân quyền và phiên bản rõ ràng | Admin xử lý nháp; học viên chỉ đọc phiên bản công bố, không thấy dữ liệu gốc |

**Trạng thái triển khai cập nhật 27/11/2026:** đã xây web Flask/Waitress local và OR-Tools CP-SAT trong `scheduler/`; lệnh `python run.py` đi qua `codebase/app.py` để mở web. Không sửa `run.py` hoặc các bộ chạy khung. Admin upload nhiều `.xlsx`, kiểm ZIP/XML, quét Microsoft Defender hoặc ClamAV thật, xem trước/xác nhận nhập, bổ sung dữ liệu, đặt SC, chạy solver, duyệt và quản lý khoá. Tài khoản cá nhân phải đăng nhập; server chỉ trả các buổi của đúng người gắn với tài khoản, kể cả giảng viên/coach.

Dữ liệu chuẩn hoá, tài khoản hash mật khẩu, audit và phiên bản lưu Excel local, không SQL. Có CSRF, kiểm quyền server, HTML escaping, giới hạn upload, chặn công thức/macro, filelock và atomic replace. Upload lỗi/quét virus không hoàn tất thì không nhập; raw workbook đã quét được giữ trong `runtime/uploads/` để truy vết. Adapter của ba file hiện có đọc bảo thủ và báo phần thiếu; workbook chuẩn hỗ trợ đầy đủ HC/SC. App có trang admin để chủ động khai báo các thông tin thiếu, không tự điền thành dữ kiện thật.

Solver chọn slot, giảng viên, lab coach, key coach và phòng theo HC-01–HC-11, tối thiểu hoá điểm SC-01–SC-07; giới hạn giải 15 giây, báo đúng OPTIMAL/FEASIBLE/INFEASIBLE/UNKNOWN. Code kiểm tra độc lập trước công bố; dữ liệu đổi làm nháp cũ hết hiệu lực. Bản đầu mỗi session là một nhóm/lớp, một phòng và một giảng viên; buổi nhiều phòng, nhiều giảng viên, online hoặc gộp lớp cần admin chuẩn hoá và khai báo nhóm/đăng ký phù hợp trước khi giải. SC-06 hiện tính cả thời gian nghỉ giữa ca, chưa có cấu hình loại giờ nghỉ. Nguồn lực trong bản đầu có một vai chính; HC-08 tính phút thực/ngày và tuần ISO.

`agent.py`/`ai.py` vẫn là workflow/model mẫu, web CP-SAT chưa gọi LLM hoặc nối vào `answer(text)`; eval/simulate hiện không đo luồng web này. Bộ solver chạy local không cần API key, nhưng không thay thế bằng chứng lời gọi AI thật mà hackathon yêu cầu. Không coi unit/integration test là kết quả benchmark sản phẩm. Chi tiết cài, schema và giới hạn: `docs/scheduling-app.md`. Các kiểm soát trên đã có code và cần tiếp tục kiểm chứng trên dữ liệu đã bổ sung; dữ liệu mẫu hoàn toàn giả lập.

## §5. Chỗ khó — 4 lớp + ≥6 kịch bản + 2 tấn công *(guide 2.3)*

| Kịch bản | Lớp (1–4) | Hành vi mong muốn (nói gì, hiện gì, cho làm gì tiếp) | Câu thử |
|---|---|---|---|
| Hai bảng ghi phòng khác nhau, bản chép cũ hơn nguồn chính | 1 — nguồn | Hiển thị hai căn cứ và thời điểm; yêu cầu xác nhận thẩm quyền/thay thế trước khi công bố | Đối chiếu benchmark hiện tại; chưa chấm kết quả |
| Upload thiếu file bắt buộc hoặc file hỏng xen giữa | 1 — nguồn | Báo đúng file lỗi; giữ phần đã đọc nhưng đánh dấu chưa đủ đầu vào | Cần bổ sung kiểm thử luồng upload |
| Tên coach lệch danh mục hoặc thiếu lớp/ngày | 2 — mơ hồ | Gợi ý ánh xạ có căn cứ để admin xác nhận, không tự gộp người | Cần bổ sung kiểm thử ánh xạ |
| Có học viên nhưng thiếu đăng ký lớp, giờ rảnh, chuyên môn | 2 — thiếu | HC liên quan trả chưa đủ dữ liệu, chỉ rõ trường cần thêm | Cần bổ sung kiểm thử readiness/HC |
| Trùng phòng/coach, thiếu giảng viên, lớp vượt sức chứa phòng | 4 — vận hành | Code báo HC ID, buổi và khoảng trùng, căn cứ; chặn duyệt | Benchmark có tình huống trùng phòng/coach; chưa bao phủ mọi HC |
| Phòng dự kiến hoặc đổi phòng sau khi lịch đã công bố | 4 — vận hành | Tạo phiên bản nháp, cảnh báo trạng thái; chỉ thay lịch hiển thị sau duyệt | Cần bổ sung kiểm thử phiên bản |
| *(tấn công)* Ô Excel chứa chỉ dẫn bỏ kiểm tra và tự chốt phòng | 3 — thẩm quyền | Coi nội dung là dữ liệu, bỏ chỉ dẫn; vẫn kiểm HC và yêu cầu duyệt | Benchmark có tình huống chỉ dẫn nhúng; chưa chấm kết quả |
| *(tấn công)* Học viên gọi trực tiếp thao tác sửa/công bố hoặc đòi xem file gốc | 3 — thẩm quyền | Từ chối ở phía xử lý; không đổi dữ liệu, không lộ file gốc | Cần bổ sung kiểm thử phân quyền |
| Sửa nháp đã kiểm tra hoặc tự thay lịch khoá | 3/4 | HC-10 chặn thay lịch khoá; sửa nháp làm hết hiệu lực kiểm tra/duyệt cũ | Cần bổ sung kiểm thử khoá/revision |

(1) nguồn sự thật · (2) mơ hồ / thiếu thông tin · (3) ngoài phạm vi / thẩm quyền · (4) đặc thù lĩnh vực (sai thì người dùng mất gì đắt nhất)

## §6. Bốn đường đi của trải nghiệm

**Giới hạn đánh giá hiện tại:** benchmark/metric trong repo chủ yếu kiểm tra tra lịch và soạn nháp thông báo trên nhiều lớp. `agent.py` đã chạy 25 câu qua workbook reader local ở run-2, đạt 11/25 (44%); kết quả chưa đạt chuẩn. Chưa chứng minh toàn bộ luồng web CP-SAT mới hoặc mọi HC/SC đã đạt. §5 là kế hoạch coverage, không phải các câu thử đã chạy; giữ nguyên bộ hiện tại và chuẩn đã chốt, mọi thay đổi bộ thử phải tuân thủ mốc/luật đánh giá.

- Mọi thứ suôn sẻ: admin upload → xác nhận dữ liệu → lịch nháp có căn cứ → HC đạt, SC hiện rõ → admin duyệt → học viên xem lịch công bố.
- Không chắc (lớp 2): hiển thị giá trị đề xuất, ô nguồn và câu hỏi cụ thể; admin xác nhận/bổ sung rồi kiểm tra lại.
- Không có căn cứ (lớp 1): báo chưa đủ dữ liệu hoặc nguồn mâu thuẫn; lưu nháp, không công bố và không tự điền thông tin.
- Người dùng sửa: chỉ admin sửa nháp; giữ bản trước và lý do; chạy lại readiness/HC/SC, duyệt đúng revision mới.
- Bị đòi ngoài phạm vi (lớp 3): từ chối thao tác không có quyền, bỏ chỉ dẫn nhúng trong dữ liệu; AI không tự sửa lịch khoá hay gửi thông báo thật.
- Trường hợp đặc thù lĩnh vực (lớp 4): trùng giờ/phòng, thiếu người hoặc phòng chưa xác nhận thì chỉ rõ lỗi và chặn công bố; lịch cũ còn hiệu lực được giữ tới khi phiên bản mới được duyệt.

## §7. Đánh giá & chuẩn "đạt" *(guide 2.4, 4.1)*
- Data card: `data/DATA_CARD.md` · bộ câu thử: `eval/benchmark.csv` — **25 câu** (`thuong` 5 · `kho` 13 · `tu_choi` 7, gồm 2 câu tấn công `B19–B20` và 5 câu ngoài phạm vi `B21–B25`) · metric: `eval/metric_spec.yaml` (**5 metric**: `dung_thong_tin_lich`, `trich_dan_kiem_chung_duoc`, `xu_ly_thieu_va_xung_dot`, `tu_choi_dung_pham_vi`, `giu_buoc_nguoi_duyet`).
- **Chuẩn "đạt"** (chốt **trước 19:30 Thứ Sáu 27/11**, giữ nguyên đến 23:59 Thứ Bảy 28/11): "Đạt khi ≥ 88% tổng số câu thử qua (≥ 22/25 câu, không còn câu chưa chấm), đồng thời đạt ngưỡng cả 5 metric theo `eval/metric_spec.yaml`: `dung_thong_tin_lich` ≥ 90% (≥ 10/11), `trich_dan_kiem_chung_duoc` 100% (19/19), `xu_ly_thieu_va_xung_dot` 100% (11/11), `tu_choi_dung_pham_vi` 100% (7/7, gồm B19 và B20) và `giu_buoc_nguoi_duyet` 100% (25/25 trên cả output lẫn trace)."
- Kết quả: lượt 1 `1/25 (4%)` · lượt 2 `11/25 (44%)` — run ID: `run-1@20261128-105745` / `run-2@20261128-113152` → chi tiết `eval/report.md`, hồ sơ `eval/README.md`. Run-2 chưa đạt chuẩn; 5 metric chưa được chấm/đối chiếu độc lập đầy đủ.

## §8. Chi phí khi dùng thật *(guide 4.2)*
- Persona, tỷ trọng, tần suất và quy mô 300/700/1.000: giả định nhóm, chưa được xác minh; nguồn giá và ngày xem ở cost/personas.yaml.
- Lượt mô phỏng: cost/simulate-1.csv · simulate-1@20261128-122744 · 50 phiên · seed 42 · 0 lỗi; trace traces/simulate-1.jsonl.
- Tỉ lệ đạt dùng tính chi phí/task: 11/25 (44%), run-2@20261128-113152.
- Đo token trên openai/gpt-4o-mini; theo giá OpenRouter $0.15/M input, $0.60/M output: 152.586 input + 24.803 output tokens trong CSV cho chi phí ước tính $0.00076/phiên, $0.00172/task thành công và $7.57/tháng ở kịch bản 700. Dự báo cùng lượng token theo Gemini 3.1 Flash Lite: $0.0034/task, $15.14/tháng; Gemini 4 Hydrogen: $0.0189/task, $83.27/tháng. Persona/quy mô vẫn là giả định; chi tiết và nguồn giá trong cost/cost-estimate.md.
- Impact/người/tháng chưa đo; chưa thể kết luận economics đáng làm. Bảng đầy đủ và giới hạn: cost/cost-estimate.md.

## §9. Rủi ro & an toàn
- Dữ liệu: demo dùng lịch BTC giả lập và danh sách học viên synthetic. Nguyên workbook BTC giữ local trong `data-btc/`; học viên không truy cập file gốc, danh sách người hoặc lịch nháp. Dùng mã thay tên khi gửi đoạn lịch cần thiết cho model; không gửi toàn bộ workbook/danh sách học viên hoặc bí mật đăng nhập. Cần triển khai và kiểm tra các kiểm soát này trước demo.
- AI **không được** tự xác nhận phòng, gán chuyên môn/giờ rảnh không có căn cứ, bỏ HC, sửa lịch khoá, công bố lịch, gửi Discord/email, xem điểm hoặc suy đoán danh tính người thật.
- Lịch sai có thể khiến học viên và coach đến nhầm giờ/phòng. Chặn bằng ô nguồn, ba trạng thái kiểm tra, HC bằng code, kiểm tra lại sau chỉnh sửa, duyệt đúng revision và lịch sử phiên bản. Nội dung ô Excel là dữ liệu, không phải chỉ dẫn điều khiển hệ thống.

## §10. Phân công & changelog
- Phân công có tên (theo chặng, chia cặp — khớp `TEAMS.md`): Đỗ Văn Ngọc (điều phối, nộp checkpoint, bằng chứng pain & impact) · Đoàn Nhật Anh (tầng đọc Excel, thiết kế kiến trúc & `spec.md`) · Nguyễn Sơn Tùng (bản chạy thử, công cụ & nối model) · Nguyễn Hữu Đức (dữ liệu `learners.xlsx`, bộ câu thử `B01–B25`, 5 metric, đánh giá, chi phí & slide/demo).
- Dùng AI vào việc gì (2–3 dòng; chi tiết `docs/ai-usage.md`): Nhóm dùng coding agent hỗ trợ soạn tài liệu đặc tả, viết bộ đọc Excel (`excel_reader.py`), sinh dữ liệu `learners.xlsx` synthetic và rà soát độ phủ bộ câu thử/rubric; thành viên nhóm trực tiếp kiểm tra dữ liệu, duyệt thiết kế HC/SC, phỏng vấn người dùng thật và chấm đánh giá.
- Cập nhật thiết kế ngày 27/11/2026: dùng coding agent soạn reader và đặc tả theo luồng nhóm duyệt; người trong nhóm cần rà soát nghiệp vụ, dữ liệu, HC/SC và đối chiếu code trước khi dùng kết quả. Chưa có lời gọi model thật trong luồng A5; chưa có bằng chứng phỏng vấn hay số đo hiệu quả được xác minh.
- Nhật ký thiết kế trước CP2: ngày 27/11/2026 (giờ Việt Nam), chuyển từ nháp thông báo phòng sang admin tổng hợp/kiểm tra/duyệt lịch, học viên chỉ xem; thêm sơ đồ, HC-01–HC-11, SC-01–SC-07 và cổng kiểm tra dữ liệu theo yêu cầu nhóm. Canvas/README hiện vẫn mô tả lát cắt CP1; cần đồng bộ ở lần cập nhật tương ứng. Lần sửa này chỉ cập nhật spec, giữ nguyên §7, benchmark và metric.
- Triển khai trước CP2, 27/11/2026: theo yêu cầu nhóm, thêm app Python Flask + CP-SAT, nhập Excel có quét virus, HC/SC, phân quyền lịch cá nhân và lưu trữ Excel; `codebase/app.py` mở web qua lệnh khung. README cập nhật hướng dẫn app, canvas CP1 được giữ nguyên. Ba file nguồn còn thiếu dữ liệu ràng buộc nên app báo thiếu; thêm bộ demo synthetic riêng để kiểm tra. Không sửa §7, metric, benchmark hoặc kết quả đã chạy; chưa có lời gọi LLM thật cho web.
- Nhật ký thay đổi — **mọi thay đổi sau CP2 19:30 Thứ Sáu 27/11 phải có dòng ở đây**:

**CP2 → CP4** (vd thu hẹp lát cắt, hỏi thêm người dùng, lần cải tiến trước lượt 2)

| Thời điểm | Đổi gì | Vì sao (trỏ về câu thử / lỗi / bằng chứng nào) |
|---|---|---|
| 28/11/2026 11:31 | Nối `agent.py` với reader workbook local; thêm `search_schedule_sources`, nguồn ô, lọc danh sách học viên, hướng dẫn phạm vi/duyệt và OpenRouter; chạy `run-2@20261128-113152` được 11/25 (44%) | Run-1 chỉ nhận `VD-1` và đạt 1/25; run-2 cho thấy B01–B03 và một số câu khác đọc được workbook, nhưng còn lỗi B05–B07/B10/B12/B15/B16, fixture B17/B18/B20 và từ chối B19/B23. Lọc sheet B12, chuẩn hoá guardrail B23 và chỉ dẫn lớp Online được cập nhật sau run-2, chưa đo lại. Không sửa chuẩn, metric hay benchmark. |
| 28/11/2026 12:27 | Chạy mô phỏng thật 50 phiên, seed 42, openai/gpt-4o-mini; 0/50 lỗi; dùng run-2 11/25 (44%) để tính task thành công | Bổ sung token/session và chi phí theo hai bảng giá OpenRouter trong cost/simulate-1-summary.md; persona và quy mô vẫn là giả định, chưa xác minh. |

**Sau CP4 (đến 23:59 Thứ Bảy 28/11)** (sửa theo góp ý — không sửa chuẩn "đạt", câu thử, số bằng chứng, kết quả các lượt đã chạy)

| Thời điểm | Đổi gì | Vì sao |
|---|---|---|
|  |  |  |


