from flask import current_app, Blueprint, Response
import io, csv
from extensions import db
from models import Main, Details, ImageRecord
import traceback

export_bp = Blueprint("export", __name__)


@export_bp.route("/export/csv", methods=["GET"])
def export_csv():
    try:
        current_app.logger.info("开始处理 CSV 导出请求...")

        output = io.StringIO()
        writer = csv.writer(output)

        # 写入表头
        writer.writerow(
            [
                "Main ID",
                "URL",
                "Title",
                "Company Name",
                "Company URL",
                "Detail ID",
                "Other Model",
                "Self Model",
                "Price",
                "Stock",
                "Detail Image URL",
                "Local Image Path",
                "ImageRecord ID",
                "Image URL",
                "Local Path",
                "Download Time",
            ]
        )

        # 执行联表查询
        results = (
            db.session.query(Main, Details, ImageRecord)
            .outerjoin(Details, Main.id == Details.main_id)
            .outerjoin(ImageRecord, Details.id == ImageRecord.details_id)
            .all()
        )

        current_app.logger.info(f"查询返回 {len(results)} 条记录")

        # 写入数据
        for index, (main, detail, image) in enumerate(results):
            try:
                writer.writerow(
                    [
                        main.id,
                        main.url,
                        main.title,
                        main.company_name,
                        main.company_url,
                        detail.id if detail else "",
                        detail.other_model if detail else "",
                        detail.self_model if detail else "",
                        detail.price if detail else "",
                        detail.stock if detail else "",
                        detail.image_url if detail else "",
                        detail.local_image_path if detail else "",
                        image.id if image else "",
                        image.image_url if image else "",
                        image.local_path if image else "",
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

        # 返回错误信息供调试使用（生产环境中建议隐藏）
        return Response(f"导出失败，服务器错误: {str(e)}", status=500)
