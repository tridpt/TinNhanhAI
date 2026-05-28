# TinNhanh AI

Web app tiếng Việt để:

- tóm tắt tin nóng theo chủ đề mỗi ngày
- hiển thị giá thị trường cho vàng, dầu, xăng
- tra cứu giá hoặc thông tin sản phẩm theo yêu cầu người dùng

## Chạy nhanh

```bash
pip install -r requirements.txt
python app.py
```

Mở `http://127.0.0.1:5055`

## Tuỳ chọn AI

Đặt `OPENAI_API_KEY` để bật phần tổng hợp bằng AI. Không có key thì app vẫn chạy, nhưng phần tóm tắt sẽ dùng fallback từ dữ liệu nguồn.

```powershell
$env:OPENAI_API_KEY="your_key"
```

## Nguồn dữ liệu

- RSS tin tức từ VnExpress và Thanh Niên
- giá hàng hóa từ Yahoo Finance chart endpoint
- tìm kiếm web bằng DuckDuckGo

## Lưu ý

- Giá vàng/dầu/xăng ở đây là giá thị trường quốc tế tham khảo.
- Giá sản phẩm là giá tham khảo từ nguồn web tìm được, không phải cam kết bán lẻ cố định.

