/* ============================================================
   智能数据库查询系统 —— 前端交互
   纯原生 JS，无框架依赖；图表使用本地 ECharts。
   ============================================================ */
(() => {
    "use strict";

    const $ = (sel) => document.querySelector(sel);
    const messagesEl = $("#messages");
    const inputEl = $("#input");
    const sendBtn = $("#send");

    /** 每条助手消息的结果数据（供导出使用） */
    const store = new Map();
    let seq = 0;
    let busy = false;

    const SAMPLES = [
        "各部门分别有多少名员工",
        "2025 年每个月的销售额分别是多少",
        "销量最高的前 5 个商品是哪些",
        "各大类（一级分类）的销售额占比是多少",
        "销售额排名前 10 的城市及对应金额",
        "库存低于安全库存的商品有哪些",
        "付款状态为未付款的订单有多少笔，涉及金额多少",
        "供应商评级为 A 的供应商各有几家采购单",
        "每个业务员负责的订单总金额排名前 5",
        "2026 年与 2025 年同期的销售额对比",
        "有哪些商品属于停售状态但仍有库存",
        "每个仓库的商品种类数分别是多少",
    ];

    /* ----------------------------------------------------- 工具 */
    const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
        (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

    const isNum = (v) => typeof v === "number";

    function fmt(v) {
        if (v === null || v === undefined) return "";
        if (typeof v === "number") {
            return Number.isInteger(v)
                ? v.toLocaleString("zh-CN")
                : v.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }
        return String(v);
    }

    const secs = (v) => (v === undefined || v === null ? "—" : `${Number(v).toFixed(2)}s`);

    /* ----------------------------------------------------- 初始化 */
    async function init() {
        renderSamples();
        renderSchemaPlaceholder();
        try {
            const h = await (await fetch("/api/health")).json();
            setBadge("#badge-db", h.database.ok, h.database.detail);
            setBadge("#badge-llm", h.model.ok, h.model.detail);
        } catch (e) {
            setBadge("#badge-db", false, "接口不可用");
            setBadge("#badge-llm", false, "接口不可用");
        }
        try {
            const s = await (await fetch("/api/schema")).json();
            renderSchema(s);
        } catch (e) {
            $("#schema-hint").textContent = "读取数据库结构失败";
        }
    }

    function setBadge(sel, ok, title) {
        const el = $(sel);
        el.classList.add(ok ? "ok" : "bad");
        el.title = title || "";
    }

    function renderSchemaPlaceholder() {
        $("#schema-hint").textContent = "加载中…";
    }

    function renderSchema(data) {
        const total = data.tables.reduce((a, t) => a + t.rows, 0);
        $("#schema-hint").textContent =
            `${data.database} ｜ ${data.tables.length} 张表 ｜ 共 ${total.toLocaleString("zh-CN")} 行`;
        $("#schema-list").innerHTML = data.tables.map((t) => `
            <details class="tbl">
                <summary>
                    <span class="tname">${esc(t.name)}</span>
                    <span class="trow">${t.rows.toLocaleString("zh-CN")}</span>
                </summary>
                <div class="cols">
                    ${t.columns.map((c) => `<div class="col">
                        <b>${esc(c.name)}</b><span>${esc(c.comment || c.type)}</span>
                    </div>`).join("")}
                </div>
            </details>`).join("");
    }

    async function refreshSchema() {
        const btn = $("#refresh-schema");
        btn.disabled = true;
        btn.textContent = "刷新中";
        try {
            const res = await fetch("/api/schema/refresh", { method: "POST" });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
            renderSchema(data);
            if (data.changed) {
                $("#schema-hint").textContent += " ｜ 结构已更新";
                setBadge("#badge-db", true, "数据库结构已刷新");
            } else {
                $("#schema-hint").textContent += " ｜ 结构无变化";
            }
        } catch (e) {
            $("#schema-hint").textContent = `刷新失败：${e.message}`;
        } finally {
            btn.disabled = false;
            btn.textContent = "刷新";
        }
    }

    function renderSamples() {
        $("#samples").innerHTML = SAMPLES.map((q) =>
            `<button class="sample">${esc(q)}</button>`).join("");
        $("#samples").querySelectorAll(".sample").forEach((btn) => {
            btn.addEventListener("click", () => {
                inputEl.value = btn.textContent;
                autoGrow();
                ask();
            });
        });
    }

    /* ----------------------------------------------------- 发送提问 */
    async function ask() {
        const question = inputEl.value.trim();
        if (!question || busy) return;

        busy = true;
        sendBtn.disabled = true;
        inputEl.value = "";
        autoGrow();

        if (messagesEl.querySelector(".welcome")) messagesEl.innerHTML = "";

        appendUser(question);
        const pending = appendPending();

        const t0 = performance.now();
        try {
            const res = await fetch("/api/ask", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question }),
            });
            const data = await res.json();
            pending.remove();
            renderResult(question, data, (performance.now() - t0) / 1000);
        } catch (err) {
            pending.remove();
            appendHTML(`<div class="msg bot"><div class="bubble">
                <div class="error">请求失败：${esc(err.message)}</div></div></div>`);
        } finally {
            busy = false;
            sendBtn.disabled = false;
            inputEl.focus();
            scrollToBottom();
        }
    }

    function appendUser(text) {
        appendHTML(`<div class="msg user"><div class="bubble">${esc(text)}</div></div>`);
        scrollToBottom();
    }

    const STAGES = ["正在理解查询意图…", "正在生成 SQL…", "正在执行查询…", "正在生成结论…"];

    function appendPending() {
        const id = `p${++seq}`;
        const node = document.createElement("div");
        node.className = "msg bot";
        node.innerHTML = `<div class="bubble"><div class="progress">
            <span class="spinner"></span><span class="stage">${STAGES[0]}</span>
        </div></div>`;
        messagesEl.appendChild(node);
        scrollToBottom();

        let i = 0;
        const timer = setInterval(() => {
            i = Math.min(i + 1, STAGES.length - 1);
            const s = node.querySelector(".stage");
            if (s) s.textContent = STAGES[i];
        }, 1100);
        node._timer = timer;
        return {
            remove() {
                clearInterval(timer);
                node.remove();
            },
        };
    }

    function appendHTML(html) {
        messagesEl.insertAdjacentHTML("beforeend", html);
        return messagesEl.lastElementChild;
    }

    function scrollToBottom() {
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    /* ----------------------------------------------------- 渲染结果 */
    function renderResult(question, data, clientElapsed) {
        if (!data.ok) {
            const detail = (data.steps || [])
                .filter((s) => s.error)
                .map((s) => `第 ${s.attempt} 次：${s.error}`).join("\n");
            appendHTML(`<div class="msg bot"><div class="bubble">
                <div class="error">${esc(data.error || "查询失败")}</div>
                ${detail ? `<div class="retry-note">${esc(detail)}</div>` : ""}
            </div></div>`);
            return;
        }

        const id = `m${++seq}`;
        store.set(id, { question, data, chartInstance: null });

        const columns = data.columns || [];
        const rows = data.rows || [];
        const numeric = columns.map((_, i) =>
            rows.length > 0 && rows.every((r) => r[i] === null || isNum(r[i])));

        const node = appendHTML(`<div class="msg bot" id="${id}"><div class="bubble">
            <div class="card-title">生成的 SQL</div>
            <div class="sqlbox">
                <div class="bar"><span>MySQL · 只读校验已通过</span>
                    <button class="copy">复制</button></div>
                <pre>${esc(data.sql)}</pre>
            </div>

            <div class="card-title">查询结果（${(data.row_count || 0).toLocaleString("zh-CN")} 行）</div>
            ${rows.length ? `
                <div class="tablewrap"><table class="data">
                    <thead><tr>${columns.map((c, i) =>
                        `<th class="${numeric[i] ? "num" : ""}">${esc(c)}</th>`).join("")}</tr></thead>
                    <tbody>${rows.slice(0, 200).map((r) => `<tr>${r.map((v, i) =>
                        `<td class="${numeric[i] ? "num" : ""}">${esc(fmt(v))}</td>`).join("")}</tr>`).join("")}</tbody>
                </table></div>
                ${rows.length > 200 ? `<button class="expander">还有 ${rows.length - 200} 行未显示（导出 Word 可查看前 200 行）</button>` : ""}
            ` : `<div class="answer">没有查询到符合条件的数据。</div>`}

            <div class="chart-slot"></div>

            <div class="card-title">分析结论</div>
            <div class="answer">${esc(data.answer || "（无）")}</div>

            <div class="meta">
                <span class="tag">SQL 生成 ${secs(data.timings?.["SQL生成合计"])}</span>
                <span class="tag">数据库 ${secs(data.timings?.["数据库执行"])}</span>
                <span class="tag">结论生成 ${secs(data.timings?.["生成答案"])}</span>
                <span class="tag ${data.within_3s ? "good" : "bad"}">
                    结果就绪 ${secs(data.result_elapsed)}${data.within_3s ? " · 满足3秒" : ""}</span>
                <span class="tag">完整 ${secs(data.elapsed)}</span>
                ${data.schema_reloaded
                    ? `<span class="tag good">已自动同步新的表结构</span>` : ""}
                <span class="actions">
                    <button class="word">导出 Word</button>
                    <button class="pdf">导出 PDF</button>
                </span>
            </div>
        </div></div>`);

        if (data.chart) {
            try {
                renderChart(node.querySelector(".chart-slot"), id, data);
            } catch (e) {
                console.warn("图表渲染失败", e);
            }
        }

        node.querySelector(".copy").addEventListener("click", (e) => {
            navigator.clipboard.writeText(data.sql).then(() => {
                e.target.textContent = "已复制";
                setTimeout(() => (e.target.textContent = "复制"), 1400);
            });
        });
        node.querySelector(".word").addEventListener("click", (e) => exportWord(id, e.target));
        node.querySelector(".pdf").addEventListener("click", () => {
            scrollToBottom();
            setTimeout(() => window.print(), 250);
        });
        const expander = node.querySelector(".expander");
        if (expander) expander.addEventListener("click", () => expander.remove());

        scrollToBottom();
    }

    /* ----------------------------------------------------- 图表 */
    function renderChart(slot, id, data) {
        const { x, y, type, unit, title } = data.chart;
        const columns = data.columns;
        const rows = data.rows;
        const xi = columns.indexOf(x);
        const yi = y.map((c) => columns.indexOf(c)).filter((i) => i >= 0);
        if (xi < 0 || yi.length === 0) return;

        slot.innerHTML = `<div class="card-title">统计图表</div>
            <div class="chartbox"><div class="chart"></div></div>`;

        const chart = echarts.init(slot.querySelector(".chart"));
        const palette = ["#2563eb", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#06b6d4"];
        const axisFmt = (v) => (Math.abs(v) >= 10000 ? `${(v / 10000).toFixed(1)}万` : v.toLocaleString("zh-CN"));

        let option;
        if (type === "pie") {
            option = {
                tooltip: {
                    trigger: "item",
                    formatter: (p) => `${p.name}<br/><b>${p.value.toLocaleString("zh-CN")}</b> ${unit}（${p.percent}%）`,
                },
                // 图例自动换行（不再分页）；百分比放到扇区内部，窄容器也不会被截断
                legend: {
                    bottom: 0, itemWidth: 10, itemHeight: 8, itemGap: 10,
                    textStyle: { fontSize: 10 },
                },
                series: [{
                    type: "pie",
                    radius: ["38%", "64%"],
                    center: ["50%", "44%"],
                    minAngle: 6,
                    data: rows.map((r) => ({ name: String(r[xi]), value: r[yi[0]] })),
                    label: {
                        position: "inside",
                        formatter: "{d}%",
                        fontSize: 10,
                        fontWeight: "bold",
                        color: "#fff",
                    },
                    labelLine: { show: false },
                    itemStyle: { borderColor: "#fff", borderWidth: 2 },
                }],
            };
        } else if (type === "line") {
            option = {
                tooltip: { trigger: "axis" },
                legend: { bottom: 0 },
                grid: { left: 70, right: 28, top: 26, bottom: 46 },
                xAxis: {
                    type: "category",
                    data: rows.map((r) => String(r[xi])),
                    axisLabel: { rotate: rows.length > 12 ? 40 : 0, fontSize: 11 },
                },
                yAxis: {
                    type: "value",
                    name: unit,
                    axisLabel: { formatter: axisFmt, fontSize: 11 },
                    splitLine: { lineStyle: { type: "dashed", color: "#eef2f7" } },
                },
                series: yi.map((ci, k) => ({
                    name: columns[ci],
                    type: "line",
                    smooth: true,
                    symbolSize: 6,
                    lineStyle: { width: 2.5 },
                    areaStyle: k === 0 ? { opacity: 0.12 } : undefined,
                    itemStyle: { color: palette[k] },
                    data: rows.map((r) => r[ci]),
                })),
            };
        } else if (type === "bar_line") {
            option = {
                tooltip: { trigger: "axis" },
                legend: { bottom: 0 },
                grid: { left: 70, right: 70, top: 26, bottom: 46 },
                xAxis: {
                    type: "category",
                    data: rows.map((r) => String(r[xi])),
                    axisLabel: { rotate: rows.length > 10 ? 35 : 0, fontSize: 11 },
                },
                yAxis: [
                    { type: "value", name: columns[yi[0]], axisLabel: { formatter: axisFmt, fontSize: 11 } },
                    {
                        type: "value", name: columns[yi[1]],
                        axisLabel: { formatter: axisFmt, fontSize: 11 },
                        splitLine: { show: false },
                    },
                ],
                series: [
                    {
                        name: columns[yi[0]], type: "bar", barMaxWidth: 42,
                        itemStyle: { color: "#93c5fd", borderRadius: [4, 4, 0, 0] },
                        data: rows.map((r) => r[yi[0]]),
                    },
                    {
                        name: columns[yi[1]], type: "line", yAxisIndex: 1,
                        smooth: true, symbolSize: 6,
                        lineStyle: { width: 2.5, color: "#f59e0b" },
                        itemStyle: { color: "#f59e0b" },
                        data: rows.map((r) => r[yi[1]]),
                    },
                ],
            };
        } else {
            option = {
                tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
                grid: { left: 70, right: 28, top: 26, bottom: 46 },
                xAxis: {
                    type: "category",
                    data: rows.map((r) => String(r[xi])),
                    axisLabel: { rotate: rows.length > 8 ? 35 : 0, fontSize: 11 },
                },
                yAxis: {
                    type: "value", name: unit,
                    axisLabel: { formatter: axisFmt, fontSize: 11 },
                    splitLine: { lineStyle: { type: "dashed", color: "#eef2f7" } },
                },
                series: yi.map((ci, k) => ({
                    name: columns[ci],
                    type: "bar",
                    barMaxWidth: 46,
                    itemStyle: { color: palette[k], borderRadius: [4, 4, 0, 0] },
                    data: rows.map((r) => r[ci]),
                })),
            };
        }

        chart.setOption(option);
        store.get(id).chartInstance = chart;
        window.addEventListener("resize", () => chart.resize());
    }

    /* ----------------------------------------------------- 导出 */
    async function exportWord(id, btn) {
        const rec = store.get(id);
        if (!rec) return;
        const { question, data, chartInstance } = rec;

        btn.disabled = true;
        btn.textContent = "生成中…";
        try {
            const chartImage = chartInstance
                ? chartInstance.getDataURL({ pixelRatio: 2, backgroundColor: "#ffffff" })
                : null;

            const res = await fetch("/api/export/word", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    question,
                    answer: data.answer || "",
                    sql: data.sql || "",
                    columns: data.columns || [],
                    rows: data.rows || [],
                    row_count: data.row_count || 0,
                    chartImage,
                }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "");
            a.download = `智能查询报告_${stamp}.docx`;
            a.click();
            URL.revokeObjectURL(url);
            btn.textContent = "已导出";
        } catch (e) {
            btn.textContent = "导出失败";
            console.error(e);
        } finally {
            setTimeout(() => {
                btn.disabled = false;
                btn.textContent = "导出 Word";
            }, 1600);
        }
    }

    /* ----------------------------------------------------- 事件绑定 */
    function autoGrow() {
        inputEl.style.height = "auto";
        inputEl.style.height = Math.min(inputEl.scrollHeight, 150) + "px";
    }

    inputEl.addEventListener("input", autoGrow);
    inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            ask();
        }
    });
    sendBtn.addEventListener("click", ask);
    $("#refresh-schema").addEventListener("click", refreshSchema);

    init();
})();
