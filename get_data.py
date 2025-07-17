# get_data.py
import re
from DrissionPage import Chromium
from lxml import etree
import time
from decimal import Decimal, ROUND_HALF_UP

# 全局浏览器实例
_browser = None
page_path = "temp.html"


def get_browser():
    global _browser
    if _browser is None:
        _browser = Chromium()
    return _browser


def get_page(url, ifvisit):
    tab = get_browser().latest_tab
    # 是否访问网址
    if ifvisit:
        tab.get(url)
    return tab


# def get_page(url):
#     tab = Chromium().latest_tab
#     tab.get(url)
#     return tab


def down_data(url, ifvisit=True):
    tab = get_page(url, ifvisit)

    company_xpath = (
        'x://div[@id="shopNavigation"]//a[contains(@class,"company-name")]/h1'
    )

    tab.wait.ele_displayed(company_xpath, timeout=10)
    # html_content = tab.html
    return tab
    # with open(page_path, "w", encoding="utf-8") as f:
    #     f.write(html_content)
    # with open(page_path, "r", encoding="utf-8") as fp:
    #     return fp.read()


def images_url_replace(img_url):
    img_url = img_url.strip()
    img_url = img_url.replace("_sum.jpg", "")
    return img_url


def price_replace(price):
    price = price.strip()
    price = price.replace("¥", "")
    return price


def stock_replace(my_str: str):
    re_pattern = r"\d{1,12}"
    match = re.search(re_pattern, my_str)
    if match:
        return match.group(0)
    else:
        return "0"


def type_one(html_text):
    line_xpath = '//div[contains(@class, "expand-view-item")]'

    img_url_xpath = ".//img/@src"
    sku_xpath = './/span[@class="item-label"]/text()'
    price_xpath = "./span[1]/text()"
    stock_xpath = "./span[2]/text()"

    # 1. 访问网址
    # 2. 获取标题，公司名称，公司网址
    # 3. 获取SKU列
    # 4. 每列获取图片网址，名称，价格

    line_list = html_text.xpath(line_xpath)

    products_list = []
    for line in line_list:
        try:
            img_url = line.xpath(img_url_xpath)[0]
            img_url = images_url_replace(img_url)
        except:
            img_url = "原链接无图"

        try:
            sku = line.xpath(sku_xpath)[0]
        except:
            sku = ""

        try:
            price = line.xpath(price_xpath)[0]
            price = price_replace(price)
        except:
            price = "0"

        try:
            stock = line.xpath(stock_xpath)[0]
            stock_int = stock_replace(stock)
        except:
            stock_int = 0

        products_list.append(
            {"img_url": img_url, "sku": sku, "price": price, "stock": stock_int}
        )

    return products_list


def type_two(tab):
    button_xpath = 'x://button[contains(@class,"sku-filter-button")]'
    line_xpath = 'x://div[@id="skuSelection"]//div[@class="expand-view-item v-flex"]'
    img_xpath = "x:.//img"
    name_xpath = "x:.//span"
    size_xpath = "x:./div/span"
    price_xpath = "x:./span[1]"
    stock_xpath = "x:./span[2]"
    button_list = tab.eles(button_xpath)
    products_list = []
    for button in button_list:
        button.click()
        line_list = tab.eles(line_xpath)
        for line in line_list:
            img_url = button.ele(img_xpath).attr("src")
            img_url = images_url_replace(img_url)
            name = button.ele(name_xpath).text
            size = line.ele(size_xpath).text
            price = line.ele(price_xpath).text
            price = price_replace(price)
            stock = line.ele(stock_xpath).text
            stock = stock_replace(stock)
            sku = f"{name}+{size}"
            products_list.append(
                {"img_url": img_url, "sku": sku, "price": price, "stock": stock}
            )

            # print(img_url, sku, price, stock)
        # print("-" * 60)
        time.sleep(0.3)
    return products_list


# def parse_price_fragments(fragments):
#     prices = []
#     current = []
#     for part in fragments:
#         if part.strip() == "¥":
#             if current:
#                 prices.append(current)
#             current = []
#         else:
#             current.append(part)
#     if current:
#         prices.append(current)
#     return [float("".join(p)) for p in prices]


# def parse_quantity_range(qty_text):
#     if "起批" in qty_text:
#         min_qty = int(re.search(r"\d+", qty_text).group())
#         return {"min": min_qty, "max": None}
#     elif "≥" in qty_text:
#         min_qty = int(re.search(r"\d+", qty_text).group())
#         return {"min": min_qty, "max": None}
#     elif "-" in qty_text:
#         nums = list(map(int, re.findall(r"\d+", qty_text)))
#         if len(nums) == 2:
#             return {"min": nums[0], "max": nums[1]}
#     return {"min": None, "max": None}


# def get_price(html_text):
#     if not html_text:
#         return None

#     html_content = etree.HTML(html_text)

#     price_xpath1 = '//div[contains(@class,"range-price")]/span/text()'
#     price_xpath2 = '//div[@class="price-component step-price"]//div[@class="price-info currency"]//span/text()'
#     price_fragments1 = html_content.xpath(price_xpath1)
#     if price_fragments1:
#         if price_fragments1[0] == "券后":
#             price_fragments1 = html_content.xpath(price_xpath2)
#     price_list = parse_price_fragments(price_fragments1)

#     quantity_xpath = '//div[contains(@class,"price-component")]/p/text()'
#     quantity_list = html_content.xpath(quantity_xpath)
#     if quantity_list:
#         print(quantity_list)
#     print("price_list")
#     print(price_list)
#     print("quantity_list")
#     print(quantity_list)
#     if len(price_list) != len(quantity_list):
#         price = price_list[0]
#         quantity = quantity_list[0]
#         if quantity:
#             match = re.search(r"\d{1,8}", quantity)
#             print(quantity)
#             try:
#                 if match:
#                     quantity = match.group(0)
#                 else:
#                     quantity = 1
#             except:
#                 quantity = 1

#         # print(price)
#         # print(quantity)

#         wholesale_prices = [{"min": quantity, "max": None, "price": price}]
#         print(wholesale_prices)
#         # 测试示例 [{'min': 1, 'max': None, 'price': 6.2}]
#         return wholesale_prices

#     # Step 1: 初步配对
#     wholesale_prices = []

#     for qty_text, price in zip(quantity_list, price_list):
#         q_range = parse_quantity_range(qty_text)
#         q_range["price"] = price

#         wholesale_prices.append(q_range)

#     # Step 2: 自动填充 max（除了最后一个）
#     for i in range(len(wholesale_prices) - 1):
#         if wholesale_prices[i]["max"] is None:
#             wholesale_prices[i]["max"] = wholesale_prices[i + 1]["min"] - 1

#     print(wholesale_prices)

#     # 测试示例 [{'min': 1, 'max': 11, 'price': 5.7}, {'min': 12, 'max': 24, 'price': 5.6}, {'min': 24, 'max': None, 'price': 5.5}]

#     return wholesale_prices


def read_html_file(file_path="temp.html"):
    """读取HTML文件内容"""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        print(f"错误：找不到文件 {file_path}")
        return None
    except Exception as e:
        print(f"读取文件时发生错误：{e}")
        return None


def extract_price_text(element):
    """从价格元素中提取价格文本"""
    price_parts = element.xpath('.//div[@class="price-info currency"]/span/text()')
    return "".join(price_parts[1:])  # 跳过货币符号


def parse_quantity_text(quantity_text):
    """解析数量文本，返回最小和最大数量"""
    if not quantity_text:
        return 1, None

    # 处理"1个起批"格式
    match_single = re.match(r"(\d+)\s*个?\s*起批", quantity_text)
    if match_single:
        return int(match_single.group(1)), None

    # 处理"≥24个"格式
    match_min = re.match(r"≥\s*(\d+)\s*个?", quantity_text)
    if match_min:
        return int(match_min.group(1)), None

    # 处理"12-24个"格式
    match_range = re.match(r"(\d+)\s*-\s*(\d+)\s*个?", quantity_text)
    if match_range:
        return int(match_range.group(1)), int(match_range.group(2))

    # 默认返回
    return 1, None


def process_step_prices(step_price_div):
    """处理阶梯价格"""
    price_comps = step_price_div.xpath('.//div[@class="price-comp"]')
    price_data = []

    for comp in price_comps:
        price_text = extract_price_text(comp)
        price = Decimal(price_text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        quantity_text = comp.xpath(".//p/span/text()")
        quantity_text = quantity_text[0] if quantity_text else ""

        min_qty, max_qty = parse_quantity_text(quantity_text)
        price_data.append({"min": min_qty, "max": max_qty, "price": price})

    # 确保每个阶梯的 max = 下一个阶梯的 min - 1
    for i in range(len(price_data) - 1):
        price_data[i]["max"] = price_data[i + 1]["min"] - 1  # 关键修改

    return price_data


def process_range_price(range_price_div):
    """处理范围价格"""
    price_comps = range_price_div.xpath('.//div[@class="price-comp"]')
    prices = []

    for comp in price_comps:
        price_text = extract_price_text(comp)
        if price_text:
            # 使用Decimal处理价格
            prices.append(
                Decimal(price_text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )

    if not prices:
        return []

    # 如果有多个价格，返回最高价格
    max_price = max(prices)

    # 提取起批数量
    quantity_text = range_price_div.xpath('.//p[contains(text(), "起批")]/text()')
    quantity_text = quantity_text[0].strip() if quantity_text else ""

    min_qty, _ = parse_quantity_text(quantity_text)

    return [{"min": min_qty, "max": None, "price": max_price}]


def extract_prices(html_content):
    """从HTML内容中提取价格信息"""
    if not html_content:
        return []

    tree = etree.HTML(html_content)
    all_products = []

    # 查找所有价格模块
    price_modules = tree.xpath('//div[@id="mainPrice"]')

    for module in price_modules:
        # 检查是否为阶梯价
        step_price_div = module.xpath('.//div[contains(@class, "step-price")]')

        if step_price_div:
            # 处理阶梯价
            product_prices = process_step_prices(step_price_div[0])
        else:
            # 处理非阶梯价（范围价格）
            range_price_div = module.xpath('.//div[contains(@class, "range-price")]')

            if range_price_div:
                class_name = range_price_div[0].get("class")
                span_ele = module.xpath('//span[@class="label-name"]')

                print(class_name)
                print(span_ele[0].text)
                product_prices = process_range_price(range_price_div[0])
            else:
                product_prices = []

        if product_prices:
            all_products = product_prices

    return all_products


def analysis_data(url, ifvisit=True):
    tab = down_data(url, ifvisit)
    type_xpath = '//div[@id="skuSelection"]//div[@class="feature-item"]'
    html_text = etree.HTML(tab.html)
    type_list = html_text.xpath(type_xpath)

    company_xpath = (
        '//div[@id="shopNavigation"]//a[contains(@class,"company-name")]/h1/text()'
    )
    company_url_xpath = (
        '//div[@id="shopNavigation"]//a[contains(@class,"company-name")]/@href'
    )
    title_list = html_text.xpath("//title/text()")
    title = ""
    if title_list:
        title = title_list[0]
        title = title.strip()
    if title:
        title = title.replace(" - 阿里巴巴", "")
    company_name = html_text.xpath(company_xpath)
    company_url = html_text.xpath(company_url_xpath)
    if company_name:
        company_name = company_name[0]
    if company_url:
        company_url = company_url[0]

    if len(type_list) == 1:
        products_list = type_one(html_text)
    else:
        products_list = type_two(tab)

    price_xpath = 'x://div[@id="mainPrice"]'
    price_html = tab.ele(price_xpath).html
    price_data = extract_prices(price_html)

    my_dict = {
        "url": url,
        "title": title,
        "company_name": company_name,
        "company_url": company_url,
        "products": products_list,
        "price_data": price_data,
    }
    print(my_dict)
    return my_dict


if __name__ == "__main__":
    # url = "https://detail.1688.com/offer/800331861182.html?offerId=800331861182&spm=a260k.home2025.recommendpart.4"
    # url = "https://detail.1688.com/offer/843708233884.html?_t=1750819202560&spm=a2615.7691456.co_0_0_wangpu_score_0_0_0_0_0_0_0000_0.0"
    url = "https://detail.1688.com/offer/903597883974.html?spm=a26352.13672862.offerlist.9.78361e62i5i3RI"  # 多按钮，多尺寸，点击
    # url=''
    # get_page(url)
    # ifvisit = True
    ifvisit = False

    # 有效的函数
    data = analysis_data(url, ifvisit)

    # 从文件读取HTML内容
    # html_content = read_html_file()
    # formatted_prices = extract_prices(html_content)
    # print(formatted_prices)

    # print(data)

    # tab = down_data(url)
    # type_two(tab)

    # # 示例字典1
    mydict1 = {
        "url": "https://detail.1688.com/offer/843708233884.html?_t=1750819202560&spm=a2615.7691456.co_0_0_wangpu_score_0_0_0_0_0_0_0000_0.0",
        "title": "欧美夸张复古玻璃胸针女气质优雅服装配饰高级感胸花金属饰品别针",
        "company_name": "义乌市唯曼饰品有限公司",
        "company_url": "https://ywwmsp888.1688.com/page/creditdetail.htm",
        "products": [
            {
                "img_url": "https://cbu01.alicdn.com/img/ibank/O1CN01uzzfdF1smZkEWi0Dm_!!2146215809-0-cib.jpg",
                "sku": "古金、深咖+浅咖+金黄亚克力（环保袋包）",
                "price": "5.5",
                "stock": "333",
            },
            {
                "img_url": "https://cbu01.alicdn.com/img/ibank/O1CN01TJzKuu1smZnEVtw0D_!!2146215809-0-cib.jpg",
                "sku": "古金、深紫+浅紫+白AB+紫色亚克力",
                "price": "5.5",
                "stock": "172",
            },
        ],
        "price_data": [
            {"min": 1, "max": 11, "price": Decimal("5.70")},
            {"min": 12, "max": 23, "price": Decimal("5.60")},
            {"min": 24, "max": None, "price": Decimal("5.50")},
        ],
    }

    # # 示例字典2
    # mydict2 = {
    #     "url": "https://detail.1688.com/offer/903597883974.html?spm=a26352.13672862.offerlist.9.78361e62i5i3RI",
    #     "title": "简约立体中空相框diy摆台框架干花作品创意手工空白标本画框装饰",
    #     "company_name": "东阳市静美工艺品有限公司",
    #     "company_url": "https://shop71i962493j338.1688.com/page/creditdetail.htm",
    #     "products": [
    #         {
    #             "img_url": "https://cbu01.alicdn.com/img/ibank/O1CN01xMbJ721zyDAAXbxVE_!!2200730886782-0-cib.jpg",
    #             "sku": "原木色中空3厘米【相框+底纸】+6寸摆台：内径10.2*15.2cm",
    #             "price": "2.8",
    #             "stock": "693",
    #         },
    #         {
    #             "img_url": "https://cbu01.alicdn.com/img/ibank/O1CN01xMbJ721zyDAAXbxVE_!!2200730886782-0-cib.jpg",
    #             "sku": "原木色中空3厘米【相框+底纸】+7寸摆台：内径12.7*17.8cm",
    #             "price": "3.7",
    #             "stock": "395",
    #         },
    #     ],
    # }
