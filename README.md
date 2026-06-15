# TinNhanh AI

[![CI](https://github.com/tridpt/TinNhanhAI/actions/workflows/ci.yml/badge.svg)](https://github.com/tridpt/TinNhanhAI/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-000000.svg)](https://flask.palletsprojects.com/)
[![PWA](https://img.shields.io/badge/PWA-installable-5a0fc8.svg)](https://developer.mozilla.org/docs/Web/Progressive_web_apps)

Web app tin tức & thị trường tiếng Việt: tổng hợp tin nóng, bảng giá thời gian thực,
biểu đồ, và trợ lý AI — chạy bằng Flask, đóng gói thành PWA cài được trên điện thoại.

🔗 **Demo:** https://tinnhanh-ai.fly.dev

---

## Tính năng

### 📰 Tin tức
- **10 chủ đề**: Tổng hợp, Thời sự, Kinh tế, Công nghệ, Thế giới, Thể thao, Giải trí, Sức khỏe, Giáo dục, Xe.
- **9 đầu báo uy tín**: VnExpress, Thanh Niên, Tuổi Trẻ, Dân Trí, Zing, Tiền Phong,
  Người Lao Động, Nhân Dân, VOV (+ BBC Tiếng Việt cho mục Thế giới).
- **Kho tin tích lũy**: bài cũ không bị xóa khi làm mới — lưu tối đa 200 bài/chủ đề
  trong SQLite, phân trang (1, 2, 3… + ô nhảy trang).
- **Đọc inline**: bấm tin → mở reader modal đọc full text, không rời app.
- **Tóm tắt AI**: nút tóm tắt bài báo bằng AI, có **cache** theo nội dung để khỏi
  gọi lại API cho bài đã tóm tắt.
- **Tìm kiếm nâng cao**: tìm trên toàn bộ kho tin (mọi chủ đề) theo từ khóa + lọc
  chủ đề + lọc nguồn; **lưu bộ lọc** yêu thích.
- **Tin đã lưu (bookmark)**: lưu bài kèm metadata nên vẫn đọc được dù bài rời feed.
- **Badge tin mới** trên tiêu đề tab giống Gmail/Facebook.

### 📈 Thị trường
- **Giá hàng hóa**: vàng/dầu/xăng thế giới (Yahoo Finance), vàng SJC/PNJ/BTMC,
  xăng Petrolimex.
- **Tỷ giá ngoại tệ**: Vietcombank + công cụ quy đổi 166 loại tiền; thêm cặp tiền
  tùy chỉnh.
- **Crypto** (Binance) & **chứng khoán** (VNDirect + Yahoo): danh sách mặc định +
  **watchlist tùy chỉnh** (tự chuẩn hóa mã, kiểm tra hợp lệ trước khi thêm).
- **Lịch sử giá**: sparkline mini-chart tích lũy qua mỗi lần fetch (SQLite).
- **Biểu đồ chi tiết**: bấm vào thẻ/sparkline → modal biểu đồ lớn, chọn khoảng thời
  gian (24h→3 tháng), crosshair, thống kê (mở/cao/thấp/TB/biên độ).
- **So sánh nhiều mã**: chọn 2–4 coin/cổ phiếu vẽ chồng, chuẩn hóa theo % thay đổi.
- Hiển thị thông minh cho coin giá siêu nhỏ (SHIB, PEPE… không bị làm tròn về 0).

### 🌤️ Thời tiết
- 3 thành phố mặc định + **thêm thành phố** / **định vị GPS** ("Vị trí của tôi").
- Dự báo 5 ngày, bấm từng ngày xem chi tiết theo giờ. Ẩn/xóa thành phố không cần.

### 🤖 AI
- Hỏi nhanh tin tức / giá / tra cứu sản phẩm — kết quả chia 3 tab (Tóm tắt / Nguồn / Raw).
- Hỗ trợ **Google Gemini** (ưu tiên) và **OpenAI**, tự fallback model khi gặp 429.
- Nút "Thử lại" khi AI quá tải; rate-limit theo IP.

### 📱 PWA & hiệu năng
- Cài được lên màn hình chính (manifest + service worker), có nút "Cài đặt".
- Hoạt động offline ở mức shell + dữ liệu đã cache; banner báo offline; toast cập nhật.
- **Nén gzip** toàn bộ JSON + static (dashboard 487KB→64KB, app.js 139KB→34KB).
- Mobile responsive; giao diện sáng/tối.

### 🔔 Telegram (tùy chọn)
- Watcher chạy nền gửi alert khi có tin chứa từ khóa bạn theo dõi.
- **Cảnh báo giá**: đặt ngưỡng cho vàng/coin/cổ phiếu/ngoại tệ (≥ hoặc ≤), nhận
  thông báo Telegram khi giá chạm ngưỡng (cảnh báo một lần, tự tắt sau khi kích hoạt).

---

## Kiến trúc

```
app.py                  # Thin assembler: tạo Flask app, đăng ký blueprint, chạy server
routes/                 # Flask blueprints (HTTP layer)
  pages.py              #   shell tĩnh, PWA assets, /api/health
  news.py               #   /api/dashboard, /api/news/<topic>, /api/news/search
  market.py             #   prices, crypto, stocks, forex, weather, history
  ai.py                 #   /api/ask, /api/read, /api/summarize (rate-limited)
services/               # Business logic (không phụ thuộc Flask)
  news.py, news_store.py   #   thu thập RSS + kho SQLite tích lũy
  crypto.py, stocks.py     #   Binance / VNDirect / Yahoo
  vn_prices.py, vn_gold.py #   vàng, xăng, tỷ giá Vietcombank
  weather.py               #   Open-Meteo
  ai.py, assistant.py      #   provider AI + điều phối câu hỏi
  summary_cache.py         #   cache tóm tắt (SQLite)
  history.py               #   lịch sử giá (SQLite)
  reader.py, search.py     #   trích xuất bài + tìm kiếm web
  cache.py                 #   TTL cache (diskcache)
  rate_limit.py            #   token-bucket theo IP
  compression.py           #   gzip after_request hook
  telegram_alert.py        #   watcher nền
frontend/               # SPA tĩnh (vanilla JS, không build step)
  index.html, app.js, styles.css, sw.js, manifest.webmanifest
data/                   # SQLite: news.db, history.db, summaries.db (gitignored)
tests/                  # pytest (172 test)
```

Dữ liệu chảy: `routes/*` (mỏng, parse request) → `services/*` (logic + cache) → JSON.
Frontend tải song song từng phần và render khi mỗi phần về (streaming UX).

---

## Chạy nhanh (dev)

```bash
pip install -r requirements.txt
python app.py
```

Mở `http://127.0.0.1:5055`.

> `DEBUG` mặc định **tắt** (không bật Werkzeug debugger). Khi dev muốn hot-reload
> + traceback chi tiết, chạy `DEBUG=1 python app.py` (hoặc đặt `DEBUG=1` trong
> `.env`). Server vẫn là Flask dev; chỉ bật waitress khi đặt `TINNHANH_PROD=1`.

## Chạy tests

```bash
python -m pytest          # 172 test backend, ~vài giây
ruff check .              # lint
node -c frontend/app.js   # kiểm cú pháp JS
npm install && npm test   # 21 test logic frontend (Vitest)
```

> Trên Windows PowerShell, đặt `$env:PYTHONIOENCODING="utf-8"` trước khi chạy
> pytest để in tiếng Việt không lỗi.

## Chạy production (waitress)

```bash
TINNHANH_PROD=1 DEBUG=0 python app.py
```

Hoặc Docker:

```bash
docker build -t tinnhanh-ai .
docker run --rm -p 8080:8080 --env-file .env \
  -v $(pwd)/data:/app/data tinnhanh-ai
```

## Deploy lên Fly.io

```bash
fly launch --no-deploy          # lần đầu (tạo app + volume)
fly volumes create tinnhanh_data --region sin --size 1
fly secrets set GEMINI_API_KEY=... GEMINI_MODEL=gemini-2.5-flash-lite
fly deploy
```

Cấu hình ở `fly.toml` (region `sin`, máy shared-cpu 256MB, volume `/app/data`,
health-check `/api/health`). Chi tiết thêm: [docs/DEPLOY.md](docs/DEPLOY.md).

---

## Cấu hình (.env)

Copy `.env.example` → `.env` rồi điền. **Mọi biến đều tùy chọn** — không có key AI
thì app vẫn chạy, chỉ tắt phần tóm tắt/hỏi AI.

| Biến | Mặc định | Ghi chú |
| --- | --- | --- |
| `GEMINI_API_KEY` | _empty_ | Bật AI bằng Google Gemini (ưu tiên nếu có). |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Model Gemini (free tier rộng rãi). |
| `OPENAI_API_KEY` | _empty_ | Bật AI bằng OpenAI (nếu không có Gemini). |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model OpenAI. |
| `ASK_RATE_LIMIT_PER_MINUTE` | `20` | Giới hạn `/api/ask` + summarize theo IP. |
| `TINNHANH_PROD` | `0` | `1` để dùng waitress thay Flask dev. |
| `HOST` / `PORT` | `127.0.0.1` / `5055` | Địa chỉ bind. |
| `TELEGRAM_BOT_TOKEN` | _empty_ | Bật alert tin nóng theo keyword. |
| `TELEGRAM_CHAT_ID` | _empty_ | Chat/channel nhận tin. |
| `TELEGRAM_KEYWORDS` | _empty_ | Keyword cách nhau bằng dấu phẩy. |
| `TELEGRAM_POLL_SECONDS` | `600` | Khoảng quét RSS. |
| `PRICE_ALERT_POLL_SECONDS` | `300` | Khoảng so giá cho cảnh báo giá. |

---

## Nguồn dữ liệu

| Loại | Nguồn |
| --- | --- |
| Tin RSS | VnExpress, Thanh Niên, Tuổi Trẻ, Dân Trí, Zing, Tiền Phong, NLĐ, Nhân Dân, VOV, BBC |
| Giá thế giới | Yahoo Finance (vàng `GC=F`, dầu `CL=F`, xăng `RB=F`) |
| Vàng VN | SJC, PNJ, BTMC (chạy song song, chịu lỗi từng nguồn) |
| Tỷ giá | Vietcombank (fallback open.er-api.com) |
| Xăng VN | Petrolimex (best-effort) |
| Crypto | Binance public API |
| Chứng khoán | VNDirect (chỉ số) + Yahoo Finance (cổ phiếu) |
| Thời tiết | Open-Meteo |
| Tìm kiếm web | DuckDuckGo (`ddgs`) |

Lưu trữ cục bộ (SQLite, gitignored trong `data/`): kho tin, lịch sử giá, cache tóm tắt.

---

## Lưu ý

- Giá hiển thị mang tính tham khảo, không phải cam kết giao dịch.
- Telegram watcher chạy nền trong cùng process, không cần dịch vụ riêng.
  **Lưu ý scale:** watcher giữ trạng thái trong bộ nhớ process; nếu chạy nhiều
  máy (Fly.io scale > 1), mỗi máy sẽ quét và gửi alert độc lập → trùng thông
  báo. Hiện tại chạy 1 máy nên không sao; muốn scale ngang thì cần khóa phân
  tán (Redis/DB) hoặc tách watcher ra một máy riêng.
- Trạng thái watcher (đang chạy/lần quét cuối/lỗi gần nhất) lộ ở `/api/health`
  dưới khóa `watchers`, tiện cho việc giám sát.
- Service worker cache shell + CDN; bump `SW_VERSION` trong `frontend/sw.js` khi đổi
  CSS/JS để client nạp bản mới (hoặc dùng toast "Tải lại").
- API key AI nên tách riêng cho production để tránh đụng quota free tier với local.
