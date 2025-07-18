from threading import Thread, Lock
from decimal import Decimal, InvalidOperation
from extensions import db
from flask import (
    Flask,
    flash,
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    copy_current_request_context,
)
from flask_login import login_required, current_user, logout_user
from models import Product, ProductDetail, ImageRecord, Company, User, Role, Permission
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
from export import export_bp, data_bp
from utils import process_url_data
from werkzeug.security import generate_password_hash
from flask_login import LoginManager

download_lock = Lock()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = config("SECRET_KEY")

db.init_app(app)
migrate = Migrate(app, db)

# 配置图片存储路径（使用pathlib处理）
IMAGE_FOLDER = Path("static") / "images"
IMAGE_FOLDER.mkdir(parents=True, exist_ok=True)

app.register_blueprint(export_bp)
app.register_blueprint(data_bp)

# 初始化 Flask-Login


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"  # 未登录时重定向到登录页面


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


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
                # 更新ProductDetail表的local_image_path字段
                detail = ProductDetail.query.get(details_id)
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

            # 更新ProductDetail表的local_image_path字段
            detail = ProductDetail.query.get(details_id)
            if detail:
                detail.local_image_path = str(local_path)
                db.session.commit()

            return True, str(local_path)
        else:
            return False, f"下载失败: HTTP状态码 {response.status_code}"
    except Exception as e:
        return False, f"下载失败: {str(e)}"


@app.route("/download_images/<int:product_id>", methods=["POST"])
@login_required
def download_images(product_id):
    # 检查用户是否有下载图片的权限
    if not current_user.has_permission("download_images"):
        flash("您没有权限下载图片", "danger")
        return jsonify({"status": "error", "message": "无权限"})

    with app.app_context():
        details = ProductDetail.query.filter_by(product_id=product_id).all()
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
    for detail in ProductDetail.query.filter(
        ProductDetail.local_image_path.isnot(None)
    ).all():
        if detail.local_image_path:
            db_images.add(os.path.basename(detail.local_image_path))

    # 扫描static/images目录
    missing_count = 0
    for filename in os.listdir(images_dir):
        # 检查是否是文件且不在数据库中
        filepath = os.path.join(images_dir, filename)
        if os.path.isfile(filepath) and filename not in db_images:
            # 查找是否有对应的ProductDetail记录（根据URL末尾匹配）
            matching_detail = ProductDetail.query.filter(
                ProductDetail.image_url.endswith(filename)
            ).first()

            if matching_detail:
                # 创建本地路径（根据你的实际路径结构可能需要调整）
                local_path = os.path.join("static", "images", filename)

                # 更新ProductDetail记录
                matching_detail.local_image_path = local_path

                # 添加ImageRecord记录
                image_record = ImageRecord(
                    details_id=matching_detail.id,
                    image_url=matching_detail.image_url,
                    local_path=local_path,
                    download_time=datetime.now(),
                )
                db.session.add(image_record)
                missing_count += 1

    db.session.commit()
    return missing_count


@app.route("/download_images/all", methods=["POST"])
@login_required
def download_all_images():
    # 检查用户是否有批量下载图片的权限
    if not current_user.has_permission("download_all_images"):
        flash("您没有权限执行批量下载", "danger")
        return jsonify({"status": "error", "message": "无权限"})

    with app.app_context():
        # 第一步：清理已记录但本地文件不存在的记录
        details_all = ProductDetail.query.filter(
            ProductDetail.image_url.isnot(None)
        ).all()
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

        # 第三步：找出还未下载的记录
        details_pending = ProductDetail.query.filter(
            ProductDetail.image_url.isnot(None),
            ProductDetail.local_image_path.is_(None),
        ).all()
        detail_imgs = [d.image_url for d in details_pending]

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
    """批量下载任务"""
    total = len(details_ids)
    success_count = 0
    failed_count = 0
    failed_list = []

    with app.app_context():
        for i, details_id in enumerate(details_ids):
            details = ProductDetail.query.get(details_id)
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


def get_best_prices(product):
    if product.details:
        first_detail = product.details[0]

        # 处理图片路径
        if first_detail.local_image_path and os.path.exists(
            first_detail.local_image_path
        ):
            first_detail.display_image_url = (
                "/" + first_detail.local_image_path.replace("\\", "/")
            )
        else:
            first_detail.display_image_url = first_detail.image_url

        # 获取所有批发价格信息
        all_prices = [
            float(price.price)
            for detail in product.details
            for price in detail.wholesale_prices
        ] + [detail.price for detail in product.details]

        moqs = {
            price.min_quantity
            for detail in product.details
            for price in detail.wholesale_prices
        }

        # 计算价格范围和最小起订量
        if all_prices:
            product.min_price = min(all_prices)
            product.max_price = max(all_prices)
            product.min_moq = min(moqs) if moqs else 1
            product.moqs = sorted(moqs)  # 排序后的起订量列表
            product.spec_count = len(product.details)  # 规格数量
        else:
            # 如果没有批发价格，使用详情中的基础价格
            price = first_detail.price
            product.min_price = price
            product.max_price = price
            product.min_moq = 1
            product.moqs = [1]
            product.spec_count = len(product.details)
        print(product.min_price)
        print(product.max_price)
        print(product.min_moq)
        print(product.moqs)
        print("-" * 60)
    return product


# 登录路由
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            from flask_login import login_user

            login_user(user)
            flash("登录成功", "success")
            return redirect(url_for("list_main"))
        else:
            flash("用户名或密码错误", "danger")
    return render_template("login.html")


# 退出登录
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("已退出登录", "success")
    return redirect(url_for("login"))


@app.route("/admin/manage", methods=["GET"])
@login_required
def admin_manage():
    # 检查是否为超级管理员
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not admin_role or admin_role not in current_user.roles:
        flash("只有超级管理员可以访问此页面", "danger")
        return redirect(url_for("index"))

    users = User.query.all()
    # 为每个用户添加 role_names 属性
    for user in users:
        user.role_names = ", ".join([role.name for role in user.roles]) or "无角色"

    roles = Role.query.all()
    # 为每个角色添加 permissions_names 属性
    for role in roles:
        role.permissions_names = (
            ", ".join([perm.name for perm in role.permissions]) or "无权限"
        )

    permissions = Permission.query.all()
    return render_template(
        "users/admin_manage.html", users=users, roles=roles, permissions=permissions
    )


@app.route("/admin/user/add", methods=["GET", "POST"])
@login_required
def add_user():
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not admin_role or admin_role not in current_user.roles:
        flash("只有超级管理员可以添加用户", "danger")
        return redirect(url_for("admin_manage"))

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        if not username or not password:
            flash("用户名和密码不能为空", "danger")
            return redirect(url_for("add_user"))

        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            name_cn=request.form.get("name_cn", ""),
            name_en=request.form.get("name_en", ""),
            phone=request.form.get("phone", ""),
            email=request.form.get("email", ""),
            is_active=request.form.get("is_active") == "on",
        )

        # 处理角色关联
        role_ids = request.form.getlist("roles")
        for role_id in role_ids:
            role = Role.query.get(role_id)
            if role:
                user.roles.append(role)

        # 处理直接权限关联
        permission_ids = request.form.getlist("permissions")
        for permission_id in permission_ids:
            permission = Permission.query.get(permission_id)
            if permission:
                user.permissions.append(permission)

        db.session.add(user)
        db.session.commit()
        flash("用户添加成功", "success")
        return redirect(url_for("admin_manage"))

    roles = Role.query.all()
    permissions = Permission.query.all()
    return render_template("users/add_user.html", roles=roles, permissions=permissions)


@app.route("/admin/user/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_user(id):
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not admin_role or admin_role not in current_user.roles:
        flash("只有超级管理员可以编辑用户", "danger")
        return redirect(url_for("admin_manage"))

    user = User.query.get_or_404(id)
    if request.method == "POST":
        user.username = request.form["username"].strip() or user.username
        password = request.form.get("password", "").strip()
        if password:
            user.password_hash = generate_password_hash(password)
        user.name_cn = request.form.get("name_cn", "")
        user.name_en = request.form.get("name_en", "")
        user.phone = request.form.get("phone", "")
        user.email = request.form.get("email", "")
        user.is_active = request.form.get("is_active") == "on"

        # 更新角色关联
        user.roles = []
        role_ids = request.form.getlist("roles")
        for role_id in role_ids:
            role = Role.query.get(role_id)
            if role:
                user.roles.append(role)

        # 更新直接权限关联
        user.permissions = []
        permission_ids = request.form.getlist("permissions")
        for permission_id in permission_ids:
            permission = Permission.query.get(permission_id)
            if permission:
                user.permissions.append(permission)

        db.session.commit()
        flash("用户更新成功", "success")
        return redirect(url_for("admin_manage"))

    roles = Role.query.all()
    permissions = Permission.query.all()
    return render_template(
        "users/edit_user.html", user=user, roles=roles, permissions=permissions
    )


@app.route("/admin/user/delete/<int:id>")
@login_required
def delete_user(id):
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not admin_role or admin_role not in current_user.roles:
        flash("只有超级管理员可以删除用户", "danger")
        return redirect(url_for("admin_manage"))

    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash("不能删除当前登录用户", "danger")
    else:
        db.session.delete(user)
        db.session.commit()
        flash("用户删除成功", "success")
    return redirect(url_for("admin_manage"))


@app.route("/admin/role/add", methods=["GET", "POST"])
@login_required
def add_role():
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not admin_role or admin_role not in current_user.roles:
        flash("只有超级管理员可以添加角色", "danger")
        return redirect(url_for("admin_manage"))

    if request.method == "POST":
        name = request.form["name"].strip()
        if not name:
            flash("角色名称不能为空", "danger")
            return redirect(url_for("add_role"))

        role = Role(name=name)
        permission_ids = request.form.getlist("permissions")
        for perm_id in permission_ids:
            perm = Permission.query.get(perm_id)
            if perm:
                role.permissions.append(perm)

        db.session.add(role)
        db.session.commit()
        flash("角色添加成功", "success")
        return redirect(url_for("admin_manage"))

    permissions = Permission.query.all()
    return render_template("users/add_role.html", permissions=permissions)


@app.route("/admin/role/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_role(id):
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not admin_role or admin_role not in current_user.roles:
        flash("只有超级管理员可以编辑角色", "danger")
        return redirect(url_for("admin_manage"))

    role = Role.query.get_or_404(id)
    if request.method == "POST":
        role.name = request.form["name"].strip() or role.name
        role.permissions = []
        permission_ids = request.form.getlist("permissions")
        for perm_id in permission_ids:
            perm = Permission.query.get(perm_id)
            if perm:
                role.permissions.append(perm)

        db.session.commit()
        flash("角色更新成功", "success")
        return redirect(url_for("admin_manage"))

    permissions = Permission.query.all()
    return render_template("users/edit_role.html", role=role, permissions=permissions)


@app.route("/admin/role/delete/<int:id>")
@login_required
def delete_role(id):
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not admin_role or admin_role not in current_user.roles:
        flash("只有超级管理员可以删除角色", "danger")
        return redirect(url_for("admin_manage"))

    role = Role.query.get_or_404(id)
    if role.name == "超级管理员":
        flash("不能删除超级管理员角色", "danger")
    else:
        db.session.delete(role)
        db.session.commit()
        flash("角色删除成功", "success")
    return redirect(url_for("admin_manage"))


@app.route("/admin/permission/add", methods=["GET", "POST"])
@login_required
def add_permission():
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not admin_role or admin_role not in current_user.roles:
        flash("只有超级管理员可以添加权限", "danger")
        return redirect(url_for("admin_manage"))

    if request.method == "POST":
        codename = request.form["codename"].strip()
        name = request.form["name"].strip()
        content_type = request.form["content_type"].strip()
        if not codename or not name or not content_type:
            flash("所有字段均为必填", "danger")
            return redirect(url_for("add_permission"))

        permission = Permission(codename=codename, name=name, content_type=content_type)
        db.session.add(permission)
        db.session.commit()
        flash("权限添加成功", "success")
        return redirect(url_for("admin_manage"))

    return render_template("users/add_permission.html")


@app.route("/admin/permission/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_permission(id):
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not admin_role or admin_role not in current_user.roles:
        flash("只有超级管理员可以编辑权限", "danger")
        return redirect(url_for("admin_manage"))

    permission = Permission.query.get_or_404(id)
    if request.method == "POST":
        permission.codename = request.form["codename"].strip() or permission.codename
        permission.name = request.form["name"].strip() or permission.name
        permission.content_type = (
            request.form["content_type"].strip() or permission.content_type
        )
        db.session.commit()
        flash("权限更新成功", "success")
        return redirect(url_for("admin_manage"))

    return render_template("users/edit_permission.html", permission=permission)


@app.route("/admin/permission/delete/<int:id>")
@login_required
def delete_permission(id):
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not admin_role or admin_role not in current_user.roles:
        flash("只有超级管理员可以删除权限", "danger")
        return redirect(url_for("admin_manage"))

    permission = Permission.query.get_or_404(id)
    db.session.delete(permission)
    db.session.commit()
    flash("权限删除成功", "success")
    return redirect(url_for("admin_manage"))


@app.route("/")
def index():
    return redirect(url_for("list_main"))


@app.route("/main", defaults={"page": 1})
@app.route("/main/page/<int:page>")
@login_required
def list_main(page):
    try:
        # 确保 page 有效，防止负数或过大值
        if page < 1:
            page = 1

        # 每页显示50条数据，按ID降序排列
        if Role.query.filter_by(name="超级管理员").first() in current_user.roles:
            # 超级管理员查看所有产品
            query = Product.query.order_by(Product.id.desc())
        else:
            # 普通用户只查看自己的产品
            query = Product.query.filter_by(user_id=current_user.id).order_by(
                Product.id.desc()
            )

        # 分页处理，捕获可能的数据库错误
        pagination = query.paginate(page=page, per_page=50, error_out=False)
        products = pagination.items
        new_products = [get_best_prices(product) for product in products]

        return render_template(
            "products/main_list.html", pagination=pagination, mains=new_products
        )
    except Exception as e:
        app.logger.error(f"Error in list_main: {str(e)}")
        flash("加载产品列表失败，请稍后重试", "danger")
        return render_template("products/main_list.html", pagination=None, mains=[])


@app.route("/main/add", methods=["GET", "POST"])
@login_required
def add_main():
    if not current_user.has_permission("add_product"):
        flash("您没有权限添加产品", "danger")
        return redirect(url_for("list_main", page=1))

    if request.method == "POST":
        try:
            if "\n" not in request.form["url"]:
                url = request.form["url"].strip()
                if url and "1688.com" in url:

                    @copy_current_request_context
                    def process_in_thread():
                        process_url_data(url, db, user_id=current_user.id)

                    thread = Thread(target=process_in_thread)
                    thread.start()
                    flash("正在处理 1688 URL，请稍后刷新查看", "info")
                    return render_template(
                        "products/main_form.html",
                        main=None,
                        loading=True,
                        users=User.query.filter_by(is_active=True).all(),
                    )
                new_product = Product(
                    url=url,
                    title=request.form["title"],
                    company_name=request.form["company_name"],
                    company_url=request.form["company_url"],
                    user_id=current_user.id,
                )
                db.session.add(new_product)
                db.session.commit()
                flash("产品添加成功", "success")
                return redirect(url_for("list_main", page=1))
            else:
                urls = [
                    url.strip()
                    for url in request.form["url"].split("\n")
                    if url.strip() and "1688.com" in url
                ]
                if urls:
                    for url in urls:
                        thread = Thread(
                            target=process_url_data, args=(url, db, current_user.id)
                        )
                        thread.start()
                    flash("批量处理 1688 URLs 已开始，请稍后刷新查看", "info")
                    return redirect(url_for("list_main", page=1))
                else:
                    new_product = Product(
                        url=request.form["url"],
                        title=request.form["title"],
                        company_name=request.form["company_name"],
                        company_url=request.form["company_url"],
                        user_id=current_user.id,
                    )
                    db.session.add(new_product)
                    db.session.commit()
                    flash("产品添加成功", "success")
                    return redirect(url_for("list_main", page=1))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error in add_main: {str(e)}")
            flash("添加产品失败，请检查输入或稍后重试", "danger")
            return redirect(url_for("list_main", page=1))

    return render_template(
        "products/main_form.html",
        main=None,
        loading=False,
        users=User.query.filter_by(is_active=True).all(),
    )


@app.route("/main/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_main(id):
    product = Product.query.get_or_404(id)
    admin_role = Role.query.filter_by(name="超级管理员").first()

    if not current_user.has_permission("edit_product") or (
        product.user_id != current_user.id
        and not (admin_role and admin_role in current_user.roles)
    ):
        flash("您没有权限编辑此产品", "danger")
        return redirect(url_for("list_main", page=1))

    if request.method == "POST":
        try:
            product.url = request.form["url"]
            product.title = request.form["title"]
            product.company_name = request.form["company_name"]
            product.company_url = request.form["company_url"]
            if admin_role and admin_role in current_user.roles:
                user_id = request.form.get("user_id")
                if user_id:
                    product.user_id = int(user_id)
            db.session.commit()
            flash("产品更新成功", "success")
            return redirect(url_for("list_main", page=1))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error in edit_main: {str(e)}")
            flash("更新产品失败，请检查输入或稍后重试", "danger")
            return redirect(url_for("list_main", page=1))

    return render_template(
        "products/main_form.html",
        main=product,
        users=User.query.filter_by(is_active=True).all(),
    )


@app.route("/main/delete/<int:id>")
@login_required
def delete_main(id):
    product = Product.query.get_or_404(id)

    # 检查用户是否有删除权限，超级管理员可删除所有产品
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not current_user.has_permission("delete_product") or (
        product.user_id != current_user.id
        and not (admin_role and admin_role in current_user.roles)
    ):
        flash("您没有权限删除此产品", "danger")
        return redirect(url_for("list_main"))

    db.session.delete(product)
    db.session.commit()
    flash("产品删除成功", "success")
    return redirect(url_for("list_main"))


@app.route("/add_company", methods=["GET", "POST"])
@login_required
def add_company():
    # 检查用户是否有添加公司的权限
    if not current_user.has_permission("add_company"):
        flash("您没有权限添加公司", "danger")
        return redirect(url_for("list_companies"))

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
    return render_template("company/add_company.html")


@app.route("/companies")
@login_required
def list_companies():
    companies = Company.query.all()
    return render_template("company/list_companies.html", companies=companies)


@app.route("/salespersons/add", methods=["GET", "POST"])
@login_required
def add_salesperson():
    # 检查用户是否有添加销售员的权限
    if not current_user.has_permission("add_salesperson"):
        flash("您没有权限添加销售员", "danger")
        return redirect(url_for("list_salespersons"))

    if request.method == "POST":
        username = request.form["username"].strip()
        password_plain = request.form["password"].strip()
        if not username or not password_plain:
            flash("用户名和密码不能为空", "danger")
            return redirect(url_for("add_salesperson"))

        salesperson = User(
            username=username,
            password_hash=generate_password_hash(password_plain),
            name_cn=request.form["name_cn"],
            name_en=request.form["name_en"],
            phone=request.form["phone"],
            email=request.form["email"],
            wechat=request.form.get("wechat") or None,
            whatsapp=request.form.get("whatsapp") or None,
            facebook=request.form.get("facebook") or None,
            instagram=request.form.get("instagram") or None,
            tiktok=request.form.get("tiktok") or None,
            twitter=request.form.get("twitter") or None,
        )
        sales_role = Role.query.filter_by(name="销售员").first()
        if sales_role:
            salesperson.roles.append(sales_role)

        db.session.add(salesperson)
        db.session.commit()
        flash("销售员已添加", "success")
        return redirect(url_for("list_salespersons"))
    return render_template("users/add_salesperson.html")


@app.route("/salespersons/edit/<int:id>", methods=["GET", "POST"])
@login_required  # 确保用户已登录（未登录用户会被flask-login拦截）
def edit_salesperson(id):
    # 获取目标用户对象
    salesperson = User.query.get_or_404(id)

    # 核心安全检查：
    # 1. 普通用户只能编辑自己的信息（id匹配当前登录用户）
    # 2. 管理员/有权限的用户可以编辑所有信息
    is_admin = current_user.has_permission("admin")  # 管理员权限判断
    is_self = current_user.id == salesperson.id  # 自身信息判断

    # 既不是管理员，也不是编辑自己的信息 → 拒绝访问
    if not (is_admin or is_self):
        flash("您没有权限编辑该用户的信息", "danger")
        return redirect(url_for("list_salespersons"))

    # 获取所有角色（用于表单选择）
    roles = Role.query.all()

    if request.method == "POST":
        # 进一步限制：普通用户不能修改角色（只有管理员可以）
        if not is_admin:
            # 强制使用当前用户的角色（忽略表单提交的角色数据）
            role_ids = [role.id for role in current_user.roles]
        else:
            role_ids = request.form.getlist("roles")

        # 基本信息更新
        salesperson.username = request.form.get("username").strip()
        salesperson.name_cn = request.form.get("name_cn").strip()
        salesperson.name_en = request.form.get("name_en").strip()
        salesperson.phone = request.form.get("phone").strip()
        salesperson.email = request.form.get("email").strip()
        salesperson.wechat = request.form.get("wechat").strip() or None
        salesperson.whatsapp = request.form.get("whatsapp").strip() or None
        salesperson.facebook = request.form.get("facebook").strip() or None
        salesperson.instagram = request.form.get("instagram").strip() or None
        salesperson.tiktok = request.form.get("tiktok").strip() or None
        salesperson.twitter = request.form.get("twitter").strip() or None

        # 处理密码更新（留空则不修改）
        password = request.form.get("password").strip()
        if password:
            salesperson.set_password(password)

        # 处理角色更新（已通过is_admin限制）
        salesperson.roles = Role.query.filter(Role.id.in_(role_ids)).all()

        # 处理激活状态（普通用户不能修改自己的激活状态）
        if is_admin:
            salesperson.is_active = "is_active" in request.form
        # 普通用户提交时忽略is_active字段，保持原有状态

        try:
            db.session.commit()
            flash("销售员信息已更新", "success")
            return redirect(url_for("list_salespersons"))
        except Exception as e:
            db.session.rollback()
            flash(f"更新失败: {str(e)}", "danger")

    return render_template(
        "users/edit_salesperson.html",
        salesperson=salesperson,
        roles=roles,
        is_admin=is_admin,
    )


@app.route("/salespersons")
@login_required
def list_salespersons():
    # 判断当前用户是否为管理员（假设拥有"admin"角色的用户是管理员）
    is_admin = current_user.has_permission("admin")

    if is_admin:
        # 管理员查看所有销售员
        salespersons = User.query.all()
    else:
        # 普通销售员只能查看自己的信息
        salespersons = [current_user]

    return render_template(
        "users/list_salespersons.html", salespersons=salespersons, is_admin=is_admin
    )  # 传递是否为管理员的标志到模板


@app.route("/details/<int:product_id>")
@login_required
def list_details(product_id):
    product = Product.query.get_or_404(product_id)

    # 检查用户是否是产品拥有者或超级管理员
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if product.user_id != current_user.id and not (
        admin_role and admin_role in current_user.roles
    ):
        flash("您没有权限查看此产品详情", "danger")
        return redirect(url_for("list_main"))

    details = ProductDetail.query.filter_by(product_id=product_id).all()

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

        # 优先使用本地图片
        if detail.local_image_path and os.path.exists(detail.local_image_path):
            detail.display_image_url = "/" + detail.local_image_path.replace("\\", "/")
        else:
            detail.display_image_url = detail.image_url

        # 构造阶梯价格数据列表
        price_ranges = []
        for wp in sorted(detail.wholesale_prices, key=lambda x: x.min_quantity):
            if wp.max_quantity is not None:
                range_text = f"{wp.min_quantity} - {wp.max_quantity}"
            else:
                range_text = f"≥ {wp.min_quantity}"
            price_ranges.append({"range": range_text, "price": wp.price})
        detail.price_ranges = price_ranges

    return render_template("products/details_list.html", main=product, details=details)


@app.route("/details/add/<int:product_id>", methods=["GET", "POST"])
@login_required
def add_details(product_id):
    product = Product.query.get_or_404(product_id)

    # 检查用户是否有添加详情的权限且是产品拥有者或超级管理员
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not current_user.has_permission("add_product_detail") or (
        product.user_id != current_user.id
        and not (admin_role and admin_role in current_user.roles)
    ):
        flash("您没有权限添加产品详情", "danger")
        return redirect(url_for("list_details", product_id=product_id))

    if request.method == "POST":
        stock_input = request.form["stock"]
        stock = float(stock_input) if stock_input else None

        new_detail = ProductDetail(
            product_id=product_id,
            other_model=request.form["other_model"],
            self_model=request.form["self_model"],
            price=float(request.form["price"]),
            image_url=request.form["image_url"],
            stock=stock,
        )
        db.session.add(new_detail)
        db.session.commit()
        flash("产品详情添加成功", "success")
        return redirect(url_for("list_details", product_id=product_id))
    return render_template("products/details_form.html", main=product, detail=None)


@app.route("/details/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_details(id):
    detail = ProductDetail.query.get_or_404(id)

    # 检查用户是否有编辑详情的权限且是产品拥有者或超级管理员
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not current_user.has_permission("edit_product_detail") or (
        detail.product.user_id != current_user.id
        and not (admin_role and admin_role in current_user.roles)
    ):
        flash("您没有权限编辑产品详情", "danger")
        return redirect(url_for("list_details", product_id=detail.product_id))

    if request.method == "POST":
        detail.other_model = request.form["other_model"]
        detail.self_model = request.form["self_model"]
        detail.price = float(request.form["price"])
        detail.image_url = request.form["image_url"]
        stock_input = request.form["stock"]
        detail.stock = float(stock_input) if stock_input else 0
        db.session.commit()
        flash("产品详情更新成功", "success")
        return redirect(url_for("list_details", product_id=detail.product_id))
    return render_template(
        "products/details_form.html", main=detail.product, detail=detail
    )


# @login_required 自动编号暂时不设置登录权限


@app.route("/details/auto_number/<int:id>", methods=["GET", "POST"])
def auto_number_details(id):
    detail = ProductDetail.query.get_or_404(id)

    # # 检查用户是否有自动编号的权限且是产品拥有者
    # if (
    #     not current_user.has_permission("edit_product_detail")
    #     or detail.product.user_id != current_user.id
    # ):
    #     flash("您没有权限执行自动编号", "danger")
    #     return redirect(url_for("list_details", product_id=detail.product_id))

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
                ProductDetail.query.filter_by(product_id=detail.product_id)
                .order_by(ProductDetail.id)
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
            return redirect(url_for("list_details", product_id=detail.product_id))

        except Exception as e:
            db.session.rollback()
            flash(f"生成失败: {str(e)}", "error")
            return redirect(url_for("auto_number_details", id=id))

    preview_value = f"{default_data['prefix']}{str(default_data['start_number']).zfill(default_data['digits'])}"

    return render_template(
        "products/auto_number.html",
        detail=detail,
        defaults=default_data,
        preview_value=preview_value,
    )


@app.route("/details/delete/<int:id>")
@login_required
def delete_details(id):
    detail = ProductDetail.query.get_or_404(id)

    # 检查用户是否有删除详情的权限且是产品拥有者或超级管理员
    admin_role = Role.query.filter_by(name="超级管理员").first()
    if not current_user.has_permission("delete_product_detail") or (
        detail.product.user_id != current_user.id
        and not (admin_role and admin_role in current_user.roles)
    ):
        flash("您没有权限删除产品详情", "danger")
        return redirect(url_for("list_details", product_id=detail.product_id))

    product_id = detail.product_id
    db.session.delete(detail)
    db.session.commit()
    flash("产品详情删除成功", "success")
    return redirect(url_for("list_details", product_id=product_id))


@app.route("/search")
@login_required
def search():
    query = request.args.get("q", "").strip()
    results = []
    admin_role = Role.query.filter_by(name="超级管理员").first()

    if query:
        if admin_role and admin_role in current_user.roles:
            # 超级管理员搜索所有产品
            product_results = (
                Product.query.filter(
                    db.or_(
                        Product.title.ilike(f"%{query}%"),
                        Product.company_name.ilike(f"%{query}%"),
                    )
                )
                .options(db.joinedload(Product.details))
                .all()
            )

            detail_results = (
                ProductDetail.query.filter(
                    db.or_(
                        ProductDetail.other_model.ilike(f"%{query}%"),
                        ProductDetail.self_model.ilike(f"%{query}%"),
                    )
                )
                .join(Product)
                .options(db.joinedload(ProductDetail.product))
                .all()
            )
        else:
            # 普通用户只搜索自己的产品
            product_results = (
                Product.query.filter(
                    db.or_(
                        Product.title.ilike(f"%{query}%"),
                        Product.company_name.ilike(f"%{query}%"),
                    ),
                    Product.user_id == current_user.id,
                )
                .options(db.joinedload(Product.details))
                .all()
            )

            detail_results = (
                ProductDetail.query.filter(
                    db.or_(
                        ProductDetail.other_model.ilike(f"%{query}%"),
                        ProductDetail.self_model.ilike(f"%{query}%"),
                    )
                )
                .join(Product)
                .filter(Product.user_id == current_user.id)
                .options(db.joinedload(ProductDetail.product))
                .all()
            )

        # 处理结果
        for product in product_results:
            for detail in product.details:
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

                results.append(
                    {"main": product, "detail": detail, "match_type": "main"}
                )

        for detail in detail_results:
            if not any(r["detail"].id == detail.id for r in results):
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

                results.append(
                    {"main": detail.product, "detail": detail, "match_type": "detail"}
                )

    return render_template("search/search_results.html", results=results, query=query)


@app.route("/export", methods=["GET"])
@login_required
def export_page():
    return render_template("export.html")


if __name__ == "__main__":
    import logging

    with app.app_context():
        db.create_all()
    logging.basicConfig(level=logging.DEBUG)
    app.run(debug=True, port=1000, host="0.0.0.0")
