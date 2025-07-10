import os
import secrets


def generate_secret_key(length=64):
    """生成指定长度的安全随机密钥"""
    # 方法1: 使用secrets.token_hex (推荐)
    return secrets.token_hex(length // 2)  # 转换为字节长度


def generate_secret_key_alternative(length=64):
    """备选方法: 使用os.urandom"""
    return os.urandom(length).hex()


def generate_flask_config():
    """生成完整的Flask配置文件"""
    secret_key = generate_secret_key()
    config = f"""
# Flask 应用配置
SECRET_KEY = '{secret_key}'
SQLALCHEMY_DATABASE_URI = 'sqlite:///your_database.db'
SQLALCHEMY_TRACK_MODIFICATIONS = False
DEBUG = True  # 开发环境开启，生产环境请关闭
    """.strip()

    return config


if __name__ == "__main__":
    # 生成并打印密钥
    secret_key = generate_secret_key()
    print(f"生成的安全密钥: \n{secret_key}\n")

    # 生成完整配置示例
    config = generate_flask_config()
    print("建议的配置文件内容:")
    print(config)

    # 保存到文件
    with open("key.txt", "w", encoding="utf-8") as f:
        f.write(config)
    print("\n已保存到 config.py 文件")
