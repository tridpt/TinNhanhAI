# Đóng góp cho TinNhanh AI

Cảm ơn bạn quan tâm đến dự án! Dưới đây là hướng dẫn ngắn để bắt đầu.

## Thiết lập môi trường

```bash
pip install -r requirements.txt
python app.py            # mở http://127.0.0.1:5055
```

Đặt `DEBUG=1` (hoặc trong `.env`) để có hot-reload + traceback chi tiết khi dev.
Mọi biến môi trường đều tuỳ chọn — không có khoá AI thì app vẫn chạy, chỉ tắt
phần tóm tắt/hỏi AI. Xem `.env.example` để biết các biến.

## Chạy kiểm thử

Trước khi mở pull request, hãy chắc cả ba bước sau đều xanh:

```bash
python -m pytest          # test backend (Python)
ruff check .              # lint Python
npm install && npm test   # test frontend (Vitest) — chỉ cần cài lần đầu
```

> Trên Windows PowerShell, đặt `$env:PYTHONIOENCODING="utf-8"` trước khi chạy
> pytest để in tiếng Việt không lỗi.

## Quy ước commit

Dự án dùng [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` tính năng mới
- `fix:` sửa lỗi
- `perf:` cải thiện hiệu năng
- `refactor:` đổi cấu trúc, không đổi hành vi
- `test:` thêm/sửa test
- `docs:` tài liệu
- `security:` vá bảo mật

Có thể thêm phạm vi: `feat(ui): ...`, `fix(ai): ...`.

## Nguyên tắc code

- Routes (`routes/`) giữ mỏng — chỉ parse request; logic đặt ở `services/`.
- Thêm test cho hành vi mới; logic frontend thuần đặt ở `frontend/logic.js`
  để test được dưới Node.
- Khi đổi CSS/JS, tăng `SW_VERSION` trong `frontend/sw.js` để client nạp bản mới.
- Không commit khoá API, `.env`, hay file trong `data/`.

## Báo lỗi

Mở issue kèm: bước tái hiện, kết quả mong đợi vs thực tế, trình duyệt/OS.
