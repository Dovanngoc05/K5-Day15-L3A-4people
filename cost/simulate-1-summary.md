# Tóm tắt mô phỏng simulate-1@20261128-122744

Do `python run.py simulate` sinh ra — không sửa tay. Chép bảng sang `cost/cost-estimate.md`.

| Persona | Số phiên mô phỏng | Lượt hỏi / phiên | Token vào / phiên | Token ra / phiên | Gọi model / phiên | Gọi công cụ / phiên |
|---|---:|---:|---:|---:|---:|---:|
| dung_it | 26 | 1 | 1423 | 214 | 1.0 | 1.0 |
| dung_vua | 16 | 3 | 3489 | 564 | 3.0 | 3.0 |
| dung_nhieu | 8 | 5 | 7470 | 1275 | 5.0 | 5.0 |

Tỉ lệ đạt dùng để tính: 11/25 (44%) — lượt run-2@20261128-113152

- Tỉ lệ đạt lấy từ lượt nhóm chọn: eval/run-2.csv (--rate-from).

| Model (giá) | Chi phí / phiên | Chi phí / task thành công | Chi phí / câu hỏi đạt | Chi phí / tháng — thấp (300 người) | Chi phí / tháng — cơ sở (700 người) | Chi phí / tháng — cao (1.000 người) | Chi phí / người / tháng (cơ sở) |
|---|---:|---:|---:|---:|---:|---:|---:|
| gemini-3.1-flash-lite (vào 0.25 · ra 1.5 $/1M) | $0.0015 | $0.0034 | $0.0015 | $6.49 | $15.14 | $21.63 | $0.0216 |
| gemini-4-hydrogen (vào 1.5 · ra 7.5 $/1M) | $0.0083 | $0.0189 | $0.0083 | $35.69 | $83.27 | $118.96 | $0.1190 |

- Chi phí / task thành công = chi phí / phiên ÷ tỉ lệ đạt. Chi phí / câu hỏi đạt = chi phí / phiên ÷ số lượt hỏi trung bình mỗi phiên (2.3) ÷ tỉ lệ đạt — tỉ lệ đạt đo theo từng câu thử.
- Token đo trên model: openai/gpt-4o-mini. Giá tính theo từng model trong bảng — model khác bộ tách token thì số token thật có thể lệch; ghi rõ "đo trên model X, tính giá model Y" trong cost/cost-estimate.md.
- Phiên lỗi (không tính vào trung bình): 0/50.
