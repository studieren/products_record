from models import ProductDetail, Product, WholesalePrice
from get_data import analysis_data
from threading import Thread
from download_service import download_images_async
from flask import current_app
from sqlalchemy.exc import IntegrityError
import time
from extensions import db


def collect_missing_prices_task():
    app = current_app._get_current_object()
    with app.app_context():
        print("开始查找缺失价格的商品...")
        # 找出所有 WholesalePrice 为空的 Details
        subquery = db.session.query(WholesalePrice.details_id).distinct()
        missing_details = (
            db.session.query(ProductDetail)
            .filter(~ProductDetail.id.in_(subquery))
            .all()
        )

        if not missing_details:
            print("没有发现缺失价格的商品。")
            return

        # 提取唯一 Main 的 URL 列表（避免重复采集）
        main_ids = {detail.main_id for detail in missing_details}
        main_entries = db.session.query(Product).filter(Product.id.in_(main_ids)).all()

        print(f"共需要采集 {len(main_entries)} 个链接，开始定时采集，每 10 秒一次")

        for idx, main in enumerate(main_entries):
            print(f"[{idx + 1}/{len(main_entries)}] 采集中: {main.url}")
            try:
                process_url_data(
                    main.url, db
                )  # 调用你已有的函数重新采集数据（会补上价格）
            except Exception as e:
                print(f"采集失败: {main.url} 错误: {e}")
            time.sleep(10)

        print("所有缺失价格的链接采集完成")


def add_price(price_data, details_list, db):
    """新增价格数据处理函数：将price_data映射到对应的Details记录"""
    print("插入价格到数据库中")
    price_list = []

    # 检查price_data是否存在且有内容
    if not price_data.get("price_data"):
        print("警告：未找到价格数据")
        return

    # 遍历价格数据，为每个Details记录创建对应的批发价格
    for price_info in price_data["price_data"]:
        # 为每个商品详情都绑定相同的批发价格规则
        for details in details_list:
            # 确保details对象有有效的ID
            if details.id is None:
                print(
                    f"错误：Details对象ID为空，无法关联价格数据: {details.self_model}"
                )
                continue

            wp = WholesalePrice(
                details_id=details.id,
                min_quantity=price_info["min"],
                max_quantity=price_info.get("max"),  # 处理无上限的情况
                price=str(price_info["price"]),  # 保留价格精度
            )
            price_list.append(wp)

    if price_list:
        try:
            db.session.bulk_save_objects(price_list)
            db.session.commit()  # 提交价格数据
            print(f"成功插入 {len(price_list)} 条价格数据")
        except IntegrityError as e:
            db.session.rollback()  # 回滚事务
            print(f"价格数据插入失败: {str(e)}")
        except Exception as e:
            db.session.rollback()
            print(f"未知错误: {str(e)}")


def process_url_data(url, db, user_id=None):
    data = analysis_data(url)

    # 创建主记录
    main = Product(
        url=url,
        title=data["title"],
        company_name=data["company_name"],
        company_url=data["company_url"],
        user_id=user_id or 1,  # 默认用户ID为1
    )
    db.session.add(main)
    db.session.commit()

    # 创建并收集商品详情记录
    details_list = []
    self_models = []
    for product in data["products"]:
        details = ProductDetail(
            main_id=main.id,
            other_model=product["sku"],
            self_model=product["sku"],
            price=float(product["price"]),
            image_url=product["img_url"],
            stock=float(product["stock"]) if "stock" in product else 0,
        )
        details_list.append(details)
        self_models.append(product["sku"])

    # 保存商品详情
    try:
        db.session.bulk_save_objects(details_list)
        db.session.commit()

        # 重新查询获取带有ID的Details记录
        details_list = (
            db.session.query(ProductDetail)
            .filter(
                ProductDetail.main_id == main.id,
                ProductDetail.self_model.in_(self_models),
            )
            .all()
        )

        # 调用价格处理函数
        add_price(data, details_list, db)

        print(f"成功处理URL: {url}")

    except IntegrityError as e:
        db.session.rollback()
        print(f"数据插入失败: {str(e)}")
    except Exception as e:
        db.session.rollback()
        print(f"处理URL时发生未知错误: {str(e)}")
    finally:
        db.session.close()

    # 图片下载逻辑（保持原有逻辑不变）
    app = current_app._get_current_object()

    def download_all_pending_images(app):
        with app.app_context():
            details_without_image = ProductDetail.query.filter(
                ProductDetail.image_url.isnot(None), ~ProductDetail.image_records.any()
            ).all()
            detail_ids = [d.id for d in details_without_image]
            if detail_ids:
                download_images_async(app, detail_ids)

    Thread(target=download_all_pending_images, args=(app,)).start()


def collect_only_missing_prices_task():
    print("🔍 正在查找缺失价格的商品...")

    # 获取所有没有 WholesalePrice 的 details
    subquery = db.session.query(WholesalePrice.details_id).distinct()
    details_missing_price = (
        db.session.query(ProductDetail).filter(~ProductDetail.id.in_(subquery)).all()
    )

    if not details_missing_price:
        print("✅ 所有商品详情均已有价格数据，无需更新。")
        return

    # 获取需要处理的 Main.id 和对应 URL（避免重复请求）
    main_ids = {d.main_id for d in details_missing_price}
    main_entries = db.session.query(Product).filter(Product.id.in_(main_ids)).all()
    main_url_map = {m.id: m.url for m in main_entries}

    print(f"🔧 共需采集 {len(main_url_map)} 个商品链接，每10秒一个")

    for idx, (main_id, url) in enumerate(main_url_map.items(), 1):
        print(f"[{idx}/{len(main_url_map)}] 采集中: {url}")
        try:
            # 采集数据（打开页面）
            data = analysis_data(url, ifvisit=True)

            # 仅查找已有 Details（不要重建）
            details_list = (
                db.session.query(ProductDetail).filter_by(main_id=main_id).all()
            )

            # 调用已有的价格写入函数
            add_price(data, details_list, db)

        except Exception as e:
            print(f"❌ 错误采集 {url}: {e}")

        time.sleep(10)

    print("🎉 缺失的价格信息已全部补齐")


# def change_role():


# 生成SQL建表语句的正确方式
def create_users_table():
    from sqlalchemy import Enum
    from models import UserRole

    sql = f"""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role {Enum(UserRole)},  # 使用SQLAlchemy的Enum类型
        CHECK (role IN ('superadmin', 'salesperson'))
    );
    """


if __name__ == "__main__":
    from app import app  # 你项目的 app 工厂函数，调整为你自己的路径

    # app = create_app()  # 初始化 app
    with app.app_context():
        # collect_only_missing_prices_task()
        create_users_table()
