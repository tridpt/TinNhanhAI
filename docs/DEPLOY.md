# Deploy lên Fly.io

Hướng dẫn từng bước để đưa TinNhanh AI lên public URL `https://<app>.fly.dev`.

## Yêu cầu

- Tài khoản [Fly.io](https://fly.io) — free tier không cần credit card cho 1 small app
- `flyctl` CLI cài trên máy

## 1. Cài flyctl

```powershell
# Windows PowerShell
iwr https://fly.io/install.ps1 -useb | iex

# Hoặc qua winget / scoop
winget install Fly.Flyctl
scoop install flyctl
```

Mở terminal mới sau khi cài xong, rồi:

```powershell
fly auth login    # mở browser để đăng nhập / đăng ký
```

## 2. Lần đầu setup (chỉ chạy 1 lần)

Từ thư mục `TinNhanhAI`:

```powershell
# Tạo app trên Fly với name từ fly.toml. Nếu trùng, đổi `app = "..."` trong fly.toml.
fly apps create tinnhanh-ai

# Tạo persistent volume 1 GB cho cache + history DB + telegram state.
fly volumes create tinnhanh_data --region sin --size 1 --yes

# (Tùy chọn) Set key AI để bật tóm tắt/hỏi AI. Ưu tiên Gemini (free tier rộng).
fly secrets set GEMINI_API_KEY=AIza... GEMINI_MODEL=gemini-2.5-flash-lite
# Hoặc dùng OpenAI:
# fly secrets set OPENAI_API_KEY=sk-... OPENAI_MODEL=gpt-4o-mini

# (Tùy chọn) Set Telegram credentials để bật alert watcher.
fly secrets set TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... TELEGRAM_KEYWORDS="vàng,iPhone"
```

## 3. Deploy

```powershell
fly deploy
```

Lần đầu mất ~3 phút (build Docker image + push lên Fly registry). Các lần sau ~1 phút.

Sau khi xong, app live tại `https://tinnhanh-ai.fly.dev`. Mở trên điện thoại Chrome → menu "Add to home screen" để cài như native app (PWA).

## 4. Theo dõi & vận hành

```powershell
fly status                       # xem health check, machines
fly logs                         # tail server log
fly logs --app tinnhanh-ai -i    # interactive
fly ssh console                  # ssh vào machine
fly secrets list                 # xem env vars đã set (giá trị bị mask)
fly volumes list                 # check volume usage
```

## 5. Update sau khi push code

Mỗi lần push lên GitHub xong, redeploy:

```powershell
fly deploy
```

Hoặc setup GitHub Actions để auto-deploy:

```yaml
# .github/workflows/fly-deploy.yml
name: Fly Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

Lấy token: `fly auth token`, rồi paste vào GitHub repo → Settings → Secrets → New `FLY_API_TOKEN`.

## Troubleshooting

| Triệu chứng | Cách xử lý |
|---|---|
| `Error: app name has already been taken` | Đổi `app = "..."` trong `fly.toml` thành slug khác |
| Healthcheck fail liên tục | `fly logs` xem có lỗi import hoặc port không match. Đảm bảo `PORT=8080` |
| App rất chậm sau idle | Bình thường — `auto_stop_machines = "stop"` tiết kiệm tài nguyên, request đầu sau idle ~5s để wake |
| Cache/history mất sau deploy | Verify `fly volumes list` thấy volume mounted vào `/app/data` |

## Free tier limits

- 3 shared-cpu-1x machines
- 3 GB total persistent volume
- 160 GB outbound bandwidth/tháng

App này dùng 1 machine + 1 GB volume, dư xài cho dùng cá nhân.
