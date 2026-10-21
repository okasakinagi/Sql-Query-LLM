-- ============================================================================
-- ERP 智能数据库查询系统 —— 01 表结构定义
-- 共 12 张表：主数据 7 张 + 业务明细 5 张
--   主数据：departments / employees / warehouses / categories
--           suppliers   / customers / products
--   业务表：inventory / purchase_orders / purchase_order_items
--           sales_orders / sales_order_items
-- 说明  ：每张表、每个字段都写了中文注释，这些注释会被自动读取并注入
--         大模型提示词，是保证 Text-to-SQL 准确率的重要信息来源。
-- ============================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS sales_order_items;
DROP TABLE IF EXISTS sales_orders;
DROP TABLE IF EXISTS purchase_order_items;
DROP TABLE IF EXISTS purchase_orders;
DROP TABLE IF EXISTS inventory;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS warehouses;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS departments;

SET FOREIGN_KEY_CHECKS = 1;

-- ----------------------------------------------------------------- 部门表
CREATE TABLE departments (
    department_id   INT           NOT NULL AUTO_INCREMENT COMMENT '部门ID',
    department_name VARCHAR(50)   NOT NULL                COMMENT '部门名称',
    city            VARCHAR(30)   NOT NULL                COMMENT '部门所在城市',
    PRIMARY KEY (department_id),
    UNIQUE KEY uk_department_name (department_name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '部门表';

-- ----------------------------------------------------------------- 员工表
CREATE TABLE employees (
    employee_id   INT            NOT NULL AUTO_INCREMENT COMMENT '员工ID',
    employee_name VARCHAR(30)    NOT NULL                COMMENT '员工姓名',
    gender        CHAR(1)        NOT NULL                COMMENT '性别：男 / 女',
    hire_date     DATE           NOT NULL                COMMENT '入职日期',
    job_title     VARCHAR(30)    NOT NULL                COMMENT '岗位名称',
    salary        DECIMAL(10, 2) NOT NULL                COMMENT '月薪（元）',
    manager_id    INT            NULL                    COMMENT '直属上级的员工ID，关联 employees.employee_id，总经理为 NULL',
    department_id INT            NOT NULL                COMMENT '所属部门ID',
    phone         VARCHAR(20)    NULL                    COMMENT '联系电话',
    PRIMARY KEY (employee_id),
    KEY idx_emp_department (department_id),
    KEY idx_emp_manager (manager_id),
    CONSTRAINT fk_emp_department FOREIGN KEY (department_id) REFERENCES departments (department_id),
    CONSTRAINT fk_emp_manager    FOREIGN KEY (manager_id)    REFERENCES employees (employee_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '员工表';

-- ----------------------------------------------------------------- 仓库表
CREATE TABLE warehouses (
    warehouse_id   INT         NOT NULL AUTO_INCREMENT COMMENT '仓库ID',
    warehouse_name VARCHAR(40) NOT NULL                COMMENT '仓库名称',
    city           VARCHAR(30) NOT NULL                COMMENT '仓库所在城市',
    manager_id     INT         NULL                    COMMENT '仓库负责人（员工ID）',
    PRIMARY KEY (warehouse_id),
    KEY idx_wh_manager (manager_id),
    CONSTRAINT fk_wh_manager FOREIGN KEY (manager_id) REFERENCES employees (employee_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '仓库表';

-- ------------------------------------------------------------- 商品分类表
CREATE TABLE categories (
    category_id   INT         NOT NULL AUTO_INCREMENT COMMENT '分类ID',
    category_name VARCHAR(40) NOT NULL                COMMENT '分类名称',
    parent_id     INT         NULL                    COMMENT '上级分类ID，NULL 表示一级分类；二级分类时指向本表 category_id',
    PRIMARY KEY (category_id),
    KEY idx_cat_parent (parent_id),
    CONSTRAINT fk_cat_parent FOREIGN KEY (parent_id) REFERENCES categories (category_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '商品分类表（支持二级分类）';

-- ----------------------------------------------------------------- 供应商表
CREATE TABLE suppliers (
    supplier_id   INT         NOT NULL AUTO_INCREMENT COMMENT '供应商ID',
    supplier_name VARCHAR(60) NOT NULL                COMMENT '供应商名称',
    contact_name  VARCHAR(30) NOT NULL                COMMENT '联系人姓名',
    city          VARCHAR(30) NOT NULL                COMMENT '所在城市',
    rating        CHAR(1)     NOT NULL                COMMENT '供应商评级：A / B / C',
    created_date  DATE        NOT NULL                COMMENT '合作开始日期',
    PRIMARY KEY (supplier_id),
    KEY idx_sup_city (city),
    KEY idx_sup_rating (rating)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '供应商表';

-- ------------------------------------------------------------------- 客户表
CREATE TABLE customers (
    customer_id   INT         NOT NULL AUTO_INCREMENT COMMENT '客户ID',
    customer_name VARCHAR(60) NOT NULL                COMMENT '客户公司名称',
    contact_name  VARCHAR(30) NOT NULL                COMMENT '联系人姓名',
    city          VARCHAR(30) NOT NULL                COMMENT '客户所在城市',
    industry      VARCHAR(20) NOT NULL                COMMENT '所属行业，如 制造业、零售业、信息技术',
    credit_level  CHAR(1)     NOT NULL                COMMENT '信用等级：A（优）/ B（良）/ C（一般）',
    created_date  DATE        NOT NULL                COMMENT '成为客户的日期',
    PRIMARY KEY (customer_id),
    KEY idx_cust_city (city),
    KEY idx_cust_industry (industry),
    KEY idx_cust_credit (credit_level)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '客户表';

-- ------------------------------------------------------------------- 商品表
CREATE TABLE products (
    product_id   INT            NOT NULL AUTO_INCREMENT COMMENT '商品ID',
    product_name VARCHAR(60)    NOT NULL                COMMENT '商品名称',
    category_id  INT            NOT NULL                COMMENT '商品分类ID（二级分类）',
    supplier_id  INT            NOT NULL                COMMENT '主要供应商ID',
    unit         VARCHAR(10)    NOT NULL                COMMENT '计量单位，如 台、件、箱',
    cost_price   DECIMAL(10, 2) NOT NULL                COMMENT '采购成本价（元）',
    sale_price   DECIMAL(10, 2) NOT NULL                COMMENT '标准销售价（元）',
    status       VARCHAR(10)    NOT NULL                COMMENT '商品状态：在售 / 停售',
    created_date DATE           NOT NULL                COMMENT '上架日期',
    PRIMARY KEY (product_id),
    KEY idx_prod_category (category_id),
    KEY idx_prod_supplier (supplier_id),
    KEY idx_prod_status (status),
    CONSTRAINT fk_prod_category FOREIGN KEY (category_id) REFERENCES categories (category_id),
    CONSTRAINT fk_prod_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers (supplier_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '商品表';

-- ------------------------------------------------------------------- 库存表
CREATE TABLE inventory (
    inventory_id INT  NOT NULL AUTO_INCREMENT COMMENT '库存记录ID',
    warehouse_id INT  NOT NULL                COMMENT '仓库ID',
    product_id   INT  NOT NULL                COMMENT '商品ID',
    quantity     INT  NOT NULL DEFAULT 0      COMMENT '当前库存数量',
    safety_stock INT  NOT NULL DEFAULT 0      COMMENT '安全库存（低于该值需要补货）',
    last_update  DATE NOT NULL                COMMENT '最后盘点/更新日期',
    PRIMARY KEY (inventory_id),
    UNIQUE KEY uk_wh_product (warehouse_id, product_id),
    KEY idx_inv_product (product_id),
    CONSTRAINT fk_inv_wh      FOREIGN KEY (warehouse_id) REFERENCES warehouses (warehouse_id),
    CONSTRAINT fk_inv_product FOREIGN KEY (product_id)   REFERENCES products (product_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '库存表（仓库 × 商品）';

-- --------------------------------------------------------------- 采购单主表
CREATE TABLE purchase_orders (
    po_id         INT            NOT NULL AUTO_INCREMENT COMMENT '采购单ID',
    po_no         VARCHAR(20)    NOT NULL                COMMENT '采购单号，如 PO20240315001',
    supplier_id   INT            NOT NULL                COMMENT '供应商ID',
    employee_id   INT            NOT NULL                COMMENT '采购员（员工ID）',
    order_date    DATE           NOT NULL                COMMENT '采购下单日期',
    expected_date DATE           NULL                    COMMENT '预计到货日期',
    status        VARCHAR(10)    NOT NULL                COMMENT '采购状态：已完成 / 进行中 / 已取消',
    total_amount  DECIMAL(12, 2) NOT NULL                COMMENT '采购总金额（元）',
    PRIMARY KEY (po_id),
    UNIQUE KEY uk_po_no (po_no),
    KEY idx_po_date (order_date),
    KEY idx_po_supplier (supplier_id),
    KEY idx_po_status (status),
    CONSTRAINT fk_po_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers (supplier_id),
    CONSTRAINT fk_po_employee FOREIGN KEY (employee_id) REFERENCES employees (employee_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '采购单主表';

-- --------------------------------------------------------------- 采购单明细
CREATE TABLE purchase_order_items (
    po_item_id INT            NOT NULL AUTO_INCREMENT COMMENT '采购明细ID',
    po_id      INT            NOT NULL                COMMENT '所属采购单ID',
    product_id INT            NOT NULL                COMMENT '商品ID',
    quantity   INT            NOT NULL                COMMENT '采购数量',
    unit_price DECIMAL(10, 2) NOT NULL                COMMENT '采购单价（元）',
    amount     DECIMAL(12, 2) NOT NULL                COMMENT '本行金额 = quantity * unit_price',
    PRIMARY KEY (po_item_id),
    KEY idx_poi_po (po_id),
    KEY idx_poi_product (product_id),
    CONSTRAINT fk_poi_po      FOREIGN KEY (po_id)      REFERENCES purchase_orders (po_id) ON DELETE CASCADE,
    CONSTRAINT fk_poi_product FOREIGN KEY (product_id) REFERENCES products (product_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '采购单明细表';

-- --------------------------------------------------------------- 销售单主表
CREATE TABLE sales_orders (
    so_id          INT            NOT NULL AUTO_INCREMENT COMMENT '销售单ID',
    so_no          VARCHAR(20)    NOT NULL                COMMENT '销售单号，如 SO20240315001',
    customer_id    INT            NOT NULL                COMMENT '客户ID',
    employee_id    INT            NOT NULL                COMMENT '负责业务员（员工ID）',
    order_date     DATE           NOT NULL                COMMENT '下单日期',
    ship_date      DATE           NULL                    COMMENT '发货日期，未发货为 NULL',
    status         VARCHAR(10)    NOT NULL                COMMENT '订单状态：已完成 / 待发货 / 已取消 / 退货中',
    payment_status VARCHAR(10)    NOT NULL                COMMENT '付款状态：已付款 / 部分付款 / 未付款',
    city           VARCHAR(30)    NOT NULL                COMMENT '收货城市',
    total_amount   DECIMAL(12, 2) NOT NULL                COMMENT '订单总金额（元）',
    PRIMARY KEY (so_id),
    UNIQUE KEY uk_so_no (so_no),
    KEY idx_so_date (order_date),
    KEY idx_so_customer (customer_id),
    KEY idx_so_employee (employee_id),
    KEY idx_so_status (status),
    KEY idx_so_payment (payment_status),
    KEY idx_so_city (city),
    CONSTRAINT fk_so_customer FOREIGN KEY (customer_id) REFERENCES customers (customer_id),
    CONSTRAINT fk_so_employee FOREIGN KEY (employee_id) REFERENCES employees (employee_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '销售订单主表';

-- --------------------------------------------------------------- 销售单明细
CREATE TABLE sales_order_items (
    so_item_id INT            NOT NULL AUTO_INCREMENT COMMENT '销售明细ID',
    so_id      INT            NOT NULL                COMMENT '所属销售单ID',
    product_id INT            NOT NULL                COMMENT '商品ID',
    quantity   INT            NOT NULL                COMMENT '销售数量',
    unit_price DECIMAL(10, 2) NOT NULL                COMMENT '销售单价（商品标准售价，元）',
    discount   DECIMAL(3, 2)  NOT NULL DEFAULT 1.00   COMMENT '折扣系数，1.00 表示无折扣，0.90 表示九折',
    amount     DECIMAL(12, 2) NOT NULL                COMMENT '本行金额 = quantity * unit_price * discount',
    PRIMARY KEY (so_item_id),
    KEY idx_soi_so (so_id),
    KEY idx_soi_product (product_id),
    CONSTRAINT fk_soi_so      FOREIGN KEY (so_id)      REFERENCES sales_orders (so_id) ON DELETE CASCADE,
    CONSTRAINT fk_soi_product FOREIGN KEY (product_id) REFERENCES products (product_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '销售订单明细表';
