/* ==========================================================================
   Detection Page JavaScript
   Extracted from detection.html – Phase 6.1
   Reads server data from window.__DETECTION_DATA (set by inline template script).
   jQuery usage is isolated and marked for Phase 6.3 removal.
   ========================================================================== */

/* ---------- Overlay Helpers ---------- */
function showOverlay() {
    const el = document.getElementById("loadingOverlay");
    if (el) el.style.display = "flex";
}

function hideOverlay() {
    const el = document.getElementById("loadingOverlay");
    if (el) el.style.display = "none";
}

/* ---------- Color Helpers (for Chart.js) ---------- */
function generateColors(n) {
    const colors = [];
    for (let i = 0; i < n; i++) {
        const hue = i * 360 / n;
        colors.push(`hsl(${hue}, 70%, 50%)`);
    }
    return colors;
}

/* ---------- Docs Pagination Module ---------- */
const DocsPagination = {
    PAGE_SIZE: 100,
    MAX_BUTTONS: 5,
    activeCharts: {},

    init(containerId, paginationId, docsData) {
        if (!docsData || !docsData.length) return;

        this.instances = this.instances || {};
        const instance = {
            data: docsData,
            container: document.getElementById(containerId),
            pagination: document.getElementById(paginationId),
            currentPage: 0,
            charts: {}
        };
        this.instances[containerId] = instance;
        this.renderPage(instance);
        this.renderPagination(instance);
    },

    clearPage(inst) {
        Object.values(inst.charts).forEach(chart => chart.destroy());
        inst.charts = {};
        inst.container.innerHTML = '';
    },

    renderPage(inst) {
        this.clearPage(inst);
        const start = inst.currentPage * this.PAGE_SIZE;
        const end = Math.min(start + this.PAGE_SIZE, inst.data.length);

        for (let i = start; i < end; i++) {
            const doc = inst.data[i];
            const index = i;

            const docGroup = document.createElement('div');
            docGroup.className = 'doc-group mb-3 border rounded-2 shadow-sm';

            const header = document.createElement('div');
            header.className = 'dataset-header doc-header list-group-item fw-bold bg-body-tertiary d-flex justify-content-between';
            header.style.cursor = 'pointer';
            header.innerHTML = `
                <div style="margin-left:15px;">Document ${doc.id}</div>
                <span class="chev" style="transition: transform .2s;">▸</span>
            `;

            const contentDiv = document.createElement('div');
            contentDiv.className = 'list-group doc-content';
            contentDiv.style.display = 'none';
            contentDiv.dataset.initialized = "false";

            header.addEventListener('click', () => {
                const chev = header.querySelector('.chev');
                const open = contentDiv.style.display === 'block';

                if (!open) {
                    contentDiv.style.display = 'block';
                    chev.style.transform = 'rotate(90deg)';

                    if (contentDiv.dataset.initialized === "false") {
                        contentDiv.dataset.initialized = "true";

                        const flexDiv = document.createElement('div');
                        flexDiv.style.display = 'flex';
                        flexDiv.style.maxHeight = '350px';

                        const leftDiv = document.createElement('div');
                        leftDiv.style.flex = '1';
                        leftDiv.style.padding = '10px';
                        leftDiv.style.borderRight = '1px solid var(--bs-border-color)';
                        leftDiv.innerHTML = `<h5 style="text-align:center;">Text</h5><hr><p>${doc.text}</p>`;

                        const rightDiv = document.createElement('div');
                        rightDiv.style.flex = '1';
                        rightDiv.style.padding = '10px';
                        rightDiv.style.textAlign = 'center';
                        rightDiv.innerHTML = `<h5>Chart</h5><hr>`;

                        const canvas = document.createElement('canvas');
                        canvas.style.width = '200px';
                        canvas.style.height = '200px';
                        canvas.style.display = 'block';
                        canvas.style.margin = '0 auto';
                        rightDiv.appendChild(canvas);

                        flexDiv.appendChild(leftDiv);
                        flexDiv.appendChild(rightDiv);
                        contentDiv.appendChild(flexDiv);

                        const topicKeys = Object.keys(doc.topics);
                        const topicValues = Object.values(doc.topics);

                        inst.charts[index] = new Chart(canvas, {
                            type: 'pie',
                            data: {
                                labels: topicKeys.map(t => "Topic " + t.replace('(', '\n').replace(')', '').replace('||', '\n')),
                                datasets: [{
                                    data: topicValues,
                                    backgroundColor: generateColors(topicKeys.length)
                                }]
                            },
                            options: {
                                responsive: false,
                                maintainAspectRatio: false,
                                plugins: { legend: { display: false } }
                            }
                        });
                    }
                } else {
                    contentDiv.style.display = 'none';
                    chev.style.transform = 'rotate(0deg)';
                }
            });

            docGroup.appendChild(header);
            docGroup.appendChild(contentDiv);
            inst.container.appendChild(docGroup);
        }
    },

    renderPagination(inst) {
        inst.pagination.innerHTML = '';
        const totalPages = Math.ceil(inst.data.length / this.PAGE_SIZE);

        const tempBtn = document.createElement('button');
        tempBtn.style.visibility = 'hidden';
        tempBtn.style.position = 'absolute';
        tempBtn.innerText = totalPages;
        document.body.appendChild(tempBtn);

        const self = this;
        const createButton = (text, pageNum, disabled = false, active = false) => {
            const btn = document.createElement('button');
            btn.style.width = '60px';
            btn.innerText = text;
            if (disabled) btn.disabled = true;
            if (active) btn.classList.add('active');
            btn.addEventListener('click', () => {
                inst.currentPage = pageNum;
                self.renderPage(inst);
                self.renderPagination(inst);
            });
            inst.pagination.appendChild(btn);
        };

        createButton('Prev', Math.max(0, inst.currentPage - 1), inst.currentPage === 0);

        let startPage = Math.max(0, inst.currentPage - Math.floor(this.MAX_BUTTONS / 2));
        let endPage = startPage + this.MAX_BUTTONS - 1;
        if (endPage >= totalPages) {
            endPage = totalPages - 1;
            startPage = Math.max(0, endPage - this.MAX_BUTTONS + 1);
        }

        let btnWidth = tempBtn.offsetWidth + 10;
        if (startPage > 0) {
            const btn1 = document.createElement('button');
            btn1.style.width = btnWidth + 'px';
            btn1.innerText = '1';
            btn1.addEventListener('click', () => {
                inst.currentPage = 0;
                self.renderPage(inst);
                self.renderPagination(inst);
            });
            inst.pagination.appendChild(btn1);
            if (startPage > 1) {
                const dots = document.createElement('span');
                dots.innerText = '...';
                inst.pagination.appendChild(dots);
            }
        }

        for (let i = startPage; i <= endPage; i++) {
            const btn = document.createElement('button');
            btn.style.width = btnWidth + 'px';
            btn.innerText = (i + 1);
            if (i === inst.currentPage) btn.classList.add('active');
            btn.addEventListener('click', ((page) => () => {
                inst.currentPage = page;
                self.renderPage(inst);
                self.renderPagination(inst);
            })(i));
            inst.pagination.appendChild(btn);
        }

        if (endPage < totalPages - 1) {
            if (endPage < totalPages - 2) {
                const dots = document.createElement('span');
                dots.innerText = '...';
                inst.pagination.appendChild(dots);
            }
            const btnLast = document.createElement('button');
            btnLast.style.width = btnWidth + 'px';
            btnLast.innerText = totalPages;
            btnLast.addEventListener('click', () => {
                inst.currentPage = totalPages - 1;
                self.renderPage(inst);
                self.renderPagination(inst);
            });
            inst.pagination.appendChild(btnLast);
        }

        createButton('Next', Math.min(totalPages - 1, inst.currentPage + 1), inst.currentPage === totalPages - 1);
        document.body.removeChild(tempBtn);
    }
};

/* ---------- D3 Topic Visualization ---------- */
function drawTopicVis(topicsData) {
    console.log("[DEBUG] drawTopicVis called with topicsData:", topicsData);
    const container = document.getElementById("topicVis");
    if (!container) return;
    container.innerHTML = "";

    const width = container.clientWidth;
    const height = container.clientHeight;

    const svg = d3.select(container)
        .append("svg")
        .attr("width", width)
        .attr("height", height);

    svg.append("rect")
        .attr("x", 0).attr("y", 0)
        .attr("width", width).attr("height", height)
        .style("fill", "rgba(255,255,255,0.6)");

    console.log("[DEBUG] SVG width:", width, "height:", height);

    const margin = { top: 20, right: 20, bottom: 40, left: 40 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    const g = svg.append("g")
        .attr("transform", `translate(${margin.left},${margin.top})`);

    const xExtent = d3.extent(topicsData, d => d.x);
    const yExtent = d3.extent(topicsData, d => d.y);

    const xScale = d3.scaleLinear().domain(xExtent).range([0, innerWidth]);
    const yScale = d3.scaleLinear().domain(yExtent).range([innerHeight, 0]);

    const xMid = (xExtent[0] + xExtent[1]) / 2;
    const yMid = (yExtent[0] + yExtent[1]) / 2;

    g.append("g")
        .attr("transform", `translate(0, ${yScale(yMid)})`)
        .call(d3.axisBottom(xScale).ticks(5));

    g.append("g")
        .attr("transform", `translate(${xScale(xMid)},0)`)
        .call(d3.axisLeft(yScale).ticks(5));

    const sizeExtent = d3.extent(topicsData, d => d.size);
    const sizeScale = d3.scaleLinear().domain(sizeExtent).range([20, 60]);

    const tooltip = d3.select("body")
        .append("div")
        .attr("class", "tooltip-topic")
        .style("position", "absolute")
        .style("padding", "8px")
        .style("background-color", "rgba(0,0,0,0.7)")
        .style("color", "#fff")
        .style("border-radius", "4px")
        .style("pointer-events", "none")
        .style("opacity", 0);

    const normPos = d => ((d.x - xExtent[0]) / (xExtent[1] - xExtent[0]) + (d.y - yExtent[0]) / (yExtent[1] - yExtent[0])) / 2;

    const nodes = g.selectAll("g.node")
        .data(topicsData)
        .enter()
        .append("g")
        .attr("class", "node")
        .attr("transform", d => `translate(${xScale(d.x)},${yScale(d.y)})`)
        .style("cursor", "pointer")
        .on("mousemove", function (event, d) {
            let html_node = `<strong>Topic ${d.id} ${d.label}</strong><br>`;
            ["EN", "ES", "IT", "DE"].forEach(lang => {
                const key = `keywords_${lang}`;
                if (d[key]?.length) {
                    html_node += `<b>${lang}:</b> ${d[key].join(", ")}<br>`;
                }
            });
            tooltip
                .style("opacity", 1)
                .html(html_node)
                .style("left", (event.pageX + 15) + "px")
                .style("top", (event.pageY + 15) + "px");
        })
        .on("mouseout", () => tooltip.style("opacity", 0))
        .on("click", function (event, d) {
            if (window.currentVisibleTopics.includes(d.id)) {
                window.currentVisibleTopics = window.currentVisibleTopics.filter(x => x !== d.id);
                d3.select(this).select("circle").style("stroke", "none");
            } else {
                window.currentVisibleTopics.push(d.id);
                d3.select(this).select("circle")
                    .style("stroke", "rgba(255,0,0,0.8)")
                    .style("stroke-width", 2);
            }
            console.log("Selected topics:", [...window.currentVisibleTopics]);
            // Update select-all/clear button visibility if bound
            if (typeof window._topicVisSelectCallback === 'function') window._topicVisSelectCallback();
        });

    nodes.append("circle")
        .attr("r", d => sizeScale(d.size))
        .style("fill", d => d3.interpolateViridis(normPos(d)))
        .style("opacity", 0.85)
        .each(function (d) {
            if (window.currentVisibleTopics.includes(d.id)) {
                d3.select(this)
                    .style("stroke", "rgba(255,0,0,0.8)")
                    .style("stroke-width", 2);
            }
        });

    nodes.select("circle")
        .on("mouseover", function (event, d) {
            d3.select(this)
                .transition().duration(200)
                .attr("r", sizeScale(d.size) * 1.1)
                .style("fill", "rgba(255,0,0,0.5)");
        })
        .on("mouseout", function (event, d) {
            d3.select(this)
                .transition().duration(200)
                .attr("r", sizeScale(d.size))
                .style("fill", d => d3.interpolateViridis(normPos(d)));
        });

    nodes.append("text")
        .text(d => d.id)
        .attr("text-anchor", "middle")
        .attr("alignment-baseline", "middle")
        .style("fill", "#fff")
        .style("font-size", "12px")
        .style("pointer-events", "none");
}

/* ---------- Topic View Toggle ---------- */
function initTopicViewToggle(topicsData) {
    console.log("[DEBUG] initTopicViewToggle called with topicsData:", topicsData);
    window.currentView = "visual";
    window.currentVisibleTopics = [];

    const btnVisual = document.getElementById("btn-visual");
    const btnText = document.getElementById("btn-text");
    const btnDocs1 = document.getElementById("btn-docs1");
    const btnDocs2 = document.getElementById("btn-docs2");
    const topicVis = document.getElementById("topicVis");
    const topicDocs1 = document.getElementById("topicDocs1");
    const topicDocs2 = document.getElementById("topicDocs2");
    const topicAccordion = document.querySelector(".topic-accordion");

    console.log("[DEBUG] Elements found:", { btnVisual, btnText, btnDocs1, btnDocs2, topicVis, topicDocs1, topicDocs2, topicAccordion });

    function setActive(active) {
        [btnVisual, btnText, btnDocs1, btnDocs2].forEach(btn => {
            if (!btn) return;
            if (btn === active) {
                btn.classList.add("active", "btn-primary");
                btn.classList.remove("btn-outline-primary");
            } else {
                btn.classList.remove("active", "btn-primary");
                btn.classList.add("btn-outline-primary");
            }
        });
    }

    if (btnVisual) {
        btnVisual.addEventListener("click", () => {
            console.log("[DEBUG] Visual button clicked");
            window.currentView = "visual";
            if (topicVis) topicVis.style.display = "block";
            if (topicDocs1) topicDocs1.style.display = "none";
            if (topicDocs2) topicDocs2.style.display = "none";
            if (topicAccordion) topicAccordion.style.display = "none";
            setActive(btnVisual);
            drawTopicVis(topicsData);
        });
    }

    if (btnText) {
        btnText.addEventListener("click", () => {
            console.log("[DEBUG] Text button clicked");
            window.currentView = "text";
            if (topicVis) topicVis.style.display = "none";
            if (topicDocs1) topicDocs1.style.display = "none";
            if (topicDocs2) topicDocs2.style.display = "none";
            if (topicAccordion) topicAccordion.style.display = "block";
            setActive(btnText);
        });
    }

    if (btnDocs1) {
        btnDocs1.addEventListener("click", () => {
            window.currentView = "docs";
            if (topicVis) topicVis.style.display = "none";
            if (topicDocs1) topicDocs1.style.display = "flex";
            if (topicDocs2) topicDocs2.style.display = "none";
            if (topicAccordion) topicAccordion.style.display = "none";
            setActive(btnDocs1);
        });
    }

    if (btnDocs2) {
        btnDocs2.addEventListener("click", () => {
            window.currentView = "docs";
            if (topicVis) topicVis.style.display = "none";
            if (topicDocs1) topicDocs1.style.display = "none";
            if (topicDocs2) topicDocs2.style.display = "flex";
            if (topicAccordion) topicAccordion.style.display = "none";
            setActive(btnDocs2);
        });
    }

    drawTopicVis(topicsData);

    window.addEventListener("resize", () => {
        if (window.currentView === "visual") {
            drawTopicVis(topicsData);
        }
    });

    // --- Select All / Clear All topic buttons ---
    const btnSelectAll = document.getElementById('btn-select-all-topics');
    const btnClearAll = document.getElementById('btn-clear-all-topics');

    function updateSelectAllVisibility() {
        if (!btnSelectAll || !btnClearAll) return;
        const hasSelected = window.currentVisibleTopics.length > 0 ||
            Array.from(document.querySelectorAll('.topic-checkbox')).some(cb => cb.checked);
        btnSelectAll.style.display = hasSelected ? 'none' : '';
        btnClearAll.style.display = hasSelected ? '' : 'none';
    }

    if (btnSelectAll) {
        btnSelectAll.addEventListener('click', () => {
            if (window.currentView === 'visual') {
                // Select every node
                window.currentVisibleTopics = topicsData.map(d => d.id);
                // Update visual ring
                d3.selectAll('.node circle')
                    .style('stroke', 'rgba(255,0,0,0.8)')
                    .style('stroke-width', 2);
            } else if (window.currentView === 'text') {
                document.querySelectorAll('.topic-checkbox').forEach(cb => cb.checked = true);
            }
            updateSelectAllVisibility();
        });
    }

    if (btnClearAll) {
        btnClearAll.addEventListener('click', () => {
            if (window.currentView === 'visual') {
                window.currentVisibleTopics = [];
                d3.selectAll('.node circle')
                    .style('stroke', 'none')
                    .style('stroke-width', 0);
            } else if (window.currentView === 'text') {
                document.querySelectorAll('.topic-checkbox').forEach(cb => cb.checked = false);
            }
            updateSelectAllVisibility();
        });
    }

    // Keep visibility in sync when topics are toggled individually (visual click is handled inside drawTopicVis)
    document.querySelectorAll('.topic-checkbox').forEach(cb => {
        cb.addEventListener('change', updateSelectAllVisibility);
    });
    // Patch drawTopicVis click side-effect to call updateSelectAllVisibility
    const _origDraw = drawTopicVis;
    window._topicVisSelectCallback = updateSelectAllVisibility;
}

/* ---------- Exit Warning Modal ---------- */
let shouldWarn = false;

function initExitWarning() {
    window.addEventListener("beforeunload", e => {
        if (!shouldWarn) return;
        e.preventDefault();
        e.returnValue = "";
    });

    document.addEventListener("click", e => {
        const el = e.target.closest("a, button[data-navigate]");
        if (!el) return;
        if (!shouldWarn) return;
        if (el.hasAttribute("data-no-warning")) return;

        e.preventDefault();
        const url = el.href || el.dataset.navigate;
        showExitModal(url);
    });

    const modal = document.getElementById("exitModal");
    const exitYes = document.getElementById("exitYes");
    const exitNo = document.getElementById("exitNo");
    const exitClose = document.getElementById("exitModalClose");

    function showExitModal(url) {
        if (!modal) return;
        modal.style.display = "flex";
        requestAnimationFrame(() => modal.classList.add("show"));

        exitYes.onclick = () => {
            shouldWarn = false;
            window.removeEventListener("beforeunload", () => { });
            window.location.href = url;
        };

        exitNo.onclick = exitClose.onclick = () => {
            modal.classList.remove("show");
            modal.addEventListener('transitionend', () => {
                modal.style.display = "none";
            }, { once: true });
        };
    }
}

/* ---------- Label Color Helper ---------- */
function getColorForLabel(label) {
    const defaultColors = {
        'CONTRADICTION': { bg: '#dc3545', text: '#fff' },
        'CULTURAL_DISCREPANCY': { bg: '#ffc107', text: '#212529' },
        'NOT_ENOUGH_INFO': { bg: '#17a2b8', text: '#fff' },
        'NO_DISCREPANCY': { bg: '#28a745', text: '#fff' },
    };
    if (defaultColors[label]) return defaultColors[label];

    // hash string to pick from color palette
    const palette = [
        { bg: '#6f42c1', text: '#fff' }, // purple
        { bg: '#fd7e14', text: '#fff' }, // orange
        { bg: '#20c997', text: '#fff' }, // teal
        { bg: '#e83e8c', text: '#fff' }, // pink
        { bg: '#6610f2', text: '#fff' }, // indigo
        { bg: '#0dcaf0', text: '#212529' }, // cyan
        { bg: '#198754', text: '#fff' }, // green
        { bg: '#052c65', text: '#fff' }, // dark blue
        { bg: '#d63384', text: '#fff' }, // light pink
        { bg: '#6c757d', text: '#fff' }  // grey
    ];
    let hash = 0;
    for (let i = 0; i < label.length; i++) {
        hash = label.charCodeAt(i) + ((hash << 5) - hash);
    }
    const index = Math.abs(hash) % palette.length;
    return palette[index];
}

/* ---------- Label Color Updater ---------- */
// jQuery — marked for Phase 6.3 removal
function updateColors() {
    // final_label
    $('.final-label-select').each(function () {
        var value = $(this).val();
        var c = getColorForLabel(value);
        $(this).css({ 'background-color': c.bg, 'color': c.text });
        $(this).siblings('.custom-arrow').css('color', c.text);
    });

    // label
    $('.badge-label').each(function () {
        var value = $(this).data('label-value');
        var c = getColorForLabel(value);
        $(this).css({ 'background-color': c.bg, 'color': c.text });
    });

    // quick-filter bar labels
    $('.label-filter-quick').each(function () {
        var val = $(this).data('lf-value');
        if (val && val !== 'ALL') {
            var c = getColorForLabel(val);
            $(this).css({ 'background-color': c.bg, 'color': c.text });
        }
    });

    // Update max 5 category selection constraint
    const checkboxes = document.querySelectorAll('.category-checkbox');
    if (checkboxes.length > 0) {
        document.addEventListener('change', function (e) {
            if (e.target.matches('.category-checkbox')) {
                const checked = Array.from(checkboxes).filter(cb => cb.checked);
                const warning = document.getElementById('categoryWarning');

                if (checked.length >= 5) {
                    checkboxes.forEach(cb => {
                        if (!cb.checked) cb.disabled = true;
                    });
                    if (warning) {
                        warning.innerHTML = "⚠️ Selecting more than 5 categories may reduce detection accuracy due to LLM context limitations.";
                        warning.style.display = 'block';
                    }
                } else {
                    checkboxes.forEach(cb => cb.disabled = false);
                    if (warning) warning.style.display = 'none';
                }
            }
        });

        // Trigger manually on init to lock if started with 5
        const checked = Array.from(checkboxes).filter(cb => cb.checked);
        if (checked.length >= 5) {
            checkboxes.forEach(cb => {
                if (!cb.checked) cb.disabled = true;
            });
            const warning = document.getElementById('categoryWarning');
            if (warning) {
                warning.innerHTML = "⚠️ Selecting more than 5 categories may reduce detection accuracy due to LLM context limitations.";
                warning.style.display = 'block';
            }
        }
    }
}

/* ---------- Column Default Visibility ---------- */
function initDefaultColumnVisibility() {
    var defaultVisibleCols = ['question', 'anchor_passage', 'comparison_passage', 'anchor_answer', 'comparison_answer', 'label', 'final_label', 'reason'];

    document.querySelectorAll('.column-checkbox').forEach(function (checkbox) {
        var colValue = checkbox.value;
        if (colValue === 'ALL') {
            checkbox.checked = true;
        } else {
            checkbox.checked = defaultVisibleCols.includes(colValue);
        }
    });
}

/* ---------- DataTable Initializer ---------- */
// jQuery — marked for Phase 6.3 removal
function initResultsDataTable() {
    const DATA = window.__DETECTION_DATA || {};
    var defaultVisibleCols = ['question', 'anchor_passage', 'comparison_passage', 'anchor_answer', 'comparison_answer', 'label', 'final_label', 'reason'];
    var columns = DATA.columnsJson;
    var allResultCols = DATA.resultColumns;
    var nonOrderable = DATA.nonOrderableIndices;

    if (!columns || !allResultCols) return;

    var visibleIndices = [];
    for (var i = 0; i < columns.length; i++) {
        if (defaultVisibleCols.includes(columns[i].name)) visibleIndices.push(i);
    }

    var table = $('#resultsTable').DataTable({
        data: [],
        columns: columns,
        columnDefs: [
            {
                targets: "_all",
                createdCell: function (td) {
                    td.classList.add('truncated');
                }
            },
            { orderable: false, targets: nonOrderable },
        ],
        pageLength: 25,
        lengthMenu: [[10, 25, 50, 100, -1], ["10", "25", "50", "100", "All"]],
        scrollY: "50vh",
        scrollCollapse: true,
        orderCellsTop: true,
        autoWidth: false,
        language: {
            zeroRecords: "No records were found",
            info: "Showing _START_ to _END_ of _TOTAL_ records",
            infoEmpty: "Showing 0 records",
            infoFiltered: "(filtered from _MAX_ total)",
            lengthMenu: "Show _MENU_ rows"
        }
    });

    var defaultLabels = ['CONTRADICTION', 'CULTURAL_DISCREPANCY', 'NOT_ENOUGH_INFO', 'NO_DISCREPANCY'];
    var dynamicLabels = DATA.uniqueLabels || defaultLabels;

    var possibleValues = {
        'label': dynamicLabels.slice(),
        'final_label': dynamicLabels.slice()
    };

    var activeFilters = {
        'label': possibleValues['label'].slice(),
        'final_label': possibleValues['final_label'].slice()
    };

    function applyVisibleColumns(visibleColumns) {
        table.columns().every(function (index) {
            var colName = this.settings()[0].aoColumns[index].name;
            this.visible(visibleColumns.includes(colName));
        });
    }

    var visibleColumns = $('.column-checkbox:checked').map(function () {
        return $(this).val();
    }).get();

    if (visibleColumns.length === 0) {
        visibleColumns = allResultCols.filter(c => defaultVisibleCols.includes(c));
    }

    if (visibleColumns.length === allResultCols.length) {
        $('#columnAll').prop('checked', true);
    } else {
        $('#columnAll').prop('checked', false);
    }

    applyVisibleColumns(visibleColumns);

    $('body').on('change', '.column-all', function () {
        var checked = $(this).prop('checked');
        if (checked) {
            $('.column-checkbox').prop('checked', true);
            visibleColumns = allResultCols.slice();
        } else {
            $('.column-checkbox').prop('checked', false);
            visibleColumns = [];
        }
        applyVisibleColumns(visibleColumns);
    });

    $('body').on('change', '.column-checkbox', function () {
        visibleColumns = $('.column-checkbox:checked').map(function () {
            return $(this).val();
        }).get();

        if (visibleColumns.length === allResultCols.length) {
            $('#columnAll').prop('checked', true);
        } else {
            $('#columnAll').prop('checked', false);
        }

        applyVisibleColumns(visibleColumns);
    });

    updateColors();
    $('#resultsTable').on('draw.dt', function () {
        updateColors();
    });

    $('body').on('change', '.final-label-select', function () {
        updateColors();
        var row = $(this).closest('tr');
        table.row(row).invalidate().draw(false);
    });

    // Column filter
    $.fn.dataTable.ext.search.push(function (settings, data, dataIndex) {
        for (var colName in activeFilters) {
            var selectedValues = activeFilters[colName];
            if (!selectedValues || selectedValues.length === 0) return false;

            var colIndex = table.column(colName + ":name").index();
            var cellNode = table.cell(dataIndex, colIndex).node();
            var cellValue;

            if (colName === 'final_label') {
                cellValue = $(cellNode).find('select.final-label-select').val();
            } else {
                var cellHtml = $(cellNode).html() || "";
                cellValue = cellHtml.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
            }

            if (!selectedValues.includes(cellValue)) return false;
        }
        return true;
    });

    $('body').on('change', '.final-label-select', function () {
        var row = $(this).closest('tr');
        var table = $('#resultsTable').DataTable();
        table.row(row).invalidate().draw(false);

        activeFilters['final_label'] = table.rows().nodes().to$().find('.final-label-select').map(function () {
            return $(this).val();
        }).get();
    });

    // Filter checkbox
    $('body').on('click', '.filter-checkbox', function (e) {
        e.stopPropagation();

        var checkbox = $(this);
        var value = checkbox.data('value');
        var dropdown = checkbox.closest('.dropdown-menu');
        var btn = dropdown.siblings('.filter-btn');
        var colName = btn.data('column');
        var allCheckbox = dropdown.find('input.filter-checkbox[data-value="ALL"]');

        if (!activeFilters[colName]) activeFilters[colName] = [];

        if (value === "ALL") {
            if (checkbox.prop('checked')) {
                activeFilters[colName] = possibleValues[colName].slice();
                dropdown.find('input.filter-checkbox').prop('checked', true);
            } else {
                activeFilters[colName] = [];
                dropdown.find('input.filter-checkbox').prop('checked', false);
            }
        } else {
            if (checkbox.prop('checked')) {
                if (!activeFilters[colName].includes(value)) activeFilters[colName].push(value);
            } else {
                activeFilters[colName] = activeFilters[colName].filter(v => v !== value);
            }

            if (activeFilters[colName].length === possibleValues[colName].length) {
                allCheckbox.prop('checked', true);
            } else {
                allCheckbox.prop('checked', false);
            }
        }

        if (activeFilters[colName].length > 0) {
            btn.removeClass('btn-light').addClass('btn-primary');
        } else {
            btn.removeClass('btn-primary').addClass('btn-light');
        }

        table.draw();
    });

    $('body').on('click', '.dropdown-item', function (e) {
        e.stopPropagation();
    });

    $('.filter-checkbox').each(function () {
        var checkbox = $(this);
        var value = checkbox.data('value');
        var colName = checkbox.closest('.dropdown-menu').siblings('.filter-btn').data('column');
        if (value === "ALL") {
            checkbox.prop('checked', activeFilters[colName].length === possibleValues[colName].length);
        } else {
            checkbox.prop('checked', activeFilters[colName].includes(value));
        }
    });

    table.draw();
    initLabelFilterBar(table, activeFilters, possibleValues);
}

/* ---------- Label Quick-Filter Bar ---------- */
function initLabelFilterBar(table, activeFilters, possibleValues) {
    const bar = document.getElementById('label-filter-bar');
    if (!bar) return;

    const countEl = document.getElementById('label-filter-count');
    const allBtn = document.getElementById('lf-btn-all');
    const quickBtns = bar.querySelectorAll('.label-filter-quick');

    // Update row-count badge after every DataTable draw
    table.on('draw.dt', function () {
        const info = table.page.info();
        if (countEl) {
            countEl.textContent = info.recordsDisplay === info.recordsTotal
                ? `${info.recordsTotal} rows`
                : `${info.recordsDisplay} / ${info.recordsTotal} rows`;
        }
    });

    function setAllActive() {
        allBtn.classList.add('active');
        quickBtns.forEach(b => b.style.opacity = '1');

        // Reset both filter columns to show all values
        ['label', 'final_label'].forEach(col => {
            activeFilters[col] = possibleValues[col].slice();
            // Sync hidden checkboxes too
            document.querySelectorAll(`.filter-checkbox[data-value]`).forEach(cb => {
                const colBtn = cb.closest('.dropdown-menu')?.previousElementSibling;
                if (colBtn && colBtn.dataset.column === col) cb.checked = true;
            });
        });
        table.draw();
    }

    function setFilter(value) {
        allBtn.classList.remove('active');
        quickBtns.forEach(b => {
            b.style.opacity = b.dataset.lfValue === value ? '1' : '0.45';
        });

        ['label', 'final_label'].forEach(col => {
            activeFilters[col] = [value];
            document.querySelectorAll(`.filter-checkbox`).forEach(cb => {
                const colBtn = cb.closest('.dropdown-menu')?.previousElementSibling;
                if (colBtn && colBtn.dataset.column === col) {
                    cb.checked = (cb.dataset.value === value || cb.dataset.value === 'ALL') ? false : false;
                    cb.checked = (cb.dataset.value === value);
                }
            });
        });
        table.draw();
    }

    allBtn.addEventListener('click', setAllActive);
    quickBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Toggle: clicking the active filter again resets to All
            if (btn.style.opacity !== '0.45' && !allBtn.classList.contains('active')) {
                setAllActive();
            } else {
                setFilter(btn.dataset.lfValue);
            }
        });
    });
}

/* ---------- Load Result Chunk ---------- */
// jQuery — marked for Phase 6.3 removal
async function loadChunk(start) {
    showOverlay();
    const urlParams = new URLSearchParams(window.location.search);
    const res = await fetch(`/results_chunk?start=${start}&TM=${urlParams.get('TM')}&topics=${urlParams.get('topics')}`);
    const data = await res.json();

    const rows = data.rows;
    const columns = data.columns;

    // Update dynamic labels if chunk returns them
    if (data.unique_labels && window.__DETECTION_DATA) {
        window.__DETECTION_DATA.uniqueLabels = data.unique_labels;
    }

    const table = $('#resultsTable').DataTable();
    table.clear();

    const formattedRows = rows.map(row => {
        return columns.map(col => {
            const colName = col.name;

            if (colName === "final_label") {
                const labelOptions = (window.__DETECTION_DATA || {}).uniqueLabels || ["CONTRADICTION", "CULTURAL_DISCREPANCY", "NOT_ENOUGH_INFO", "NO_DISCREPANCY"];
                return `<div class="custom-select-container">
                        <select class="final-label-select">
                            ${labelOptions
                        .map(opt => `<option value="${opt}" ${row[colName] === opt ? "selected" : ""}>${opt}</option>`)
                        .join("")}
                        </select>
                        <span class="custom-arrow">▼</span>
                    </div>`;
            }

            if (colName === "label") {
                return `<span class="badge-label" data-label-value="${row[colName] ?? ''}">
                        ${row[colName] ?? ''}
                    </span>`;
            }

            let text = row[colName] ?? '';
            if (typeof text === "string") {
                const words = text.split(" ");
                if (words.length > 50) text = words.slice(0, 50).join(" ") + "...";
            }
            return text;
        });
    });

    table.rows.add(formattedRows).draw();

    $('body').off('change', '.final-label-select');
    $('body').on('change', '.final-label-select', function () {
        updateColors();
    });
    hideOverlay();
}

/* ---------- Range Selector ---------- */
function initRangeSelector() {
    const selector = document.getElementById("rangeSelector");
    if (!selector) return;
    selector.addEventListener("change", function () {
        loadChunk(this.value);
    });
}

/* ---------- DataTable Controls Layout ---------- */
// jQuery — marked for Phase 6.3 removal
function initDatatableLayout() {
    var lengthDiv = $('#resultsTable_length');
    var label = lengthDiv.find('label');
    var select = label.find('select');

    label.contents().filter(function () {
        return this.nodeType === 3;
    }).remove();

    label.prepend('<span style="white-space: nowrap;">Show entries</span> ');

    label.css({
        display: 'flex',
        alignItems: 'center',
        gap: '5px',
        marginBottom: '0'
    });

    select.addClass('ms-2');

    $('#datatable-controls-1').append(lengthDiv);

    $('#datatable-controls-2').append(
        $('#resultsTable_info'),
        $('#resultsTable_paginate'),
        $('#exportXlsxBtn')
    );

    $('#resultsTable_filter').remove();

    document.getElementById('jumbotron-detection').style.marginBottom = '15px';
    document.getElementById('jumbotron-detection').style.marginTop = '-1rem';
    document.getElementById('jumbotron-detection').style.height = '68vh';
    document.getElementById('resultsTable_info').style.marginLeft = '10px';
    document.getElementById('resultsTable_length').style.marginLeft = 'auto';
}

/* ---------- XLSX Export ---------- */
// jQuery — marked for Phase 6.3 removal
function initXlsxExport() {
    const DATA = window.__DETECTION_DATA || {};
    var table = $('#resultsTable').DataTable();

    $('#exportXlsxBtn').on('click', function () {
        exportTableToXLSX();
    });

    function exportTableToXLSX(filename = 'results_mind.xlsx') {
        const selector = document.getElementById('exportXlsxBtn');
        if (!selector) {
            console.error("Selector not found!");
            return;
        }

        selector.style.pointerEvents = 'none';
        selector.style.opacity = '0.6';
        selector.classList.add('disabled');

        var originalHTML = selector.innerHTML;
        selector.innerHTML = `
            <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
            Waiting...
        `;

        try {
            var ws_data = [];
            var headers = DATA.resultColumns;
            ws_data.push(headers);

            var columnVisibility = [];
            table.columns().every(function (idx) {
                columnVisibility[idx] = this.visible();
            });

            table.columns().visible(true, false);

            table.rows().nodes().each(function (tr) {
                var row_data = [];
                var $tr = $(tr);

                headers.forEach(function (colName) {
                    var colIdx = table.column(colName + ":name").index();
                    var $td = $tr.find('td').eq(colIdx);
                    var cell;

                    if ($td.find('select.final-label-select').length) {
                        cell = $td.find('select.final-label-select').val() || '';
                    } else if ($td.find('.badge-label').length) {
                        cell = $td.find('.badge-label').data('label-value') || '';
                    } else {
                        var cellHtml = $td.html() || '';
                        cell = cellHtml
                            .replace(/<br\s*\/?>/gi, '\n')
                            .replace(/<[^>]+>/g, '')
                            .replace(/\s+/g, ' ')
                            .trim();
                    }
                    row_data.push(cell);
                });

                ws_data.push(row_data);
            });

            table.columns().every(function (idx) {
                this.visible(columnVisibility[idx], false);
            });
            table.draw(false);

            var wb = XLSX.utils.book_new();
            var ws = XLSX.utils.aoa_to_sheet(ws_data);
            XLSX.utils.book_append_sheet(wb, ws, "Sheet1");

            var wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
            var blob = new Blob([wbout], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

            var formData = new FormData();
            formData.append('file', blob, filename);
            const urlParams = new URLSearchParams(window.location.search);
            formData.append('TM', urlParams.get('TM') || '');
            formData.append('topics', urlParams.get('topics') || '');
            formData.append('start', document.getElementById("rangeSelector").value);

            fetch('/update_results', {
                method: 'POST',
                body: formData
            })
                .then(response => {
                    if (response.ok) return response.blob();
                    return response.json().then(err => { throw new Error(err.message || 'Error in backend') });
                })
                .then(blob => {
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.style.display = 'none';
                    a.href = url;
                    a.download = 'mind_results_updated.xlsx';
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                })
                .catch(err => {
                    console.error("Error downloading XLSX:", err);
                })
                .finally(() => {
                    selector.style.pointerEvents = 'auto';
                    selector.style.opacity = '1';
                    selector.classList.remove('disabled');
                    selector.innerHTML = originalHTML;
                });
        }
        catch (e) {
            selector.style.pointerEvents = 'auto';
            selector.style.opacity = '1';
            selector.classList.remove('disabled');
            selector.innerHTML = originalHTML;
        }
    }
}

/* ---------- LLM Config Toggle ---------- */
function initLLMConfigToggle() {
    const selectType = document.getElementById("llmSelect_type");
    if (!selectType) return;

    const geminiDiv = document.getElementById("llmSelect_gemini");
    const ollamaDiv = document.getElementById("llmSelect_ollama");
    const ollamaServer = document.getElementById("server_ollama");
    const gptDiv = document.getElementById("llmSelect_gpt");
    const gptApiKey = document.getElementById("gptApiKey");

    function show(el) { if (el) { el.classList.add("d-flex"); el.classList.remove("d-none"); } }
    function hide(el) { if (el) { el.classList.remove("d-flex"); el.classList.add("d-none"); } }

    function updateVisibility() {
        const value = selectType.value;

        if (value === "GPT") {
            hide(geminiDiv); hide(ollamaDiv); hide(ollamaServer);
            show(gptDiv); show(gptApiKey);
        } else if (value === "ollama") {
            hide(geminiDiv); hide(gptDiv); hide(gptApiKey);
            show(ollamaDiv); show(ollamaServer);
        } else if (value === "gemini") {
            show(geminiDiv);
            hide(ollamaDiv); hide(ollamaServer); hide(gptDiv); hide(gptApiKey);
        } else {
            // default / config-driven — hide everything, backend uses Prompter.from_config()
            hide(geminiDiv); hide(ollamaDiv); hide(ollamaServer); hide(gptDiv); hide(gptApiKey);
        }
    }

    updateVisibility();
    selectType.addEventListener("change", updateVisibility);
}

/* ---------- LLM Model Selector ---------- */
function initModelSelector() {
    const DATA = window.__DETECTION_DATA || {};
    const availableModels = DATA.availableModels;
    if (!availableModels) return;

    const serverSelect = document.getElementById("server_ollama_input");
    const modelSelect = document.getElementById("llmSelect_ollama_input");
    if (!serverSelect || !modelSelect) return;

    function updateModels() {
        const selectedServer = serverSelect.value;
        const models = availableModels[selectedServer] || [];

        modelSelect.innerHTML = "";
        models.forEach(model => {
            const option = document.createElement("option");
            option.value = model;
            option.textContent = model;
            modelSelect.appendChild(option);
        });
    }
    serverSelect.addEventListener("change", updateModels);
    updateModels();
}

/* ---------- SSE Log Streaming ---------- */
// jQuery — marked for Phase 6.3 removal
function initLogStreaming() {
    const terminal = $("#logTerminal");
    if (!terminal.length) return;

    $('#logModal').on('shown.bs.modal', function () {
        terminal.scrollTop(terminal[0].scrollHeight);
    });

    const evtSource = new EventSource("/stream_detection");

    evtSource.onmessage = function (event) {
        const data = JSON.parse(event.data);
        const logLine = data.log;
        terminal.append(document.createTextNode(logLine + "\n"));
        terminal.scrollTop(terminal[0].scrollHeight);
    };

    evtSource.onerror = function (err) {
        console.error("SSE error:", err);
    };
}

/* ---------- Accordion Toggle ---------- */
function initAccordionToggle() {
    document.querySelectorAll('.topic-checkbox').forEach(function (checkbox) {
        checkbox.addEventListener('click', function (event) {
            event.stopPropagation();
        });
    });

    document.querySelectorAll('.dataset-header').forEach(function (header) {
        header.addEventListener('click', function () {
            var contentId = header.getAttribute('aria-controls');
            var content = document.getElementById(contentId);
            if (!content) return;

            var expanded = header.getAttribute('aria-expanded') === 'true';
            if (expanded) {
                content.style.display = 'none';
                header.setAttribute('aria-expanded', 'false');
                var chev = header.querySelector('.chev');
                if (chev) chev.style.transform = '';
            } else {
                content.style.display = 'block';
                header.setAttribute('aria-expanded', 'true');
                var chev = header.querySelector('.chev');
                if (chev) chev.style.transform = 'rotate(90deg)';
            }
        });
    });
}

/* ---------- Pipeline Polling ---------- */
let originalHTML = '';

function startPipelinePolling(TM, topics) {
    const selector = document.querySelector(`#analyze_contradictions`);
    const interval = setInterval(() => {
        fetch(`/pipeline_status?TM=${encodeURIComponent(TM)}&topics=${encodeURIComponent(topics)}`)
            .then(res => res.json())
            .then(data => {
                console.log(data);
                if (data.status === 'finished') {
                    clearInterval(interval);
                    shouldWarn = false;
                    window.location.href = `/detection_results?TM=${encodeURIComponent(TM)}&topics=${encodeURIComponent(topics)}`;
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    selector.style.pointerEvents = 'auto';
                    selector.style.opacity = '1';
                    selector.classList.remove('disabled');
                    selector.innerHTML = originalHTML;
                    shouldWarn = false;
                }
            })
            .catch(err => {
                console.error("Error checking pipeline status:", err);
                clearInterval(interval);
            });
    }, 2000);
}

/* ---------- MIND Interface Class ---------- */
class MINDInterface {
    constructor() {
        this.datasetItems = document.querySelectorAll('.dataset-item');
        this.modeSelectors = document.querySelectorAll('.mode-selectors');
        this.form = document.getElementById('mind-number-form');
        this.numberInput = document.getElementById('numberInput');
        this.topicButtons = document.querySelectorAll('.topic_button') ?? [];
        this.listViewBtn = document.getElementById('list-view-btn');
        this.graphViewBtn = document.getElementById('graph-view-btn');

        this.initEventListeners();
    }

    initEventListeners() {
        this.datasetItems.forEach(item => {
            item.addEventListener('click', () => {
                const datasetName = item.getAttribute("dataset-tm");
                this.handleDatasetSelection(datasetName);
            });
        });

        // "All" sample toggle
        const sampleAllBtn = document.getElementById('sampleAllBtn');
        const sampleSizeInput = document.getElementById('sampleSizeInput');
        if (sampleAllBtn && sampleSizeInput) {
            sampleAllBtn.addEventListener('click', () => {
                const isActive = sampleAllBtn.classList.toggle('active');
                sampleSizeInput.disabled = isActive;
                sampleAllBtn.classList.toggle('btn-secondary', isActive);
                sampleAllBtn.classList.toggle('btn-outline-secondary', !isActive);
            });
        }

        if (this.form) {
            this.form.addEventListener('submit', (e) => {
                e.preventDefault();
                const value = parseInt(this.numberInput.value, 10);
                if (!isNaN(value)) {
                    this.handleSubmitNumber(value);
                }
            });
        }

        this.modeSelectors.forEach(selector => {
            selector.addEventListener('click', (e) => {
                e.preventDefault();
                const instruction = 'Analyze contradictions';
                let selected = [];

                if (window.currentView === "visual") {
                    selected = window.currentVisibleTopics;
                }
                else if (window.currentView === "text") {
                    const checkboxes = document.querySelectorAll('.topic-checkbox');
                    selected = Array.from(checkboxes)
                        .filter(cb => cb.checked)
                        .map(cb => cb.value);
                }
                else {
                    showToast("Choose Topics in Option Visual or Text.");
                    return;
                }

                if (selected.length < 1) {
                    showToast('Select at least 1 topic.');
                    return;
                }

                const sampleAllBtn = document.getElementById('sampleAllBtn');
                const isAllSamples = sampleAllBtn && sampleAllBtn.classList.contains('active');
                const sampleSizeInput = isAllSamples ? null : document.getElementById('sampleSizeInput').value;

                if (!isAllSamples && sampleSizeInput < 1) {
                    showToast('Sample Size must be greater than 0.');
                    return;
                }

                const topics = selected.join(',');
                const TM = document.getElementById('TopicModel-h3').getAttribute("TM-name");

                const llm_type = document.getElementById('llmSelect_type').value;
                let llm_model = "";
                let gpt_api = "";
                let ollama_server = "";

                if (llm_type === "gemini") {
                    // Use selected Gemini model; backend uses Prompter.from_config() or the model name.
                    llm_model = document.getElementById("llmSelect_gemini_input")?.value || "gemini-2.5-flash";
                } else if (llm_type === "ollama") {
                    llm_model = document.getElementById("llmSelect_ollama_input").value;
                    ollama_server = document.getElementById('server_ollama_input').value;
                    if (!llm_model || !ollama_server) {
                        showToast('Select an Ollama LLM and server.');
                        return;
                    }
                } else if (llm_type === "GPT") {
                    llm_model = document.getElementById("llmSelect_gpt_input").value;
                    gpt_api = document.getElementById("gptApiKeyInput").value;
                    if (!gpt_api || !llm_model) {
                        showToast('Select a GPT LLM and indicate your API Key.');
                        return;
                    }
                } else {
                    // Unknown type — let backend use Prompter.from_config() default.
                }

                const config = {
                    "llm_type": llm_type,
                    "llm": llm_model,
                    "gpt_api": gpt_api,
                    "ollama_server": ollama_server,
                    "method": document.getElementById("methodSelect").value,
                    "do_weighting": document.getElementById("enableWeight").checked ? true : false
                };

                // --- Category selection ---
                const checkedCats = document.querySelectorAll('.category-checkbox:checked');
                if (checkedCats.length === 0) {
                    showToast('Select at least 1 detection category.');
                    return;
                }
                if (checkedCats.length > 5) {
                    showToast('Maximum of 5 categories allowed.');
                    return;
                }
                const selected_categories = Array.from(checkedCats).map(cb => ({
                    name: cb.value,
                    prompt_instruction: cb.dataset.catPrompt || '',
                    examples: cb.dataset.catExamples || '[]'
                }));
                config.selected_categories = selected_categories;

                this.handleInstruction(instruction, topics, TM, sampleSizeInput, config);
            });
        });
    }

    getCSRFToken() {
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrf_token='))
            ?.split('=')[1];
        return cookieValue || '';
    }

    handleDatasetSelection(datasetName) {
        console.log("Selected option:\n", datasetName);
        showOverlay();

        fetch('/detection_topickeys', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken?.() || ''
            },
            body: JSON.stringify(datasetName)
        })
            .then(res => {
                if (!res.ok) {
                    hideOverlay();
                    throw new Error("Backend error");
                }
                return res.json();
            })
            .then(data => {
                window.location.href = data.redirect;
            })
            .catch(err => {
                hideOverlay();
                console.error("Dataset selection error:", err);
            });
    }

    handleInstruction(instruction, topics, TM, sample_size, config) {
        console.log("Selected instruction:", instruction);
        const data = { "instruction": instruction, "topics": topics, "TM": TM, "sample_size": sample_size, "config": config };
        const selector = document.querySelector(`#analyze_contradictions`);
        if (!selector) {
            console.error("Selector not found!");
            return;
        }

        selector.style.pointerEvents = 'none';
        selector.style.opacity = '0.6';
        selector.classList.add('disabled');

        originalHTML = selector.innerHTML;
        selector.innerHTML = `
            <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
            Waiting...
        `;

        // jQuery — marked for Phase 6.3 removal
        $("#logTerminal").empty();

        shouldWarn = true;
        fetch('/mode_selection', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(data)
        })
            .then(res => {
                if (res.ok) {
                    startPipelinePolling(TM, topics);
                } else {
                    shouldWarn = false;
                    selector.style.pointerEvents = 'auto';
                    selector.style.opacity = '1';
                    selector.classList.remove('disabled');
                    selector.innerHTML = originalHTML;
                }
            })
            .catch(err => {
                console.error("Dataset selection error:", err);
                shouldWarn = false;
                selector.style.pointerEvents = 'auto';
                selector.style.opacity = '1';
                selector.classList.remove('disabled');
                selector.innerHTML = originalHTML;
            });
    }
}

/* ---------- Doc Modal Viewer ---------- */
// jQuery — marked for Phase 6.3 removal
function initDocModal() {
    const modal = $('#docModal');
    if (!modal.length) return;

    const modalTitle = modal.find('.modal-title');
    const modalBody = modal.find('.modal-body');

    document.querySelectorAll('.view-doc-link').forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            const docId = this.getAttribute('data-doc-id');
            const docContent = this.getAttribute('data-doc-content');
            modalTitle.text(`Document ${docId}`);
            modalBody.html(`<pre style="white-space: pre-wrap;">${docContent}</pre>`);
            modal.modal('show');
        });
    });
}

/* ---------- Main Initialization ---------- */
document.addEventListener("DOMContentLoaded", function () {
    const DATA = window.__DETECTION_DATA || {};

    // Always init
    initExitWarning();
    initAccordionToggle();

    // Topic view (when topic_keys are present)
    if (DATA.topicKeys) {
        initTopicViewToggle(DATA.topicKeys.topics);
    }

    // Docs pagination
    if (DATA.docsData1) {
        DocsPagination.init('topicDocsContent1', 'paginationContainer1', DATA.docsData1);
    }
    if (DATA.docsData2) {
        DocsPagination.init('topicDocsContent2', 'paginationContainer2', DATA.docsData2);
    }

    // Results table
    if (DATA.columnsJson) {
        initDefaultColumnVisibility();
        initResultsDataTable();
        initDatatableLayout();
        initXlsxExport();
        initRangeSelector();

        // Load first chunk
        const rangeSelector = document.getElementById("rangeSelector");
        if (rangeSelector) {
            hideOverlay();
            loadChunk(rangeSelector.value);
        }
    }

    // LLM config
    if (DATA.availableModels) {
        initModelSelector();
        initLLMConfigToggle();
        initLogStreaming();
    }

    // Category selection max-5 enforcement
    const catGroup = document.getElementById('categorySelectionGroup');
    const catWarning = document.getElementById('categoryWarning');
    if (catGroup) {
        catGroup.addEventListener('change', function () {
            const checked = catGroup.querySelectorAll('.category-checkbox:checked');
            const unchecked = catGroup.querySelectorAll('.category-checkbox:not(:checked)');
            if (checked.length >= 5) {
                unchecked.forEach(cb => cb.disabled = true);
                if (catWarning) { catWarning.textContent = 'Maximum 5 categories reached.'; catWarning.style.display = 'block'; }
            } else {
                catGroup.querySelectorAll('.category-checkbox').forEach(cb => cb.disabled = false);
                if (catWarning) catWarning.style.display = 'none';
            }
        });
    }

    // CSRF token
    if (DATA.csrfToken) {
        document.cookie = "csrf_token=" + DATA.csrfToken;
    }

    // Live-refresh custom categories when the config modal opens
    const configModal = document.getElementById('configPipelineModalLabel');
    if (configModal) {
        configModal.addEventListener('show.bs.modal', () => {
            console.log("Config modal opening, fetching fresh categories...");
            const catGroup = document.getElementById('categorySelectionGroup');
            if (!catGroup) return;

            // Remember which custom cats were already checked
            const prevChecked = new Set(
                Array.from(catGroup.querySelectorAll('.category-checkbox[data-cat-type="custom"]:checked'))
                    .map(cb => cb.value)
            );

            fetch('/categories')
                .then(r => r.json())
                .catch(() => null)
                .then(data => {
                    if (!data || !data.categories) return;

                    // Remove old custom block (hr + label + checkboxes)
                    catGroup.querySelectorAll('.custom-cat-separator, .custom-cat-label, .custom-cat-item').forEach(el => el.remove());

                    if (!data.categories.length) return;

                    const sep = document.createElement('hr');
                    sep.className = 'my-2 custom-cat-separator';
                    catGroup.appendChild(sep);

                    const lbl = document.createElement('p');
                    lbl.className = 'text-muted small mb-1 custom-cat-label';
                    lbl.textContent = 'Custom categories:';
                    catGroup.appendChild(lbl);

                    data.categories.forEach(cat => {
                        const wrapper = document.createElement('div');
                        wrapper.className = 'form-check mb-1 custom-cat-item';
                        const input = document.createElement('input');
                        input.type = 'checkbox';
                        input.className = 'form-check-input category-checkbox';
                        input.value = cat.name;
                        input.id = `cat-modal-${cat.id}`;
                        input.dataset.catType = 'custom';
                        input.dataset.catPrompt = cat.prompt_instruction || '';
                        input.dataset.catExamples = cat.examples || '[]';
                        input.checked = prevChecked.has(cat.name);
                        const label = document.createElement('label');
                        label.className = 'form-check-label';
                        label.htmlFor = input.id;
                        label.textContent = cat.name;
                        wrapper.appendChild(input);
                        wrapper.appendChild(label);
                        catGroup.appendChild(wrapper);
                    });

                    // Re-apply max-5 enforcement
                    catGroup.dispatchEvent(new Event('change'));
                });
        });
    }

    // MIND interface
    const mindInterface = new MINDInterface();
    console.log("MINDInterface initialized");

    // Doc modal
    initDocModal();

    // Hide overlay on full load
    window.addEventListener("load", hideOverlay);
});
