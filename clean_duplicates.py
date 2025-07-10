import os
import hashlib
from pathlib import Path
from collections import defaultdict
from app import app, db
from models import Details, ImageRecord

# 设置图片目录
IMAGE_FOLDER = Path("static/images")


def get_md5(file_path):
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"[ERROR] 读取文件失败 {file_path}: {e}")
        return None


def clean_duplicate_images():
    print("开始扫描图片目录去重...")
    hash_map = defaultdict(list)

    # 遍历所有图片文件
    for file in IMAGE_FOLDER.glob("*.*"):
        if file.is_file():
            file_hash = get_md5(file)
            if file_hash:
                hash_map[file_hash].append(file)

    removed_count = 0
    with app.app_context():
        for file_hash, files in hash_map.items():
            if len(files) <= 1:
                continue  # 无重复

            # 排序，保留文件名最短的（如有多个最短，保留最先的）
            files.sort(key=lambda f: (len(f.name), f.name))
            keep = files[0]
            delete_list = files[1:]

            for f in delete_list:
                try:
                    os.remove(f)
                    removed_count += 1
                    print(f"🗑 删除重复文件: {f}")

                    # 清理数据库中引用这个文件的路径
                    records = Details.query.filter_by(local_image_path=str(f)).all()
                    for r in records:
                        r.local_image_path = None

                    ImageRecord.query.filter_by(local_path=str(f)).delete()

                except Exception as e:
                    print(f"[ERROR] 删除失败: {f} - {e}")

        db.session.commit()
    print(f"✅ 清理完成，共删除重复文件 {removed_count} 个")
