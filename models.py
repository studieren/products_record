# models.py
from extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# ✅ 中间表定义（必须放在模型类之前）
user_permissions = db.Table(
    "user_permissions",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column(
        "permission_id", db.Integer, db.ForeignKey("permissions.id"), primary_key=True
    ),
)

user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
)

role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
    db.Column(
        "permission_id", db.Integer, db.ForeignKey("permissions.id"), primary_key=True
    ),
)


class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    codename = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100), nullable=False)  # 如 'product', 'user'

    # 反向关联：拥有此权限的组和用户
    roles = db.relationship(
        "Role", secondary="role_permissions", back_populates="permissions"
    )
    users = db.relationship(
        "User", secondary="user_permissions", back_populates="permissions"
    )


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    permissions = db.relationship(
        "Permission", secondary="role_permissions", back_populates="roles"
    )
    users = db.relationship("User", secondary="user_roles", back_populates="roles")


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(
        db.String(100), unique=True, nullable=False
    )  # 登录时用到的用户名
    password_hash = db.Column(db.String(128), nullable=False)  # 密码hash值
    name_cn = db.Column(db.String(100))  # 用户的真实姓名
    name_en = db.Column(db.String(100))  # 用户的英文名
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    wechat = db.Column(db.String(255))
    whatsapp = db.Column(db.String(255))
    facebook = db.Column(db.String(255))
    instagram = db.Column(db.String(255))
    tiktok = db.Column(db.String(255))
    twitter = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    # 关联组和权限
    roles = db.relationship("Role", secondary="user_roles", back_populates="users")
    permissions = db.relationship(
        "Permission", secondary="user_permissions", back_populates="users"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_permission(self, codename):
        # 检查直接分配的权限
        if any(p.codename == codename for p in self.permissions):
            return True

        # 检查角色继承的权限
        for role in self.roles:
            if any(p.codename == codename for p in role.permissions):
                return True

        return False

    def has_role(self, role_name):
        return any(role.name == role_name for role in self.roles)


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    url = db.Column(db.String(255))
    title = db.Column(db.String(255))
    company_name = db.Column(db.String(255))
    company_url = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.now())

    # 产品详情（一对多关系）
    details = db.relationship(
        "ProductDetail", backref="product", lazy=True, cascade="all, delete-orphan"
    )
    user = db.relationship("User", backref="products")


class ProductDetail(db.Model):
    __tablename__ = "product_details"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    other_model = db.Column(db.String(255))  # 其他型号
    self_model = db.Column(db.String(255))  # 自身型号
    price = db.Column(db.Float)
    image_url = db.Column(db.String(255))
    stock = db.Column(db.Numeric(10, 3))
    local_image_path = db.Column(db.String(255), nullable=True)

    # 图片记录（一对多关系）
    image_records = db.relationship(
        "ImageRecord", backref="detail", lazy=True, cascade="all, delete-orphan"
    )

    # 批发价格（一对多关系）
    wholesale_prices = db.relationship(
        "WholesalePrice", backref="detail", lazy=True, cascade="all, delete-orphan"
    )


class WholesalePrice(db.Model):
    __tablename__ = "wholesale_prices"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    detail_id = db.Column(
        db.Integer, db.ForeignKey("product_details.id"), nullable=False
    )
    min_quantity = db.Column(db.Integer, nullable=False)  # 最小起订量
    max_quantity = db.Column(db.Integer)  # 最大起订量（None表示无上限）
    price = db.Column(
        db.String(20), nullable=False
    )  # 价格（支持字符串格式，如带货币符号）

    __table_args__ = (
        db.UniqueConstraint("detail_id", "min_quantity", name="uq_detail_min_quantity"),
    )


class ImageRecord(db.Model):
    __tablename__ = "image_records"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    detail_id = db.Column(
        db.Integer, db.ForeignKey("product_details.id"), nullable=False
    )
    image_url = db.Column(db.String(255), nullable=False)
    local_path = db.Column(db.String(255), nullable=False)
    download_time = db.Column(db.DateTime, default=db.func.current_timestamp())


class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    name_cn = db.Column(db.String(100), nullable=False)
    name_en = db.Column(db.String(100), nullable=False)
    address_cn = db.Column(db.String(255), nullable=False)
    address_en = db.Column(db.String(255), nullable=False)
    website = db.Column(db.String(255), nullable=False)
