# Security notes

Theo dõi các vấn đề bảo mật đang mở và quyết định liên quan đến dependency.

## CVE đang theo dõi (chưa có bản vá)

### diskcache 5.6.3 — CVE-2025-69872 (pickle deserialization RCE)

- **Tình trạng:** chưa có bản vá. 5.6.3 vẫn là bản mới nhất trên PyPI.
- **Bản chất:** diskcache dùng `pickle` để serialize giá trị cache. Kẻ tấn công
  **có quyền ghi vào thư mục cache** (`.cache/`) có thể chèn payload độc và đạt
  RCE khi app đọc lại cache.
- **Rủi ro thực tế ở TinNhanhAI: thấp.** Thư mục `.cache/` nằm cục bộ trên
  server, không phơi ra mạng, không nhận input từ người dùng. Để khai thác,
  attacker phải đã có quyền ghi filesystem — lúc đó họ đã kiểm soát được nhiều
  thứ hơn cache.
- **Giảm thiểu hiện tại:**
  - CI (`pip-audit`) bỏ qua riêng CVE này (`--ignore-vuln CVE-2025-69872`) để
    vẫn bắt được các CVE *mới* khác.
  - `requirements.txt` ghi chú lý do pin 5.6.3.
- **Việc cần làm:** khi diskcache phát hành bản vá, bump version trong
  `requirements.txt` và **gỡ** `--ignore-vuln CVE-2025-69872` khỏi
  `.github/workflows/ci.yml`.
- **Tham khảo:** <https://nvd.nist.gov/vuln/detail/CVE-2025-69872>

## Đã vá

| Package | CVE | Vá ở phiên bản |
| --- | --- | --- |
| requests | CVE-2024-47081 (rò rỉ `.netrc` credential) | 2.32.4+ (đang dùng 2.34.2) |
| requests | CVE-2026-25645 | 2.33.0+ (đang dùng 2.34.2) |
| flask | CVE-2025-47278 | 3.1.1+ (đang dùng 3.1.3) |
| flask | CVE-2026-27205 | 3.1.3 (đang dùng 3.1.3) |

## Kiểm tra định kỳ

```bash
pip install pip-audit
pip-audit -r requirements.txt
```

CI chạy bước này mỗi lần push/PR vào `main`.
