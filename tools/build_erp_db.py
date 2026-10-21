# -*- coding: utf-8 -*-
"""
ERP 示例库构建脚本。

一条命令完成：建库 -> 建表 -> 生成数据 -> 批量导入 -> 导出 sql/02_seed_data.sql

    python tools/build_erp_db.py --rebuild      # 重建结构并重新生成数据（默认）
    python tools/build_erp_db.py --keep-schema  # 保留现有表结构，只重灌数据

数据规模（约 1.2 万行，固定随机种子，每次生成结果完全一致）：
    departments 8 / employees 60 / warehouses 6 / categories 24
    suppliers 60 / customers 300 / products 400 / inventory ~1600
    purchase_orders 700 (+ ~1750 明细) / sales_orders 2400 (+ ~7200 明细)

时间跨度：2024-01-01 ~ 2026-09-09（含季节波动），便于做趋势 / 同比 / Top-N 类图表。
"""

from __future__ import annotations

import argparse
import datetime as dt
import random
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db as dbm  # noqa: E402
from config import SEED  # noqa: E402

SQL_DIR = ROOT / "sql"
SEED_FILE = SQL_DIR / "02_seed_data.sql"

# ============================================================ 全局时间设置
SNAPSHOT_DATE = dt.date(2026, 9, 10)  # 数据快照日（"今天"）
START_DATE = dt.date(2024, 1, 1)  # 业务数据起始
END_DATE = dt.date(2026, 9, 9)  # 业务数据截止
CUSTOMER_START = dt.date(2020, 1, 1)
PRODUCT_START = dt.date(2022, 1, 1)

# 月度权重：模拟春节、618、双 11 等销售旺季
MONTH_WEIGHT = {
    1: 1.15,
    2: 0.80,
    3: 1.10,
    4: 1.00,
    5: 1.05,
    6: 1.30,
    7: 0.95,
    8: 1.00,
    9: 1.10,
    10: 1.05,
    11: 1.35,
    12: 1.20,
}

# ================================================================ 基础语料
CITIES = [
    "北京",
    "上海",
    "广州",
    "深圳",
    "杭州",
    "成都",
    "武汉",
    "西安",
    "南京",
    "重庆",
    "苏州",
    "天津",
    "长沙",
    "青岛",
    "郑州",
    "沈阳",
    "合肥",
    "福州",
    "济南",
    "东莞",
]

SURNAMES = list(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛段雷侯龙史陶黎贺顾毛郝龚邵万钱严戴莫孔向汤"
)

MALE_GIVEN = [
    "伟",
    "强",
    "磊",
    "军",
    "洋",
    "勇",
    "杰",
    "涛",
    "明",
    "超",
    "刚",
    "鹏",
    "文涛",
    "晓东",
    "志强",
    "建国",
    "建华",
    "浩然",
    "子豪",
    "宇轩",
    "思远",
    "嘉伟",
    "俊杰",
    "天佑",
    "泽宇",
    "宇航",
    "晨光",
    "博文",
    "立辉",
    "国庆",
]

FEMALE_GIVEN = [
    "芳",
    "娜",
    "敏",
    "静",
    "丽",
    "艳",
    "娟",
    "霞",
    "萍",
    "雪梅",
    "海燕",
    "雨欣",
    "梦琪",
    "嘉怡",
    "梓涵",
    "佳怡",
    "思琪",
    "婉婷",
    "静怡",
    "欣然",
    "诗涵",
    "晓燕",
    "丽娟",
    "秀英",
    "桂英",
    "雅琴",
    "若曦",
]

INDUSTRIES = [
    "制造业",
    "零售业",
    "批发业",
    "信息技术",
    "建筑业",
    "医疗健康",
    "教育培训",
    "物流运输",
    "餐饮服务",
    "金融保险",
    "电力能源",
    "政府机构",
]

COMPANY_WORDS = [
    "华信",
    "恒通",
    "鑫源",
    "中泰",
    "宏远",
    "瑞丰",
    "嘉和",
    "安捷",
    "联创",
    "凯瑞",
    "天润",
    "金辉",
    "卓越",
    "博纳",
    "万邦",
    "骏达",
    "远东",
    "众诚",
    "兴华",
    "明德",
    "泰和",
    "正邦",
    "润泽",
    "广盛",
    "德昌",
    "合众",
    "易通",
    "远洋",
    "海纳",
    "翔宇",
    "中科",
    "启明",
    "智联",
    "腾飞",
    "同心",
]

COMPANY_MIDS = [
    "科技",
    "贸易",
    "实业",
    "电子",
    "商贸",
    "智能",
    "物流",
    "建材",
    "食品",
    "机械",
    "医药",
    "能源",
    "纺织",
    "家居",
    "供应链",
    "供应链管理",
]

COMPANY_SUFFIX = ["有限公司", "股份有限公司", "有限责任公司"]

SUPPLIER_MIDS = [
    "电子",
    "材料",
    "制造",
    "供应链",
    "五金",
    "包装",
    "塑胶",
    "纺织",
    "化工",
    "食品",
    "机电",
    "元器件",
]

# ------------------------------------------------------------ 部门 / 岗位规划
# (部门名, 城市, [(岗位, 人数, 月薪区间)])
DEPT_PLAN = [
    (
        "总经办",
        "北京",
        [
            ("总经理", 1, (38000, 45000)),
            ("副总经理", 1, (28000, 34000)),
            ("总经理助理", 1, (9000, 12000)),
        ],
    ),
    (
        "销售部",
        "北京",
        [
            ("销售总监", 1, (22000, 28000)),
            ("销售经理", 3, (13000, 18000)),
            ("高级销售代表", 6, (9000, 12000)),
            ("销售代表", 10, (6000, 8500)),
        ],
    ),
    (
        "采购部",
        "上海",
        [
            ("采购总监", 1, (20000, 26000)),
            ("采购经理", 2, (13000, 17000)),
            ("采购专员", 6, (6500, 9500)),
        ],
    ),
    (
        "仓储物流部",
        "上海",
        [
            ("仓储物流经理", 1, (16000, 21000)),
            ("仓储主管", 2, (10000, 13000)),
            ("库管员", 5, (5500, 7500)),
        ],
    ),
    (
        "财务部",
        "北京",
        [
            ("财务总监", 1, (22000, 30000)),
            ("会计", 3, (8000, 12000)),
            ("出纳", 2, (5500, 7500)),
        ],
    ),
    (
        "人力资源部",
        "北京",
        [
            ("人力资源经理", 1, (15000, 20000)),
            ("招聘专员", 2, (7000, 10000)),
            ("薪酬专员", 2, (7500, 10500)),
        ],
    ),
    (
        "信息技术部",
        "深圳",
        [
            ("IT经理", 1, (20000, 26000)),
            ("系统管理员", 2, (11000, 15000)),
            ("开发工程师", 2, (13000, 18000)),
        ],
    ),
    (
        "市场部",
        "广州",
        [
            ("市场经理", 1, (15000, 20000)),
            ("市场专员", 2, (7000, 10000)),
            ("品牌策划", 1, (9000, 13000)),
        ],
    ),
]

WAREHOUSES = [
    ("北京中心仓", "北京"),
    ("上海仓", "上海"),
    ("广州仓", "广州"),
    ("成都仓", "成都"),
    ("武汉仓", "武汉"),
    ("西安仓", "西安"),
]

# ------------------------------------------------------- 商品分类（一级/二级）
CATEGORY_TREE = {
    "电子数码": ["手机通讯", "电脑整机", "数码配件"],
    "家用电器": ["大家电", "厨房电器", "生活电器"],
    "办公用品": ["办公设备", "文具耗材", "办公家具"],
    "家居建材": ["厨卫用具", "五金工具", "家纺布艺"],
    "食品饮料": ["休闲零食", "粮油调味", "酒水饮料"],
    "服装鞋帽": ["男装", "女装", "运动户外"],
}

# 二级分类 -> 商品命名素材。(单位, 成本价下限, 成本价上限, 品牌, 型号)
PRODUCT_TEMPLATES = {
    "手机通讯": (
        "台",
        900,
        7200,
        ["华为", "小米", "OPPO", "vivo", "荣耀", "三星", "realme", "iPhone"],
        [
            "Mate 60 Pro",
            "nova 13",
            "15 Pro",
            "K80",
            "Find X8",
            "X200",
            "Magic6",
            "S24",
            "GT7",
        ],
        ["", "(128GB)", "(256GB)", "(512GB)"],
    ),
    "电脑整机": (
        "台",
        2400,
        11000,
        ["联想", "戴尔", "惠普", "华硕", "宏碁", "苹果", "华为", "机械革命"],
        [
            "拯救者 Y7000P",
            "灵越 14",
            "暗影精灵 10",
            "无畏 Pro15",
            "非凡 S3",
            "MacBook Air",
            "MateBook D16",
            "蛟龙 16K",
        ],
        ["", "(16G/512G)", "(32G/1T)"],
    ),
    "数码配件": (
        "个",
        18,
        420,
        ["绿联", "倍思", "Anker", "罗技", "闪迪", "小米", "华为"],
        [
            "65W 氮化镓充电器",
            "10000mAh 充电宝",
            "无线鼠标 M330",
            "64G U 盘",
            "Type-C 数据线",
            "蓝牙耳机",
            "手机支架",
        ],
        [""],
    ),
    "大家电": (
        "台",
        1000,
        7500,
        ["海尔", "美的", "格力", "西门子", "小天鹅", "TCL", "松下"],
        [
            "对开门冰箱",
            "滚筒洗衣机",
            "1.5 匹变频空调",
            "55 寸 4K 电视",
            "立式冰柜",
            "嵌入式洗碗机",
        ],
        [""],
    ),
    "厨房电器": (
        "台",
        130,
        1500,
        ["美的", "苏泊尔", "九阳", "格兰仕", "松下", "飞利浦"],
        ["破壁机", "电压力锅", "微波炉", "电饭煲", "空气炸锅", "电烤箱"],
        [""],
    ),
    "生活电器": (
        "台",
        180,
        3600,
        ["戴森", "小米", "徕芬", "科沃斯", "石头", "飞利浦"],
        ["无线吸尘器", "高速吹风机", "扫地机器人", "加湿器", "除螨仪", "电熨斗"],
        [""],
    ),
    "办公设备": (
        "台",
        320,
        3800,
        ["惠普", "佳能", "爱普生", "兄弟", "得力", "联想"],
        ["激光打印机", "喷墨一体机", "标签打印机", "碎纸机", "扫描仪", "投影仪"],
        [""],
    ),
    "文具耗材": (
        "箱",
        12,
        220,
        ["得力", "晨光", "齐心", "3M", "真彩", "国誉"],
        [
            "A4 复印纸 5 包装",
            "中性笔 12 支装",
            "文件夹 10 个装",
            "订书机",
            "白板笔套装",
            "标签纸",
        ],
        [""],
    ),
    "办公家具": (
        "件",
        260,
        3200,
        ["震旦", "欧林", "百利", "恒林", "西昊"],
        ["人体工学椅", "办公桌 1.4 米", "文件柜", "会议桌", "屏风工位"],
        [""],
    ),
    "厨卫用具": (
        "件",
        130,
        2400,
        ["九牧", "箭牌", "科勒", "摩恩", "苏泊尔"],
        ["抽拉式水龙头", "不锈钢水槽", "淋浴花洒套装", "浴室柜", "虹吸式马桶"],
        [""],
    ),
    "五金工具": (
        "套",
        25,
        1100,
        ["博世", "世达", "史丹利", "田岛", "绿林"],
        ["电动螺丝刀", "18 件套扳手", "锂电电钻", "卷尺 5 米", "工具箱", "角磨机"],
        [""],
    ),
    "家纺布艺": (
        "套",
        35,
        1000,
        ["水星", "罗莱", "富安娜", "博洋", "恒源祥"],
        ["纯棉四件套", "乳胶枕", "蚕丝被", "毛巾 3 条装", "遮光窗帘", "珊瑚绒毯"],
        [""],
    ),
    "休闲零食": (
        "箱",
        12,
        130,
        ["三只松鼠", "良品铺子", "百草味", "旺旺", "盼盼"],
        ["每日坚果礼盒", "芒果干", "手撕面包", "薯片", "肉松饼", "黑巧克力"],
        [""],
    ),
    "粮油调味": (
        "袋",
        6,
        110,
        ["金龙鱼", "福临门", "海天", "李锦记", "中粮"],
        ["五常大米 5kg", "一级大豆油 5L", "生抽酱油 1.9L", "蚝油 700g", "加碘食用盐"],
        [""],
    ),
    "酒水饮料": (
        "箱",
        20,
        800,
        ["农夫山泉", "可口可乐", "青岛啤酒", "茅台", "伊利", "蒙牛"],
        [
            "饮用天然水 24 瓶",
            "纯净水 24 瓶",
            "精酿啤酒 12 罐",
            "果汁饮料 12 盒",
            "纯牛奶 12 盒",
        ],
        [""],
    ),
    "男装": (
        "件",
        60,
        700,
        ["海澜之家", "太平鸟", "杰克琼斯", "优衣库", "森马"],
        ["商务休闲夹克", "纯棉衬衫", "直筒牛仔裤", "羊毛大衣"],
        [""],
    ),
    "女装": (
        "件",
        80,
        1000,
        ["ONLY", "VERO MODA", "优衣库", "太平鸟", "伊芙丽"],
        ["针织连衣裙", "雪纺衬衫", "风衣外套", "阔腿裤"],
        [""],
    ),
    "运动户外": (
        "双",
        80,
        1000,
        ["李宁", "安踏", "耐克", "阿迪达斯", "探路者"],
        ["跑步鞋", "篮球鞋", "冲锋衣", "运动 T 恤", "登山包"],
        [""],
    ),
}

TARGET_PRODUCTS = 400
TARGET_CUSTOMERS = 300
TARGET_SUPPLIERS = 60
TARGET_POS = 700
TARGET_SOS = 2400


# ================================================================ 工具函数
def weighted(rng: random.Random, items, weights):
    return rng.choices(items, weights=weights, k=1)[0]


def weighted_sample(rng: random.Random, items, n: int, weights):
    """按权重不放回抽样（random.sample 不支持权重）。"""
    pool = list(items)
    w = list(weights)
    out = []
    for _ in range(min(n, len(pool))):
        total = sum(w)
        r = rng.random() * total
        acc = 0.0
        for i, wi in enumerate(w):
            acc += wi
            if r <= acc or i == len(w) - 1:
                out.append(pool.pop(i))
                w.pop(i)
                break
    return out


def qty_for_price(rng: random.Random, price: float) -> int:
    """数量与单价成反比：高价商品小批量、低价商品大宗走量。

    这样既贴近真实分销业务，也让各分类的销售额分布均衡、图表更有看头。
    """
    if price >= 3000:
        return rng.choices(
            [1, 1, 2, 2, 3, 4, 5], weights=[0.25, 0.20, 0.18, 0.14, 0.11, 0.07, 0.05]
        )[0]
    if price >= 1000:
        return rng.choices(
            [1, 2, 3, 4, 5, 8, 10], weights=[0.18, 0.18, 0.16, 0.14, 0.12, 0.12, 0.10]
        )[0]
    if price >= 300:
        return rng.choices(
            [2, 3, 5, 8, 12, 20, 30], weights=[0.14, 0.16, 0.18, 0.17, 0.14, 0.13, 0.08]
        )[0]
    if price >= 50:
        return rng.choices(
            [5, 10, 20, 30, 50, 80, 120],
            weights=[0.12, 0.16, 0.19, 0.18, 0.15, 0.12, 0.08],
        )[0]
    return rng.choices(
        [10, 20, 30, 50, 80, 120, 200, 300],
        weights=[0.10, 0.14, 0.16, 0.17, 0.15, 0.12, 0.10, 0.06],
    )[0]


def price_weights(products):
    """选品权重：价格越低越容易出现在订单里（1/sqrt(price)）。"""
    return [1.0 / max(float(p[6]) ** 0.5, 1.0) for p in products]


def rand_date(
    rng: random.Random, start: dt.date, end: dt.date, seasonal: bool = False
) -> dt.date:
    """在 [start, end] 内取随机日期；seasonal=True 时按 MONTH_WEIGHT 做月份加权。"""
    span = (end - start).days
    for _ in range(100):
        d = start + dt.timedelta(days=rng.randint(0, span))
        if not seasonal:
            return d
        w = MONTH_WEIGHT.get(d.month, 1.0)
        if rng.random() < w / 1.35:
            return d
    return start + dt.timedelta(days=rng.randint(0, span))


def money(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"))


def cn_name(rng: random.Random, gender: str, used: set) -> str:
    for _ in range(200):
        ln = rng.choice(SURNAMES)
        gn = rng.choice(MALE_GIVEN if gender == "男" else FEMALE_GIVEN)
        name = ln + gn
        if name not in used:
            used.add(name)
            return name
    return rng.choice(SURNAMES) + rng.choice(MALE_GIVEN + FEMALE_GIVEN) + str(len(used))


def company_name(rng: random.Random, mid_pool, used: set) -> str:
    for _ in range(300):
        name = (
            rng.choice(CITIES)
            + rng.choice(COMPANY_WORDS)
            + rng.choice(mid_pool)
            + rng.choice(COMPANY_SUFFIX)
        )
        if name not in used:
            used.add(name)
            return name
    return rng.choice(CITIES) + rng.choice(COMPANY_WORDS) + str(len(used)) + "有限公司"


def phone(rng: random.Random) -> str:
    return (
        "1" + rng.choice("35678") + "".join(rng.choice("0123456789") for _ in range(9))
    )


# ============================================================ 各表数据生成
def gen_departments(rng):
    return [(i + 1, name, city) for i, (name, city, _) in enumerate(DEPT_PLAN)]


def gen_employees(rng):
    """生成 60 名员工。

    组织结构：总经理（manager_id = NULL）-> 各部门负责人 -> 部门成员。
    生成顺序保证上级 employee_id 一定小于下级，便于顺序插入满足自引用外键。
    """
    rows = []  # (id, 姓名, 性别, 入职日期, 岗位, 月薪, 上级ID, 部门ID, 电话)
    dept_head: dict = {}  # 部门名 -> 负责人 employee_id
    dept_member: dict = {}  # 部门名 -> [employee_id, ...]
    used_names: set = set()
    next_id = 1

    for dept_id, (dept_name, _city, posts) in enumerate(DEPT_PLAN, start=1):
        head_id = None
        for post_name, count, (lo, hi) in posts:
            for _ in range(count):
                if dept_name == "总经办":
                    manager = None if post_name == "总经理" else 1
                elif head_id is None:
                    head_id = next_id
                    manager = 1
                else:
                    manager = head_id

                gender = rng.choice(["男", "女"])
                rows.append(
                    (
                        next_id,
                        cn_name(rng, gender, used_names),
                        gender,
                        rand_date(rng, dt.date(2015, 1, 1), dt.date(2025, 6, 30)),
                        post_name,
                        money(rng.randint(lo, hi)),
                        manager,
                        dept_id,
                        phone(rng),
                    )
                )
                dept_member.setdefault(dept_name, []).append(next_id)
                next_id += 1
        dept_head[dept_name] = head_id

    return rows, dept_head, dept_member


def gen_warehouses(rng, dept_member):
    keepers = dept_member.get("仓储物流部", [1])
    rows = []
    for i, (wname, city) in enumerate(WAREHOUSES, start=1):
        rows.append((i, wname, city, rng.choice(keepers)))
    return rows


def gen_categories():
    rows = []
    cid = 1
    for top_name, subs in CATEGORY_TREE.items():
        rows.append((cid, top_name, None))
        parent = cid
        cid += 1
        for sub in subs:
            rows.append((cid, sub, parent))
            cid += 1
    return rows


def gen_suppliers(rng):
    rows = []
    used: set = set()
    for i in range(1, TARGET_SUPPLIERS + 1):
        rows.append(
            (
                i,
                company_name(rng, SUPPLIER_MIDS, used),
                cn_name(rng, rng.choice(["男", "女"]), set()),
                rng.choice(CITIES),
                weighted(rng, ["A", "B", "C"], [0.3, 0.5, 0.2]),
                rand_date(rng, dt.date(2016, 1, 1), dt.date(2024, 6, 30)),
            )
        )
    return rows


def gen_customers(rng):
    rows = []
    used: set = set()
    for i in range(1, TARGET_CUSTOMERS + 1):
        city = rng.choice(CITIES)
        rows.append(
            (
                i,
                company_name(rng, COMPANY_MIDS, used),
                cn_name(rng, rng.choice(["男", "女"]), set()),
                city,
                rng.choice(INDUSTRIES),
                weighted(rng, ["A", "B", "C"], [0.35, 0.5, 0.15]),
                rand_date(rng, CUSTOMER_START, dt.date(2025, 12, 31)),
            )
        )
    return rows


def gen_products(rng, categories, suppliers):
    """按二级分类的品牌/型号组合，随机抽样 400 个商品（名称唯一）。"""
    leaf = [(cid, cname) for cid, cname, parent in categories if parent is not None]
    catalog = []
    for cid, cname in leaf:
        unit, lo, hi, brands, models, specs = PRODUCT_TEMPLATES[cname]
        for b in brands:
            for m in models:
                for s in specs:
                    catalog.append((cid, f"{b} {m} {s}".strip(), unit, lo, hi))
    rng.shuffle(catalog)
    picked = catalog[:TARGET_PRODUCTS]

    sup_ids = [s[0] for s in suppliers]
    rows = []
    for i, (cid, name, unit, lo, hi) in enumerate(picked, start=1):
        cost = round(rng.uniform(lo, hi), 2)
        sale = round(cost * rng.uniform(1.15, 1.45), 2)
        rows.append(
            (
                i,
                name,
                cid,
                rng.choice(sup_ids),
                unit,
                money(cost),
                money(sale),
                weighted(rng, ["在售", "停售"], [0.88, 0.12]),
                rand_date(rng, PRODUCT_START, dt.date(2026, 6, 30)),
            )
        )
    return rows


def gen_inventory(rng, warehouses, products):
    rows = []
    iid = 1
    for p in products:
        pid = p[0]
        n = rng.choices([1, 2, 3, 4, 5], weights=[0.05, 0.15, 0.35, 0.30, 0.15])[0]
        for wh in rng.sample([w[0] for w in warehouses], n):
            safety = rng.choice([20, 30, 50, 80, 100, 150, 200])
            if rng.random() < 0.13:  # 约 13% 低于安全库存
                qty = rng.randint(0, max(safety - 1, 0))
            else:
                qty = rng.randint(safety, safety * 12)
            rows.append(
                (
                    iid,
                    wh,
                    pid,
                    qty,
                    safety,
                    rand_date(rng, dt.date(2026, 6, 1), END_DATE),
                )
            )
            iid += 1
    return rows


def gen_purchase_orders(rng, suppliers, products, buyer_ids):
    orders, items = [], []
    seq_by_day: dict = {}
    oid = iid = 1
    sup_ids = [s[0] for s in suppliers]
    pw = price_weights(products)
    for _ in range(TARGET_POS):
        odate = rand_date(rng, START_DATE, dt.date(2026, 8, 31), seasonal=True)
        key = odate.strftime("%Y%m%d")
        seq_by_day[key] = seq_by_day.get(key, 0) + 1
        if (SNAPSHOT_DATE - odate).days <= 30:
            status = weighted(rng, ["已完成", "进行中", "已取消"], [0.60, 0.35, 0.05])
        else:
            status = weighted(rng, ["已完成", "已取消"], [0.94, 0.06])
        n = rng.choices([1, 2, 3, 4], weights=[0.35, 0.35, 0.20, 0.10])[0]
        picked = weighted_sample(rng, products, n, pw)
        total = Decimal("0.00")
        for p in picked:
            price = money(p[5])  # 采购价 = 商品成本价
            # 采购批量比销售批量大 3~8 倍
            qty = max(10, qty_for_price(rng, float(price)) * rng.randint(3, 8))
            amt = money(float(qty) * float(price))
            items.append((iid, oid, p[0], qty, price, amt))
            total += amt
            iid += 1
        orders.append(
            (
                oid,
                f"PO{key}{seq_by_day[key]:03d}",
                rng.choice(sup_ids),
                rng.choice(buyer_ids),
                odate,
                odate + dt.timedelta(days=rng.randint(3, 15)),
                status,
                total,
            )
        )
        oid += 1
    return orders, items


def gen_sales_orders(rng, customers, products, seller_ids):
    orders, items = [], []
    seq_by_day: dict = {}
    oid = iid = 1
    cust_city = {c[0]: c[3] for c in customers}
    pw = price_weights(products)
    for _ in range(TARGET_SOS):
        cust = rng.choice(customers)
        odate = rand_date(rng, START_DATE, END_DATE, seasonal=True)
        key = odate.strftime("%Y%m%d")
        seq_by_day[key] = seq_by_day.get(key, 0) + 1
        if (SNAPSHOT_DATE - odate).days <= 45:
            status = weighted(rng, ["待发货", "已完成", "已取消"], [0.58, 0.37, 0.05])
        else:
            status = weighted(rng, ["已完成", "已取消", "退货中"], [0.86, 0.09, 0.05])

        if status in ("已完成", "退货中"):
            ship = odate + dt.timedelta(days=rng.randint(1, 7))
        else:
            ship = None

        if status == "已完成":
            pay = weighted(rng, ["已付款", "部分付款", "未付款"], [0.88, 0.08, 0.04])
        elif status == "待发货":
            pay = weighted(rng, ["未付款", "部分付款", "已付款"], [0.55, 0.35, 0.10])
        elif status == "退货中":
            pay = "已付款"
        else:
            pay = "未付款"

        n = rng.choices([1, 2, 3, 4, 5], weights=[0.32, 0.28, 0.20, 0.13, 0.07])[0]
        picked = weighted_sample(rng, products, n, pw)
        total = Decimal("0.00")
        for p in picked:
            price = money(p[6])  # 销售价 = 商品标准售价
            qty = qty_for_price(rng, float(price))
            disc = Decimal(
                str(
                    weighted(
                        rng,
                        [1.00, 0.95, 0.90, 0.85, 0.80],
                        [0.60, 0.15, 0.15, 0.07, 0.03],
                    )
                )
            )
            amt = money(float(qty) * float(price) * float(disc))
            items.append((iid, oid, p[0], qty, price, disc, amt))
            total += amt
            iid += 1

        city = cust_city[cust[0]] if rng.random() < 0.85 else rng.choice(CITIES)
        orders.append(
            (
                oid,
                f"SO{key}{seq_by_day[key]:03d}",
                cust[0],
                rng.choice(seller_ids),
                odate,
                ship,
                status,
                pay,
                city,
                total,
            )
        )
        oid += 1
    return orders, items


# ================================================================ 写入工具
TABLES = [
    ("departments", ["department_id", "department_name", "city"]),
    (
        "employees",
        [
            "employee_id",
            "employee_name",
            "gender",
            "hire_date",
            "job_title",
            "salary",
            "manager_id",
            "department_id",
            "phone",
        ],
    ),
    ("warehouses", ["warehouse_id", "warehouse_name", "city", "manager_id"]),
    ("categories", ["category_id", "category_name", "parent_id"]),
    (
        "suppliers",
        [
            "supplier_id",
            "supplier_name",
            "contact_name",
            "city",
            "rating",
            "created_date",
        ],
    ),
    (
        "customers",
        [
            "customer_id",
            "customer_name",
            "contact_name",
            "city",
            "industry",
            "credit_level",
            "created_date",
        ],
    ),
    (
        "products",
        [
            "product_id",
            "product_name",
            "category_id",
            "supplier_id",
            "unit",
            "cost_price",
            "sale_price",
            "status",
            "created_date",
        ],
    ),
    (
        "inventory",
        [
            "inventory_id",
            "warehouse_id",
            "product_id",
            "quantity",
            "safety_stock",
            "last_update",
        ],
    ),
    (
        "purchase_orders",
        [
            "po_id",
            "po_no",
            "supplier_id",
            "employee_id",
            "order_date",
            "expected_date",
            "status",
            "total_amount",
        ],
    ),
    (
        "purchase_order_items",
        ["po_item_id", "po_id", "product_id", "quantity", "unit_price", "amount"],
    ),
    (
        "sales_orders",
        [
            "so_id",
            "so_no",
            "customer_id",
            "employee_id",
            "order_date",
            "ship_date",
            "status",
            "payment_status",
            "city",
            "total_amount",
        ],
    ),
    (
        "sales_order_items",
        [
            "so_item_id",
            "so_id",
            "product_id",
            "quantity",
            "unit_price",
            "discount",
            "amount",
        ],
    ),
]


def sql_literal(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return "'" + v.isoformat() + "'"
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def export_sql(data: dict) -> None:
    lines = [
        "-- ============================================================================",
        "-- ERP 智能数据库查询系统 —— 02 示例数据（由 tools/build_erp_db.py 自动生成）",
        f"-- 生成时间：{dt.datetime.now():%Y-%m-%d %H:%M:%S}    随机种子：{SEED}",
        "-- 数据范围：2024-01-01 ~ 2026-09-09，快照日 2026-09-10",
        "-- 切勿手工修改本文件，需要重新生成请执行：python tools/build_erp_db.py --rebuild",
        "-- ============================================================================",
        "",
        "USE erp_demo;",
        "SET NAMES utf8mb4;",
        "",
    ]
    for table, cols in TABLES:
        rows = data[table]
        lines.append(f"-- ------------------------------ {table}（{len(rows)} 行）")
        collist = ", ".join(f"`{c}`" for c in cols)
        for i in range(0, len(rows), 200):
            chunk = rows[i : i + 200]
            values = ",\n  ".join(
                "(" + ", ".join(sql_literal(v) for v in r) + ")" for r in chunk
            )
            lines.append(f"INSERT INTO `{table}` ({collist}) VALUES\n  {values};")
        lines.append("")
    SEED_FILE.write_text("\n".join(lines), encoding="utf-8")


def load(data: dict) -> None:
    conn = dbm.connect()
    try:
        with conn.cursor() as cur:
            for table, cols in TABLES:
                rows = data[table]
                collist = ", ".join(f"`{c}`" for c in cols)
                holders = ", ".join(["%s"] * len(cols))
                sql = f"INSERT INTO `{table}` ({collist}) VALUES ({holders})"
                for i in range(0, len(rows), 1000):
                    cur.executemany(sql, rows[i : i + 1000])
        conn.commit()
    finally:
        conn.close()


# ===================================================================== 主流程
def main() -> None:
    ap = argparse.ArgumentParser(description="构建 ERP 示例数据库")
    ap.add_argument(
        "--rebuild",
        action="store_true",
        default=True,
        help="删除并重建所有表（默认行为）",
    )
    ap.add_argument(
        "--keep-schema", action="store_true", help="保留现有表结构，只重新灌入数据"
    )
    ap.add_argument(
        "--no-export", action="store_true", help="不导出 sql/02_seed_data.sql"
    )
    args = ap.parse_args()

    rng = random.Random(SEED)

    print("[1/5] 创建数据库 ...")
    dbm.run_sql_file(SQL_DIR / "00_create_database.sql", with_database=False)

    if not args.keep_schema:
        print("[2/5] 重建表结构 ...")
        dbm.run_sql_file(SQL_DIR / "01_schema.sql")
    else:
        print("[2/5] 跳过表结构重建（--keep-schema）")

    print("[3/5] 生成示例数据 ...")
    departments = gen_departments(rng)
    employees, dept_head, dept_member = gen_employees(rng)
    warehouses = gen_warehouses(rng, dept_member)
    categories = gen_categories()
    suppliers = gen_suppliers(rng)
    customers = gen_customers(rng)
    products = gen_products(rng, categories, suppliers)

    seller_ids = dept_member.get("销售部", [1])
    buyer_ids = dept_member.get("采购部", [1])

    inventory = gen_inventory(rng, warehouses, products)
    pos, poi = gen_purchase_orders(rng, suppliers, products, buyer_ids)
    sos, soi = gen_sales_orders(rng, customers, products, seller_ids)

    data = {
        "departments": departments,
        "employees": employees,
        "warehouses": warehouses,
        "categories": categories,
        "suppliers": suppliers,
        "customers": customers,
        "products": products,
        "inventory": inventory,
        "purchase_orders": pos,
        "purchase_order_items": poi,
        "sales_orders": sos,
        "sales_order_items": soi,
    }

    print("[4/5] 导入 MySQL ...")
    load(data)

    if not args.no_export:
        print("[5/5] 导出 SQL 脚本 ...")
        export_sql(data)

    counts = dbm.table_counts([t for t, _ in TABLES])
    print("\n构建完成，各表行数：")
    total = 0
    for t, n in counts:
        total += n
        print(f"    {t:<24} {n:>7,}")
    print(f"    {'合计':<24} {total:>7,}")
    if not args.no_export:
        size_mb = SEED_FILE.stat().st_size / 1024 / 1024
        print(f"\n数据脚本：{SEED_FILE}  ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
