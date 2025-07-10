# download_service.py（你可以新建这个模块）
import os
import re
import requests
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import current_app
from extensions import db
from models import Details, ImageRecord
from config import headers

IMAGE_FOLDER = Path("static/images")
IMAGE_FOLDER.mkdir(parents=True, exist_ok=True)
MAX_WORKERS = 5  # 最多并发下载数


def extract_filename_from_url(url):
    path = urlparse(url).path
    filename = os.path.basename(path)
    if not filename or filename == "/":
        filename = f"image_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
    filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
    return filename


def save_unique_image_file(filename, content):
    filename_base, ext = os.path.splitext(filename)
    date_str = datetime.now().strftime("%Y%m%d")
    local_path = IMAGE_FOLDER / filename
    counter = 1
    while local_path.exists():
        filename = f"{filename_base}_{date_str}_{counter}{ext}"
        local_path = IMAGE_FOLDER / filename
        counter += 1

    with open(local_path, "wb") as f:
        f.write(content)
    return str(local_path)


def download_single_image(detail):
    if not detail.image_url:
        return None, "无URL"

    try:
        response = requests.get(detail.image_url, headers=headers, timeout=10)
        print(f"开始下载图片{detail.image_url}")
        if response.status_code == 200:
            filename = extract_filename_from_url(detail.image_url)
            local_path = save_unique_image_file(filename, response.content)

            # 数据库操作需在上下文中执行
            with current_app.app_context():
                record = ImageRecord(
                    details_id=detail.id,
                    image_url=detail.image_url,
                    local_path=local_path,
                )
                db.session.add(record)
                detail.local_image_path = local_path  # 写入缓存路径
                db.session.commit()

            return detail.id, None
        else:
            return detail.id, f"HTTP错误 {response.status_code}"
    except Exception as e:
        return detail.id, f"异常：{e}"


def download_images_async(current_app, detail_ids):
    with current_app.app_context():
        details = Details.query.filter(Details.id.in_(detail_ids)).all()
        image_records_to_add = []
        details_to_update = []

        for detail in details:
            try:
                if not detail.image_url:
                    continue

                response = requests.get(detail.image_url, headers=headers, timeout=10)
                if response.status_code != 200:
                    print(f"[跳过] 图片下载失败 {detail.id}: {response.status_code}")
                    continue

                filename = extract_filename_from_url(detail.image_url)
                local_path = save_unique_image_file(filename, response.content)

                # 更新对象（此时未入库）
                detail.local_image_path = local_path
                details_to_update.append(detail)

                record = ImageRecord(
                    details_id=detail.id,
                    image_url=detail.image_url,
                    local_path=local_path,
                )
                image_records_to_add.append(record)

                print(f"[成功] 下载并准备写入数据库: {detail.id}")

            except Exception as e:
                print(f"[错误] 下载失败\n{detail.image_url}: {str(e)}")
                continue

        # ✅ 批量提交更新和插入
        try:
            db.session.bulk_save_objects(image_records_to_add)
            db.session.commit()  # 插入 ImageRecord

            # local_image_path 的更新要在 ORM 层 commit（不能 bulk update）
            db.session.commit()  # 第二次 commit 更新 Details
            print(f"[完成] 提交 {len(image_records_to_add)} 张图片记录和路径")
        except Exception as e:
            db.session.rollback()
            print(f"[失败] 提交数据库失败: {str(e)}")
