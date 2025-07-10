# app.py
from utils import process_url_data
from threading import Thread, Lock
from decimal import Decimal, InvalidOperation
from extensions import db
from flask import (
    Flask,
    flash,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    copy_current_request_context,
)
from models import Main, Details, ImageRecord, Company, Salesperson
import requests
from urllib.parse import urlparse
from datetime import datetime
import time
import re
import os
from pathlib import Path
from flask_migrate import Migrate
from config import headers
from sqlalchemy import func
from download_service import download_images_async
from decouple import config
from export import export_bp

download_lock = Lock()


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = config("SECRET_KEY")
app.register_blueprint(export_bp)

db.init_app(app)


migrate = Migrate(app, db)

# 配置图片存储路径（使用pathlib处理）
IMAGE_FOLDER = Path("static") / "images"
IMAGE_FOLDER.mkdir(parents=True, exist_ok=True)


def extract_filename_from_url(url):
    """从URL中提取原始文件名，使用pathlib处理路径"""
    try:
        path = urlparse(url).path
        filename = os.path.basename(path)

        if not filename or filename == "/":
            return f"image_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"

        # 替换非法文件名字符
        invalid_chars = r'[<>:"/\\|?*]'
        filename = re.sub(invalid_chars, "_", filename)

        if not filename.strip():
            return f"image_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"

        return filename
    except Exception as e:
        print(f"文件名提取失败: {str(e)}")
        return f"image_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"


def download_image(image_url, details_id):
    try:
        filename = extract_filename_from_url(image_url)
        local_path = IMAGE_FOLDER / filename

        # 检查是否已存在该URL的下载记录
        existing_records = ImageRecord.query.filter_by(
            details_id=details_id, image_url=image_url
        ).all()
        if existing_records:
            existing_path = Path(existing_records[0].local_path)
            if existing_path.exists():
                # 更新Details表的local_image_path字段
                detail = Details.query.get(details_id)
                if detail:
                    detail.local_image_path = str(existing_path)
                    db.session.commit()
                return True, str(existing_path)

        # 下载图片
        response = requests.get(image_url, headers=headers, timeout=15)
        if response.status_code == 200:
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)

            # 保存记录到ImageRecord表
            image_record = ImageRecord(
                details_id=details_id,
                image_url=image_url,
                local_path=str(local_path),
            )
            db.session.add(image_record)

            # 更新Details表的local_image_path字段
            detail = Details.query.get(details_id)
            if detail:
                detail.local_image_path = str(local_path)
                db.session.commit()

            return True, str(local_path)
        else:
            return False, f"下载失败: HTTP状态码 {response.status_code}"
    except Exception as e:
        return False, f"下载失败: {str(e)}"


@app.route("/download_images/<int:main_id>", methods=["POST"])
def download_images(main_id):
    with app.app_context():
        details = Details.query.filter_by(main_id=main_id).all()
        detail_ids = [d.id for d in details if d.image_url and not d.local_image_path]

    # 异步后台任务
    thread = Thread(target=download_images_async, args=(app, detail_ids))
    thread.start()

    return jsonify({"status": "started", "count": len(detail_ids)})


def scan_and_add_missing_images():
    # 获取static/images目录路径
    images_dir = os.path.join(app.root_path, "static", "images")

    # 获取数据库中所有已记录的图片文件名（去掉路径，只保留文件名）
    db_images = set()
    for detail in Details.query.filter(Details.local_image_path.isnot(None)).all():
        if detail.local_image_path:
            db_images.add(os.path.basename(detail.local_image_path))

    # 扫描static/images目录
    missing_count = 0
    for filename in os.listdir(images_dir):
        # 检查是否是文件且不在数据库中
        filepath = os.path.join(images_dir, filename)
        if os.path.isfile(filepath) and filename not in db_images:
            # 查找是否有对应的Details记录（根据URL末尾匹配）
            matching_detail = Details.query.filter(
                Details.image_url.endswith(filename)
            ).first()

            if matching_detail:
                # 创建本地路径（根据你的实际路径结构可能需要调整）
                local_path = os.path.join("static", "images", filename)

                # 更新Details记录
                matching_detail.local_image_path = local_path

                # 添加ImageRecord记录（确保提供所有必需的字段）
                image_record = ImageRecord(
                    details_id=matching_detail.id,
                    image_url=matching_detail.image_url,  # 添加image_url
                    local_path=local_path,
                    download_time=datetime.now(),  # 添加下载时间
                )
                db.session.add(image_record)
                missing_count += 1

    db.session.commit()
    return missing_count


@app.route("/export", methods=["GET"])
def export_page():
    return render_template("export.html")


@app.route("/download_images/all", methods=["POST"])
def download_all_images():
    with app.app_context():
        # 第一步： 清理已记录但本地文件不存在的记录
        details_all = Details.query.filter(Details.image_url.isnot(None)).all()
        repaired_count = 0
        for d in details_all:
            if d.local_image_path and not os.path.exists(d.local_image_path):
                # 删除 ImageRecord 中的记录
                db.session.query(ImageRecord).filter_by(
                    details_id=d.id, local_path=d.local_image_path
                ).delete()

                # 清空 local_image_path 字段
                d.local_image_path = None
                repaired_count += 1

        db.session.commit()
        # 第二步：扫描并添加缺失的记录
        added_count = scan_and_add_missing_images()
        repaired_count += added_count

        # 第三步：找出还未下载的记录（local_image_path 为 None）
        details_pending = Details.query.filter(
            Details.image_url.isnot(None), Details.local_image_path.is_(None)
        ).all()
        detail_imgs = [d.image_url for d in details_pending]
        print(detail_imgs)

        detail_ids = [d.id for d in details_pending]

    # 异步执行批量下载
    thread = Thread(target=download_images_async, args=(app, detail_ids))
    thread.start()

    return jsonify(
        {
            "status": "started",
            "count": repaired_count,
            "detail_imgs": detail_imgs,
            "to_download": len(detail_ids),
        }
    )


def batch_download_images(details_ids):
    """批量下载任务（路径处理与单文件一致）"""
    total = len(details_ids)
    success_count = 0
    failed_count = 0
    failed_list = []

    with app.app_context():
        for i, details_id in enumerate(details_ids):
            details = Details.query.get(details_id)
            if details and details.image_url:
                with download_lock:
                    success, message = download_image(details.image_url, details_id)
                    if success:
                        success_count += 1
                    else:
                        failed_count += 1
                        failed_list.append(
                            {
                                "details_id": details_id,
                                "image_url": details.image_url,
                                "error": message,
                            }
                        )
            time.sleep(0.3)
            if i % 10 == 0:
                db.session.commit()

    db.session.commit()
    print(f"下载统计: 总数{total}, 成功{success_count}, 失败{failed_count}")


# 路由和视图函数（保持原有代码完全不变）
@app.route("/")
def index():
    return redirect(url_for("list_main"))


# @app.route("/main")
# def list_main():
#     mains = Main.query.order_by(Main.id.desc()).all()

#     # 为每个main的第一个detail添加本地图片路径
#     for main in mains:
#         if main.details:
#             first_detail = main.details[0]
#             if first_detail.local_image_path and os.path.exists(
#                 first_detail.local_image_path
#             ):
#                 first_detail.display_image_url = (
#                     "/" + first_detail.local_image_path.replace("\\", "/")
#                 )
#             else:
#                 first_detail.display_image_url = first_detail.image_url


#     return render_template("main_list.html", mains=mains)


@app.route("/main", defaults={"page": 1})
@app.route("/main/page/<int:page>")
def list_main(page):
    # 每页显示50条数据，按ID降序排列
    pagination = Main.query.order_by(Main.id.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    mains = pagination.items

    # 为每个main的第一个detail添加本地图片路径
    for main in mains:
        if main.details:
            first_detail = main.details[0]
            if first_detail.local_image_path and os.path.exists(
                first_detail.local_image_path
            ):
                first_detail.display_image_url = (
                    "/" + first_detail.local_image_path.replace("\\", "/")
                )
            else:
                first_detail.display_image_url = first_detail.image_url

    return render_template("main_list.html", pagination=pagination, mains=mains)


@app.route("/main/add", methods=["GET", "POST"])
def add_main():
    if request.method == "POST":
        # 处理单个URL的情况
        if "\n" not in request.form["url"]:
            url = request.form["url"].strip()

            # 修改 add_main 路由中的线程调用部分
            if url and "1688.com" in url:

                @copy_current_request_context
                def process_in_thread():
                    process_url_data(url, db)

                thread = Thread(target=process_in_thread)
                thread.start()

                return render_template("main_form.html", main=None, loading=True)
            # 普通提交处理
            new_main = Main(
                url=url,
                title=request.form["title"],
                company_name=request.form["company_name"],
                company_url=request.form["company_url"],
            )
            db.session.add(new_main)
            db.session.commit()
            return redirect(url_for("list_main"))

        # 处理多URL的情况
        else:
            urls = [
                url.strip()
                for url in request.form["url"].split("\n")
                if url.strip() and "1688.com" in url
            ]

            if urls:
                for url in urls:
                    thread = Thread(
                        target=process_url_data, args=(url, db)
                    )  # 传入db参数
                    thread.start()
                return redirect(url_for("list_main"))
            else:
                # 如果没有有效的1688 URL，当作普通提交处理
                new_main = Main(
                    url=request.form["url"],
                    title=request.form["title"],
                    company_name=request.form["company_name"],
                    company_url=request.form["company_url"],
                )
                db.session.add(new_main)
                db.session.commit()
                return redirect(url_for("list_main"))

    # GET请求返回表单
    return render_template("main_form.html", main=None, loading=False)


@app.route("/main/edit/<int:id>", methods=["GET", "POST"])
def edit_main(id):
    main = Main.query.get_or_404(id)
    if request.method == "POST":
        main.url = request.form["url"]
        main.title = request.form["title"]
        main.company_name = request.form["company_name"]
        main.company_url = request.form["company_url"]
        db.session.commit()
        return redirect(url_for("list_main"))
    return render_template("main_form.html", main=main)


@app.route("/main/delete/<int:id>")
def delete_main(id):
    main = Main.query.get_or_404(id)
    db.session.delete(main)
    db.session.commit()
    return redirect(url_for("list_main"))


# 添加公司信息
@app.route("/add_company", methods=["GET", "POST"])
def add_company():
    if request.method == "POST":
        company = Company(
            name_cn=request.form["name_cn"],
            name_en=request.form["name_en"],
            address_cn=request.form["address_cn"],
            address_en=request.form["address_en"],
            website=request.form["website"],
        )
        db.session.add(company)
        db.session.commit()
        return redirect(url_for("list_companies"))
    return render_template("add_company.html")


# 展示公司信息
@app.route("/companies")
def list_companies():
    companies = Company.query.all()
    return render_template("list_companies.html", companies=companies)


# 添加销售员信息
@app.route("/add_salesperson", methods=["GET", "POST"])
def add_salesperson():
    if request.method == "POST":
        salesperson = Salesperson(
            name_cn=request.form["name_cn"],
            name_en=request.form["name_en"],
            phone=request.form["phone"],
            email=request.form["email"],
            wechat=request.form.get("wechat"),
            whatsapp=request.form.get("whatsapp"),
            facebook=request.form.get("facebook"),
            instagram=request.form.get("instagram"),
            tiktok=request.form.get("tiktok"),
            twitter=request.form.get("twitter"),
        )
        db.session.add(salesperson)
        db.session.commit()
        return redirect(url_for("list_salespersons"))
    return render_template("add_salesperson.html")


@app.route("/salespersons/edit/<int:id>", methods=["GET", "POST"])
def edit_salesperson(id):
    salesperson = Salesperson.query.get_or_404(id)

    if request.method == "POST":
        salesperson.name_cn = request.form["name_cn"]
        salesperson.name_en = request.form["name_en"]
        salesperson.phone = request.form["phone"]
        salesperson.email = request.form["email"]
        salesperson.wechat = request.form.get("wechat") or None
        salesperson.whatsapp = request.form.get("whatsapp") or None
        salesperson.facebook = request.form.get("facebook") or None
        salesperson.instagram = request.form.get("instagram") or None
        salesperson.tiktok = request.form.get("tiktok") or None
        salesperson.twitter = request.form.get("twitter") or None

        db.session.commit()
        flash("销售员信息已更新", "success")
        return redirect(url_for("list_salespersons"))

    return render_template("edit_salesperson.html", salesperson=salesperson)


# 展示销售员信息
@app.route("/salespersons")
def list_salespersons():
    salespersons = Salesperson.query.all()
    return render_template("list_salespersons.html", salespersons=salespersons)


@app.route("/details/<int:main_id>")
def list_details(main_id):
    main = Main.query.get_or_404(main_id)
    details = Details.query.filter_by(main_id=main_id).all()

    for detail in details:
        # 处理库存数据
        if detail.stock is not None:
            try:
                stock_decimal = Decimal(str(detail.stock))
                detail.stock_str = str(
                    stock_decimal.to_integral_value()
                    if stock_decimal == stock_decimal.to_integral_value()
                    else stock_decimal.normalize()
                )
            except InvalidOperation:
                detail.stock_str = "格式错误"
        else:
            detail.stock_str = "无数据"

        # ✅ 优先使用 local_image_path 字段
        if detail.local_image_path and os.path.exists(detail.local_image_path):
            detail.display_image_url = "/" + detail.local_image_path.replace("\\", "/")
        else:
            detail.display_image_url = detail.image_url

    return render_template("details_list.html", main=main, details=details)


# @app.route("/details/<int:main_id>")
# def list_details(main_id):
#     main = Main.query.get_or_404(main_id)
#     details = Details.query.filter_by(main_id=main_id).all()

#     # 格式化库存数据为字符串
#     for detail in details:
#         if detail.stock is not None:
#             try:
#                 stock_decimal = Decimal(str(detail.stock))
#                 if stock_decimal == stock_decimal.to_integral_value():
#                     detail.stock_str = str(stock_decimal.to_integral_value())
#                 else:
#                     detail.stock_str = str(stock_decimal.normalize())
#             except InvalidOperation:
#                 detail.stock_str = "格式错误"
#         else:
#             detail.stock_str = "无数据"

#     return render_template("details_list.html", main=main, details=details)


@app.route("/details/add/<int:main_id>", methods=["GET", "POST"])
def add_details(main_id):
    main = Main.query.get_or_404(main_id)
    if request.method == "POST":
        stock_input = request.form["stock"]
        stock = float(stock_input) if stock_input else None

        new_detail = Details(
            main_id=main_id,
            other_model=request.form["other_model"],
            self_model=request.form["self_model"],
            price=float(request.form["price"]),
            image_url=request.form["image_url"],
            stock=stock,
        )
        db.session.add(new_detail)
        db.session.commit()
        return redirect(url_for("list_details", main_id=main_id))
    return render_template("details_form.html", main=main, detail=None)


@app.route("/details/edit/<int:id>", methods=["GET", "POST"])
def edit_details(id):
    detail = Details.query.get_or_404(id)
    if request.method == "POST":
        detail.other_model = request.form["other_model"]
        detail.self_model = request.form["self_model"]
        detail.price = float(request.form["price"])
        detail.image_url = request.form["image_url"]
        stock_input = request.form["stock"]
        detail.stock = float(stock_input) if stock_input else 0
        db.session.commit()
        return redirect(url_for("list_details", main_id=detail.main_id))
    return render_template("details_form.html", main=detail.main, detail=detail)


@app.route("/details/auto_number/<int:id>", methods=["GET", "POST"])
def auto_number_details(id):
    detail = Details.query.get_or_404(id)

    # 默认参数
    default_data = {"prefix": "SLN", "increment": 1, "digits": 2, "start_number": 1}

    if request.method == "POST":
        prefix = request.form.get("prefix", "").strip()
        increment = int(request.form.get("increment", 1))
        digits = int(request.form.get("digits", 2))
        start_number = int(request.form.get("start_number", 1))

        if not prefix:
            flash("请输入前缀", "error")
            return redirect(url_for("auto_number_details", id=id))

        try:
            details = (
                Details.query.filter_by(main_id=detail.main_id)
                .order_by(Details.id)
                .all()
            )
            current_number = start_number

            for detail_item in details:
                new_code = f"{prefix}{str(current_number).zfill(digits)}"
                detail_item.self_model = new_code
                current_number += increment

            db.session.commit()
            flash(
                f"已成功为{len(details)}条记录生成顺序编号，从{start_number}开始",
                "success",
            )
            return redirect(url_for("list_details", main_id=detail.main_id))

        except Exception as e:
            db.session.rollback()
            flash(f"生成失败: {str(e)}", "error")
            return redirect(url_for("auto_number_details", id=id))

    # 计算预览值（后端处理）
    preview_value = f"{default_data['prefix']}{str(default_data['start_number']).zfill(default_data['digits'])}"

    return render_template(
        "auto_number.html",
        detail=detail,
        defaults=default_data,
        preview_value=preview_value,  # 后端计算好的预览值
    )


# @app.route("/details/edit/<int:id>", methods=["GET", "POST"])
# def edit_details(id):
#     detail = Details.query.get_or_404(id)
#     if request.method == "POST":
#         # 获取表单数据
#         other_model = request.form["other_model"]
#         new_self_model = request.form["self_model"]
#         price = float(request.form["price"])
#         image_url = request.form["image_url"]
#         stock_input = request.form["stock"]
#         stock = float(stock_input) if stock_input else 0

#         # 检查新的self_model是否已存在（排除当前记录自身）
#         if new_self_model != detail.self_model:  # 如果用户修改了self_model
#             existing = Details.query.filter_by(self_model=new_self_model).first()
#             if existing:
#                 flash("自用型号已存在，请使用其他型号", "error")
#                 return render_template(
#                     "details_form.html", main=detail.main, detail=detail
#                 )

#         # 更新记录
#         detail.other_model = other_model
#         detail.self_model = new_self_model
#         detail.price = price
#         detail.image_url = image_url
#         detail.stock = stock

#         try:
#             db.session.commit()
#             flash("详情更新成功", "success")
#             return redirect(url_for("list_details", main_id=detail.main_id))
#         except Exception as e:
#             db.session.rollback()
#             flash(f"更新失败: {str(e)}", "error")

#     return render_template("details_form.html", main=detail.main, detail=detail)


@app.route("/details/delete/<int:id>")
def delete_details(id):
    detail = Details.query.get_or_404(id)
    main_id = detail.main_id
    db.session.delete(detail)
    db.session.commit()
    return redirect(url_for("list_details", main_id=main_id))


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    results = []

    if query:
        # 搜索Main表
        main_results = (
            Main.query.filter(
                db.or_(
                    Main.title.ilike(f"%{query}%"),
                    Main.company_name.ilike(f"%{query}%"),
                )
            )
            .options(db.joinedload(Main.details))
            .all()
        )

        # 搜索Details表
        detail_results = (
            Details.query.filter(
                db.or_(
                    Details.other_model.ilike(f"%{query}%"),
                    Details.self_model.ilike(f"%{query}%"),
                )
            )
            .options(db.joinedload(Details.main))
            .all()
        )

        # 处理结果
        for main in main_results:
            for detail in main.details:
                # 格式化库存数据
                if detail.stock is not None:
                    try:
                        stock_decimal = Decimal(str(detail.stock))
                        if stock_decimal == stock_decimal.to_integral_value():
                            detail.stock_str = str(stock_decimal.to_integral_value())
                        else:
                            detail.stock_str = str(stock_decimal.normalize())
                    except InvalidOperation:
                        detail.stock_str = "格式错误"
                else:
                    detail.stock_str = "无数据"

                results.append({"main": main, "detail": detail, "match_type": "main"})

        for detail in detail_results:
            if not any(r["detail"].id == detail.id for r in results):
                # 格式化库存数据
                if detail.stock is not None:
                    try:
                        stock_decimal = Decimal(str(detail.stock))
                        if stock_decimal == stock_decimal.to_integral_value():
                            detail.stock_str = str(stock_decimal.to_integral_value())
                        else:
                            detail.stock_str = str(stock_decimal.normalize())
                    except InvalidOperation:
                        detail.stock_str = "格式错误"
                else:
                    detail.stock_str = "无数据"

                results.append(
                    {"main": detail.main, "detail": detail, "match_type": "detail"}
                )

    return render_template("search_results.html", results=results, query=query)


if __name__ == "__main__":
    import logging

    with app.app_context():
        db.create_all()

    logging.basicConfig(level=logging.DEBUG)
    app.run(debug=True, port=1000, host="0.0.0.0")
