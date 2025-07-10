from app import app, db, batch_download_images
from models import Details

with app.app_context():
    # 获取所有有图片URL但未下载的Details记录
    details_to_process = Details.query.filter(
        Details.image_url.isnot(None), Details.local_image_path.is_(None)
    ).all()

    if details_to_process:
        detail_ids = [d.id for d in details_to_process]
        print(f"开始批量下载{len(detail_ids)}张图片...")
        batch_download_images(detail_ids)
        print("批量下载完成！")
    else:
        print("没有需要下载的图片")
