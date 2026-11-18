# Ảnh nền

Repo **không kèm ảnh Kafka**: nhân vật và hình ảnh Honkai: Star Rail thuộc bản quyền HoYoverse
(ảnh fan art thuộc về tác giả). Hãy tự tải ảnh mà bạn có quyền dùng và đặt vào thư mục này:

| File | Dùng cho | Gợi ý |
|---|---|---|
| `kafka_landscape_3.jpg` | Hình nền chính, màn hình khoá, nền màn hình đăng nhập | Ảnh ngang 1920x1080 |
| `kafka_main.jpg` | Cắt banner rofi, nền khung walker, ảnh vuông fastfetch/hyprlock | Ảnh dọc, nhân vật ở nửa trên |

Sau đó tạo lại các ảnh phụ:

```bash
./install.sh --only assets --force-assets
```

Chưa có ảnh thì `install.sh` tạo ảnh gradient màu Kafka để mọi thứ vẫn chạy.

Ảnh dọc muốn làm hình nền thì ghép thành ảnh ngang trước (lệnh ImageMagick ở `CLAUDE.md`, mục "Xử lý hình nền mới").
`wallpaper-cycle.sh` chỉ nhận ảnh `kafka_*.jpg|png` có chiều ngang lớn hơn chiều dọc.
