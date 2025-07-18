from models import Product, ProductDetail, ImageRecord, User
from flask import current_app, Blueprint, Response, jsonify, g
from flask_login import current_user
import io
import csv
from extensions import db
import traceback
from threading import Thread
from utils import collect_missing_prices_task

export_bp = Blueprint("export", __name__)
data_bp = Blueprint("data", __name__)


@export_bp.route("/export/csv", methods=["GET"])
def export_csv():
    try:
        current_app.logger.info("开始处理 CSV 导出请求...")

        output = io.StringIO()
        writer = csv.writer(output)

        # 写入表头
        writer.writerow(
            [
                "产品id",
                "用户id",
                "网址",
                "标题",
                "公司名称",
                "公司网址",
                "详情id",
                "其他型号",
                "自用型号",
                "价格",
                "库存",
                "详情图片网址",
                "本地图片路径",
                "下载时间",
            ]
        )

        # 构建基础查询
        base_query = (
            db.session.query(Product, ProductDetail, ImageRecord, User)
            .outerjoin(ProductDetail, Product.id == ProductDetail.product_id)
            .outerjoin(ImageRecord, ProductDetail.id == ImageRecord.detail_id)
            .outerjoin(User, Product.user_id == User.id)
        )

        # 根据用户角色过滤数据
        if current_user.is_authenticated and current_user.has_role("销售员"):
            results = base_query.filter(Product.user_id == current_user.id).all()
            current_app.logger.info(
                f"销售员 {current_user.username} 导出自己的产品，共 {len(results)} 条记录"
            )
        else:
            results = base_query.all()
            current_app.logger.info(f"管理员导出所有产品，共 {len(results)} 条记录")

        # 写入数据
        for index, (product, detail, image, user) in enumerate(results):
            try:
                new_img_url = (
                    f"http://127.0.0.1:1000/{detail.local_image_path}"
                    if detail and detail.local_image_path
                    else ""
                )
                new_img_url = new_img_url.replace("\\", "/")

                writer.writerow(
                    [
                        product.id,
                        user.name_cn if user else "",
                        product.url,
                        product.title,
                        product.company_name,
                        product.company_url,
                        detail.id if detail else "",
                        detail.other_model if detail else "",
                        detail.self_model if detail else "",
                        detail.price if detail else "",
                        detail.stock if detail else "",
                        detail.image_url if detail else "",
                        new_img_url,
                        image.download_time.strftime("%Y-%m-%d %H:%M:%S")
                        if image and image.download_time
                        else "",
                    ]
                )
            except Exception as row_err:
                current_app.logger.error(f"写入第 {index + 1} 行失败: {row_err}")
                current_app.logger.debug(traceback.format_exc())

        current_app.logger.info("CSV 写入完成，准备生成响应")

        response = Response(output.getvalue().encode("utf-8-sig"), mimetype="text/csv")
        response.headers.set(
            "Content-Disposition", "attachment", filename="exported_data.csv"
        )

        return response

    except Exception as e:
        current_app.logger.error(f"导出 CSV 时发生错误: {str(e)}")
        current_app.logger.debug(traceback.format_exc())

        return Response(f"导出失败，服务器错误: {str(e)}", status=500)


@data_bp.route("/collect_missing_prices", methods=["POST"])
def trigger_missing_price_collection():
    thread = Thread(target=collect_missing_prices_task)
    thread.start()
    return jsonify({"status": "started", "message": "后台已开始采集缺失价格数据"})
