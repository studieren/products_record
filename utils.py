from models import Main, Details
from get_data import analysis_data
from threading import Thread
from download_service import download_images_async
from flask import current_app

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
                download_images_async(detail_ids)

    # ✅ 启动线程并传入 app
    Thread(target=download_all_pending_images, args=(app,)).start()
