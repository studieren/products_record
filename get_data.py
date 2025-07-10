# get_data.py
import re
from DrissionPage import Chromium
from lxml import etree
import time

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

    my_dict = {
        "url": url,
        "title": title,
        "company_name": company_name,
        "company_url": company_url,
        "products": products_list,
    }
    print(my_dict)
    return my_dict


if __name__ == "__main__":
    # url = "https://detail.1688.com/offer/800331861182.html?offerId=800331861182&spm=a260k.home2025.recommendpart.4"
    url = "https://detail.1688.com/offer/843708233884.html?_t=1750819202560&spm=a2615.7691456.co_0_0_wangpu_score_0_0_0_0_0_0_0000_0.0"
    # url = "https://detail.1688.com/offer/903597883974.html?spm=a26352.13672862.offerlist.9.78361e62i5i3RI"  # 多按钮，多尺寸，点击
    # get_page(url)
    ifvisit = True
    # ifvisit = False
    data = analysis_data(url, ifvisit)
    # print(data)

    # tab = down_data(url)
    # type_two(tab)

    # # 示例字典1
    # mydict1 = {
    #     "url": "https://detail.1688.com/offer/843708233884.html?_t=1750819202560&spm=a2615.7691456.co_0_0_wangpu_score_0_0_0_0_0_0_0000_0.0",
    #     "title": "欧美夸张复古玻璃胸针女气质优雅服装配饰高级感胸花金属饰品别针",
    #     "company_name": "义乌市唯曼饰品有限公司",
    #     "company_url": "https://ywwmsp888.1688.com/page/creditdetail.htm",
    #     "products": [
    #         {
    #             "img_url": "https://cbu01.alicdn.com/img/ibank/O1CN01uzzfdF1smZkEWi0Dm_!!2146215809-0-cib.jpg",
    #             "sku": "古金、深咖+浅咖+金黄亚克力（环保袋包）",
    #             "price": "5.7",
    #             "stock": "346",
    #         },
    #         {
    #             "img_url": "https://cbu01.alicdn.com/img/ibank/O1CN01TJzKuu1smZnEVtw0D_!!2146215809-0-cib.jpg",
    #             "sku": "古金、深紫+浅紫+白AB+紫色亚克力",
    #             "price": "5.7",
    #             "stock": "178",
    #         },
    #         {
    #             "img_url": "https://cbu01.alicdn.com/img/ibank/O1CN01Tvpx9c1smZnFKH75f_!!2146215809-0-cib.jpg",
    #             "sku": "古金、墨兰+灰钻+白AB+灰色亚克力",
    #             "price": "5.7",
    #             "stock": "147",
    #         },
    #     ],
    # }

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
