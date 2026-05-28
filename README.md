# TinNhanh AI

Web app tiếng Việt:

- tóm tắt tin nóng theo chủ đề (thời sự, kinh tế, công nghệ, thế giới, thể thao)
- bảng giá thị trường: vàng/dầu/xăng quốc tế **và** vàng SJC, USD/VND, xăng Petrolimex
- lịch sử giá 7 ngày (sparkline mini-chart) tự thu thập qua mỗi lần fetch
- hỏi nhanh AI: tin tức, giá hàng hóa hoặc tra cứu giá sản phẩm
- (tùy chọn) gửi alert Telegram khi có tin chứa từ khóa bạn theo dõi

## Chạy nhanh (dev)

```bash
pip install -r requirements.txt
python app.py
```

Mở `http://127.0.0.1:5055`.

## Chạy production (waitress)

```bash
TINNHANH_PROD=1 DEBUG=0 python app.py
```

Hoặc dùng Docker:

```bash
docker build -t tinnhanh-ai .
docker run --rm -p 5055:5055 \
  -v $(pwd)/.cache:/app/.cache \
  -v $(pwd)/state:/app/state \
  --env-file .env \
  tinnhanh-ai
```

Mount `.cache` và `state` để giữ cache giữa các lần restart và bộ nhớ
"đã gửi" của Telegram watcher.

## Cấu hình

Copy `.env.example` thành `.env` rồi điền:

| Biến | Mặc định | Ghi chú |
| --- | --- | --- |
| `OPENAI_API_KEY` | _empty_ | Bật phần tóm tắt AI. Không có vẫn chạy được. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model OpenAI dùng cho summarize. |
| `ASK_RATE_LIMIT_PER_MINUTE` | `20` | Giới hạn `/api/ask` theo IP. |
| `TINNHANH_PROD` | `0` | `1` để dùng waitress thay vì Flask dev. |
| `TELEGRAM_BOT_TOKEN` | _empty_ | Bật alert tin nóng theo keyword. |
| `TELEGRAM_CHAT_ID` | _empty_ | Chat hoặc channel nhận tin. |
| `TELEGRAM_KEYWORDS` | _empty_ | Danh sách keyword cách nhau bằng dấu phẩy. |
| `TELEGRAM_POLL_SECONDS` | `600` | Khoảng thời gian quét RSS. |

## Nguồn dữ liệu

- RSS: VnExpress, Thanh Niên
- Giá thế giới: Yahoo Finance chart (vàng GC=F, dầu CL=F, xăng RB=F)
- Giá Việt Nam: SJC, Vietcombank, Petrolimex
- Tìm kiếm web: DuckDuckGo (qua thư viện `ddgs`)
- Lịch sử giá: SQLite cục bộ tại `data/history.db` (throttle 4 phút/datapoint, giữ 60 ngày)

## Lưu ý

- Giá hiển thị mang tính tham khảo, không phải cam kết bán lẻ.
- Telegram watcher chạy nền trong cùng process, không cần dịch vụ riêng.
- Cache lưu vào `.cache/` (qua `diskcache`) để app "ấm" sau restart.
