# models.py
from extensions import db


class Main(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    url = db.Column(db.String(255))
    title = db.Column(db.String(255))
    company_name = db.Column(db.String(255))
    company_url = db.Column(db.String(255))

    details = db.relationship(
        "Details", backref="main", lazy=True, cascade="all, delete-orphan"
    )


class Details(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    main_id = db.Column(db.Integer, db.ForeignKey("main.id"), nullable=False)
    other_model = db.Column(db.String(255))
    self_model = db.Column(db.String(255))
    price = db.Column(db.Float)
    image_url = db.Column(db.String(255))
    stock = db.Column(db.Numeric(10, 3))
    image_records = db.relationship(
        "ImageRecord", backref="details", lazy=True, cascade="all, delete-orphan"
    )
    local_image_path = db.Column(db.String(255), nullable=True)


class ImageRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    details_id = db.Column(db.Integer, db.ForeignKey("details.id"), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    local_path = db.Column(db.String(255), nullable=False)
    download_time = db.Column(db.DateTime, default=db.func.current_timestamp())


# 公司信息模型
class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    name_cn = db.Column(db.String(100), nullable=False)
    name_en = db.Column(db.String(100), nullable=False)
    address_cn = db.Column(db.String(255), nullable=False)
    address_en = db.Column(db.String(255), nullable=False)
    website = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f"<Company {self.name_en}>"


# 销售员信息模型
class Salesperson(db.Model):
    __tablename__ = "salespersons"

    id = db.Column(db.Integer, primary_key=True)
    name_cn = db.Column(db.String(100), nullable=False)
    name_en = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    wechat = db.Column(db.String(255), nullable=True)
    whatsapp = db.Column(db.String(255), nullable=True)
    facebook = db.Column(db.String(255), nullable=True)
    instagram = db.Column(db.String(255), nullable=True)
    tiktok = db.Column(db.String(255), nullable=True)
    twitter = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<Salesperson {self.name_en}>"
