# Changelog

Mọi thay đổi đáng chú ý của TinNhanh AI được ghi lại ở đây.

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/),
dự án dùng [Semantic Versioning](https://semver.org/lang/vi/).

## [1.0.0] - 2026-06-14

### Đã thêm
- Tóm tắt AI trong trình đọc có thể thu gọn về một dòng.
- Tin liên quan cùng chủ đề ở cuối trình đọc bài.
- Nút chia sẻ bài (Web Share API trên mobile, copy link trên desktop).
- Chip lọc tin nhanh theo nguồn báo ngay trên feed.
- Kéo-thả sắp xếp lại thứ tự chủ đề (lưu localStorage).
- Hàng đợi "đọc sau": đánh dấu bài, tự xoá khi đã mở đọc.
- Modal trạng thái hệ thống: tình trạng AI + watcher nền (từ `/api/health`).
- Log JSON có cấu trúc và metric cache hit/miss.
- Unit test frontend bằng Vitest cho các hàm logic thuần.

### Đã đổi
- Dashboard tải song song toàn bộ nguồn dữ liệu + stale-while-revalidate:
  cold-load giảm từ ~52s xuống ~15s, lượt thường ~0.3s.
- `DEBUG` mặc định tắt để `python app.py` không vô tình bật Werkzeug debugger.
- Dùng chung một SQLite connection cho mỗi store thay vì mở lại mỗi truy vấn.

### Đã sửa
- Rò rỉ bộ nhớ ở rate limiter (dọn bucket theo IP đã hết hạn).
- Render tóm tắt AI dạng markdown (gạch đầu dòng/đậm) thay vì text thô.

### Bảo mật
- Vá CVE flask (3.1.0 → 3.1.3) và requests (2.32.3 → 2.34.2).
- Chống SSRF ở `/api/read`, rate-limit endpoint đọc bài.
- Gửi khóa Gemini qua header thay vì query string URL.
- Kiểm tra hợp lệ tham số forex (mã tiền tệ, số tiền).
- `pip-audit` chạy trong CI mỗi lần push.

---

> Lịch sử chi tiết trước đây xem trong `git log`. Dự án phát triển nhanh qua
> nhiều commit nhỏ; phần trên gom nhóm những thay đổi đáng chú ý nhất.
