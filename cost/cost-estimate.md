# Chi phí khi dùng thật

> 50 phiên gọi model thật qua agent benchmark. Số model OpenAI bên dưới tính trực tiếp từ token từng dòng trong CSV và giá chuẩn OpenRouter; hai dòng Gemini là dự báo nếu cùng lượng token được xử lý bởi các model đó.

## 1. Đầu vào

- **Persona:** dung_it (50%, 4 phiên/tháng, 1 lượt/phiên), dung_vua (30%, 10 phiên/tháng, 3 lượt/phiên), dung_nhieu (20%, 20 phiên/tháng, 5 lượt/phiên). Đây là **giả định nhóm**, chưa được kiểm chứng; khảo sát chỉ có n=4.
- **Quy mô kịch bản:** thấp 300 · cơ sở 700 · cao 1.000 người. Ba con số là **giả định nhóm**, chưa xác nhận bằng số tuyển sinh/vận hành chính thức.
- **Giá OpenRouter (USD / 1 triệu token, xem 28/11/2026):** GPT-4o-mini input $0.15, output $0.60; Gemini 3.1 Flash Lite input $0.25, output $1.50; Gemini 4 Hydrogen input $1.50, output $7.50. [GPT-4o-mini](https://openrouter.ai/openai/gpt-4o-mini) · [Gemini 3.1 Flash Lite](https://openrouter.ai/google/gemini-3.1-flash-lite) · [Gemini 4 Hydrogen](https://openrouter.ai/google/gemini-4-hydrogen).
- **Tỉ lệ đạt để tính chi phí/task:** 11/25 = 44%, eval/run-2.csv, run-2@20261128-113152.
- **Mô phỏng:** cost/simulate-1.csv · simulate-1@20261128-122744 · 50 phiên · seed 42 · 0 phiên lỗi; trace traces/simulate-1.jsonl.
- **Token thực đo:** 152.586 input và 24.803 output trên openai/gpt-4o-mini. Không tính phí cache riêng; estimate dùng giá chuẩn công khai.

## 2. Kết quả

| Model / cách tính | Chi phí / phiên | Chi phí / task thành công | / tháng — thấp (300) | / tháng — cơ sở (700) | / tháng — cao (1.000) | / người / tháng (cơ sở) |
|---|---:|---:|---:|---:|---:|---:|
| OpenAI GPT-4o-mini · token mô phỏng thực đo | $0.00076 | $0.00172 | $3.24 | $7.57 | $10.81 | $0.0108 |
| Gemini 3.1 Flash Lite · dự báo theo cùng token | $0.0015 | $0.0034 | $6.49 | $15.14 | $21.63 | $0.0216 |
| Gemini 4 Hydrogen · dự báo theo cùng token | $0.0083 | $0.0189 | $35.69 | $83.27 | $118.96 | $0.1190 |

Chi phí/task thành công = chi phí trung bình mỗi phiên ÷ tỉ lệ đạt 44%. Trung bình 2.3 lượt hỏi/phiên. Tỉ lệ phiên theo persona trong lần chạy: dung_it 26, dung_vua 16, dung_nhieu 8. Chi phí tháng dùng tỷ trọng persona, phiên/người/tháng và quy mô khai trong cost/personas.yaml; các đầu vào này là giả định.

**Đối chiếu dashboard:** ảnh OpenRouter nhóm cung cấp ghi tổng usage $0.0177 cho GPT-4o-mini trước lượt mô phỏng 50 phiên; đó là số gộp của dashboard, không tách riêng theo run. Không dùng nó làm chi phí của lượt này.

## 3. So với impact

- Impact/người/tháng trong spec §2: **chưa đo được**; chưa có dữ liệu đúng vai về thời gian xử lý pain và quy mô người dùng thực.
- Chi phí/người/tháng ở kịch bản cơ sở theo token GPT-4o-mini: **$0.0108**; dự báo Gemini: $0.0216–$0.1190.
- **Kết luận:** chưa thể kết luận economics đáng làm khi impact chưa đo và benchmark mới đạt 44%; tiếp tục kiểm chứng pain, cải thiện chất lượng và xác nhận quy mô trước quyết định triển khai.

## 4. Giới hạn

- GPT-4o-mini cost/session được tính lại từ token thực đo trong CSV × giá chuẩn OpenRouter ($0.15/M input, $0.60/M output); làm tròn trong bảng.
- Hai model Gemini là kịch bản giá dự báo, không phải benchmark chất lượng hay lượt chạy thật của Gemini.
- Chưa tính hosting, lưu trữ, vận hành, thuế/phí và thời gian admin duyệt.
- Tỷ trọng persona, mức dùng và quy mô 300/700/1.000 là giả định, không phải dữ liệu hành vi/quy mô đã xác minh.
