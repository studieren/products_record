import sqlite3
import csv
import os
import sys
from pathlib import Path


def export_tables_to_csv(db_path, output_dir="csv_backup"):
    """将 SQLite 数据库中的所有表导出为 CSV 文件"""
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            print("数据库中没有找到表！")
            return

        print(f"找到 {len(tables)} 个表，开始导出数据...")

        # 为每个表导出数据到 CSV
        for table in tables:
            table_name = table[0]

            # 获取表结构
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = [col[1] for col in cursor.fetchall()]

            # 查询表中的所有数据
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()

            # 写入 CSV 文件
            csv_path = os.path.join(output_dir, f"{table_name}.csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(columns)  # 写入表头
                writer.writerows(rows)  # 写入数据

            print(f"表 '{table_name}' 已导出到 {csv_path}")

        conn.close()
        print(f"所有表数据已成功导出到 {output_dir} 目录！")
        return True

    except Exception as e:
        print(f"导出数据时出错: {str(e)}")
        if conn:
            conn.close()
        return False


def create_new_database(db_path, sql_schema_file=None):
    """创建新的 SQLite 数据库"""
    try:
        # 如果数据库文件已存在，先删除
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"已删除原数据库文件: {db_path}")

        # 创建新的空数据库
        conn = sqlite3.connect(db_path)
        conn.close()
        print(f"新数据库已创建: {db_path}")

        # 如果提供了 SQL 模式文件，则执行它
        if sql_schema_file and os.path.exists(sql_schema_file):
            conn = sqlite3.connect(db_path)
            with open(sql_schema_file, "r") as f:
                sql = f.read()
                conn.executescript(sql)
            conn.close()
            print(f"已从 {sql_schema_file} 导入表结构")

        return True

    except Exception as e:
        print(f"创建数据库时出错: {str(e)}")
        return False


def import_csv_to_tables(db_path, csv_dir="csv_backup"):
    """从 CSV 文件导入数据到 SQLite 表"""
    if not os.path.exists(csv_dir):
        print(f"错误: CSV 目录 '{csv_dir}' 不存在！")
        return False

    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 获取所有 CSV 文件
        csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]

        if not csv_files:
            print(f"在目录 '{csv_dir}' 中没有找到 CSV 文件！")
            return False

        print(f"找到 {len(csv_files)} 个 CSV 文件，开始导入数据...")

        # 为每个 CSV 文件导入数据到对应表
        for csv_file in csv_files:
            table_name = os.path.splitext(csv_file)[0]
            csv_path = os.path.join(csv_dir, csv_file)

            # 检查表是否存在
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            if not cursor.fetchone():
                print(f"警告: 表 '{table_name}' 不存在，跳过导入")
                continue

            # 读取 CSV 文件
            with open(csv_path, "r", newline="", encoding="utf-8") as csvfile:
                reader = csv.reader(csvfile)
                headers = next(reader)  # 获取表头

                # 构建 INSERT 语句
                placeholders = ", ".join(["?"] * len(headers))
                insert_query = f"INSERT INTO {table_name} ({', '.join(headers)}) VALUES ({placeholders})"

                # 逐行导入数据
                row_count = 0
                for row in reader:
                    try:
                        # 处理 NULL 值
                        processed_row = [None if val == "" else val for val in row]
                        cursor.execute(insert_query, processed_row)
                        row_count += 1
                    except sqlite3.Error as e:
                        print(
                            f"导入表 '{table_name}' 的第 {row_count + 1} 行时出错: {str(e)}"
                        )
                        # 可以选择继续导入其他行，或中断导入
                        # conn.rollback()
                        # return False

                conn.commit()
                print(f"已成功将 {row_count} 行数据导入到表 '{table_name}'")

        conn.close()
        print(f"所有 CSV 文件已成功导入到数据库！")
        return True

    except Exception as e:
        print(f"导入数据时出错: {str(e)}")
        if conn:
            conn.rollback()
            conn.close()
        return False


if __name__ == "__main__":
    # 配置参数
    DB_PATH = r"D:\pyproject\products_record\instance\data.db"  # 替换为你的数据库路径
    CSV_DIR = "csv_backup"  # CSV 文件目录
    SQL_SCHEMA_FILE = "schema.sql"  # 表结构 SQL 文件（可选）

    # 操作菜单
    print("请选择要执行的操作:")
    print("1. 导出数据库到 CSV")
    print("2. 创建新数据库")
    print("3. 从 CSV 导入数据到数据库")
    print("4. 执行全套操作 (导出 -> 创建 -> 导入)")

    choice = input("请输入选项 (1-4): ").strip()

    if choice == "1":
        export_tables_to_csv(DB_PATH, CSV_DIR)
    elif choice == "2":
        create_new_database(DB_PATH, SQL_SCHEMA_FILE)
    elif choice == "3":
        import_csv_to_tables(DB_PATH, CSV_DIR)
    elif choice == "4":
        if export_tables_to_csv(DB_PATH, CSV_DIR):
            if create_new_database(DB_PATH, SQL_SCHEMA_FILE):
                import_csv_to_tables(DB_PATH, CSV_DIR)
    else:
        print("无效的选项！")
