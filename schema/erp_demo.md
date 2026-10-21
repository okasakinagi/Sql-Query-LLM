# 数据库结构：erp_demo

<!-- fingerprint: 9659401b8992f706 -->

> 本文件由 `python tools/gen_schema_md.py` 自动生成，也可以手工微调（例如补充同义词、常见口径）。
> 系统启动时会校验指纹，若与真实库不一致会自动重新生成。
> 这个文件会**原样**作为提示词的一部分发给大模型，请保持简洁。

## categories（商品分类表（支持二级分类），24 行）
category_id(分类ID)[主键]，category_name(分类名称)，parent_id(上级分类ID，NULL 表示一级分类；二级分类时指向本表 category_id)
外键：parent_id→categories.category_id

## customers（客户表，300 行）
customer_id(客户ID)[主键]，customer_name(客户公司名称)，contact_name(联系人姓名)，city(客户所在城市)，industry(所属行业，如 制造业、零售业、信息技术)，credit_level(信用等级：A（优）/ B（良）/ C（一般）){A/B/C}，created_date(成为客户的日期)

## departments（部门表，8 行）
department_id(部门ID)[主键]，department_name(部门名称)，city(部门所在城市)

## employees（员工表，60 行）
employee_id(员工ID)[主键]，employee_name(员工姓名)，gender(性别：男 / 女)，hire_date(入职日期)，job_title(岗位名称)，salary(月薪（元）)，manager_id(直属上级的员工ID，关联 employees.employee_id，总经理为 NULL)，department_id(所属部门ID)，phone(联系电话)
外键：department_id→departments.department_id；manager_id→employees.employee_id

## inventory（库存表（仓库 × 商品），1381 行）
inventory_id(库存记录ID)[主键]，warehouse_id(仓库ID)，product_id(商品ID)，quantity(当前库存数量)，safety_stock(安全库存（低于该值需要补货）)，last_update(最后盘点/更新日期)
外键：product_id→products.product_id；warehouse_id→warehouses.warehouse_id

## products（商品表，400 行）
product_id(商品ID)[主键]，product_name(商品名称)，category_id(商品分类ID（二级分类）)，supplier_id(主要供应商ID)，unit(计量单位，如 台、件、箱){箱/台/袋/件/个/双/套}，cost_price(采购成本价（元）)，sale_price(标准销售价（元）)，status(商品状态：在售 / 停售){停售/在售}，created_date(上架日期)
外键：category_id→categories.category_id；supplier_id→suppliers.supplier_id

## purchase_order_items（采购单明细表，1403 行）
po_item_id(采购明细ID)[主键]，po_id(所属采购单ID)，product_id(商品ID)，quantity(采购数量)，unit_price(采购单价（元）){895.77/1929.48/703.89/96.53/377.70/425.88/3285.33/53.96/1402.96/87.57/6307.02/114.01/1163.91/118.03/30.22/371.41/275.99/212.30/148.89/1088.11/230.16/626.68/195.61/4390.47/116.68}，amount(本行金额 = quantity * unit_price)
外键：po_id→purchase_orders.po_id；product_id→products.product_id

## purchase_orders（采购单主表，700 行）
po_id(采购单ID)[主键]，po_no(采购单号，如 PO20240315001)，supplier_id(供应商ID)，employee_id(采购员（员工ID）)，order_date(采购下单日期)，expected_date(预计到货日期)，status(采购状态：已完成 / 进行中 / 已取消){已取消/已完成/进行中}，total_amount(采购总金额（元）)
外键：employee_id→employees.employee_id；supplier_id→suppliers.supplier_id

## sales_order_items（销售订单明细表，5652 行）
so_item_id(销售明细ID)[主键]，so_id(所属销售单ID)，product_id(商品ID)，quantity(销售数量)，unit_price(销售单价（商品标准售价，元）){33.58/3392.51/707.04/431.37/8302.14/772.35/724.09/369.73/10154.82/1580.74/5788.61/249.49/960.89/113.42/160.60/2600.67/147.77/800.29/1452.27/9225.45/232.09/284.73/303.79/57.00/249.82}，discount(折扣系数，1.00 表示无折扣，0.90 表示九折)，amount(本行金额 = quantity * unit_price * discount)
外键：product_id→products.product_id；so_id→sales_orders.so_id

## sales_orders（销售订单主表，2400 行）
so_id(销售单ID)[主键]，so_no(销售单号，如 SO20240315001)，customer_id(客户ID)，employee_id(负责业务员（员工ID）)，order_date(下单日期)，ship_date(发货日期，未发货为 NULL)，status(订单状态：已完成 / 待发货 / 已取消 / 退货中){已取消/已完成/待发货/退货中}，payment_status(付款状态：已付款 / 部分付款 / 未付款){已付款/未付款/部分付款}，city(收货城市)，total_amount(订单总金额（元）)
外键：customer_id→customers.customer_id；employee_id→employees.employee_id

## suppliers（供应商表，60 行）
supplier_id(供应商ID)[主键]，supplier_name(供应商名称)，contact_name(联系人姓名)，city(所在城市)，rating(供应商评级：A / B / C){A/B/C}，created_date(合作开始日期)

## warehouses（仓库表，6 行）
warehouse_id(仓库ID)[主键]，warehouse_name(仓库名称)，city(仓库所在城市)，manager_id(仓库负责人（员工ID）)
外键：manager_id→employees.employee_id
