from models import Main, Details, WholesalePrice
from get_data import analysis_data
from threading import Thread
from download_service import download_images_async
from flask import current_app


def add_price(price_data, details_list, db):
    print("插入价格到数据库中")
    price_list = []
    if "price_data" in price_data and len(price_data["price_data"]) == len(
        details_list
    ):
        for details, wholesale_list in zip(details_list, price_data["price_data"]):
            for item in wholesale_list:
                wp = WholesalePrice(
                    details_id=details.id,
                    min_quantity=item["min"],
                    max_quantity=item.get("max"),
                    price=str(item["price"]),
                )
                price_list.append(wp)
        db.session.bulk_save_objects(price_list)  # 正确写入所有对象
        db.session.commit()


def process_url_data(url, db):
    data = analysis_data(url)

    main = Main(
        url=url,
        title=data["title"],
        company_name=data["company_name"],
        company_url=data["company_url"],
    )
    db.session.add(main)
    db.session.flush()

    details_list = []
    for product in data["products"]:
        details_list.append(
            Details(
                main_id=main.id,
                other_model=product["sku"],
                self_model=product["sku"],
                price=float(product["price"]),
                image_url=product["img_url"],
                stock=float(product["stock"]) if "stock" in product else 0,
            )
        )

    db.session.bulk_save_objects(details_list)
    db.session.commit()

    # ✅ 正确传入 app 实例

    app = current_app._get_current_object()

    def download_all_pending_images(app):
        with app.app_context():  # ✅ 注意这里用 app 而不是 current_app
            details_without_image = Details.query.filter(
                Details.image_url.isnot(None), ~Details.image_records.any()
            ).all()
            detail_ids = [d.id for d in details_without_image]
            if detail_ids:
                download_images_async(app, detail_ids)

    # ✅ 启动线程并传入 app
    Thread(target=download_all_pending_images, args=(app,)).start()

    add_price(data["price_data"], details_list, db)
