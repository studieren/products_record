from app import app  # Flask 实例
from extensions import db
from models import Permission, Role, User

# 示例权限
default_permissions = [
    {"codename": "view_user", "name": "查看用户", "content_type": "user"},
    {"codename": "add_user", "name": "添加用户", "content_type": "user"},
    {"codename": "edit_user", "name": "编辑用户", "content_type": "user"},
    {"codename": "delete_user", "name": "删除用户", "content_type": "user"},
    {"codename": "view_product", "name": "查看产品", "content_type": "product"},
    {"codename": "add_product", "name": "添加产品", "content_type": "product"},
    {"codename": "delete_product", "name": "删除产品", "content_type": "product"},
]

# 角色
default_roles = ["超级管理员", "销售员"]


def init_db():
    with app.app_context():
        print("🔄 正在重建数据库表...")
        db.drop_all()
        db.create_all()

        print("✅ 正在插入默认权限...")
        for perm in default_permissions:
            db.session.add(
                Permission(
                    codename=perm["codename"],
                    name=perm["name"],
                    content_type=perm["content_type"],
                )
            )
        db.session.commit()

        print("✅ 正在创建默认角色...")
        superadmin_role = Role(name="超级管理员")
        salesman_role = Role(name="销售员")
        db.session.add_all([superadmin_role, salesman_role])
        db.session.commit()

        print("🔗 分配权限给超级管理员...")
        all_permissions = Permission.query.all()
        superadmin_role.permissions = all_permissions
        db.session.commit()

        print("👤 创建超级管理员用户（admin）...")
        admin = User(
            username="admin",
            name_cn="张三",  # 用户真实姓名
            name_en="Zhang San",
            email="admin@example.com",
            is_active=True,
        )
        admin.set_password("admin123")
        admin.roles.append(superadmin_role)  # 分配超级管理员角色
        db.session.add(admin)
        db.session.commit()

        print("🎉 初始化完成！默认账号：admin，密码：admin123")


def data_init():
    with app.app_context():
        db.create_all()
        # 添加权限
        permissions = [
            ("add_product", "添加产品", "product"),
            ("edit_product", "编辑产品", "product"),
            ("delete_product", "删除产品", "product"),
            ("add_product_detail", "添加产品详情", "product_detail"),
            ("edit_product_detail", "编辑产品详情", "product_detail"),
            ("delete_product_detail", "删除产品详情", "product_detail"),
            ("download_images", "下载图片", "image"),
            ("download_all_images", "批量下载图片", "image"),
            ("add_company", "添加公司", "company"),
            ("add_salesperson", "添加销售员", "user"),
            ("edit_salesperson", "编辑销售员", "user"),
        ]
        for codename, name, content_type in permissions:
            if not Permission.query.filter_by(codename=codename).first():
                db.session.add(
                    Permission(codename=codename, name=name, content_type=content_type)
                )
        db.session.commit()


if __name__ == "__main__":
    # init_db()
    data_init()
