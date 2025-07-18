from models import ProductDetail, Product, WholesalePrice
from get_data import analysis_data
from threading import Thread
from download_service import download_images_async
from flask import current_app
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import time
from extensions import db


def collect_missing_prices_task():
    app = current_app._get_current_object()
    with app.app_context():
        print("开始查找缺失价格的商品...")
        # 找出所有 WholesalePrice 为空的 ProductDetail（外键是 product_id）
        subquery = db.session.query(
            WholesalePrice.detail_id
        ).distinct()  # 注意是 detail_id
        missing_details = (
            db.session.query(ProductDetail)
            .filter(~ProductDetail.id.in_(subquery))
            .all()
        )

        if not missing_details:
            print("没有发现缺失价格的商品。")
            return

        # 提取唯一 Product 的 URL 列表（外键是 product_id）
        product_ids = {
            detail.product_id for detail in missing_details
        }  # 修正为 product_id
        product_entries = (
            db.session.query(Product).filter(Product.id.in_(product_ids)).all()
        )

        print(f"共需要采集 {len(product_entries)} 个链接，开始定时采集，每 10 秒一次")

        for idx, product in enumerate(product_entries):
            print(f"[{idx + 1}/{len(product_entries)}] 采集中: {product.url}")
            try:
                process_url_data(
                    product.url, db, user_id=product.user_id
                )  # 传递原用户ID
            except Exception as e:
                print(f"采集失败: {product.url} 错误: {e}")
            time.sleep(10)

        print("所有缺失价格的链接采集完成")


def add_price(price_data, details_list, db):
    """新增价格数据处理函数：将price_data映射到对应的ProductDetail记录"""
    print("插入价格到数据库中")
    price_list = []

    # 检查price_data是否存在且有内容
    if not price_data.get("price_data"):
        print("警告：未找到价格数据")
        return

    # 遍历价格数据，为每个ProductDetail记录创建对应的批发价格
    for price_info in price_data["price_data"]:
        # 为每个商品详情绑定相同的批发价格规则
        for detail in details_list:
            # 确保detail对象有有效的ID
            if detail.id is None:
                print(
                    f"错误：ProductDetail对象ID为空，无法关联价格数据: {detail.self_model}"
                )
                continue

            # 检查是否已存在相同规则的价格（避免重复）
            existing = WholesalePrice.query.filter_by(
                detail_id=detail.id,  # 外键是 detail_id
                min_quantity=price_info["min"],
            ).first()
            if existing:
                print(
                    f"跳过重复价格规则: detail_id={detail.id}, min={price_info['min']}"
                )
                continue

            wp = WholesalePrice(
                detail_id=detail.id,  # 修正外键字段名
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
            db.session.rollback()
            print(f"价格数据插入失败（约束冲突）: {str(e)}")
        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"数据库错误: {str(e)}")


def process_url_data(url, db, user_id=None):
    """处理1688 URL，创建Product和ProductDetail"""
    try:
        # 1. 解析1688数据（处理可能的解析失败）
        data = analysis_data(url)
        if not data:
            print(f"解析URL失败: {url}，返回空数据")
            return

        # 2. 创建主产品记录（Product）
        main = Product(
            url=url,
            title=data.get("title", "").strip(),  # 避免空字符串
            company_name=data.get("company_name", "").strip(),
            company_url=data.get("company_url", "").strip(),
            user_id=user_id,  # 使用传入的用户ID（默认为当前用户）
            created_at=db.func.now(),  # 显式赋值创建时间
        )
        # 检查必填字段
        if not main.title or not main.company_name:
            print(f"产品标题或公司名称为空，跳过URL: {url}")
            return

        db.session.add(main)
        db.session.flush()  # 刷新获取main.id，不提交事务

        # 3. 创建商品详情（ProductDetail）
        details_list = []
        self_models = []
        for product in data.get("products", []):  # 处理products为空的情况
            # 提取商品详情字段，避免None导致错误
            sku = product.get("sku", "").strip()
            price = product.get("price", 0.0)
            img_url = product.get("img_url", "").strip()
            stock = product.get("stock", 0.0)

            # 转换价格和库存为正确类型
            try:
                price = float(price) if price else 0.0
                stock = float(stock) if stock else 0.0
            except (ValueError, TypeError):
                price = 0.0
                stock = 0.0
                print(f"价格或库存格式错误: {product}")

            details = ProductDetail(
                product_id=main.id,  # 修正外键字段为product_id
                other_model=sku,
                self_model=sku,
                price=price,
                image_url=img_url,
                stock=stock,
            )
            details_list.append(details)
            self_models.append(sku)

        if not details_list:
            print(f"未提取到商品详情，删除空产品记录: {main.title}")
            db.session.rollback()
            return

        # 4. 批量保存商品详情
        db.session.bulk_save_objects(details_list)
        db.session.flush()

        # 5. 添加批发价格
        add_price(data, details_list, db)

        # 6. 提交所有事务（确保原子性）
        db.session.commit()
        print(f"成功创建产品: {main.title}，ID: {main.id}")

        # 7. 异步下载图片
        app = current_app._get_current_object()

        def download_images():
            with app.app_context():
                detail_ids = [d.id for d in details_list]
                if detail_ids:
                    download_images_async(app, detail_ids)

        Thread(target=download_images).start()

    except IntegrityError as e:
        db.session.rollback()
        print(f"创建产品失败（重复URL或约束冲突）: {url}，错误: {str(e)}")
    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"数据库错误: {str(e)}")
    except Exception as e:
        db.session.rollback()
        print(f"处理URL时发生未知错误: {url}，错误: {str(e)}")


def collect_only_missing_prices_task():
    """仅补充缺失的批发价格，不重建Product和ProductDetail"""
    app = current_app._get_current_object()
    with app.app_context():
        print("🔍 正在查找缺失价格的商品...")

        # 获取所有没有WholesalePrice的ProductDetail
        subquery = db.session.query(WholesalePrice.detail_id).distinct()
        details_missing_price = (
            db.session.query(ProductDetail)
            .filter(~ProductDetail.id.in_(subquery))
            .all()
        )

        if not details_missing_price:
            print("✅ 所有商品详情均已有价格数据，无需更新。")
            return

        # 按product_id分组，避免重复请求同一产品
        main_ids = {d.product_id for d in details_missing_price}
        main_entries = db.session.query(Product).filter(Product.id.in_(main_ids)).all()
        main_url_map = {m.id: m.url for m in main_entries}

        print(f"🔧 共需采集 {len(main_url_map)} 个商品链接，每10秒一个")

        for idx, (main_id, url) in enumerate(main_url_map.items(), 1):
            print(f"[{idx}/{len(main_url_map)}] 采集中: {url}")
            try:
                data = analysis_data(url, ifvisit=True)
                if not data:
                    print(f"解析价格数据失败: {url}")
                    continue

                # 获取该产品下的所有详情
                details_list = (
                    db.session.query(ProductDetail).filter_by(product_id=main_id).all()
                )
                if not details_list:
                    print(f"未找到商品详情，跳过: {url}")
                    continue

                add_price(data, details_list, db)

            except Exception as e:
                print(f"❌ 采集价格错误 {url}: {e}")

            time.sleep(10)

        print("🎉 缺失的价格信息已全部补齐")


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
