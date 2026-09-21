(() => {
    "use strict";

    const {t, locale, setLanguage} = window.SIGCPI18n;
    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
    const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}"></use></svg>`;
    const esc = (value) => String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    const attr = esc;
    const areaLabel = (value) => !value || value === "Não definido" ? t("Não definido") : value;
    const fmtNumber = (value) => new Intl.NumberFormat(locale()).format(Number(value || 0));
    const fmtDate = (value) => {
        if (!value) return "—";
        const [year, month, day] = String(value).slice(0, 10).split("-");
        return year && month && day ? `${day}/${month}/${year}` : value;
    };
    const fmtWeekdayDate = (value) => {
        if (!value) return "—";
        const dateValue = new Date(`${String(value).slice(0, 10)}T12:00:00`);
        if (Number.isNaN(dateValue.getTime())) return fmtDate(value);
        const weekday = new Intl.DateTimeFormat(locale(), {weekday: "long"}).format(dateValue);
        return `${weekday.charAt(0).toUpperCase()}${weekday.slice(1)}, ${fmtDate(value)}`;
    };
    const fmtDateTime = (value) => value ? `${fmtDate(value)}${String(value).length > 10 ? ` · ${String(value).slice(11, 16)}` : ""}` : "—";
    const toDateTimeInput = (value) => value ? String(value).slice(0, 16).replace(" ", "T") : "";
    const paddedNumberOptions = (limit, selected) => Array.from({length: limit}, (_, value) => {
        const padded = String(value).padStart(2, "0");
        return `<option value="${padded}" ${padded === selected ? "selected" : ""}>${padded}</option>`;
    }).join("");

    function dateTimeField(name, label, value = "", {required = false, disabled = false, help = "", className = ""} = {}) {
        const normalized = toDateTimeInput(value);
        const [date = "", time = ""] = normalized.split("T");
        const [hour = "", minute = ""] = time.split(":");
        const id = `datetime-${String(name).replace(/[^a-z0-9_-]/gi, "-")}`;
        const requiredAttribute = required ? "required" : "";
        const disabledAttribute = disabled ? "disabled" : "";
        return `<div class="field datetime-field${className ? ` ${attr(className)}` : ""}">
            <span id="${id}-label" class="${required ? "required" : ""}">${esc(label)}</span>
            <div class="datetime-picker" data-datetime-picker role="group" aria-labelledby="${id}-label">
                <input type="hidden" name="${attr(name)}" value="${attr(normalized)}" data-datetime-value ${disabledAttribute}>
                <input class="datetime-picker__date" type="date" value="${attr(date)}" data-datetime-date aria-label="${attr(t("{0}: data", label))}" ${requiredAttribute} ${disabledAttribute}>
                <span class="datetime-picker__time">
                    <select data-datetime-hour aria-label="${attr(t("{0}: hora", label))}" ${requiredAttribute} ${disabledAttribute}>
                        <option value="">HH</option>${paddedNumberOptions(24, hour)}
                    </select>
                    <span aria-hidden="true">:</span>
                    <select data-datetime-minute aria-label="${attr(t("{0}: minutos", label))}" ${requiredAttribute} ${disabledAttribute}>
                        <option value="">MM</option>${paddedNumberOptions(60, minute)}
                    </select>
                </span>
            </div>
            ${help ? `<small>${esc(help)}</small>` : ""}
        </div>`;
    }

    function initDateTimePickers(root = document) {
        $$('[data-datetime-picker]', root).forEach((picker) => {
            if (picker.dataset.datetimeReady === "true") return;
            picker.dataset.datetimeReady = "true";
            const source = $("[data-datetime-value]", picker);
            const date = $("[data-datetime-date]", picker);
            const hour = $("[data-datetime-hour]", picker);
            const minute = $("[data-datetime-minute]", picker);
            const controls = [date, hour, minute];

            const syncValue = () => {
                controls.forEach((control) => control.setCustomValidity(""));
                const anyValue = controls.some((control) => control.value);
                const complete = controls.every((control) => control.value);
                source.value = complete ? `${date.value}T${hour.value}:${minute.value}` : "";
                if ((date.required || anyValue) && !complete) {
                    controls.find((control) => !control.value)?.setCustomValidity(t("Indica a data e a hora completas."));
                }
            };

            controls.forEach((control) => {
                control.addEventListener("input", syncValue);
                control.addEventListener("change", syncValue);
            });
            syncValue();
        });
    }

    function snrSubstitutionFields(user, {disabled = false} = {}) {
        const selected = Boolean(user?.snr_substituto);
        const locked = Boolean(disabled);
        return `<section class="snr-substitution field--full" data-snr-substitution data-locked="${locked}">
            <div class="snr-substitution__heading">
                <div><strong>${t("Substituição temporária do SNR")}</strong><small>${t("A pessoa terá permissões de SNR apenas durante o período indicado.")}</small></div>
                <label class="checkbox"><input type="checkbox" name="snr_substituto" ${selected ? "checked" : ""} ${locked ? "disabled" : ""}> ${t("Nomear como substituto")}</label>
            </div>
            <div class="snr-substitution__controls">
                <label class="field"><span>${t("Data de início")}</span><input type="date" name="snr_substituto_inicio" value="${attr(user?.snr_substituto_inicio || "")}" ${selected && !locked ? "" : "disabled"}></label>
                <label class="field"><span>${t("Data de fim")}</span><input type="date" name="snr_substituto_fim" value="${attr(user?.snr_substituto_fim || "")}" ${selected && !locked ? "" : "disabled"}></label>
                <button class="btn btn--secondary snr-substitution__clear" type="button" data-snr-substitution-clear ${locked ? "disabled" : ""}>${t("Limpar")}</button>
            </div>
        </section>`;
    }

    function initSnrSubstitutionFields(root = document) {
        $$('[data-snr-substitution]', root).forEach((panel) => {
            const checkbox = $('input[name="snr_substituto"]', panel);
            const start = $('input[name="snr_substituto_inicio"]', panel);
            const end = $('input[name="snr_substituto_fim"]', panel);
            const clear = $('[data-snr-substitution-clear]', panel);
            const locked = panel.dataset.locked === "true";
            const sync = () => {
                const enabled = Boolean(checkbox.checked && !locked);
                start.disabled = !enabled;
                end.disabled = !enabled;
                start.required = enabled;
                end.required = enabled;
            };
            checkbox?.addEventListener("change", sync);
            clear?.addEventListener("click", () => {
                checkbox.checked = false;
                start.value = "";
                end.value = "";
                sync();
            });
            sync();
        });
    }
    const initials = (user) => {
        const base = `${user?.nome || ""} ${user?.sobrenome || ""}`.trim() || user?.nim || "U";
        return base.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
    };
    const titleCase = (value) => String(value || "").toLocaleLowerCase("pt").replace(/(^|\s)\S/g, (c) => c.toLocaleUpperCase("pt"));

    const state = {
        boot: null,
        page: "dashboard",
        year: new Date().getFullYear(),
        month: new Date().getMonth() + 1,
        calendar: null,
        dishRoster: null,
        individual: null,
        cash: null,
        individualMode: "welfare",
        pending: new Map(),
        selected: new Set(),
        users: [],
        usersAll: false,
        userSearch: "",
        myVacations: null,
        vacationNotifications: [],
        myVacationTab: "requests",
        myVacationsAll: false,
        vacationManagement: null,
        vacationManagementTab: "requests",
        vacationManagementAll: false,
        vacationPlanning: null,
        vacationPlanningMode: "calendar",
        vacationPlanningAll: false,
        vacationPlanningFilters: {statusGroup: "all", area: "", search: ""},
        vacationPeopleAll: false,
        vacationCalendar: null,
        vacationYear: new Date().getFullYear(),
        vacationHolidayYear: new Date().getFullYear(),
        vacationHolidayPreview: null,
        vacationMonth: new Date().getMonth() + 1,
        vacationFilters: {statusGroup: "all", area: "", search: ""},
        vacationNotificationChannel: "pessoal",
        adminTab: "settings",
        dayOffsAll: false,
        auditFilters: null,
        auditCursor: null,
        auditCursorStack: [],
        auditData: null,
        loadingCount: 0,
    };

    const browserLifecycle = {
        tabId: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        closed: false,
    };

    function lifecycleBody(event) {
        return JSON.stringify({tab_id: browserLifecycle.tabId, event});
    }

    async function sendLifecycleHeartbeat() {
        if (browserLifecycle.closed) return;
        try {
            await fetch("/api/lifecycle", {
                method: "POST",
                credentials: "same-origin",
                cache: "no-store",
                headers: {"Content-Type": "application/json"},
                body: lifecycleBody("heartbeat"),
            });
        } catch {
            // O servidor pode estar a encerrar; não há ação útil no browser.
        }
    }

    function closeBrowserLifecycle() {
        if (browserLifecycle.closed) return;
        browserLifecycle.closed = true;
        const body = lifecycleBody("close");
        let queued = false;
        try {
            queued = navigator.sendBeacon(
                "/api/lifecycle",
                new Blob([body], {type: "application/json"}),
            );
        } catch {
            queued = false;
        }
        if (!queued) {
            fetch("/api/lifecycle", {
                method: "POST",
                credentials: "same-origin",
                keepalive: true,
                headers: {"Content-Type": "application/json"},
                body,
            }).catch(() => {});
        }
    }

    function startBrowserLifecycle() {
        sendLifecycleHeartbeat();
        setInterval(sendLifecycleHeartbeat, 5000);
        window.addEventListener("pagehide", closeBrowserLifecycle);
        window.addEventListener("pageshow", () => {
            browserLifecycle.closed = false;
            sendLifecycleHeartbeat();
        });
        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "visible") sendLifecycleHeartbeat();
        });
    }

    const els = {
        login: $("#login-screen"),
        loginForm: $("#login-form"),
        loginError: $("#login-error"),
        shell: $("#app-shell"),
        content: $("#main-content"),
        title: $("#page-title"),
        eyebrow: $("#page-eyebrow"),
        topActions: $("#topbar-actions"),
        loading: $("#loading"),
        modalRoot: $("#modal-root"),
        toasts: $("#toast-region"),
        sidebar: $("#sidebar"),
        sidebarOverlay: $("#sidebar-overlay"),
        profileMenu: $("#profile-menu"),
    };

    function setLoading(active) {
        state.loadingCount = Math.max(0, state.loadingCount + (active ? 1 : -1));
        els.loading.classList.toggle("hidden", state.loadingCount === 0);
    }

    async function api(url, options = {}) {
        const headers = new Headers(options.headers || {});
        if (options.body && !(options.body instanceof FormData) && typeof options.body !== "string") {
            headers.set("Content-Type", "application/json");
            options.body = JSON.stringify(options.body);
        }
        if (state.boot?.csrf_token && options.method && options.method !== "GET") {
            headers.set("X-CSRF-Token", state.boot.csrf_token);
        }
        const response = await fetch(url, {credentials: "same-origin", ...options, headers});
        const type = response.headers.get("content-type") || "";
        const payload = type.includes("application/json") ? await response.json() : null;
        if (!response.ok || payload?.ok === false) {
            if (response.status === 401) {
                showLogin();
            }
            const error = new Error(payload?.error || t("Erro HTTP {0}", response.status));
            error.status = response.status;
            error.payload = payload || {};
            throw error;
        }
        return payload;
    }

    function filenameFromResponse(response, fallback) {
        const disposition = response.headers.get("content-disposition") || "";
        const utf = disposition.match(/filename\*=UTF-8''([^;]+)/i);
        const plain = disposition.match(/filename="?([^";]+)"?/i);
        try {
            return decodeURIComponent(utf?.[1] || plain?.[1] || fallback);
        } catch {
            return plain?.[1] || fallback;
        }
    }

    async function download(url, options = {}, fallback = "download") {
        if (state.pending.size && url.includes("/individual/")) {
            toast(t("Guarda primeiro as alterações pendentes."), "warning");
            return;
        }
        setLoading(true);
        try {
            const headers = new Headers(options.headers || {});
            if (options.body && typeof options.body !== "string") {
                headers.set("Content-Type", "application/json");
                options.body = JSON.stringify(options.body);
            }
            if (state.boot?.csrf_token && options.method && options.method !== "GET") {
                headers.set("X-CSRF-Token", state.boot.csrf_token);
            }
            const response = await fetch(url, {credentials: "same-origin", ...options, headers});
            if (!response.ok) {
                const type = response.headers.get("content-type") || "";
                const data = type.includes("application/json") ? await response.json() : null;
                throw new Error(data?.error || t("Não foi possível gerar o ficheiro ({0}).", response.status));
            }
            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            anchor.href = objectUrl;
            anchor.download = filenameFromResponse(response, fallback);
            document.body.append(anchor);
            anchor.click();
            anchor.remove();
            setTimeout(() => URL.revokeObjectURL(objectUrl), 2000);
            toast(t("Ficheiro criado e enviado para o browser."), "success");
        } catch (error) {
            toast(error.message, "error");
        } finally {
            setLoading(false);
        }
    }

    function toast(message, type = "success", title = "") {
        const item = document.createElement("div");
        item.className = `toast toast--${type}`;
        const glyph = type === "error" ? "alert" : type === "warning" ? "info" : "check";
        item.innerHTML = `
            <span class="toast__icon">${icon(glyph)}</span>
            <div><strong>${esc(title || (type === "error" ? t("Ocorreu um erro") : type === "warning" ? t("Atenção") : t("Concluído")))}</strong><p>${esc(message)}</p></div>
            <button type="button" aria-label="${t("Fechar")}">${icon("x")}</button>`;
        $("button", item).addEventListener("click", () => item.remove());
        els.toasts.append(item);
        setTimeout(() => item.remove(), type === "error" ? 7000 : 4300);
    }

    function closeModal() {
        els.modalRoot.innerHTML = "";
        document.body.style.overflow = "";
    }

    function openModal({title, subtitle = "", body = "", footer = "", size = "", onOpen = null, closeable = true}) {
        closeModal();
        document.body.style.overflow = "hidden";
        els.modalRoot.innerHTML = `
            <div class="modal-backdrop">
                <section class="modal ${size ? `modal--${size}` : ""}" role="dialog" aria-modal="true" aria-label="${attr(title)}">
                    <header class="modal__header">
                        <div><h2>${esc(title)}</h2>${subtitle ? `<p>${esc(subtitle)}</p>` : ""}</div>
                        ${closeable ? `<button type="button" class="icon-btn" data-modal-close aria-label="${t("Fechar")}">${icon("x")}</button>` : ""}
                    </header>
                    <div class="modal__body">${body}</div>
                    ${footer ? `<footer class="modal__footer">${footer}</footer>` : ""}
                </section>
            </div>`;
        const backdrop = $(".modal-backdrop", els.modalRoot);
        $$("[data-modal-close]", els.modalRoot).forEach((button) => button.addEventListener("click", closeModal));
        backdrop.addEventListener("mousedown", (event) => {
            if (closeable && event.target === backdrop) closeModal();
        });
        document.addEventListener("keydown", modalEscape, {once: true});
        const modal = $(".modal", els.modalRoot);
        initDateTimePickers(modal);
        initSnrSubstitutionFields(modal);
        if (onOpen) onOpen(modal);
        setTimeout(() => $("input:not([type='hidden']):not([disabled]), select:not([disabled]), textarea:not([disabled])", els.modalRoot)?.focus(), 30);
        return modal;
    }

    function modalEscape(event) {
        if (event.key === "Escape" && els.modalRoot.children.length) closeModal();
    }

    function confirmDialog(message, {title = t("Confirmar operação"), danger = false, confirmText = t("Confirmar")} = {}) {
        return new Promise((resolve) => {
            openModal({
                title,
                closeable: false,
                body: `<div class="confirm-copy">
                    <span class="confirm-icon ${danger ? "confirm-icon--danger" : ""}">${icon(danger ? "alert" : "info")}</span>
                    <h3>${esc(title)}</h3><p>${esc(message)}</p>
                </div>`,
                footer: `
                    <button type="button" class="btn btn--secondary" data-confirm-no>${t("Cancelar")}</button>
                    <button type="button" class="btn ${danger ? "btn--danger" : "btn--primary"}" data-confirm-yes>${esc(confirmText)}</button>`,
                onOpen(modal) {
                    $("[data-confirm-no]", modal).addEventListener("click", () => { closeModal(); resolve(false); });
                    $("[data-confirm-yes]", modal).addEventListener("click", () => { closeModal(); resolve(true); });
                },
            });
        });
    }

    function monthOptions(selected) {
        const names = state.boot?.config?.meses || {};
        return Array.from({length: 12}, (_, index) => {
            const month = index + 1;
            return `<option value="${month}" ${month === Number(selected) ? "selected" : ""}>${esc(names[month] || month)}</option>`;
        }).join("");
    }

    function yearOptions(selected) {
        const year = Number(selected);
        return Array.from({length: 17}, (_, index) => year - 5 + index)
            .map((item) => `<option value="${item}" ${item === year ? "selected" : ""}>${item}</option>`).join("");
    }

    function periodPicker() {
        return `<div class="period-picker">
            <button type="button" class="icon-btn" data-action="period-prev" aria-label="${t("Mês anterior")}">${icon("left")}</button>
            <select id="period-month" aria-label="${t("Mês")}">${monthOptions(state.month)}</select>
            <select id="period-year" aria-label="${t("Ano")}">${yearOptions(state.year)}</select>
            <button type="button" class="icon-btn" data-action="period-next" aria-label="${t("Mês seguinte")}">${icon("right")}</button>
        </div>`;
    }

    function syncPeriodPicker() {
        const month = $("#period-month");
        const year = $("#period-year");
        if (month) month.innerHTML = monthOptions(state.month);
        if (year) year.innerHTML = yearOptions(state.year);
    }

    function setPageHeader(title, eyebrow, actions = "") {
        els.title.textContent = title;
        els.eyebrow.textContent = eyebrow;
        els.topActions.innerHTML = actions;
    }

    function showLogin() {
        state.boot = null;
        state.myVacations = null;
        state.vacationManagement = null;
        state.vacationNotifications = [];
        state.pending.clear();
        state.selected.clear();
        els.shell.classList.add("hidden");
        els.login.classList.remove("hidden");
        els.loginError.textContent = "";
        $("#login-password").value = "";
        setTimeout(() => $("#login-nim").focus(), 20);
    }

    function setupShell() {
        const {user, permissions} = state.boot;
        setLanguage(state.boot.language);
        els.login.classList.add("hidden");
        els.shell.classList.remove("hidden");
        $("#sidebar-user").textContent = user.identificacao;
        $("#sidebar-role").textContent = user.acessos.map((access) => t(access)).join(" · ") || t("Utilizador");
        $("#sidebar-avatar").textContent = initials(user);
        $$("[data-permission]").forEach((element) => {
            element.classList.toggle("hidden", !permissions[element.dataset.permission]);
        });
        syncVacationNotificationCount();
    }

    async function bootstrap() {
        try {
            const data = await api("/api/bootstrap");
            setLanguage(data.language);
            if (!data.authenticated) {
                showLogin();
                return;
            }
            state.boot = data;
            setupShell();
            const hashPage = location.hash.replace("#", "");
            const allowed = ["dashboard", "calendar", "dish-roster", "teams", "individual", "cash", "my-vacations", "vacation-planning", "personnel", "vacations", "admin"];
            navigate(allowed.includes(hashPage) ? hashPage : "dashboard", false);
        } catch (error) {
            showLogin();
            els.loginError.textContent = error.message;
        }
    }

    async function navigate(page, updateHash = true) {
        if (state.pending.size && page !== state.page) {
            const leave = await confirmDialog(t("Existem alterações individuais por guardar. Queres anulá-las e mudar de página?"), {title: t("Alterações pendentes"), danger: true, confirmText: t("Anular e sair")});
            if (!leave) return;
            state.pending.clear();
        }
        state.page = page;
        els.content.classList.toggle("main-content--individual", page === "individual");
        if (updateHash) history.replaceState(null, "", `#${page}`);
        $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.page === page));
        closeSidebar();
        els.content.innerHTML = `<div class="page"><div class="card empty-state"><div><div class="loader"></div></div></div></div>`;
        try {
            if (page === "dashboard") await renderDashboard();
            else if (page === "calendar") await renderCalendar();
            else if (page === "dish-roster") await renderDishRoster();
            else if (page === "teams") await renderTeams();
            else if (page === "individual") await renderIndividual();
            else if (page === "cash") await renderCash();
            else if (page === "my-vacations") await renderMyVacations();
            else if (page === "vacation-planning") await renderVacationPlanning();
            else if (page === "personnel") await renderUsersPage(false);
            else if (page === "vacations") await renderVacations();
            else if (page === "admin") await renderAdmin();
        } catch (error) {
            els.content.innerHTML = `<div class="page"><div class="card empty-state"><div>${icon("alert")}<h3>${t("Não foi possível abrir esta área")}</h3><p>${esc(error.message)}</p></div></div></div>`;
            toast(error.message, "error");
        }
        els.content.focus({preventScroll: true});
    }

    function closeSidebar() {
        els.sidebar.classList.remove("open");
        els.sidebarOverlay.classList.remove("open");
    }

    // Dashboard
    async function renderDashboard() {
        setPageHeader("Dashboard", t("VISÃO GERAL"));
        const data = await api("/api/dashboard");
        const rules = data.regras_ferias;
        const personal = data.pessoal || {};
        const service = personal.proximo_servico;
        const dishService = personal.proxima_loica;
        const vacation = personal.proximas_ferias;
        const cash = data.caixa || {saldo: 0, entradas: [], saidas: []};
        const today = state.boot.config.today;
        const upcoming = data.proximos_welfares.map((item) => `<article class="dashboard-event ${item.data === today ? "dashboard-event--today" : ""}">
            <div class="dashboard-date"><span class="dashboard-date__icons">${(item.icones || []).map((file) => `<img src="/assets/${attr(file)}" alt="">`).join("")}</span><strong>${new Date(`${item.data}T12:00:00`).getDate()}</strong><span>${esc(String(state.boot.config.meses[new Date(`${item.data}T12:00:00`).getMonth() + 1] || "").slice(0, 3))}</span>${item.data === today ? `<em>${t("Hoje")}</em>` : ""}</div>
            <div><strong>${esc(t(item.refeicao))} · ${esc(t(item.tipo))}</strong><p>${esc([item.local, item.prato, item.sobremesa].filter(Boolean).join(" · ") || t("Ementa por definir"))}</p></div>
            ${item.local === "Recanto" ? `<div class="dashboard-team-support"><span class="team-badge">${esc(item.team_nome || t("Team por definir"))}</span>${item.team_nome ? `<div>${(item.membros || []).map((member) => `<span class="dashboard-team-member ${member.ferias ? "dashboard-team-member--vacation" : ""}">${esc(`${member.posto || ""} ${member.nome || ""} ${member.sobrenome || ""}`.trim())}${member.ferias ? t(" (Férias)") : ""}</span>`).join("") || `<small>${t("Sem elementos")}</small>`}</div>` : ""}</div>` : ""}
        </article>`).join("") || `<div class="empty-inline">${t("Não existem Welfares futuros planeados.")}</div>`;
        const teams = data.teams.map((team) => `<article class="dashboard-team"><div><strong>${esc(team.nome)}</strong><span>${team.membros.length} ${t("elemento")}${team.membros.length === 1 ? "" : "s"}</span></div><ul>${team.membros.map((member) => `<li class="${member.ferias ? "dashboard-team-member--vacation" : ""}">${esc(`${member.posto || ""} ${member.nome || ""} ${member.sobrenome || ""}`.trim())}${member.ferias ? ` <strong>${t("(Férias até")} ${fmtDate(member.ferias_fim)})</strong>` : ""}</li>`).join("") || `<li>${t("Sem elementos")}</li>`}</ul></article>`).join("") || `<div class="empty-inline">${t("Ainda não existem Teams.")}</div>`;
        els.content.innerHTML = `<section class="page dashboard-page">
            <section class="card personal-info">
                <header><div><p class="eyebrow">${t("INFORMAÇÃO PESSOAL")}</p><h2>${esc(state.boot.user.identificacao)}</h2></div></header>
                <div class="personal-info-grid">
                    <div class="personal-stat personal-stat--service-primary ${personal.servico_hoje ? "personal-stat--on-duty" : ""}"><span>${t("Próximo apoio à confeção")}</span><strong>${service ? `${fmtWeekdayDate(service.data)} · ${esc(t(service.refeicao))} · ${esc(service.team_nome)}` : t("Sem serviço previsto")}</strong></div>
                    <div class="personal-stat personal-stat--service-dishes ${personal.loica_proximo_fim_semana ? "personal-stat--on-duty" : ""}"><span>${t("Próximo serviço à escala da loiça")}</span><strong>${dishService ? t("{0} e {1} · Militar {2}", fmtWeekdayDate(dishService.fim_semana), fmtWeekdayDate(dishService.domingo), dishService.posicao) : t("Sem serviço previsto")}</strong></div>
                    <div class="personal-stat personal-stat--vacation"><span>${t("Próximas férias")}</span><strong>${vacation ? `${fmtDate(vacation.data_hora_inicio)} a ${fmtDate(vacation.data_hora_fim)}` : t("Sem férias previstas")}</strong></div>
                    <div class="personal-stat"><span>${t("Welfares no mês")}</span><strong>${fmtNumber(personal.welfares_mes)}</strong></div>
                    <div class="personal-stat"><span>${t("Previsão de reembolso")}</span><strong>${fmtNumber(personal.reembolso_mes)} XAF</strong></div>
                    <div class="personal-stat"><span>${t("Pagamento para a Caixa")}</span><strong>${fmtNumber(personal.caixa_mes)} XAF</strong></div>
                </div>
            </section>
            <div class="dashboard-grid">
                <section class="card dashboard-panel dashboard-panel--wide"><header><div><p class="eyebrow">WELFARE</p><h3>${t("Próximos Welfares")}</h3></div></header><div class="dashboard-events">${upcoming}</div></section>
                <section class="card dashboard-panel"><header><div><p class="eyebrow">${t("FÉRIAS")}</p><h3>${t("Regras em vigor")}</h3></div></header><div class="rules-summary">
                    <div><strong>${esc(rules.dias_por_mes)}</strong><span>${t("dias de férias por mês de missão completo")}</span></div><div><strong>${esc(rules.max_dias_ausencia)}</strong><span>${t("máx. dias de ausência")}</span></div>
                    <div><strong>${esc(rules.max_percentagem_area)}%</strong><span>${t("máx. ausentes por área")}</span></div><div><strong>${esc(rules.max_periodos)}</strong><span>${t("máx. períodos")}</span></div>
                    <p>${icon("info")} ${t("Não é permitido gozar férias no primeiro nem no último mês da missão.")}</p></div></section>
                <section class="card dashboard-panel dashboard-cash"><header><div><p class="eyebrow">${t("CAIXA")}</p><h3>${t("Balanço ao dia atual")}</h3></div><button class="btn btn--small btn--secondary" data-action="cash-consult">${t("Ver +")}</button></header>
                    <div class="dashboard-cash-balance"><span>${t("Saldo em")} ${fmtDate(cash.data)}</span><strong>${fmtNumber(cash.saldo)} XAF</strong></div>
                    <div class="dashboard-cash-columns"><div><b>${t("Últimas entradas")}</b>${cash.entradas.map((item) => `<p><span>${fmtDate(item.data)} · ${esc(item.descritivo)}</span><strong>+ ${fmtNumber(item.valor)} XAF</strong></p>`).join("") || `<small>${t("Sem entradas")}</small>`}</div><div><b>${t("Últimas saídas")}</b>${cash.saidas.map((item) => `<p><span>${fmtDate(item.data)} · ${esc(item.descritivo)}</span><strong>− ${fmtNumber(item.valor)} XAF</strong></p>`).join("") || `<small>${t("Sem saídas")}</small>`}</div></div>
                </section>
                <section class="card dashboard-panel dashboard-panel--wide dashboard-teams-panel"><header><div><p class="eyebrow">${t("EQUIPAS")}</p><h3>${t("Constituição das equipas de apoio ao Welfare")}</h3></div>${state.boot.permissions.teams ? `<button class="btn btn--secondary" data-action="teams-open">${t("Gerir Teams")}</button>` : ""}</header><div class="dashboard-teams">${teams}</div></section>
            </div></section>`;
    }

    function currentMonthRange() {
        const today = new Date(`${state.boot.config.today}T12:00:00`);
        const year = today.getFullYear(), month = today.getMonth();
        const localDate = (value) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
        return {inicio: localDate(new Date(year, month, 1)), fim: localDate(new Date(year, month + 1, 0))};
    }

    async function renderCash() {
        if (!state.boot.permissions.caixa) throw new Error(t("Não tens acesso à Gestão Caixa."));
        setPageHeader(t("Gestão Caixa"), "WELFARE", `<button class="btn btn--secondary" data-action="cash-pdf">${icon("print")} ${t("Exportar balanço")}</button><button class="btn btn--primary" data-action="cash-new">${icon("plus")} ${t("Novo movimento")}</button>`);
        const range = state.cash?.range || currentMonthRange();
        els.content.innerHTML = `<section class="page page--wide"><div class="page-toolbar cash-filter"><label class="field"><span>${t("De")}</span><input type="date" id="cash-start" value="${range.inicio}"></label><label class="field"><span>${t("Até")}</span><input type="date" id="cash-end" value="${range.fim}"></label><button class="btn btn--secondary" data-action="cash-filter">${t("Aplicar período")}</button></div><div id="cash-root"></div></section>`;
        await loadCash();
    }

    async function loadCash() {
        const inicio = $("#cash-start")?.value || currentMonthRange().inicio;
        const fim = $("#cash-end")?.value || currentMonthRange().fim;
        const data = (await api(`/api/cash?inicio=${inicio}&fim=${fim}`)).data;
        state.cash = {...data, range: {inicio, fim}};
        drawCash();
    }

    function drawCash() {
        const data = state.cash;
        const rows = data.movimentos.map((item) => `<tr><td>${fmtDate(item.data)}</td><td><span class="cash-type cash-type--${item.tipo}">${item.tipo === "entrada" ? t("Entrada") : t("Saída")}</span></td><td><strong>${esc(item.descritivo)}</strong>${item.observacoes ? `<small>${esc(item.observacoes)}</small>` : ""}</td><td>${esc(item.pessoa_gasto || "—")}</td><td>${esc(item.local || "—")}</td><td class="number ${item.tipo === "entrada" ? "cash-positive" : "cash-negative"}">${item.tipo === "entrada" ? "+" : "−"} ${fmtNumber(item.valor)} XAF</td><td class="number">${fmtNumber(item.saldo)} XAF</td><td><span>${esc(item.criado_por_nome)}</span><small>${t("Criado:")} ${fmtDateTime(item.criado_em)}</small>${item.atualizado_em !== item.criado_em ? `<small>${t("Editado por")} ${esc(item.atualizado_por_nome)}: ${fmtDateTime(item.atualizado_em)}</small>` : ""}</td><td><div class="team-actions"><button class="icon-btn" data-action="cash-edit" data-cash-id="${item.id}" title="${t("Editar")}">${icon("edit")}</button><button class="icon-btn danger-text" data-action="cash-delete" data-cash-id="${item.id}" title="${t("Apagar")}">${icon("trash")}</button></div></td></tr>`).join("");
        $("#cash-root").innerHTML = `<div class="cash-summary-grid"><div><span>${t("Saldo inicial")}</span><strong>${fmtNumber(data.saldo_inicial)} XAF</strong></div><div class="cash-summary-entry"><span>${t("Entradas")}</span><strong>+ ${fmtNumber(data.total_entradas)} XAF</strong></div><div class="cash-summary-exit"><span>${t("Saídas")}</span><strong>− ${fmtNumber(data.total_saidas)} XAF</strong></div><div><span>${t("Saldo em")} ${fmtDate(data.fim)}</span><strong>${fmtNumber(data.saldo_final)} XAF</strong></div><div class="cash-summary-forecast"><span>${t("Previsão Welfare Individual")}</span><strong>${fmtNumber(data.previsao_mes)} XAF</strong><small>${t("Informação não vinculativa")}</small></div></div><div class="card table-wrap"><table class="data-table cash-table"><thead><tr><th>${t("Data")}</th><th>${t("Tipo")}</th><th>${t("Descritivo")}</th><th>${t("Pessoa")}</th><th>${t("Local")}</th><th>${t("Valor")}</th><th>${t("Saldo")}</th><th>${t("Registo")}</th><th></th></tr></thead><tbody>${rows || `<tr><td colspan="9"><div class="empty-inline">${t("Sem movimentos neste período.")}</div></td></tr>`}</tbody></table></div>`;
    }

    function openCashMovementModal(item = null) {
        const people = state.cash?.pessoas || [];
        const selectedPerson = item?.pessoa_gasto || "";
        const personOptions = `${selectedPerson && !people.some((person) => person.identificacao === selectedPerson) ? `<option value="${attr(selectedPerson)}" selected>${esc(selectedPerson)}</option>` : ""}${people.map((person) => `<option value="${attr(person.identificacao)}" ${person.identificacao === selectedPerson ? "selected" : ""}>${esc(person.identificacao)}</option>`).join("")}`;
        openModal({title: item ? t("Editar movimento") : t("Novo movimento"), subtitle: t("Os campos Data, Valor e Descritivo são obrigatórios."), size: "wide", body: `<form id="cash-movement-form" class="cash-movement-grid"><label class="field cash-field-type"><span>${t("Tipo")}</span><select name="tipo"><option value="entrada" ${item?.tipo === "entrada" ? "selected" : ""}>${t("Entrada")}</option><option value="saida" ${item?.tipo === "saida" ? "selected" : ""}>${t("Saída")}</option></select></label><label class="field cash-field-date"><span>${t("Data *")}</span><input type="date" name="data" value="${attr(item?.data || state.boot.config.today)}" required></label><label class="field cash-field-value"><span>${t("Valor (XAF) *")}</span><input type="number" name="valor" min="0.01" step="0.01" value="${attr(item?.valor || "")}" required></label><label class="field cash-field-description"><span>${t("Descritivo *")}</span><input name="descritivo" value="${attr(item?.descritivo || "")}" maxlength="250" required></label><label class="field cash-person-field"><span>${t("Quem efetuou o gasto")}</span><select name="pessoa_gasto"><option value="">${t("Selecionar militar")}</option>${personOptions}</select></label><label class="field cash-local-field"><span>${t("Local do gasto")}</span><input name="local" value="${attr(item?.local || "")}" maxlength="150"></label><label class="field cash-field-notes"><span>${t("Observações")}</span><textarea name="observacoes" rows="3" maxlength="1000">${esc(item?.observacoes || "")}</textarea></label></form>`, footer:`<button class="btn btn--secondary" data-modal-close>${t("Cancelar")}</button><button class="btn btn--primary" type="submit" form="cash-movement-form">${t("Gravar")}</button>`, onOpen(modal) {
            const form = $("#cash-movement-form", modal), type = $("[name='tipo']", form), expenseFields = $$(".cash-person-field,.cash-local-field", form);
            const toggle = () => expenseFields.forEach((field) => field.classList.toggle("hidden", type.value !== "saida")); type.addEventListener("change", toggle); toggle();
            form.addEventListener("submit", async (event) => { event.preventDefault(); const body = Object.fromEntries(new FormData(form)); try { const response = await api(item ? `/api/cash/${item.id}` : "/api/cash", {method:item ? "PUT" : "POST", body}); closeModal(); toast(response.message); await loadCash(); } catch (error) { toast(error.message, "error"); } });
        }});
    }

    async function openCashConsultation() {
        const range = currentMonthRange();
        openModal({title:t("Consulta da Caixa"), subtitle:t("Movimentos em modo de consulta."), size:"large", body:`<div class="cash-modal-filter"><label class="field"><span>${t("De")}</span><input type="date" data-cash-consult-start value="${range.inicio}"></label><label class="field"><span>${t("Até")}</span><input type="date" data-cash-consult-end value="${range.fim}"></label><button class="btn btn--secondary" data-cash-consult-search>${t("Pesquisar")}</button></div><div data-cash-consult-results></div>`, onOpen(modal) { const load = async () => { const start=$("[data-cash-consult-start]",modal).value,end=$("[data-cash-consult-end]",modal).value; try { const data=(await api(`/api/cash/consultation?inicio=${start}&fim=${end}`)).data; const movements=[...data.movimentos].sort((a,b)=>String(b.data).localeCompare(String(a.data)) || Number(b.id)-Number(a.id)); $("[data-cash-consult-results]",modal).innerHTML=`<div class="cash-consult-balance"><span>${t("Saldo inicial:")} <b>${fmtNumber(data.saldo_inicial)} XAF</b></span><span>${t("Entradas:")} <b>+ ${fmtNumber(data.total_entradas)} XAF</b></span><span>${t("Saídas:")} <b>− ${fmtNumber(data.total_saidas)} XAF</b></span><span>${t("Saldo final:")} <b>${fmtNumber(data.saldo_final)} XAF</b></span></div><div class="cash-consult-list">${movements.map(item=>`<article><div><b>${fmtDate(item.data)} · ${esc(item.descritivo)}</b><small>${esc([item.pessoa_gasto,item.local,item.observacoes].filter(Boolean).join(" · ") || t("Sem informação adicional"))}</small></div><strong class="${item.tipo === "entrada" ? "cash-positive" : "cash-negative"}">${item.tipo === "entrada" ? "+" : "−"} ${fmtNumber(item.valor)} XAF</strong></article>`).join("") || `<div class="empty-inline">${t("Sem movimentos.")}</div>`}</div>`; } catch(error) { toast(error.message,"error"); } }; $("[data-cash-consult-search]",modal).addEventListener("click",load); load(); }});
    }

    async function renderTeams() {
        setPageHeader(t("Gestão Teams"), t("PLANEAMENTO"), `<button class="btn btn--secondary" data-action="teams-pdf">${icon("print")} ${t("Exportar PDF")}</button><button class="btn btn--secondary" data-action="go-calendar">${icon("calendar")} ${t("Voltar ao calendário")}</button>`);
        const data = await api("/api/teams");
        const editable = state.boot.permissions.teams;
        const rows = data.teams.map((team) => `<tr>
            <td><strong>${esc(team.nome)}</strong></td>
            <td class="team-elements"><div class="team-elements__head"><span class="team-count">${team.membros.length} ${t("elemento")}${team.membros.length === 1 ? "" : "s"}</span>${editable ? `<button class="btn btn--secondary btn--small" data-action="team-add-member" data-team-id="${team.id}">${icon("plus")} ${t("Adicionar")}</button>` : ""}</div>
                <div class="team-member-list">${team.membros.map((member) => `<div class="team-member"><span>${esc(`${member.posto || ""} ${member.nome || ""} ${member.sobrenome || ""}`.trim())}</span>${editable ? `<button class="icon-btn icon-btn--danger" data-action="team-remove-member" data-team-id="${team.id}" data-member-id="${member.id}" title="${t("Remover elemento")}">${icon("trash")}</button>` : ""}</div>`).join("") || `<span class="empty-inline">${t("Sem elementos")}</span>`}</div></td>
            <td class="actions-cell"><div class="team-actions">${editable ? `<button class="icon-btn" data-action="team-edit" data-team-id="${team.id}" title="${t("Editar Team")}">${icon("edit")}</button><button class="icon-btn icon-btn--danger" data-action="team-delete" data-team-id="${team.id}" title="${t("Eliminar Team")}">${icon("trash")}</button>` : ""}</div></td>
        </tr>`).join("");
        els.content.innerHTML = `<section class="page page--wide"><div class="teams-intro"><div><h2>${t("Equipas de confeção")}</h2><p>${t("Os elementos deixam automaticamente a Team após a data de partida da missão.")}</p></div>${editable ? `<button class="btn btn--primary" data-action="team-create">${icon("plus")} ${t("Criar Team")}</button>` : ""}</div>
            <div class="card teams-table-card table-wrap"><table class="data-table"><thead><tr><th>${t("Nome")}</th><th>${t("Elementos")}</th><th>${t("Ações")}</th></tr></thead><tbody>${rows || `<tr><td colspan="3"><div class="empty-inline">${t("Ainda não existem Teams.")}</div></td></tr>`}</tbody></table></div></section>`;
        state.teamsData = data;
    }

    function saveTeam(team, nome, membros = null) {
        return api(`/api/teams/${team.id}`, {method: "PUT", body: {nome, membros: membros === null ? team.membros.map((member) => member.id) : membros}});
    }

    function openTeamNameModal(team = null) {
        const creating = !team;
        openModal({title: creating ? t("Criar Team") : t("Editar Team"), body: `<form id="team-name-form"><label class="field"><span>${t("Nome da Team")}</span><input name="nome" value="${attr(team?.nome || "")}" required maxlength="100"></label></form>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Cancelar")}</button><button class="btn btn--primary" type="button" data-team-name-save>${icon("check")} ${t("Gravar")}</button>`,
            onOpen(modal) {
                const form = $("#team-name-form", modal);
                const saveButton = $("[data-team-name-save]", modal);
                const submit = async () => {
                    if (!form.reportValidity() || saveButton.disabled) return;
                    const nome = new FormData(form).get("nome");
                    saveButton.disabled = true;
                    setLoading(true);
                    try {
                        const response = creating
                            ? await api("/api/teams", {method: "POST", body: {nome}})
                            : await saveTeam(team, nome);
                        closeModal();
                        toast(response.message);
                        await renderTeams();
                    } catch (error) {
                        saveButton.disabled = false;
                        toast(error.message, "error");
                    } finally {
                        setLoading(false);
                    }
                };
                form.addEventListener("submit", (event) => { event.preventDefault(); submit(); });
                saveButton.addEventListener("click", submit);
            }});
    }

    function openTeamMembersModal(team) {
        const available = state.teamsData.pessoas.filter((person) => !person.atribuido);
        openModal({title: t("Adicionar elementos · {0}", team.nome), body: `<form id="team-members-form"><div class="team-add-list">${available.map((person) => `<label class="team-person"><input type="checkbox" name="membros" value="${person.id}"><span><strong>${esc(person.identificacao)}</strong><small>NIM ${esc(person.nim)}</small></span></label>`).join("") || `<p class="empty-inline">${t("Não existem elementos disponíveis na missão.")}</p>`}</div></form>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Cancelar")}</button><button class="btn btn--primary" type="submit" form="team-members-form" ${available.length ? "" : "disabled"}>${icon("plus")} ${t("Adicionar")}</button>`,
            onOpen(modal) { $("#team-members-form", modal).addEventListener("submit", async (event) => { event.preventDefault(); const added = new FormData(event.currentTarget).getAll("membros").map(Number); if (!added.length) return toast(t("Seleciona pelo menos um elemento."), "warning"); try { const response = await saveTeam(team, team.nome, [...team.membros.map((member) => member.id), ...added]); closeModal(); toast(response.message); await renderTeams(); } catch (error) { toast(error.message, "error"); } }); }});
    }

    // Calendar
    async function renderCalendar() {
        setPageHeader(t("Calendário mensal"), t("PLANEAMENTO"), `
            <button class="btn btn--secondary" data-action="calendar-pdf">${icon("print")}<span class="hide-mobile">${t("Exportar PDF")}</span></button>`);
        els.content.innerHTML = `<section class="page page--wide">
            <div class="page-toolbar">${periodPicker()}<div class="page-toolbar__right dish-toolbar">${state.boot.permissions.teams ? `<button class="btn btn--secondary" data-action="teams-open">${icon("users")} ${t("Gestão Teams")}</button>` : ""}<button class="btn btn--secondary" data-action="dish-roster-open">${icon("check")} ${t("Escala Loiça")}</button></div></div>
            <div id="calendar-root" class="card calendar-shell"></div>
        </section>`;
        await loadCalendar();
    }

    async function renderDishRoster() {
        setPageHeader(t("Escala Loiça"), t("FIM DE SEMANA"), `<button class="btn btn--secondary" data-action="go-calendar">${icon("calendar")} ${t("Voltar ao calendário")}</button>`);
        els.content.innerHTML = `<section class="page page--wide"><div class="page-toolbar">${periodPicker()}<div class="page-toolbar__right dish-toolbar"><button class="btn btn--secondary" data-action="dish-roster-print">${icon("print")} ${t("Imprimir")}</button>${state.boot.permissions.escala_loica_gerir ? `<button class="btn btn--secondary" data-action="dish-roster-generate">${t("Atualizar Escala")}</button><button class="btn btn--primary" data-action="dish-roster-save">${icon("check")} ${t("Gravar")}</button>` : ""}</div></div><div id="dish-roster-root"></div></section>`;
        await loadDishRoster();
    }

    async function loadDishRoster() {
        setLoading(true);
        try {
            state.dishRoster = (await api(`/api/dish-roster?ano=${state.year}&mes=${state.month}`)).data;
            drawDishRoster();
        } finally { setLoading(false); }
    }

    function dishPersonOptions(selected) {
        return `<option value="">${t("Por atribuir")}</option>${state.dishRoster.pessoas.map((person) => `<option value="${person.id}" ${Number(selected) === Number(person.id) ? "selected" : ""}>${esc(person.identificacao)}</option>`).join("")}`;
    }

    function drawDishRoster() {
        const data = state.dishRoster;
        const manager = data.gestor;
        const rows = data.linhas.map((row) => {
            const locked = Boolean(row.validada);
            const observations = row.observacoes.map((item) => `<span>${t("Férias:")} ${esc(item.identificacao)} · ${fmtDate(item.inicio)} a ${fmtDate(item.fim)}</span>`).join("");
            return `<tr data-dish-row data-weekend="${row.fim_semana}" data-original-one="${row.militar_1_id || ""}" data-original-two="${row.militar_2_id || ""}" class="${locked ? "dish-row--validated" : ""}">
                <td class="dish-weekend"><strong>${t("Sábado,")} ${fmtDate(row.fim_semana)}</strong><span>${t("Domingo,")} ${fmtDate(row.domingo)}</span><label class="checkbox dish-validation"><input type="checkbox" data-dish-validation ${locked ? "checked" : ""} ${manager ? "" : "disabled"}> ${t("Validada")}</label></td>
                <td>${manager ? `<select data-dish-person="1" ${locked ? "disabled" : ""}>${dishPersonOptions(row.militar_1_id)}</select>` : `<strong>${esc(row.militar_1 || t("Por atribuir"))}</strong>`}</td>
                <td>${manager ? `<select data-dish-person="2" ${locked ? "disabled" : ""}>${dishPersonOptions(row.militar_2_id)}</select>` : `<strong>${esc(row.militar_2 || t("Por atribuir"))}</strong>`}</td>
                <td class="dish-observations">${observations || `<span>—</span>`}</td>
            </tr>`;
        }).join("");
        $("#dish-roster-root").innerHTML = `<div class="card dish-roster-card"><div class="dish-roster-heading"><div><h2>${t("Escala Loiça - Fim de Semana")}</h2><p>${fmtDate(data.inicio)} a ${fmtDate(data.fim)}</p></div><span class="badge badge--teal">${data.linhas.length} ${t("fins de semana")}</span></div><div class="table-wrap"><table class="data-table dish-roster-table"><thead><tr><th>${t("Fim de Semana")}</th><th>${t("Militar 1")}</th><th>${t("Militar 2")}</th><th>${t("Observações")}</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
    }

    function pendingDishRows(rows = $$('[data-dish-row]'), includeChecked = false) {
        return rows.filter((row) => includeChecked || !$('[data-dish-validation]', row)?.checked).map((row) => ({
            fim_semana: row.dataset.weekend,
            militar_1_id: $('[data-dish-person="1"]', row)?.value || null,
            militar_2_id: $('[data-dish-person="2"]', row)?.value || null,
            original_1: row.dataset.originalOne,
            original_2: row.dataset.originalTwo,
        })).filter((row) =>
            String(row.militar_1_id || "") !== row.original_1 ||
            String(row.militar_2_id || "") !== row.original_2
        ).map(({original_1, original_2, ...row}) => row);
    }

    async function saveDishRows(linhas) {
        return api("/api/dish-roster", {
            method: "PUT",
            body: {ano: state.year, mes: state.month, linhas},
        });
    }

    async function loadCalendar() {
        setLoading(true);
        try {
            state.calendar = await api(`/api/calendar?ano=${state.year}&mes=${state.month}`);
            drawCalendar();
        } finally {
            setLoading(false);
        }
    }

    function drawCalendar() {
        const data = state.calendar;
        const weekdays = state.boot.config.dias_semana;
        const weeks = [...data.semanas];
        while (weeks.length < 6) weeks.push([0, 0, 0, 0, 0, 0, 0]);
        const today = state.boot.config.today;
        const canEditWelfare = data.permissions.editar || data.permissions.ementa;
        const days = weeks.flat().map((day, index) => {
            if (!day) return `<div class="calendar-day outside" aria-hidden="true"></div>`;
            const dateStr = `${state.year}-${String(state.month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
            const items = data.welfares[dateStr] || [];
            const weekend = index % 7 >= 5;
            const isDayOff = data.day_offs.includes(dateStr);
            const birthdays = data.aniversarios?.[dateStr] || [];
            const addAllowed = data.permissions.editar && items.length < 2;
            return `<article class="calendar-day ${items.length ? "has-welfare" : ""} ${birthdays.length ? "birthday" : ""} ${weekend ? "weekend" : ""} ${isDayOff ? "day-off" : ""} ${today === dateStr ? "today" : ""}">
                <div class="calendar-day__top">
                    <span class="calendar-day__number">${day}</span>
                    ${birthdays.map((birthday) => `<span class="calendar-day__birthday"><img src="/assets/cake.png" alt="">${t("Aniversário de")} ${esc(birthday.identificacao)}</span>`).join("")}
                    ${isDayOff ? `<span class="calendar-day__label">Day Off</span>` : ""}
                    ${addAllowed ? `<button class="calendar-day__add" data-action="welfare-add" data-date="${dateStr}" aria-label="${t("Adicionar Welfare")}">${icon("plus")}</button>` : ""}
                </div>
                ${items.map((item) => welfareChip(dateStr, item, canEditWelfare)).join("")}
            </article>`;
        }).join("");
        $("#calendar-root").innerHTML = `
            <div class="calendar-weekdays">${weekdays.map((day) => `<div>${esc(day)}</div>`).join("")}</div>
            <div class="calendar-grid">${days}</div>
            <div class="calendar-legend">
                <strong>${t("Legenda")}</strong>
                <span class="legend-item"><img src="/assets/cooking.png" alt="">Welfare</span>
                <span class="legend-item"><img src="/assets/cake.png" alt="">${t("Aniversário")}</span>
                <span class="legend-item"><img src="/assets/star.png" alt="">${t("Welfare Livre")}</span>
                <span class="legend-item"><span class="legend-swatch weekend"></span>${t("Fim de semana / Day Off")}</span>
                <span class="calendar-total"><img src="/assets/cooking.png" alt=""><span>${t("Total de Welfares")}</span><strong>${data.total}</strong></span>
            </div>`;
    }

    function welfareChip(dateStr, item, canEdit) {
        const menu = [item.prato, item.sobremesa].filter(Boolean).join(" / ");
        return `<button type="button" class="welfare-chip" data-action="welfare-edit" data-date="${dateStr}" data-meal="${attr(item.refeicao)}">
            <span class="welfare-chip__head">
                ${canEdit ? `<img class="welfare-chip__edit" src="/assets/editar.png" alt="" title="${t("Editar Welfare")}">` : ""}
                <strong>${esc(t(item.refeicao))}</strong>
                <span class="welfare-chip__icons">${(item.icones || []).map((file) => `<img src="/assets/${attr(file)}" alt="">`).join("")}</span>
            </span>
            ${item.observacao ? `<span class="welfare-chip__obs">${esc(item.observacao)}</span>` : ""}
            ${(item.local || item.team_nome) ? `<span class="welfare-chip__team">${icon("users")} ${esc([item.local, item.team_nome].filter(Boolean).join(" · "))}</span>` : ""}
            ${menu ? `<span class="welfare-chip__menu">${esc(menu)}</span>` : ""}
        </button>`;
    }

    function openWelfareModal(dateStr, meal = "", existing = null) {
        const items = state.calendar.welfares[dateStr] || [];
        const available = ["Almoço", "Jantar"].filter((name) => !items.some((item) => item.refeicao === name));
        const isExisting = Boolean(existing);
        const full = state.calendar.permissions.editar;
        const menuOnly = !full && state.calendar.permissions.ementa && isExisting;
        const canSave = full || menuOnly;
        const selectedMeal = meal || available[0] || "Almoço";
        const values = existing || {refeicao: selectedMeal, tipo: "Welfare", local: "Recanto", prato: "", sobremesa: "", observacao: ""};
        const title = isExisting ? (canSave ? t("Editar Welfare") : t("Consultar Welfare")) : t("Adicionar Welfare");
        openModal({
            title,
            subtitle: fmtDate(dateStr),
            body: `<form id="welfare-form" class="form-grid">
                <label class="field"><span>${t("Refeição")}</span>
                    <select name="refeicao" ${isExisting ? "disabled" : ""}>
                        ${(isExisting ? [values.refeicao] : available).map((name) => `<option value="${attr(name)}" ${name === values.refeicao ? "selected" : ""}>${esc(t(name))}</option>`).join("")}
                    </select>
                </label>
                <label class="field"><span>${t("Tipo")}</span>
                    <select name="tipo" ${!full ? "disabled" : ""}>${state.boot.config.tipos_welfare.map((type) => `<option value="${attr(type)}" ${type === values.tipo ? "selected" : ""}>${esc(t(type))}</option>`).join("")}</select>
                </label>
                <div class="field field--full welfare-location-field"><span>${t("Local")}</span><div class="welfare-location-options">${["Recanto", "Restaurante", "Outro"].map((place) => `<label class="checkbox"><input name="local" type="checkbox" value="${place}" ${values.local === place ? "checked" : ""} ${!full ? "disabled" : ""}> ${esc(t(place))}</label>`).join("")}</div></div>
                <label class="field field--full"><span>${t("Prato")}</span><input name="prato" value="${attr(values.prato || "")}" ${!canSave ? "disabled" : ""}></label>
                <label class="field field--full"><span>${t("Sobremesa")}</span><input name="sobremesa" value="${attr(values.sobremesa || "")}" ${!canSave ? "disabled" : ""}></label>
                <label class="field field--full"><span>${t("Team responsável")}</span><select name="team_id" ${(!full || !canSave) ? "disabled" : ""}><option value="">${t("Por definir")}</option>${(state.calendar.teams || []).map((team) => `<option value="${team.id}" ${Number(values.team_id) === team.id ? "selected" : ""}>${esc(team.nome)} · ${team.membros.length} ${t("elementos")}</option>`).join("")}</select></label>
                <label class="field field--full"><span>${t("Observação")}</span><textarea name="observacao" ${(!full || !canSave) ? "disabled" : ""}>${esc(values.observacao || "")}</textarea></label>
            </form>`,
            footer: `
                ${isExisting && state.calendar.permissions.apagar ? `<button class="btn btn--danger" type="button" data-welfare-delete>${icon("trash")} ${t("Eliminar")}</button>` : ""}
                <button class="btn btn--secondary" type="button" data-modal-close>${t("Fechar")}</button>
                ${canSave ? `<button class="btn btn--primary" type="submit" form="welfare-form">${icon("check")} ${t("Guardar")}</button>` : ""}`,
            onOpen(modal) {
                const typeSelect = $("select[name='tipo']", modal);
                const localCheckboxes = $$("input[name='local']", modal);
                const teamSelect = $("select[name='team_id']", modal);
                const syncTeam = () => {
                    const recanto = localCheckboxes.some((checkbox) => checkbox.checked && checkbox.value === "Recanto");
                    if (teamSelect) {
                        teamSelect.disabled = !full || !canSave || !recanto;
                        if (!recanto) teamSelect.value = "";
                    }
                };
                localCheckboxes.forEach((checkbox) => checkbox.addEventListener("change", () => {
                    if (checkbox.checked) localCheckboxes.forEach((other) => { if (other !== checkbox) other.checked = false; });
                    syncTeam();
                }));
                typeSelect?.addEventListener("change", () => {
                    localCheckboxes.forEach((checkbox) => { checkbox.checked = checkbox.value === "Recanto" && ["Welfare", "Welfare Aniversário"].includes(typeSelect.value); });
                    syncTeam();
                });
                syncTeam();
                $("#welfare-form", modal)?.addEventListener("submit", async (event) => {
                    event.preventDefault();
                    const form = new FormData(event.currentTarget);
                    const payload = {
                        data: dateStr,
                        refeicao: isExisting ? values.refeicao : form.get("refeicao"),
                        tipo: full ? form.get("tipo") : values.tipo,
                        local: full ? (form.get("local") || "") : (values.local || ""),
                        prato: form.get("prato"),
                        sobremesa: form.get("sobremesa"),
                        team_id: full ? form.get("team_id") : values.team_id,
                        observacao: full ? form.get("observacao") : values.observacao,
                    };
                    setLoading(true);
                    try {
                        const response = await api("/api/welfares", {method: "POST", body: payload});
                        closeModal();
                        toast(response.message);
                        await loadCalendar();
                    } catch (error) {
                        toast(error.message, "error");
                    } finally { setLoading(false); }
                });
                $("[data-welfare-delete]", modal)?.addEventListener("click", async () => {
                    const yes = await confirmDialog(t("Queres eliminar o Welfare de {0} em {1}?", values.refeicao, fmtDate(dateStr)), {title: t("Eliminar Welfare"), danger: true, confirmText: t("Eliminar")});
                    if (!yes) return;
                    setLoading(true);
                    try {
                        const response = await api("/api/welfares", {method: "DELETE", body: {data: dateStr, refeicao: values.refeicao}});
                        closeModal();
                        toast(response.message);
                        await loadCalendar();
                    } catch (error) { toast(error.message, "error"); }
                    finally { setLoading(false); }
                });
            },
        });
    }

    // Welfare Individual
    async function renderIndividual() {
        if (!state.boot.permissions.individual) throw new Error(t("Não tens acesso ao Welfare Individual."));
        setPageHeader(t("Welfare Individual"), t("CONTROLO DE REFEIÇÕES"), `
            <button class="btn btn--secondary" data-action="individual-pdf">${icon("print")}<span class="hide-mobile">${t("Imprimir Welfare Individual")}</span></button>`);
        els.content.innerHTML = `<section class="page page--wide individual-page">
            <div class="page-toolbar">
                ${periodPicker()}
                <div class="segmented">
                    <button type="button" class="${state.individualMode === "welfare" ? "active" : ""}" data-action="individual-mode" data-mode="welfare">${t("Almoço & Jantar")}</button>
                    <button type="button" class="${state.individualMode === "pequeno_almoco" ? "active" : ""}" data-action="individual-mode" data-mode="pequeno_almoco">${t("Pequeno-almoço")}</button>
                </div>
                <span class="page-toolbar__spacer"></span>
                <button id="individual-reset-button" type="button" class="btn btn--secondary" data-action="individual-reset" disabled>${icon("grid")} ${t("Repor origem")}</button>
                <span id="individual-lock-slot"></span>
            </div>
            <div id="individual-root" class="card individual-card"></div>
        </section>
        <div id="pending-slot" aria-live="polite"></div>`;
        state.selected.clear();
        await loadIndividual();
    }

    async function loadIndividual() {
        setLoading(true);
        try {
            const response = await api(`/api/individual?ano=${state.year}&mes=${state.month}&modo=${state.individualMode}`);
            state.individual = response.data;
            state.pending.clear();
            drawIndividual();
        } finally {
            setLoading(false);
        }
    }

    function drawIndividual() {
        renderIndividualToolbar();
        renderIndividualGrid();
    }

    function renderIndividualToolbar() {
        const data = state.individual;
        const resetButton = $("#individual-reset-button");
        if (resetButton) resetButton.disabled = !data.pode_editar || data.modo !== "welfare";

        const lockSlot = $("#individual-lock-slot");
        if (!lockSlot) return;
        lockSlot.innerHTML = data.pode_trancar_mes
            ? `<button type="button" class="btn ${data.mes_trancado ? "btn--soft" : "btn--danger-soft"}" data-action="individual-toggle-lock">
                ${icon(data.mes_trancado ? "unlock" : "lock")}${data.mes_trancado ? t("Destrancar mês") : t("Trancar mês")}</button>`
            : "";
    }

    function individualHeaderState(day) {
        if (day.day_off) return { className: "individual-head--day-off", label: "Day Off" };
        if (day.fim_semana) return { className: "individual-head--weekend", label: t("Fim de semana") };
        return { className: "", label: t("Dia normal") };
    }

    function individualIdentificationWidth(rows) {
        const probe = document.createElement("span");
        const rootStyle = getComputedStyle(document.documentElement);
        Object.assign(probe.style, {
            position: "fixed",
            left: "-10000px",
            top: "0",
            visibility: "hidden",
            whiteSpace: "nowrap",
            fontFamily: rootStyle.fontFamily || "Segoe UI",
            fontSize: "10px",
            fontWeight: "730",
        });
        document.body.append(probe);
        const labels = [
            t("IDENTIFICAÇÃO"),
            t("TOTAL SELECIONADO"),
            "TOTAL DFAC",
            t("SEMANA"),
            ...rows.map((row) => row.identificacao || ""),
        ];
        const longest = labels.reduce((width, label) => {
            probe.textContent = label;
            return Math.max(width, probe.getBoundingClientRect().width);
        }, 0);
        probe.remove();
        // 8 px à esquerda e 10 px à direita, sem encostar o nome à grelha.
        return Math.max(138, Math.ceil(longest) + 19);
    }

    function fitIndividualTable() {
        const scroller = $(".individual-scroll");
        const table = $(".individual-table");
        if (!scroller || !table) return;
        const bodyRows = $$("tbody tr", table);
        if (!bodyRows.length) return;

        table.style.setProperty("--individual-row-height", "31px");
        table.style.setProperty("--individual-row-font", "10px");
        const fixedHeight = [
            ...$$(`thead tr`, table),
            ...$$(`tfoot tr`, table),
        ].reduce((height, row) => height + row.getBoundingClientRect().height, 0);
        const available = Math.max(0, scroller.clientHeight - fixedHeight - 3);
        let rowHeight = Math.min(31, Math.max(14, Math.floor(available / bodyRows.length)));

        const applyDensity = () => {
            const fontSize = rowHeight <= 16 ? 8 : rowHeight <= 20 ? 9 : 10;
            table.style.setProperty("--individual-row-height", `${rowHeight}px`);
            table.style.setProperty("--individual-row-font", `${fontSize}px`);
        };
        applyDensity();

        // Compensa arredondamentos do motor de tabelas para evitar uma barra
        // vertical por apenas alguns píxeis.
        const excess = table.scrollHeight - scroller.clientHeight;
        if (excess > 0 && rowHeight > 12) {
            rowHeight = Math.max(12, rowHeight - Math.ceil(excess / bodyRows.length));
            applyDensity();
        }
    }

    function renderIndividualGrid() {
        const data = state.individual;
        const breakfast = data.modo === "pequeno_almoco";
        if (!data.linhas.length) {
            $("#individual-root").innerHTML = `<div class="empty-state"><div>${icon("users")}<h3>${t("Sem utilizadores ativos")}</h3><p>${t("Não existem pessoas para apresentar neste período.")}</p></div></div>`;
            renderPendingBar();
            return;
        }
        const dayHeader = data.dias.map((day) => {
            const headerState = individualHeaderState(day);
            return `<th class="individual-day-head ${breakfast ? "individual-day-head--single" : ""} ${headerState.className}" colspan="${breakfast ? 1 : 2}" title="${attr(`${day.data} · ${headerState.label}`)}">${day.dia}</th>`;
        }).join("");
        const mealHeader = data.dias.map((day) => {
            const headerState = individualHeaderState(day);
            return breakfast
                ? `<th class="breakfast-head ${headerState.className}" title="${attr(t("Pequeno-almoço · {0}", headerState.label))}">${t("PA")}</th>`
                : `<th class="meal-head ${headerState.className}" title="${attr(t("Almoço · {0}", headerState.label))}">${t("A")}</th><th class="meal-head ${headerState.className}" title="${attr(t("Jantar · {0}", headerState.label))}">${t("J")}</th>`;
        }).join("");

        const rows = data.linhas.map((row) => {
            const dates = data.dias.map((day) => {
                const cells = row.celulas[day.data];
                if (breakfast) return markingButton(row, day, "pequeno_almoco", "Pequeno-Almoço", cells.pequeno_almoco, true);
                return `${markingButton(row, day, "almoco", "Almoço", cells.almoco)}${markingButton(row, day, "jantar", "Jantar", cells.jantar)}`;
            }).join("");
            const arrival = String(row.data_chegada || "").startsWith(`${data.ano}-${String(data.mes).padStart(2, "0")}`);
            const departure = String(row.data_partida || "").startsWith(`${data.ano}-${String(data.mes).padStart(2, "0")}`);
            return `<tr class="${arrival ? "arrival" : ""} ${departure ? "departure" : ""}">
                <td class="sticky-ident" title="${attr(row.identificacao)}">${esc(row.identificacao)}</td>
                ${dates}
                ${breakfast ? "" : `
                    <td class="summary-cell" data-summary="${row.id}-welfare">${fmtNumber(row.resumo.welfare)}</td>
                    <td class="summary-cell" data-summary="${row.id}-cohesion">${fmtNumber(row.resumo.cohesion)}</td>
                    <td class="summary-cell summary-cell--wide" data-summary="${row.id}-reimbursement">${fmtNumber(row.resumo.reimbursement)}</td>
                    <td class="summary-cell summary-cell--wide" data-summary="${row.id}-caixa">${fmtNumber(row.resumo.caixa)}</td>
                    <td class="summary-cell summary-cell--wide" data-summary="${row.id}-final">${fmtNumber(row.resumo.reembolso_final)}</td>
                    <td class="select-cell"><input type="checkbox" data-action="individual-select" data-user="${row.id}" ${state.selected.has(row.id) ? "checked" : ""} aria-label="Selecionar ${attr(row.identificacao)}"></td>`}
            </tr>`;
        }).join("");

        const dailyTotals = data.dias.map((day) => breakfast
            ? `<td data-dfac="${day.data}-pequeno_almoco">${data.totais_dfac[day.data].pequeno_almoco}</td>`
            : `<td data-dfac="${day.data}-almoco">${data.totais_dfac[day.data].almoco}</td><td data-dfac="${day.data}-jantar">${data.totais_dfac[day.data].jantar}</td>`).join("");
        const selectedTotals = getSelectedTotals();
        const summaryHeads = breakfast ? "" : `
            <th class="summary-head" rowspan="2">Welfare</th>
            <th class="summary-head" rowspan="2">${t("Coesão")}</th>
            <th class="summary-head summary-head--wide" rowspan="2">${t("Reembolso")}</th>
            <th class="summary-head summary-head--wide" rowspan="2">${t("Caixa")}</th>
            <th class="summary-head summary-head--wide" rowspan="2">${t("Reembolso final")}</th>
            <th class="summary-head select-head" rowspan="2"><input type="checkbox" data-action="individual-select-all" ${state.selected.size === data.linhas.length && data.linhas.length ? "checked" : ""} aria-label="${t("Selecionar todos")}" title="${t("Selecionar todos")}"></th>`;
        const footSummary = breakfast ? "" : `
            <td>${fmtNumber(data.totais.welfare)}</td><td>${fmtNumber(data.totais.cohesion)}</td>
            <td>${fmtNumber(data.totais.reimbursement)}</td><td>${fmtNumber(data.totais.caixa)}</td>
            <td>${fmtNumber(data.totais.reembolso_final)}</td><td></td>`;
        const selectedRow = breakfast ? "" : `<tr class="selected-total-row">
            <th class="sticky-ident">${t("TOTAL SELECIONADO")}</th>
            ${data.dias.map(() => "<td></td><td></td>").join("")}
            <td>${fmtNumber(selectedTotals.welfare)}</td><td>${fmtNumber(selectedTotals.cohesion)}</td>
            <td>${fmtNumber(selectedTotals.reimbursement)}</td><td>${fmtNumber(selectedTotals.caixa)}</td>
            <td>${fmtNumber(selectedTotals.reembolso_final)}</td><td>${state.selected.size}</td>
        </tr>`;
        const weekRow = individualWeekRow(data, breakfast);
        const identificationWidth = individualIdentificationWidth(data.linhas);
        const tableMinWidth = breakfast
            ? identificationWidth + (data.dias.length * 24)
            : identificationWidth + (data.dias.length * 34) + 290;

        $("#individual-root").innerHTML = `
            <div class="card-header">
                <div><h2>${breakfast ? t("Pequenos-almoços no DFAC") : t("Marcações individuais")}</h2>
                    <p>${data.pode_editar ? t("Clica numa célula ativa para alterar. As mudanças ficam pendentes até gravares.") : t("Modo de consulta.")}</p></div>
                <div class="card-header__actions">
                    <span class="badge badge--teal">${t("Valor Welfare ·")} ${fmtNumber(data.valor_welfare)} XAF</span>
                </div>
            </div>
            <div class="individual-scroll">
                <table class="individual-table ${breakfast ? "individual-table--breakfast" : ""}" style="--individual-table-min:${tableMinWidth}px;--individual-ident-width:${identificationWidth}px">
                    <thead><tr><th class="sticky-ident" rowspan="2">${t("Identificação")}</th>${dayHeader}${summaryHeads}</tr><tr>${mealHeader}</tr></thead>
                    <tbody>${rows}</tbody>
                    <tfoot>
                        <tr class="dfac-total-row"><th class="sticky-ident">TOTAL DFAC</th>${dailyTotals}${footSummary}</tr>
                        ${selectedRow}
                        ${weekRow}
                    </tfoot>
                </table>
            </div>
            <div class="individual-footer">
                <div class="individual-footer__actions">${individualExportActions(data)}</div>
                <div class="dfac-total">${dfacFooterText(data)}</div>
            </div>`;
        fitIndividualTable();
        renderPendingBar();
    }

    function individualWeekRow(data, breakfast) {
        const columnsPerDay = breakfast ? 1 : 2;
        const weekCells = data.semanas.map((week) => {
            const visibleDays = week.dias_mes.filter((day) => day > 0);
            if (!visibleDays.length) return "";
            const span = visibleDays.length * columnsPerDay;
            const number = `S${week.numero}`;
            const actions = data.pode_exportar_semanas
                ? `<span class="week-group__actions">
                    <button type="button" class="week-print-button" data-action="week-pdf" data-start="${week.inicio}" title="${t("Imprimir semana {0}", number)}" aria-label="${t("Imprimir semana {0}", number)}"><strong>${number}</strong>${icon("print")}</button>
                    <button type="button" class="week-excel-button" data-action="week-excel" data-start="${week.inicio}" title="${t("Exportar semana {0} para Excel", number)}" aria-label="${t("Exportar semana {0} para Excel", number)}">${icon("download")}</button>
                </span>`
                : `<strong class="week-group__number">${number}</strong>`;
            const compactClass = visibleDays.length === 1 ? " week-group--compact" : "";
            return `<td class="week-group${compactClass}" colspan="${span}" title="${fmtDate(week.inicio)}">${actions}</td>`;
        }).join("");
        const summarySpace = breakfast ? "" : `<td class="week-summary-space" colspan="6"></td>`;
        return `<tr class="week-row"><th class="sticky-ident">${t("SEMANA")}</th>${weekCells}${summarySpace}</tr>`;
    }

    function markingButton(row, day, key, meal, cell, breakfast = false) {
        const editable = state.individual.pode_editar && cell.ativo && !cell.ferias;
        const mapKey = `${row.id}|${day.data}|${meal}`;
        const pending = state.pending.has(mapKey);
        return `<td><button type="button" class="mark-cell ${breakfast ? "breakfast-cell" : ""} ${day.especial ? "weekend" : ""} ${cell.estado} ${pending ? "pending" : ""} ${editable ? "editable" : ""}"
            data-action="${editable ? "individual-mark" : ""}" data-user="${row.id}" data-date="${day.data}" data-key="${key}" data-meal="${attr(meal)}"
            title="${attr(`${row.identificacao} · ${fmtDate(day.data)} · ${t(meal)}`)}">${cell.estado === "ferias" ? "F" : ""}</button></td>`;
    }

    function individualExportActions(data) {
        if (!data.responsavel_welfare || data.modo === "pequeno_almoco") return "";
        return `
            <button class="btn btn--small btn--warning" data-action="individual-export" data-type="excel_reembolso">${icon("download")} ${t("Excel Reembolso")}</button>
            <button class="btn btn--small btn--soft" data-action="individual-export" data-type="service_note">${icon("download")} Service Note</button>
            <button class="btn btn--small btn--soft" data-action="individual-export" data-type="request">${icon("download")} Request</button>
            <button class="btn btn--small btn--danger-soft" data-action="xfa-open">${icon("coins")} ${t("Distribuição XFA")}</button>`;
    }

    function dfacFooterText(data) {
        if (data.modo === "pequeno_almoco") {
            const total = Object.values(data.totais_dfac).reduce((sum, item) => sum + item.pequeno_almoco, 0);
            return t("TOTAL DFAC Pequeno-Almoço: {0}", total);
        }
        const lunch = Object.values(data.totais_dfac).reduce((sum, item) => sum + item.almoco, 0);
        const dinner = Object.values(data.totais_dfac).reduce((sum, item) => sum + item.jantar, 0);
        return t("DFAC Almoço: {0} · Jantar: {1} · Total: {2}", lunch, dinner, lunch + dinner);
    }

    function getSelectedTotals() {
        const totals = {welfare: 0, cohesion: 0, reimbursement: 0, caixa: 0, reembolso_final: 0};
        state.individual?.linhas.forEach((row) => {
            if (!state.selected.has(row.id)) return;
            Object.keys(totals).forEach((key) => totals[key] += Number(row.resumo[key] || 0));
        });
        return totals;
    }

    function toggleIndividualMark(button) {
        const userId = Number(button.dataset.user);
        const dateStr = button.dataset.date;
        const meal = button.dataset.meal;
        const key = button.dataset.key;
        const row = state.individual.linhas.find((item) => item.id === userId);
        const day = state.individual.dias.find((item) => item.data === dateStr);
        const cell = row.celulas[dateStr][key];
        if (cell._original === undefined) cell._original = Boolean(cell.marcado);
        const previous = Boolean(cell.marcado);
        const next = !previous;
        cell.marcado = next;
        if (meal === "Pequeno-Almoço") cell.estado = next ? "dfac" : "nao_dfac";
        else cell.estado = next ? "welfare" : "dfac";

        const mapKey = `${userId}|${dateStr}|${meal}`;
        if (next === cell._original) state.pending.delete(mapKey);
        else state.pending.set(mapKey, {user_id: userId, data: dateStr, refeicao: meal, marcado: next});

        const delta = next ? 1 : -1;
        if (meal === "Pequeno-Almoço") {
            state.individual.totais_dfac[dateStr].pequeno_almoco += delta;
        } else {
            const summaryKey = day.especial ? "welfare" : "cohesion";
            row.resumo[summaryKey] += delta;
            row.resumo.reimbursement += delta * state.individual.valor_welfare;
            row.resumo.reembolso_final = Math.max(0, row.resumo.reimbursement - row.resumo.caixa);
            state.individual.totais[summaryKey] += delta;
            state.individual.totais.reimbursement += delta * state.individual.valor_welfare;
            state.individual.totais.reembolso_final = state.individual.linhas.reduce((sum, item) => sum + item.resumo.reembolso_final, 0);
            state.individual.totais_dfac[dateStr][key] -= delta;
        }
        drawIndividual();
    }

    function renderPendingBar() {
        const slot = $("#pending-slot");
        if (!slot) return;
        if (state.individual?.mes_trancado) {
            slot.innerHTML = `<div class="pending-bar pending-bar--locked" role="status">
                ${icon("lock")}<strong>${t("Request efetuado! Alterações indisponíveis!")}</strong>
            </div>`;
            return;
        }
        if (!state.pending.size) {
            slot.innerHTML = "";
            return;
        }
        slot.innerHTML = `<div class="pending-bar">
            <strong>${state.pending.size} ${state.pending.size === 1 ? t("alteração pendente") : t("alterações pendentes")}</strong>
            <button class="btn btn--small btn--secondary" data-action="pending-cancel">${t("Anular")}</button>
            <button class="btn btn--small btn--success" data-action="pending-save">${icon("check")} ${t("Guardar alterações")}</button>
        </div>`;
    }

    async function savePending() {
        if (!state.pending.size) return true;
        setLoading(true);
        try {
            const response = await api("/api/individual/markings", {
                method: "PUT",
                body: {ano: state.year, mes: state.month, changes: [...state.pending.values()]},
            });
            toast(response.message);
            await loadIndividual();
            return true;
        } catch (error) {
            toast(error.message, "error");
            return false;
        } finally {
            setLoading(false);
        }
    }

    async function exportIndividual(type, extra = {}) {
        if (state.pending.size) {
            toast(t("Guarda ou anula as alterações pendentes antes de exportar."), "warning");
            return;
        }
        const selectionExports = ["excel_reembolso", "service_note", "request"];
        if (selectionExports.includes(type) && !state.selected.size) {
            toast(t("Seleciona pelo menos uma pessoa."), "warning");
            return;
        }
        if (type === "request") {
            const proceed = await confirmDialog(t("Não esquecer de verificar e colocar o N.º da Request no documento gerado."), {title: "Request", confirmText: t("Gerar documento")});
            if (!proceed) return;
        }
        if (type === "service_note") {
            const proceed = await confirmDialog(t("Não esquecer de verificar e colocar o N.º da Service Note no documento gerado."), {title: "Service Note", confirmText: t("Gerar documento")});
            if (!proceed) return;
        }
        await download("/api/individual/export", {
            method: "POST",
            body: {
                tipo: type,
                ano: state.year,
                mes: state.month,
                utilizador_ids: [...state.selected],
                ...extra,
            },
        }, "export");
    }

    function openPrintMode() {
        openModal({
            title: t("Imprimir Welfare Individual"),
            subtitle: t("Escolhe o formato mais adequado"),
            body: `<div class="settings-grid">
                <button class="card card-body" data-print-pages="1" style="text-align:left;border-color:var(--teal-100)">
                    <h3>${t("1 página")}</h3><p class="muted">${t("Formato compacto, toda a grelha numa página.")}</p>
                </button>
                <button class="card card-body" data-print-pages="2" style="text-align:left;border-color:var(--teal-100)">
                    <h3>${t("2 páginas")}</h3><p class="muted">${t("Maior e mais legível para impressão.")}</p>
                </button>
            </div>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Cancelar")}</button>`,
            onOpen(modal) {
                $$("[data-print-pages]", modal).forEach((button) => button.addEventListener("click", () => {
                    const pages = Number(button.dataset.printPages);
                    closeModal();
                    exportIndividual("pdf_mes", {modo_paginas: pages});
                }));
            },
        });
    }

    function openXfaModal() {
        if (!state.selected.size) {
            toast(t("Seleciona pelo menos uma pessoa para a Distribuição XFA."), "warning");
            return;
        }
        const selectedRows = state.individual.linhas.filter((row) => state.selected.has(row.id));
        const denoms = [10000, 5000, 2000, 1000, 500];
        const selectedTotals = selectedRows.reduce((totals, row) => {
            totals.reimbursement += Number(row.resumo.reimbursement || 0);
            totals.final += Number(row.resumo.reembolso_final || 0);
            totals.caixa += Number(row.resumo.caixa || 0);
            return totals;
        }, {reimbursement: 0, final: 0, caixa: 0});
        const selectedSummary = `<div class="xfa-ready-summary">
            <h3>${t("Pronto para calcular")}</h3>
            <div class="table-wrap"><table class="data-table xfa-ready-table">
                <thead><tr><th>${t("Pessoa")}</th><th>${t("Reembolso Total")}</th><th>${t("Valor para Caixa")}</th><th class="xfa-ready-final">${t("Reembolso final")}</th></tr></thead>
                <tbody>${selectedRows.map((row) => `<tr>
                    <td title="${attr(row.identificacao)}">${esc(row.identificacao)}</td>
                    <td>${fmtNumber(row.resumo.reimbursement || 0)} XAF</td>
                    <td>${fmtNumber(row.resumo.caixa || 0)} XAF</td>
                    <td class="xfa-ready-final">${fmtNumber(row.resumo.reembolso_final || 0)} XAF</td>
                </tr>`).join("")}</tbody>
                <tfoot><tr><th>${t("Total")}</th><th data-xfa-total="reembolso">${fmtNumber(selectedTotals.reimbursement)} XAF</th><th>${fmtNumber(selectedTotals.caixa)} XAF</th><th class="xfa-ready-final" data-xfa-total="final">${fmtNumber(selectedTotals.final)} XAF</th></tr></tfoot>
            </table></div>
            <p>${t("Indica o stock de notas e clica em Calcular.")}</p>
        </div>`;
        openModal({
            title: t("Distribuição XFA"),
            subtitle: t("{0} pessoas selecionadas", selectedRows.length),
            size: "xl",
            body: `<form id="xfa-form" class="xfa-layout">
                <div>
                    <div class="xfa-stock-heading"><h3>${t("Notas disponíveis")}</h3><strong id="xfa-stock-total">${fmtNumber(0)} XAF</strong></div>
                    <div class="banknote-grid">${denoms.map((denom) => `<label class="banknote-row">
                        <img src="/assets/${denom}.png" alt="${denom} XAF">
                        <span class="field" style="margin:0"><span>${fmtNumber(denom)} XAF</span><input type="number" min="0" value="0" name="stock-${denom}"></span>
                    </label>`).join("")}</div>
                    <fieldset style="border:0;padding:0;margin:30px 0 0">
                        <legend style="font-weight:750;font-size:12px;margin-bottom:8px">${t("Escolha o tipo de Reembolso:")}</legend>
                        <label class="radio"><input type="radio" name="tipo_valor" value="reembolso" checked> ${t("Reembolso Total")}</label>
                        <label class="radio" style="margin-left:14px"><input type="radio" name="tipo_valor" value="final"> ${t("Reembolso Final")}</label>
                    </fieldset>
                    <label class="checkbox" style="margin-top:14px"><input id="xfa-manual-toggle" type="checkbox"> ${t("Definir valores manualmente")}</label>
                    <div id="xfa-manual" class="manual-values hidden">${selectedRows.map((row) => `<label class="manual-value-row">
                        <span>${esc(row.identificacao)}</span><input class="input" type="number" min="0" name="manual-${row.id}" value="${row.resumo.reimbursement}">
                    </label>`).join("")}</div>
                    <button class="btn btn--primary btn--block" style="margin-top:16px" type="submit">${icon("coins")} ${t("Calcular distribuição")}</button>
                </div>
                <div>
                    <div id="xfa-results" class="xfa-results">${selectedSummary}</div>
                </div>
            </form>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Fechar")}</button>`,
            onOpen(modal) {
                $("#xfa-manual-toggle", modal).addEventListener("change", (event) => $("#xfa-manual", modal).classList.toggle("hidden", !event.target.checked));
                const updateStockTotal = () => {
                    const total = denoms.reduce((sum, denom) => {
                        const quantity = Number($("[name=\"stock-" + denom + "\"]", modal).value || 0);
                        return sum + (Number.isFinite(quantity) && quantity > 0 ? quantity * denom : 0);
                    }, 0);
                    $("#xfa-stock-total", modal).textContent = `${fmtNumber(total)} XAF`;
                };
                denoms.forEach((denom) => $("[name=\"stock-" + denom + "\"]", modal).addEventListener("input", updateStockTotal));
                const updateSelectedTotal = () => {
                    const selectedType = $("[name=\"tipo_valor\"]:checked", modal).value;
                    $$('[data-xfa-total]', modal).forEach((cell) => cell.classList.toggle("xfa-ready-selected", cell.dataset.xfaTotal === selectedType));
                };
                $$('[name="tipo_valor"]', modal).forEach((input) => input.addEventListener("change", updateSelectedTotal));
                updateSelectedTotal();
                $("#xfa-form", modal).addEventListener("submit", async (event) => {
                    event.preventDefault();
                    const form = new FormData(event.currentTarget);
                    const manual = $("#xfa-manual-toggle", modal).checked;
                    const stock = Object.fromEntries(denoms.map((denom) => [denom, Number(form.get(`stock-${denom}`) || 0)]));
                    const stockTotal = denoms.reduce((total, denom) => total + (denom * Math.max(0, stock[denom])), 0);
                    if (stockTotal <= 0) {
                        toast(t("Indica o número de notas disponíveis para iniciar o cálculo."), "warning");
                        return;
                    }
                    const payload = {
                        ano: state.year,
                        mes: state.month,
                        utilizador_ids: [...state.selected],
                        tipo_valor: form.get("tipo_valor"),
                        stock,
                        valores_manuais: manual ? Object.fromEntries(selectedRows.map((row) => [row.id, Number(form.get(`manual-${row.id}`) || 0)])) : null,
                    };
                    setLoading(true);
                    try {
                        const response = await api("/api/xfa", {method: "POST", body: payload});
                        renderXfaResults(response.data, modal);
                    } catch (error) { toast(error.message, "error"); }
                    finally { setLoading(false); }
                });
            },
        });
    }

    function renderXfaResults(data, modal) {
        const leftoverNotes = Object.entries(data.sobra).sort(([first], [second]) => Number(second) - Number(first));
        const leftoverTotal = leftoverNotes.reduce((total, [denom, quantity]) => total + (Number(denom) * Number(quantity || 0)), 0);
        const hasShortfalls = data.resultados.some((row) => Number(row.valor_em_falta || 0) > 0);
        $("#xfa-results", modal).innerHTML = `
            <div class="card-header"><div><h3>${t("Distribuição calculada")}</h3><p>${t("Necessário")} ${fmtNumber(data.total_necessario)} XAF · ${t("Disponível")} ${fmtNumber(data.total_disponivel)} XAF</p></div></div>
            <div class="table-wrap"><table class="data-table xfa-result-table">
                <thead><tr><th>${t("Pessoa")}</th><th>${t("Valor")}</th><th>10.000</th><th>5.000</th><th>2.000</th><th>1.000</th><th>500</th>${hasShortfalls ? `<th>${t("Observações")}</th>` : ""}</tr></thead>
                <tbody>${data.resultados.map((row) => `<tr data-xfa-result>
                    <td><strong>${esc(row.identificacao)}</strong></td><td>${fmtNumber(row.valor)}</td>
                    ${[10000,5000,2000,1000,500].map((denom) => `<td class="xfa-result-note">${row.notas[denom] || 0}</td>`).join("")}
                    ${hasShortfalls ? `<td>${row.valor_em_falta ? `<strong class="xfa-shortfall">${t("Em falta:")} ${fmtNumber(row.valor_em_falta)} XAF</strong>` : "—"}</td>` : ""}
                </tr>`).join("")}</tbody>
            </table></div>
            <div class="info-banner xfa-leftover-banner" style="margin:12px">${icon("info")}<div class="xfa-leftover-copy"><strong>${t("NOTAS QUE SOBRAM:")}</strong> ${leftoverNotes.map(([denom, qtd]) => `${fmtNumber(denom)}: ${qtd}`).join(" · ")}</div><strong class="xfa-leftover-total">${t("Total")}: ${fmtNumber(leftoverTotal)} XAF</strong>${data.falhas.length ? `<div class="xfa-incomplete"><strong>${t("Distribuição incompleta:")}</strong> ${esc(data.falhas.join(", "))}</div>` : ""}</div>`;
        $$("[data-xfa-result]", modal).forEach((row) => row.addEventListener("click", () => row.classList.toggle("done")));
    }

    // Users / Personnel
    async function renderUsersPage(adminContext = false) {
        setPageHeader(adminContext ? t("Administração") : t("Pessoal"), adminContext ? t("SISTEMA") : t("GESTÃO DE PESSOAL"));
        els.content.innerHTML = `<section class="page">
            <div class="page-toolbar">
                ${state.boot.permissions.pessoal_editar ? `<button class="btn btn--primary" data-action="user-new">${icon("plus")} ${t("Novo utilizador")}</button>` : ""}
                <button class="btn btn--secondary" data-action="users-toggle-all">${state.usersAll ? t("Mostrar só ativos") : t("Mostrar todos")}</button>
                <span class="page-toolbar__spacer"></span>
                <label class="search-box">${icon("search")}<input id="user-search" placeholder="${t("Pesquisar por NIM, nome ou posto…")}" value="${attr(state.userSearch)}"></label>
            </div>
            <div id="users-root" class="card"></div>
        </section>`;
        await loadUsers();
    }

    async function loadUsers(redraw = true) {
        setLoading(true);
        try {
            const response = await api(`/api/users?todos=${state.usersAll ? 1 : 0}`);
            state.users = response.users;
            if (redraw) drawUsers();
        } finally { setLoading(false); }
    }

    function drawUsers(root = $("#users-root")) {
        if (!root) return;
        const query = state.userSearch.trim().toLocaleLowerCase("pt");
        const users = state.users.filter((user) => {
            const haystack = `${user.nim} ${user.posto} ${user.nome} ${user.sobrenome} ${user.area_funcional || ""} ${user.posicao_numero || ""} ${user.acessos.join(" ")}`.toLocaleLowerCase("pt");
            return !query || haystack.includes(query);
        });
        root.innerHTML = `
            <div class="card-header"><div><h2>${t("Utilizadores")}</h2><p>${users.length} ${t("registos")} ${state.usersAll ? t("ativos e históricos") : t("ativos")}</p></div>
                <div class="card-header__actions"><span class="badge badge--teal">${state.users.length} total</span></div></div>
            <div class="table-wrap"><table class="data-table">
                <thead><tr><th>${t("Identificação")}</th><th>NIM</th><th>${t("Área funcional")}</th><th>${t("Posição N.º")}</th><th>${t("Antiguidade")}</th><th>${t("Funções")}</th><th>${t("Chegada")}</th><th>${t("Partida")}</th><th>${t("Acessos")}</th><th></th></tr></thead>
                <tbody>${users.map((user) => userRow(user)).join("")}</tbody>
            </table>${users.length ? "" : `<div class="empty-state"><div>${icon("search")}<h3>${t("Sem resultados")}</h3><p>${t("Experimenta outro termo de pesquisa.")}</p></div></div>`}</div>`;
    }

    function userRow(user) {
        return `<tr>
            <td><div class="person-cell"><span class="avatar">${esc(initials(user))}</span><span><strong>${esc(user.identificacao)}</strong><small>${esc(`${user.nome} ${user.sobrenome}`.trim())}</small></span></div></td>
            <td><strong>${esc(user.nim)}</strong></td>
            <td>${esc(areaLabel(user.area_funcional))}</td>
            <td>${esc(user.posicao_numero || "—")}</td>
            <td>${user.antiguidade ? fmtDate(user.antiguidade) : "—"}</td>
            <td><span class="status-icons">
                ${user.snr ? `<span class="status-icon" title="SNR"><img src="/assets/snr.png" alt="SNR"></span>` : ""}
                ${user.snr_substituto ? `<span class="badge ${user.snr_substituto_ativo ? "badge--green" : "badge--amber"}" title="${fmtDate(user.snr_substituto_inicio)} a ${fmtDate(user.snr_substituto_fim)}">${t("Subst. SNR")}</span>` : ""}
                ${user.responsavel_welfare ? `<span class="status-icon" title="${t("Responsável Welfare")}"><img src="/assets/cook.png" alt="${t("Responsável Welfare")}"></span>` : ""}
                ${user.master ? `<span class="badge badge--red">${t("Mestre")}</span>` : ""}
            </span></td>
            <td>${fmtDateTime(user.data_chegada)}</td><td>${fmtDateTime(user.data_partida)}</td>
            <td><span class="access-list">${user.acessos.map((access) => `<span class="badge">${esc(t(access))}</span>`).join("")}</span></td>
            <td class="actions-cell">
                ${state.boot.permissions.pessoal_editar || (state.boot.permissions.snr_substituicao && !user.master && !user.snr) ? `<button class="icon-btn" data-action="user-edit" data-id="${user.id}" title="${state.boot.permissions.pessoal_editar ? t("Editar") : t("Nomear substituto SNR")}">${icon("edit")}</button>` : ""}
                ${state.boot.permissions.pessoal_editar && !user.master ? `<button class="icon-btn icon-btn--danger" data-action="user-delete" data-id="${user.id}" title="${t("Eliminar")}">${icon("trash")}</button>` : ""}
            </td>
        </tr>`;
    }

    function openUserModal(user = null) {
        const editing = Boolean(user);
        const master = Boolean(user?.master);
        const admin = state.boot.permissions.admin;
        const canEditPerson = state.boot.permissions.pessoal_editar;
        const canAssignSubstitute = Boolean(editing && state.boot.permissions.snr_substituicao && !master && !user?.snr);
        const substitutionOnly = Boolean(editing && !canEditPerson && canAssignSubstitute);
        const lockedProfile = master || substitutionOnly;
        if (!editing && !canEditPerson) return;
        const currentAccess = new Set(user?.acessos || ["Leitura"]);
        const functionsField = `<div class="field"><span>${t("Funções")}</span><span class="people-form-checkline">
            <label class="checkbox"><input name="snr" type="checkbox" ${user?.snr ? "checked" : ""} ${lockedProfile ? "disabled" : ""}> SNR</label>
            <label class="checkbox"><input name="responsavel_welfare" type="checkbox" ${user?.responsavel_welfare ? "checked" : ""} ${lockedProfile ? "disabled" : ""}> ${t("Responsável Welfare")}</label>
        </span></div>`;
        const manualVacationField = `<label class="field"><span>${t("Total de dias Férias (manual)")}</span><input name="ferias_direito_override" type="number" min="0" max="365" step="0.5" value="${attr(user?.ferias_direito_override ?? "")}" ${lockedProfile ? "disabled" : ""}><small>${t("Vazio: cálculo automático a 30/360.")}</small></label>`;
        const missionField = `<div class="field"><span>${t("Missão")}</span><span class="people-form-checkline"><label class="checkbox"><input name="missao_prorrogada" type="checkbox" ${user?.missao_prorrogada ? "checked" : ""} ${lockedProfile ? "disabled" : ""}> ${t("Missão prorrogada")}</label></span></div>`;
        openModal({
            title: editing ? t("Editar utilizador") : t("Novo utilizador"),
            subtitle: editing ? user.identificacao : t("Criar um novo acesso à aplicação"),
            size: "people",
            body: `<form id="user-form">
                ${master ? `<div class="info-banner" style="margin-bottom:16px">${icon("lock")}<span>${t("O utilizador mestre está protegido e não pode ser alterado.")}</span></div>` : ""}
                <div class="form-grid form-grid--3 people-form-grid">
                    <label class="field"><span class="required">${t("NIM / Utilizador")}</span><input name="nim" value="${attr(user?.nim || "")}" ${lockedProfile ? "disabled" : ""} required></label>
                    <label class="field"><span>${t("Posto da missão")}</span><select name="posto" ${lockedProfile ? "disabled" : ""}>${state.boot.config.postos.map((posto) => `<option ${posto === (user?.posto_missao || user?.posto) ? "selected" : ""}>${esc(posto)}</option>`).join("")}</select></label>
                    <label class="field"><span>${t("Posto português")}</span><select name="posto_portugal" ${lockedProfile ? "disabled" : ""}><option value="">${t("Sem correspondência")}</option>${state.boot.config.postos_portugal.map((posto) => `<option ${posto === user?.posto_portugal ? "selected" : ""}>${esc(posto)}</option>`).join("")}</select></label>
                    <label class="field"><span>${t("Antiguidade")}</span><input name="antiguidade" type="date" value="${attr(String(user?.antiguidade || "").slice(0,10))}" ${lockedProfile ? "disabled" : ""}></label>
                    <label class="field"><span>${t("Nome")}</span><input name="nome" value="${attr(user?.nome || "")}" ${lockedProfile ? "disabled" : ""}></label>
                    <label class="field"><span>${t("Sobrenome")}</span><input name="sobrenome" value="${attr(user?.sobrenome || "")}" ${lockedProfile ? "disabled" : ""}></label>
                    <label class="field"><span>${t("Data Nascimento")}</span><input name="data_nascimento" type="date" value="${attr(String(user?.data_nascimento || "").slice(0,10))}" ${lockedProfile ? "disabled" : ""}></label>
                    <label class="field"><span>${t("Telemóvel Serviço")}</span><input name="telemovel_servico" value="${attr(user?.telemovel_servico || "")}" ${lockedProfile ? "disabled" : ""}></label>
                    <label class="field"><span>${t("Área funcional")}</span><input name="area_funcional" value="${attr(user?.area_funcional === "Não definido" ? "" : user?.area_funcional || "")}" placeholder="${attr(t("Não definido"))}" ${lockedProfile ? "disabled" : ""}></label>
                    <label class="field"><span>${t("Posição N.º")}</span><input name="posicao_numero" maxlength="40" value="${attr(user?.posicao_numero || "")}" ${lockedProfile ? "disabled" : ""}></label>
                    ${admin ? functionsField : manualVacationField}
                    ${dateTimeField("data_chegada", t("Data/hora de chegada"), user?.data_chegada, {disabled: lockedProfile})}
                    ${dateTimeField("data_partida", t("Data/hora de partida"), user?.data_partida, {disabled: lockedProfile})}
                    ${admin ? manualVacationField : missionField}
                    ${admin ? missionField : ""}
                    <div class="people-password-row field--full">
                        <label class="field"><span>${editing ? t("Nova password") : "Password"}</span><input name="password" type="password" autocomplete="new-password" ${lockedProfile ? "disabled" : ""}><small>${editing ? t("Deixa em branco para manter a atual.") : t("Obrigatória para novo utilizador.")}</small></label>
                        <label class="field"><span>${t("Confirmar password")}</span><input name="confirmar_password" type="password" autocomplete="new-password" ${lockedProfile ? "disabled" : ""}></label>
                    </div>
                    <label class="field field--full"><span>${t("Notas de férias")}</span><textarea name="notas_ferias" ${lockedProfile ? "disabled" : ""}>${esc(user?.notas_ferias || "")}</textarea></label>
                    ${canAssignSubstitute ? snrSubstitutionFields(user) : ""}
                </div>
                <div style="margin-top:5px">
                    <p style="font-size:12px;font-weight:750">${t("Tipos de acesso")}</p>
                    ${admin ? `<div class="checkbox-grid">${state.boot.config.tipos_acesso.map((access) => `<label class="access-option">
                        <input type="checkbox" name="acessos" value="${attr(access)}" ${currentAccess.has(access) ? "checked" : ""} ${master ? "disabled" : ""}>
                        <strong>${esc(t(access))}</strong><small>${esc(t(state.boot.config.tipos_acesso_descricao[access] || ""))}</small>
                    </label>`).join("")}</div>` : `<div class="field-note">${esc([...currentAccess].map((access) => t(access)).join(", "))} ${t("· Apenas os Administradores alteram os Tipos de Acesso e atribuem as funções de SNR e Responsável Welfare.")}</div>`}
                </div>
            </form>`,
            footer: `
                <button class="btn btn--secondary" data-modal-close>${t("Fechar")}</button>
                ${master || (!canEditPerson && !canAssignSubstitute) ? "" : `<button class="btn btn--primary" type="submit" form="user-form">${icon("check")} ${t("Guardar")}</button>`}`,
            onOpen(modal) {
                const missionRank = $('[name="posto"]', modal);
                const portugueseRank = $('[name="posto_portugal"]', modal);
                missionRank?.addEventListener("change", () => {
                    portugueseRank.value = state.boot.config.posto_portugal_padrao[missionRank.value] || "";
                });
                if (!editing && missionRank && portugueseRank) portugueseRank.value = state.boot.config.posto_portugal_padrao[missionRank.value] || "";
                $("#user-form", modal).addEventListener("submit", async (event) => {
                    event.preventDefault();
                    const form = new FormData(event.currentTarget);
                    const substitutionPayload = canAssignSubstitute ? {
                        snr_substituto: form.get("snr_substituto") === "on",
                        snr_substituto_inicio: form.get("snr_substituto_inicio") || "",
                        snr_substituto_fim: form.get("snr_substituto_fim") || "",
                    } : {};
                    if (substitutionOnly) {
                        setLoading(true);
                        try {
                            const response = await api(`/api/users/${user.id}/snr-substitution`, {method: "PUT", body: substitutionPayload});
                            closeModal(); toast(response.message); await loadUsers();
                        } catch (error) { toast(error.message, "error"); }
                        finally { setLoading(false); }
                        return;
                    }
                    const payload = {
                        nim: form.get("nim"), posto: form.get("posto"), posto_portugal: form.get("posto_portugal"), antiguidade: form.get("antiguidade"),
                        nome: form.get("nome"), sobrenome: form.get("sobrenome"),
                        data_nascimento: form.get("data_nascimento"),
                        data_chegada: form.get("data_chegada"), data_partida: form.get("data_partida"),
                        telemovel_servico: form.get("telemovel_servico"),
                        ...(admin ? {
                            snr: form.get("snr") === "on",
                            responsavel_welfare: form.get("responsavel_welfare") === "on",
                        } : {}),
                        area_funcional: form.get("area_funcional"),
                        posicao_numero: form.get("posicao_numero"),
                        ferias_direito_override: form.get("ferias_direito_override"),
                        missao_prorrogada: form.get("missao_prorrogada") === "on",
                        notas_ferias: form.get("notas_ferias"),
                        password: form.get("password"), confirmar_password: form.get("confirmar_password"),
                        acessos: form.getAll("acessos"),
                        ...substitutionPayload,
                    };
                    setLoading(true);
                    try {
                        const response = await api(editing ? `/api/users/${user.id}` : "/api/users", {method: editing ? "PUT" : "POST", body: payload});
                        closeModal(); toast(response.message); await loadUsers();
                    } catch (error) { toast(error.message, "error"); }
                    finally { setLoading(false); }
                });
            },
        });
    }

    // Vacations
    const vacationActionable = new Set(["Pendente", "Alteração pendente", "Cancelamento pendente"]);

    function vacationYearOptions(selected) {
        const year = Number(selected || new Date().getFullYear());
        return Array.from({length: 11}, (_, index) => year - 4 + index)
            .map((item) => `<option value="${item}" ${item === year ? "selected" : ""}>${item}</option>`).join("");
    }

    function vacationStatusClass(status) {
        if (["Aprovado"].includes(status)) return "green";
        if (vacationActionable.has(status)) return "amber";
        if (["Rejeitado", "Anulado"].includes(status)) return "red";
        if (status === "Devolvido") return "blue";
        return "teal";
    }

    function vacationStatusBadge(status) {
        return `<span class="vacation-status vacation-status--${vacationStatusClass(status)}"><span></span>${esc(t(status))}</span>`;
    }

    function vacationMetric(label, value, suffix = "") {
        return `<span class="vacation-metric"><small>${esc(label)}</small><strong>${value ?? "—"}${value !== null && value !== undefined ? suffix : ""}</strong></span>`;
    }

    function vacationStats(summary, management = false) {
        const items = management ? [
            ["users", t("Pessoas"), summary.pessoas, t("Elementos registados")],
            ["calendar", t("Períodos"), summary.periodos, t("{0} dias de férias", summary.dias_planeados)],
            ["check", t("Aprovados"), summary.aprovados, t("Refletidos no Welfare Individual")],
            ["alert", t("Ações pendentes"), summary.pendentes, t("Aguardam decisão")],
        ] : [
            ["calendar", t("Direito"), summary.direito, t("Dias calculados para a missão")],
            ["plane", t("Planeados"), summary.planeados, t("{0} período(s)", summary.periodos)],
            ["check", t("Aprovados"), summary.aprovados, t("Dias de férias autorizados")],
            ["coins", t("Dias para Guia de Marcha"), summary.disponiveis, t("{0} ação(ões) pendente(s)", summary.pendentes)],
        ];
        return `<div class="stats-grid vacation-stats">${items.map((item, index) => `<article class="stat-card ${index === 3 && Number(item[2]) > 0 ? "stat-card--amber" : index === 2 ? "stat-card--green" : ""}">
            <span class="stat-icon">${icon(item[0])}</span><div><small>${esc(item[1])}</small><strong>${item[2] ?? "—"}</strong><span>${esc(item[3])}</span></div>
        </article>`).join("")}</div>`;
    }

    function findVacation(id) {
        const own = state.myVacations?.pedidos || [];
        const managed = state.vacationManagement?.pedidos || [];
        return [...own, ...managed].find((item) => item.id === Number(id));
    }

    async function refreshVacationPage() {
        if (state.page === "my-vacations") await loadMyVacations();
        else if (state.page === "vacations") await loadVacationManagement();
    }

    function vacationRequestActions(item, context = "private") {
        const own = Number(item.utilizador_id) === Number(state.boot.user.id);
        const canDecide = state.boot.permissions.ferias_decidir;
        const actions = [`<button class="btn btn--small btn--secondary" data-action="vacation-detail" data-id="${item.id}">${icon("info")} ${t("Detalhes")}</button>`];
        if (own && ["Pendente", "Devolvido"].includes(item.estado)) {
            actions.push(`<button class="btn btn--small btn--secondary" data-action="vacation-edit" data-id="${item.id}">${icon("edit")} ${t("Corrigir")}</button>`);
        }
        if (own && ["Pendente", "Devolvido"].includes(item.estado)) {
            actions.push(`<button class="btn btn--small btn--ghost-danger" data-action="vacation-withdraw" data-id="${item.id}">${t("Retirar")}</button>`);
        }
        if (own && item.estado === "Aprovado") {
            actions.push(`<button class="btn btn--small btn--secondary" data-action="vacation-change" data-id="${item.id}">${icon("edit")} ${t("Pedir alteração")}</button>`);
            actions.push(`<button class="btn btn--small btn--ghost-danger" data-action="vacation-cancel" data-id="${item.id}">${t("Pedir cancelamento")}</button>`);
        }
        if (context === "management" && canDecide && item.estado === "Pendente") {
            actions.push(`<button class="btn btn--small btn--success" data-action="vacation-decision" data-id="${item.id}" data-workflow="request" data-decision="approve">${icon("check")} ${t("Aprovar")}</button>`);
            actions.push(`<button class="btn btn--small btn--secondary" data-action="vacation-decision" data-id="${item.id}" data-workflow="request" data-decision="return">${t("Devolver")}</button>`);
            actions.push(`<button class="btn btn--small btn--ghost-danger" data-action="vacation-decision" data-id="${item.id}" data-workflow="request" data-decision="reject">${t("Rejeitar")}</button>`);
        }
        if (context === "management" && canDecide && item.estado === "Alteração pendente") {
            actions.push(`<button class="btn btn--small btn--success" data-action="vacation-decision" data-id="${item.id}" data-workflow="change" data-decision="approve">${icon("check")} ${t("Aprovar alteração")}</button>`);
            actions.push(`<button class="btn btn--small btn--ghost-danger" data-action="vacation-decision" data-id="${item.id}" data-workflow="change" data-decision="reject">${t("Rejeitar")}</button>`);
        }
        if (context === "management" && canDecide && item.estado === "Cancelamento pendente") {
            actions.push(`<button class="btn btn--small btn--success" data-action="vacation-decision" data-id="${item.id}" data-workflow="cancellation" data-decision="approve">${icon("check")} ${t("Aprovar cancelamento")}</button>`);
            actions.push(`<button class="btn btn--small btn--ghost-danger" data-action="vacation-decision" data-id="${item.id}" data-workflow="cancellation" data-decision="reject">${t("Rejeitar")}</button>`);
        }
        const adminEdit = context === "management" && state.boot.permissions.admin
            ? `<button class="btn btn--small btn--warning vacation-admin-edit-btn" data-action="vacation-admin-edit" data-id="${item.id}" title="${t("Editar pedido")}" aria-label="${t("Editar pedido")}">${icon("edit")}</button>`
            : "";
        if (context === "management" && state.boot.permissions.ferias_atualizar_horas && item.estado === "Aprovado") {
            if (!state.vacationManagementAll) actions.push(adminEdit);
            actions.push(`<button class="btn btn--small btn--warning vacation-update-hours-btn" data-action="vacation-update-hours" data-id="${item.id}">${icon("clock")} ${t("Atualizar Horas")}</button>`);
            if (state.vacationManagementAll) actions.push(adminEdit);
        } else if (adminEdit) {
            actions.push(adminEdit);
        }
        if (context === "management" && state.boot.permissions.admin && !own && item.estado === "Aprovado") {
            actions.push(`<button class="btn btn--small btn--ghost-danger" data-action="vacation-annul" data-id="${item.id}">${t("Anular autorização")}</button>`);
        }
        if (context === "management" && canDecide && item.estado === "Anulado") {
            actions.push(`<button class="btn btn--small btn--secondary" data-action="vacation-restore" data-id="${item.id}">${icon("unlock")} ${t("Reverter anulação")}</button>`);
        }
        if (context === "management" && state.boot.permissions.admin) {
            actions.push(`<button class="btn btn--small btn--ghost-danger" data-action="vacation-delete" data-id="${item.id}">${icon("trash")} ${t("Apagar")}</button>`);
        }
        return actions.join("");
    }

    function vacationRequestCard(item, context = "private") {
        const summary = item.resumo || {};
        const proposed = item.estado === "Alteração pendente" && item.proposta_data_hora_inicio ? `
            <div class="vacation-proposal"><strong>${t("Alteração proposta")}</strong><span>${fmtDateTime(item.proposta_data_hora_inicio)} → ${fmtDateTime(item.proposta_data_hora_fim)}</span></div>` : "";
        return `<article class="vacation-request-card ${vacationActionable.has(item.estado) ? "vacation-request-card--pending" : ""}">
            <header><div>${context === "management" ? `<strong class="vacation-person-name">${esc(item.identificacao)}</strong><small>${esc(item.nim)} · ${esc(areaLabel(item.area_funcional))}</small>` : `<strong>${t("Pedido #")}${item.id}</strong><small>${t("Atualizado em")} ${fmtDateTime(item.atualizado_em)}</small>`}</div>${vacationStatusBadge(item.estado)}</header>
            <div class="vacation-route">
                <span class="vacation-route__mark">${icon("plane")}</span>
                <div><small>${t("PARTIDA")}</small><strong>${fmtDateTime(item.data_hora_inicio)}</strong></div>
                <span class="vacation-route__line"></span>
                <div><small>${t("CHEGADA")}</small><strong>${fmtDateTime(item.data_hora_fim)}</strong></div>
            </div>
            <div class="vacation-request-meta">
                ${vacationMetric(t("Férias"), summary.dias_ferias, " d")}${vacationMetric(t("Viagem"), summary.dias_viagem, " d")}${vacationMetric(t("FS / Feriados"), summary.dias_fim_semana_feriado, " d")}
                ${item.companhia_aerea ? `<span class="vacation-flight">${icon("plane")} ${esc(item.companhia_aerea)}</span>` : ""}
            </div>
            ${item.observacao ? `<p class="vacation-note">${esc(item.observacao)}</p>` : ""}${proposed}
            ${item.motivo_fluxo ? `<p class="vacation-flow-note"><strong>${t("Motivo:")}</strong> ${esc(item.motivo_fluxo)}</p>` : ""}
            <footer>${vacationRequestActions(item, context)}</footer>
        </article>`;
    }

    function vacationHistoryTable(items, context = "private") {
        const management = context === "management" || context === "planning";
        const readonly = context === "planning";
        return `<div class="card vacation-history-card"><div class="table-wrap"><table class="data-table vacation-history-table ${management ? "vacation-history-table--management" : ""}">
            <thead><tr><th>${t("Estado")}</th>${management ? "<th>Pessoa</th>" : ""}<th>${t("Partida")}</th><th>${t("Chegada")}</th><th>${t("Dias")}</th><th>${t("Informação")}</th>${readonly ? "" : "<th></th>"}</tr></thead>
            <tbody>${items.map((item) => {
                const summary = item.resumo || {};
                const information = [item.companhia_aerea, item.observacao].filter(Boolean).join(" · ");
                return `<tr>
                    <td>${vacationStatusBadge(item.estado)}</td>
                    ${management ? `<td class="vacation-history-person"><strong>${esc(item.identificacao)}</strong><small>${esc(item.nim)} · ${esc(areaLabel(item.area_funcional))}</small></td>` : ""}
                    <td class="vacation-history-period"><strong>${fmtDate(item.data_hora_inicio)}</strong><small>${esc(String(item.data_hora_inicio || "").slice(11, 16))}</small></td>
                    <td class="vacation-history-period"><strong>${fmtDate(item.data_hora_fim)}</strong><small>${esc(String(item.data_hora_fim || "").slice(11, 16))}</small></td>
                    <td class="vacation-history-days"><strong>${summary.dias_ferias ?? 0} F</strong> · ${summary.dias_viagem ?? 0} TD · ${summary.dias_fim_semana_feriado ?? 0} FS</td>
                    <td>${information ? esc(information) : "—"}</td>
                    ${readonly ? "" : `<td class="actions-cell"><div class="vacation-table-actions">${vacationRequestActions(item, context)}</div></td>`}
                </tr>`;
            }).join("")}</tbody>
        </table></div></div>`;
    }

    function vacationNotificationKey(channel) {
        return channel === "gestao" ? "ferias_gestao_nao_lidas" : "ferias_pessoais_nao_lidas";
    }

    function vacationNotificationCount(channel) {
        return Number(state.boot.notifications?.[vacationNotificationKey(channel)] || 0);
    }

    function setVacationNotificationCount(channel, count) {
        state.boot.notifications = {
            ...(state.boot.notifications || {}),
            [vacationNotificationKey(channel)]: Math.max(0, Number(count || 0)),
        };
    }

    function syncVacationNotificationCount() {
        $$("[data-vacation-notification-count]").forEach((badge) => {
            const channel = badge.dataset.vacationNotificationCount || "pessoal";
            const count = vacationNotificationCount(channel);
            const label = count > 99 ? "99+" : String(count);
            badge.classList.toggle("hidden", !count);
            badge.textContent = count ? label : "";
            badge.title = count ? t("{0} {1} por ler", count, count === 1 ? t("notificação") : t("notificações")) : "";
            badge.setAttribute("aria-label", badge.title);
        });
        $$("[data-action='vacation-notifications']", els.topActions).forEach((button) => {
            const channel = button.dataset.notificationChannel || "pessoal";
            const count = vacationNotificationCount(channel);
            const label = count > 99 ? "99+" : String(count);
            const current = $(".button-count", button);
            if (!count) current?.remove();
            else if (current) current.textContent = label;
            else button.insertAdjacentHTML("beforeend", `<b class="button-count">${label}</b>`);
        });
    }

    async function renderMyVacations() {
        const personalCount = vacationNotificationCount("pessoal");
        setPageHeader(t("As minhas férias"), t("ÁREA PRIVADA"), `
            <button class="btn btn--secondary" data-action="vacation-notifications" data-notification-channel="pessoal">${icon("info")}<span class="hide-mobile">${t("Notificações")}</span>${personalCount ? `<b class="button-count">${personalCount > 99 ? "99+" : personalCount}</b>` : ""}</button>
            <button class="btn btn--primary" data-action="vacation-new">${icon("plus")}<span class="hide-mobile">${t("Novo pedido")}</span></button>`);
        els.content.innerHTML = `<section class="page vacation-page">
            <div id="my-vacations-summary"></div>
            <div class="vacation-section-head">
                <div class="segmented">
                    <button class="${state.myVacationTab === "requests" ? "active" : ""}" data-action="my-vacation-tab" data-tab="requests">${t("Pedidos")}</button>
                    <button class="${state.myVacationTab === "calendar" ? "active" : ""}" data-action="my-vacation-tab" data-tab="calendar">${t("Calendário")}</button>
                </div>
                <div class="vacation-section-controls">
                    <button id="my-vacations-toggle-all" class="btn btn--secondary ${state.myVacationTab === "requests" ? "" : "hidden"}" data-action="my-vacations-toggle-all">${icon(state.myVacationsAll ? "calendar" : "grid")} ${state.myVacationsAll ? t("Mostrar atuais") : t("Mostrar tudo")}</button>
                    <label id="my-vacation-year-wrap" class="compact-field ${state.myVacationTab === "calendar" ? "" : "hidden"}"><span>${t("Ano")}</span><select id="my-vacation-year">${vacationYearOptions(state.vacationYear)}</select></label>
                </div>
            </div>
            <div id="my-vacations-root"></div>
        </section>`;
        await loadMyVacations();
    }

    async function loadMyVacations() {
        setLoading(true);
        try {
            const response = await api(`/api/vacations/me?ano=${state.vacationYear}&todos=${state.myVacationsAll ? 1 : 0}`);
            state.myVacations = response.data;
            state.vacationNotifications = response.data.notificacoes || [];
            state.vacationNotificationChannel = "pessoal";
            setVacationNotificationCount("pessoal", response.data.nao_lidas);
            drawMyVacations();
            syncVacationNotificationCount();
        } finally { setLoading(false); }
    }

    async function drawMyVacations() {
        const data = state.myVacations;
        if (!data) return;
        const showAllButton = $("#my-vacations-toggle-all");
        showAllButton?.classList.toggle("hidden", state.myVacationTab !== "requests");
        if (showAllButton) {
            showAllButton.innerHTML = `${icon(state.myVacationsAll ? "calendar" : "grid")} ${state.myVacationsAll ? t("Mostrar atuais") : t("Mostrar tudo")}`;
            showAllButton.setAttribute("aria-pressed", String(state.myVacationsAll));
        }
        $("#my-vacation-year-wrap")?.classList.toggle("hidden", state.myVacationTab !== "calendar");
        $("#my-vacations-summary").innerHTML = `${vacationStats(data.resumo)}
            ${!data.pessoa.data_chegada || !data.pessoa.data_partida ? `<div class="info-banner vacation-warning">${icon("info")}<span>${t("As datas da missão não estão completas. O direito automático e alguns limites só ficam disponíveis depois de serem definidos pela gestão.")}</span></div>` : ""}`;
        const root = $("#my-vacations-root");
        if (state.myVacationTab === "calendar") {
            root.innerHTML = `<div class="card empty-state"><div><div class="loader"></div></div></div>`;
            await loadVacationCalendar(false);
            return;
        }
        root.innerHTML = data.pedidos.length
            ? state.myVacationsAll
                ? vacationHistoryTable(data.pedidos)
                : `<div class="vacation-request-list">${data.pedidos.map((item) => vacationRequestCard(item)).join("")}</div>`
            : `<div class="card empty-state"><div>${icon("umbrella")}<h3>${state.myVacationsAll ? t("Ainda não existem férias registadas") : t("Sem férias atuais ou futuras")}</h3><p>${state.myVacationsAll ? t("Cria o primeiro período com data e hora de partida e de chegada.") : t("Usa “Mostrar tudo” para consultar períodos cujo regresso já passou.")}</p><button class="btn btn--primary" data-action="vacation-new">${icon("plus")} ${t("Novo pedido")}</button></div></div>`;
    }

    async function renderVacations() {
        const managementCount = vacationNotificationCount("gestao");
        setPageHeader(t("Gestão de Férias"), t("SNR · APROVAÇÕES"), `
            ${state.boot.permissions.snr ? `<button class="btn btn--secondary" data-action="vacation-notifications" data-notification-channel="gestao">${icon("info")}<span class="hide-mobile">${t("Notificações")}</span>${managementCount ? `<b class="button-count">${managementCount > 99 ? "99+" : managementCount}</b>` : ""}</button>` : ""}
            <button class="btn btn--secondary" data-action="vacation-print">${icon("print")}<span class="hide-mobile">${t("Imprimir")}</span></button>
            <button class="btn btn--secondary" data-action="vacation-report">${icon("download")}<span class="hide-mobile">${t("Relatório Excel")}</span></button>
            ${state.boot.permissions.ferias_gerir ? `<button class="btn btn--primary" data-action="vacation-new-managed">${icon("plus")}<span class="hide-mobile">${t("Novo pedido")}</span></button>` : ""}`);
        syncVacationNotificationCount();
        els.content.innerHTML = `<section class="page page--wide vacation-page vacation-management">
            <div id="vacation-management-summary"></div>
            <div class="vacation-section-head">
                <div class="segmented vacation-tabs">
                    <button class="${state.vacationManagementTab === "requests" ? "active" : ""}" data-action="vacation-management-tab" data-tab="requests">${t("Pedidos")}</button>
                    <button class="${state.vacationManagementTab === "calendar" ? "active" : ""}" data-action="vacation-management-tab" data-tab="calendar">${t("Calendário")}</button>
                    <button class="${state.vacationManagementTab === "people" ? "active" : ""}" data-action="vacation-management-tab" data-tab="people">${t("Pessoal e direitos")}</button>
                    <button class="${state.vacationManagementTab === "rules" ? "active" : ""}" data-action="vacation-management-tab" data-tab="rules">${t("Regras e feriados")}</button>
                </div>
            </div>
            <div id="vacation-management-root"></div>
        </section>`;
        await loadVacationManagement();
    }

    async function renderVacationPlanning() {
        setPageHeader(t("Planeamento Geral"), t("FÉRIAS · CALENDÁRIO"));
        els.content.innerHTML = `<section class="page page--wide vacation-page vacation-management">
            <div id="vacation-planning-root"><div class="card empty-state"><div><div class="loader"></div></div></div></div>
        </section>`;
        if (state.vacationPlanningMode === "list") await loadVacationPlanning();
        else await loadVacationCalendar(true);
    }

    function vacationPlanningQuery() {
        const query = new URLSearchParams({todos: state.vacationPlanningAll ? "1" : "0"});
        query.set("grupo_estado", state.vacationPlanningFilters.statusGroup || "all");
        if (state.vacationPlanningFilters.area) query.set("area", state.vacationPlanningFilters.area);
        if (state.vacationPlanningFilters.search) query.set("pesquisa", state.vacationPlanningFilters.search);
        return query.toString();
    }

    async function loadVacationPlanning() {
        setLoading(true);
        try {
            const response = await api(`/api/vacations/planning?${vacationPlanningQuery()}`);
            state.vacationPlanning = response.data;
            drawVacationPlanningList();
        } finally { setLoading(false); }
    }

    function drawVacationPlanningList() {
        const data = state.vacationPlanning;
        const root = $("#vacation-planning-root");
        if (!root || !data) return;
        const filters = state.vacationPlanningFilters;
        root.innerHTML = `<div class="vacation-planning-toolbar">
            <div><strong>${t("Vista em lista")}</strong><small>${state.vacationPlanningAll ? t("Histórico completo de férias") : t("Férias atuais e futuras")}</small></div>
            <div><button class="btn btn--secondary" data-action="vacation-planning-print">${icon("print")} ${t("Imprimir")}</button><button class="btn btn--secondary" data-action="vacation-planning-mode" data-mode="calendar">${icon("calendar")} ${t("Vista em calendário")}</button></div>
        </div><div class="vacation-filterbar card">
            <label class="search-box vacation-filterbar__search">${icon("search")}<input id="planning-vacation-search" placeholder="${t("NIM, posto ou nome…")}" value="${attr(filters.search)}"></label>
            <div class="segmented vacation-state-filter" role="group" aria-label="${t("Filtrar férias por estado")}">
                ${[["all", t("Todas")], ["pending", t("Pendentes")], ["approved", t("Aprovadas")], ["annulled", t("Anuladas")]].map(([value, label]) => `<button class="${filters.statusGroup === value ? "active" : ""}" data-action="vacation-planning-filter-state" data-state="${value}">${label}</button>`).join("")}
            </div>
            <label class="compact-field"><span>${t("Área")}</span><select id="planning-vacation-area"><option value="">${t("Todas")}</option>${data.areas.map((area) => `<option value="${attr(area)}" ${filters.area === area ? "selected" : ""}>${esc(areaLabel(area))}</option>`).join("")}</select></label>
            <button class="btn btn--secondary" data-action="vacation-planning-apply">${icon("search")} ${t("Aplicar")}</button>
            <button class="btn btn--ghost" data-action="vacation-planning-clear">${t("Limpar")}</button>
            <button class="btn btn--secondary vacation-filterbar__mode" data-action="vacation-planning-toggle-all">${icon(state.vacationPlanningAll ? "calendar" : "grid")} ${state.vacationPlanningAll ? t("Só atuais") : t("Incluir passadas")}</button>
        </div>${data.pedidos.length ? vacationHistoryTable(data.pedidos, "planning") : `<div class="card empty-state"><div>${icon("search")}<h3>${state.vacationPlanningAll ? t("Sem férias para estes filtros") : t("Sem férias atuais ou futuras")}</h3><p>${t("Altera os filtros ou inclui as férias passadas.")}</p></div></div>`}`;
    }

    function vacationManagementQuery() {
        const selectedYear = state.vacationManagementTab === "rules"
            ? state.vacationHolidayYear : state.vacationYear;
        const query = new URLSearchParams({ano: String(selectedYear)});
        const showAll = state.vacationManagementTab === "people"
            ? state.vacationPeopleAll : state.vacationManagementAll;
        query.set("todos", showAll ? "1" : "0");
        query.set("grupo_estado", state.vacationFilters.statusGroup || "all");
        if (state.vacationFilters.area) query.set("area", state.vacationFilters.area);
        if (state.vacationFilters.search) query.set("pesquisa", state.vacationFilters.search);
        return query.toString();
    }

    async function loadVacationManagement() {
        setLoading(true);
        try {
            const response = await api(`/api/vacations/manage?${vacationManagementQuery()}`);
            state.vacationManagement = response.data;
            await drawVacationManagement();
        } finally { setLoading(false); }
    }

    async function drawVacationManagement() {
        const data = state.vacationManagement;
        if (!data) return;
        $("#vacation-management-summary").innerHTML = `${vacationStats(data.resumo, true)}
            ${state.boot.permissions.snr_titular ? `<div class="info-banner snr-substitution-banner">${icon("info")}<span><strong>${t("Vai estar de férias?")}</strong> ${t("Pode nomear temporariamente outra pessoa como substituto SNR no perfil dessa pessoa, no separador “Pessoal e direitos”.")}</span><button class="btn btn--secondary btn--small" data-action="vacation-substitution-people">${t("Escolher substituto")}</button></div>` : ""}`;
        const root = $("#vacation-management-root");
        if (state.vacationManagementTab === "calendar") {
            root.innerHTML = `<div class="card empty-state"><div><div class="loader"></div></div></div>`;
            await loadVacationCalendar(true);
        } else if (state.vacationManagementTab === "people") {
            drawVacationPeople(root, data);
        } else if (state.vacationManagementTab === "rules") {
            drawVacationRules(root, data);
        } else {
            drawVacationRequests(root, data);
        }
    }

    function drawVacationRequests(root, data) {
        root.innerHTML = `<div class="vacation-filterbar card">
            <label class="search-box vacation-filterbar__search">${icon("search")}<input id="vacation-search" placeholder="${t("NIM, posto ou nome…")}" value="${attr(state.vacationFilters.search)}"></label>
            <div class="segmented vacation-state-filter" role="group" aria-label="${t("Filtrar licenças por estado")}">
                ${[
                    ["all", t("Todas")],
                    ["pending", t("Pendentes")],
                    ["approved", t("Aprovadas")],
                    ["annulled", t("Anuladas")],
                ].map(([value, label]) => `<button class="${state.vacationFilters.statusGroup === value ? "active" : ""}" data-action="vacation-filter-state" data-state="${value}" aria-pressed="${state.vacationFilters.statusGroup === value}">${label}</button>`).join("")}
            </div>
            <label class="compact-field"><span>${t("Área")}</span><select id="vacation-area"><option value="">${t("Todas")}</option>${data.areas.map((area) => `<option value="${attr(area)}" ${state.vacationFilters.area === area ? "selected" : ""}>${esc(areaLabel(area))}</option>`).join("")}</select></label>
            <button class="btn btn--secondary" data-action="vacation-apply-filters">${icon("search")} ${t("Aplicar")}</button>
            <button class="btn btn--ghost" data-action="vacation-clear-filters">${t("Limpar")}</button>
            <button class="btn btn--secondary vacation-filterbar__mode" data-action="vacations-toggle-all">${icon(state.vacationManagementAll ? "calendar" : "grid")} ${state.vacationManagementAll ? t("Só atuais") : t("Incluir passadas")}</button>
        </div>
        ${data.pedidos.length
            ? state.vacationManagementAll
                ? vacationHistoryTable(data.pedidos, "management")
                : `<div class="vacation-request-list vacation-request-list--management">${data.pedidos.map((item) => vacationRequestCard(item, "management")).join("")}</div>`
            : `<div class="card empty-state"><div>${icon("search")}<h3>${state.vacationManagementAll ? t("Sem férias para estes filtros") : t("Sem férias atuais ou futuras")}</h3><p>${state.vacationManagementAll ? t("Altera o estado, a área ou a pesquisa.") : t("Usa “Mostrar tudo” para consultar períodos cuja chegada já passou.")}</p></div></div>`}`;
    }

    function drawVacationPeople(root, data) {
        root.innerHTML = `<div class="card">
            <div class="card-header"><div><h2>${t("Pessoal e direitos")}</h2><p>${t("Cálculo 30/360, missão, área funcional e períodos planeados.")}</p></div><div class="team-actions"><span class="badge badge--teal">${data.pessoas.length} ${t("pessoas")}</span><button class="btn btn--secondary btn--small" data-action="vacation-people-toggle-all">${state.vacationPeopleAll ? t("Mostrar atuais") : t("Mostrar todos")}</button></div></div>
            <div class="table-wrap"><table class="data-table vacation-people-table"><thead><tr><th>${t("Pessoa")}</th><th>${t("Área")}</th><th>${t("Posição N.º")}</th><th>${t("Missão")}</th><th>${t("Direito")}</th><th>${t("Planeados")}</th><th class="vacation-days-gm">${t("Dias para GM")}</th><th>${t("Períodos")}</th><th></th></tr></thead>
            <tbody>${data.pessoas.map((person) => `<tr><td><div class="person-cell"><span class="avatar">${esc(initials(person))}</span><span><strong>${esc(person.identificacao)}</strong><small>${esc(person.nim)}${person.snr_substituto ? t(" · Subst. SNR: {0}–{1}", fmtDate(person.snr_substituto_inicio), fmtDate(person.snr_substituto_fim)) : ""}</small></span></div></td>
                <td>${esc(areaLabel(person.area_funcional))}</td><td>${esc(person.posicao_numero || "—")}</td><td><span class="date-pair">${fmtDate(person.data_chegada)}<small>${t("até")}</small>${fmtDate(person.data_partida)}</span></td>
                <td><strong>${person.resumo.direito ?? "—"}</strong></td><td>${person.resumo.planeados}</td><td class="vacation-days-gm"><strong class="${Number(person.resumo.disponiveis) < 0 ? "danger-text" : ""}">${person.resumo.disponiveis ?? "—"}</strong></td><td>${person.resumo.periodos}</td>
                <td class="actions-cell"><button class="icon-btn" data-action="vacation-person-edit" data-id="${person.id}" title="${t("Editar dados de férias")}">${icon("edit")}</button></td></tr>`).join("")}</tbody></table></div>
        </div>`;
    }

    function drawVacationRules(root, data) {
        const settings = data.settings;
        const readonly = !state.boot.permissions.admin;
        root.innerHTML = `<div class="vacation-rules-grid">
            <article class="card settings-card"><div class="card-header"><div><h2>${t("Regras de planeamento")}</h2><p>${t("Parâmetros transportados da aplicação de férias.")}</p></div>${readonly ? `<span class="badge">${t("Só leitura para SNR")}</span>` : ""}</div>
            <div class="card-body"><form id="vacation-settings-form" class="form-grid form-grid--3">
                <label class="field"><span>${t("Dias por mês")}</span><input type="number" step="0.1" name="dias_por_mes" value="${attr(settings.dias_por_mes)}" ${readonly ? "disabled" : ""}></label>
                <label class="field"><span>${t("Máx. dias de ausência")}</span><input type="number" name="max_dias_ausencia" value="${attr(settings.max_dias_ausencia)}" ${readonly ? "disabled" : ""}></label>
                <label class="field"><span>${t("Máx. ausentes por área (%)")}</span><input type="number" step="0.1" name="max_percentagem_area" value="${attr(settings.max_percentagem_area)}" ${readonly ? "disabled" : ""}></label>
                <label class="field"><span>${t("Chegada antes de")}</span><input type="time" name="hora_limite_chegada" value="${attr(settings.hora_limite_chegada)}" ${readonly ? "disabled" : ""}></label>
                <label class="field"><span>${t("Bloqueio no início/fim")}</span><input type="number" name="dias_bloqueio_missao" value="${attr(settings.dias_bloqueio_missao)}" ${readonly ? "disabled" : ""}></label>
                <label class="field"><span>${t("Máximo de períodos")}</span><input type="number" name="max_periodos" value="${attr(settings.max_periodos)}" ${readonly ? "disabled" : ""}></label>
                <label class="field"><span>${t("Ano de referência")}</span><input type="number" name="ano_calendario" value="${attr(settings.ano_calendario)}" ${readonly ? "disabled" : ""}></label>
                <label class="field"><span>${t("Limite da área")}</span><select name="modo_limite_area" ${readonly ? "disabled" : ""}><option value="warning" ${settings.modo_limite_area === "warning" ? "selected" : ""}>${t("Avisar e permitir confirmação")}</option><option value="block" ${settings.modo_limite_area === "block" ? "selected" : ""}>${t("Bloquear pedido")}</option></select></label>
                ${readonly ? "" : `<div class="field vacation-settings-submit"><span>&nbsp;</span><button class="btn btn--primary" type="submit">${icon("check")} ${t("Guardar regras")}</button></div>`}
            </form></div></article>
            <article class="card"><div class="card-header holiday-card-header"><div><h2>${t("Feriados")}</h2><p>${t("São classificados como FS no cálculo dos períodos.")}</p></div><div class="holiday-card-actions">${state.boot.permissions.admin ? `<button class="btn btn--small btn--secondary" data-action="vacation-holiday-import">${icon("download")} ${t("Importar nacionais")}</button>` : ""}<button class="btn btn--small btn--primary" data-action="vacation-holiday-new">${icon("plus")} ${t("Novo")}</button></div></div>
                <div class="holiday-year-picker"><button class="icon-btn" data-action="vacation-holiday-year" data-delta="-1" title="${t("Ano anterior")}">${icon("left")}</button><label class="field"><span>${t("Ano dos feriados")}</span><input type="number" min="1900" max="2200" value="${attr(data.ano)}" data-holiday-year></label><button class="icon-btn" data-action="vacation-holiday-year" data-delta="1" title="${t("Ano seguinte")}">${icon("right")}</button></div>
                <div class="holiday-list">${data.feriados.length ? data.feriados.map((holiday) => `<div class="holiday-item ${holiday.ativo ? "" : "holiday-item--inactive"}"><span class="holiday-date">${fmtDate(holiday.data)}</span><div><strong>${esc(holiday.descricao)}</strong><small>${holiday.ativo ? t("Ativo") : t("Inativo")}</small></div><button class="icon-btn" data-action="vacation-holiday-edit" data-id="${holiday.id}" title="${t("Editar")}">${icon("edit")}</button><button class="icon-btn icon-btn--danger" data-action="vacation-holiday-delete" data-id="${holiday.id}" title="${t("Eliminar")}">${icon("trash")}</button></div>`).join("") : `<div class="empty-state empty-state--small"><div><p>${t("Sem feriados em")} ${data.ano}.</p></div></div>`}</div>
            </article>
        </div>`;
        $("#vacation-settings-form", root)?.addEventListener("submit", async (event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            const body = Object.fromEntries(form.entries());
            setLoading(true);
            try { const response = await api("/api/vacations/settings", {method: "PUT", body}); toast(response.message); await loadVacationManagement(); }
            catch (error) { toast(error.message, "error"); }
            finally { setLoading(false); }
        });
        $("[data-holiday-year]", root)?.addEventListener("change", async (event) => {
            const year = Number(event.currentTarget.value);
            if (year < 1900 || year > 2200) return toast(t("Indica um ano entre 1900 e 2200."), "error");
            state.vacationHolidayYear = year;
            await loadVacationManagement();
        });
    }

    async function loadVacationCalendar(management) {
        const query = new URLSearchParams({ano: state.vacationYear, mes: state.vacationMonth});
        if (management) query.set("scope", "all");
        const response = await api(`/api/vacations/calendar?${query}`);
        state.vacationCalendar = response.data;
        drawVacationCalendar(management);
    }

    function drawVacationCalendar(management) {
        const data = state.vacationCalendar;
        const planning = state.page === "vacation-planning";
        const root = planning ? $("#vacation-planning-root") : management ? $("#vacation-management-root") : $("#my-vacations-root");
        if (!root || !data) return;
        const holidays = new Set((data.feriados || []).map((item) => item.data));
        const dayHeaders = data.dias.map((iso) => {
            const day = new Date(`${iso}T12:00:00`);
            const special = day.getDay() === 0 || day.getDay() === 6 || holidays.has(iso);
            return `<th class="${special ? "vacation-calendar-special" : ""}"><span>${String(day.getDate()).padStart(2, "0")}</span><small>${new Intl.DateTimeFormat(locale(), {weekday: "short"}).format(day).replace(".", "")}</small></th>`;
        }).join("");
        const rows = data.pessoas.map((person) => `<tr><th class="vacation-calendar-person"><strong>${esc(person.identificacao)}</strong>${management ? `<small>${esc(areaLabel(person.area_funcional))}</small>` : ""}</th>${data.dias.map((iso) => {
            const mark = data.grelha[String(person.id)]?.[iso];
            const day = new Date(`${iso}T12:00:00`);
            const special = day.getDay() === 0 || day.getDay() === 6 || holidays.has(iso);
            const arrival = String(person.data_chegada || "").slice(0, 10);
            const departure = String(person.data_partida || "").slice(0, 10);
            const outsideMission = (arrival && iso < arrival) || (departure && iso > departure);
            const cellClass = outsideMission
                ? "vacation-calendar-outside-mission"
                : mark
                    ? `vacation-code vacation-code--${mark.codigo.toLowerCase()} ${vacationActionable.has(mark.estado) ? "vacation-code--pending" : ""}`
                    : special ? "vacation-calendar-special" : "";
            const cellAttrs = outsideMission
                ? `title="${t("Fora da missão")}"`
                : mark ? `${planning ? "" : `data-action="vacation-detail" data-id="${mark.feria_id}"`} title="${attr(t(mark.estado))}"` : "";
            return `<td class="${cellClass}" ${cellAttrs}>${outsideMission ? "" : mark ? esc(mark.codigo) : ""}</td>`;
        }).join("")}</tr>`).join("");
        const legend = `<div class="vacation-calendar-legend"><span><b class="vacation-legend-code vacation-legend-code--f">F</b> ${t("Férias")}</span><span><b class="vacation-legend-code vacation-legend-code--td">TD</b> ${t("Viagem")}</span><span><b class="vacation-legend-code vacation-legend-code--fs">FS</b> ${t("Fim de semana / feriado")}</span><span><b class="vacation-legend-outside-mission"></b> ${t("Fora da missão")}</span><span><b class="vacation-legend-pending"></b> ${t("Decisão pendente")}</span></div>`;
        root.innerHTML = `<div class="vacation-calendar-toolbar">
            <div class="period-picker"><button class="icon-btn" data-action="vacation-month" data-delta="-1">${icon("left")}</button><strong>${esc(state.boot.config.meses[state.vacationMonth] || state.vacationMonth)} ${state.vacationYear}</strong><button class="icon-btn" data-action="vacation-month" data-delta="1">${icon("right")}</button></div>
            <div class="vacation-calendar-toolbar__actions">${legend}${management ? `<button class="btn btn--secondary" data-action="vacation-calendar-print">${icon("print")} ${planning ? t("Imprimir") : t("Imprimir mês")}</button>${planning ? `<button class="btn btn--secondary" data-action="vacation-planning-mode" data-mode="list">${icon("grid")} ${t("Vista em lista")}</button>` : ""}` : ""}</div>
        </div><div class="card vacation-calendar-card"><div class="table-wrap"><table class="vacation-calendar-table"><thead><tr><th class="vacation-calendar-person">${t("Pessoa")}</th>${dayHeaders}</tr></thead><tbody>${rows}</tbody>${management ? `<tfoot><tr><th class="vacation-calendar-person">${t("AUSENTES")}</th>${data.dias.map((iso) => `<td title="${t("{0}% dos ativos", Math.round(data.diario[iso].percentagem))}">${data.diario[iso].ausentes}</td>`).join("")}</tr></tfoot>` : ""}</table></div></div>`;
    }

    function printVacationPlanningList() {
        const root = $("#vacation-planning-root");
        const table = $(".vacation-history-table", root);
        if (!table) return toast(t("A lista de férias ainda não está disponível."), "warning");
        $("#vacation-planning-print-report")?.remove();
        const report = document.createElement("section");
        report.id = "vacation-planning-print-report";
        report.className = "vacation-calendar-print-report";
        report.innerHTML = `<header class="vacation-calendar-print-header"><div><p>${t("CONTINGENTE PORTUGUÊS · EUTM RCA")}</p><h1>${t("Planeamento Geral · Lista de férias")}</h1></div><div><strong>${state.vacationPlanning?.pedidos?.length || 0} ${t("períodos")}</strong><small>${t("Gerado em")} ${esc(new Intl.DateTimeFormat(locale(), {dateStyle: "short", timeStyle: "short"}).format(new Date()))}</small></div></header><div class="vacation-planning-print-table">${table.outerHTML}</div>`;
        const originalTitle = document.title;
        const cleanup = () => { document.body.classList.remove("vacation-planning-list-printing"); report.remove(); document.title = originalTitle; };
        document.body.append(report);
        document.body.classList.add("vacation-planning-list-printing");
        document.title = "SIGCP_Planeamento_Geral_Lista_Ferias";
        window.addEventListener("afterprint", cleanup, {once: true});
        window.print();
    }

    function printVacationCalendar() {
        const data = state.vacationCalendar;
        const root = state.page === "vacation-planning" ? $("#vacation-planning-root") : $("#vacation-management-root");
        const table = $(".vacation-calendar-table", root);
        const legend = $(".vacation-calendar-legend", root);
        if (!data || !table || !legend) {
            return toast(t("O calendário do mês ainda não está disponível."), "warning");
        }
        $("#vacation-calendar-print-report")?.remove();
        const monthName = state.boot.config.meses[data.mes] || data.mes;
        const monthTitle = `${monthName} ${data.ano}`;
        const report = document.createElement("section");
        report.id = "vacation-calendar-print-report";
        report.className = "vacation-calendar-print-report";
        report.innerHTML = `<header class="vacation-calendar-print-header">
            <div><p>${t("CONTINGENTE PORTUGUÊS · EUTM RCA")}</p><h1>${t("Calendário de Férias ·")} ${esc(monthTitle)}</h1></div>
            <div><strong>${data.pessoas.length} ${t("militares")}</strong><small>${t("Gerado em")} ${esc(new Intl.DateTimeFormat(locale(), {dateStyle: "short", timeStyle: "short"}).format(new Date()))}</small></div>
        </header>
        <div class="vacation-calendar-print-meta">
            <p>${t("Ordenação por posto e, dentro do mesmo posto, por antiguidade.")}</p>
            ${legend.outerHTML}
        </div>
        <div class="vacation-calendar-print-table">${table.outerHTML}</div>`;
        const originalTitle = document.title;
        let cleaned = false;
        const cleanup = () => {
            if (cleaned) return;
            cleaned = true;
            document.body.classList.remove("vacation-calendar-printing");
            report.remove();
            document.title = originalTitle;
        };
        document.body.append(report);
        document.body.classList.add("vacation-calendar-printing");
        document.title = `SIGCP_Calendario_Ferias_${data.ano}_${String(data.mes).padStart(2, "0")}`;
        window.addEventListener("afterprint", cleanup, {once: true});
        window.print();
    }

    function vacationRequestPeople() {
        return (state.vacationManagement?.pessoas || [])
            .filter((person) => person.pode_novo_pedido !== false);
    }

    function vacationPrintField(label, value, extraClass = "") {
        const displayValue = value === null || value === undefined || value === "" ? "—" : value;
        return `<div class="vacation-print-field ${extraClass}"><small>${esc(label)}</small><strong>${esc(displayValue)}</strong></div>`;
    }

    function vacationPrintPeriodInformation(item) {
        const details = [];
        if (item.observacao) details.push(`<span><b>${t("Observações:")}</b> ${esc(item.observacao)}</span>`);
        if (item.proposta_data_hora_inicio && item.proposta_data_hora_fim) {
            details.push(`<span><b>${t("Proposta:")}</b> ${esc(fmtDateTime(item.proposta_data_hora_inicio))} → ${esc(fmtDateTime(item.proposta_data_hora_fim))}</span>`);
        }
        if (item.motivo_fluxo) details.push(`<span><b>${t("Motivo:")}</b> ${esc(item.motivo_fluxo)}</span>`);
        if (item.nota_decisao) details.push(`<span><b>${t("Decisão:")}</b> ${esc(item.nota_decisao)}</span>`);
        return details.length ? details.join("") : "—";
    }

    function vacationPrintPerson(person, periods, index) {
        const summary = person.resumo || {};
        const roles = [person.snr ? "SNR" : "", person.responsavel_welfare ? t("Responsável Welfare") : ""]
            .filter(Boolean).join(" · ") || "—";
        const fullName = [person.posto, person.nome, person.sobrenome].filter(Boolean).join(" ") || person.identificacao;
        const rows = periods.length ? periods.map((item, periodIndex) => {
            const period = item.resumo || {};
            return `<tr>
                <td>${periodIndex + 1}</td>
                <td>${esc(fmtDateTime(item.data_hora_inicio))}</td>
                <td>${esc(fmtDateTime(item.data_hora_fim))}</td>
                <td><strong>${esc(t(item.estado))}</strong></td>
                <td class="vacation-print-days"><b>${period.dias_ferias ?? 0}</b> F · ${period.dias_viagem ?? 0} TD · ${period.dias_fim_semana_feriado ?? 0} FS</td>
                <td>${esc(item.companhia_aerea || "—")}</td>
                <td class="vacation-print-information">${vacationPrintPeriodInformation(item)}</td>
            </tr>`;
        }).join("") : `<tr><td colspan="7" class="vacation-print-empty">${t("Sem períodos marcados neste ano.")}</td></tr>`;
        return `<article class="vacation-print-person">
            <header class="vacation-print-person__header">
                <span>${index + 1}</span>
                <div><h2>${esc(fullName)}</h2><p>${esc(person.identificacao)} · NIM ${esc(person.nim)}</p></div>
                <b>${periods.length} ${t("período")}${periods.length === 1 ? "" : "s"}</b>
            </header>
            <div class="vacation-print-person__details">
                ${vacationPrintField(t("Antiguidade"), person.antiguidade ? fmtDate(person.antiguidade) : "—")}
                ${vacationPrintField(t("Área funcional"), areaLabel(person.area_funcional))}
                ${vacationPrintField(t("Posição N.º"), person.posicao_numero || "—")}
                ${vacationPrintField(t("Telemóvel Serviço"), person.telemovel_servico || "—")}
                ${vacationPrintField(t("Funções"), roles)}
                ${vacationPrintField(t("Missão prorrogada"), person.missao_prorrogada ? t("Sim") : t("Não"))}
                ${vacationPrintField(t("Início da missão"), fmtDateTime(person.data_chegada))}
                ${vacationPrintField(t("Fim da missão"), fmtDateTime(person.data_partida))}
                ${vacationPrintField(t("Total de dias Férias (manual)"), person.ferias_direito_override ?? t("Automático"))}
                ${vacationPrintField(t("Direito calculado"), summary.direito ?? "—")}
                ${vacationPrintField(t("Planeados / aprovados"), `${summary.planeados ?? 0} / ${summary.aprovados ?? 0}`)}
                ${vacationPrintField(t("Dias para Guia de Marcha"), summary.disponiveis ?? "—")}
                ${vacationPrintField(t("Notas de férias"), person.notas_ferias || "—", "vacation-print-field--full")}
            </div>
            <table class="vacation-print-periods">
                <thead><tr><th>${t("N.º")}</th><th>${t("Partida")}</th><th>${t("Chegada")}</th><th>${t("Estado")}</th><th>${t("Dias")}</th><th>${t("Companhia / voo")}</th><th>${t("Informação")}</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </article>`;
    }

    function printVacationList() {
        const data = state.vacationManagement;
        if (!data) return toast(t("Os dados da Gestão de Férias ainda não estão disponíveis."), "warning");
        $("#vacation-print-report")?.remove();
        const order = new Map((data.ordem_impressao || []).map((id, index) => [Number(id), index]));
        const people = [...(data.pessoas || [])]
            .filter((person) => person.pode_novo_pedido !== false && order.has(Number(person.id)))
            .sort((left, right) =>
                (order.get(Number(left.id)) ?? Number.MAX_SAFE_INTEGER) -
                (order.get(Number(right.id)) ?? Number.MAX_SAFE_INTEGER));
        if (!people.length) {
            return toast(t("Não existem licenças para o filtro ativo."), "warning");
        }
        const periodsByPerson = new Map();
        (data.periodos_impressao || []).forEach((item) => {
            const personPeriods = periodsByPerson.get(Number(item.utilizador_id)) || [];
            personPeriods.push(item);
            periodsByPerson.set(Number(item.utilizador_id), personPeriods);
        });
        const report = document.createElement("section");
        report.id = "vacation-print-report";
        report.className = "vacation-print-report";
        const reportTitle = t(data.titulo_impressao || "Lista de licenças");
        report.innerHTML = `<header class="vacation-print-report__header">
            <div><p>${t("CONTINGENTE PORTUGUÊS · EUTM RCA")}</p><h1>${esc(reportTitle)} · ${esc(data.ano)}</h1></div>
            <div><strong>${people.length} ${t("militares")}</strong><small>${t("Gerado em")} ${esc(new Intl.DateTimeFormat(locale(), {dateStyle: "short", timeStyle: "short"}).format(new Date()))}</small></div>
        </header>
        <p class="vacation-print-report__note">${t("Ordenação por posto e, dentro do mesmo posto, por antiguidade.")}</p>
        ${people.map((person, index) => vacationPrintPerson(person, periodsByPerson.get(Number(person.id)) || [], index)).join("")}`;
        const originalTitle = document.title;
        let cleaned = false;
        const cleanup = () => {
            if (cleaned) return;
            cleaned = true;
            document.body.classList.remove("vacation-list-printing");
            report.remove();
            document.title = originalTitle;
        };
        document.body.append(report);
        document.body.classList.add("vacation-list-printing");
        document.title = `SIGCP_${reportTitle.replaceAll(" ", "_")}_${data.ano}`;
        window.addEventListener("afterprint", cleanup, {once: true});
        window.print();
    }

    function openVacationModal(period = null, presetUserId = null, mode = "request") {
        const management = state.page === "vacations";
        const changing = mode === "change";
        const adminEditing = mode === "admin-edit";
        const allPeople = state.vacationManagement?.pessoas || [];
        const people = management && !period && !changing ? vacationRequestPeople() : allPeople;
        const requestedUserId = Number(presetUserId || period?.utilizador_id || (management ? people[0]?.id : state.boot.user.id));
        const userId = people.some((person) => Number(person.id) === requestedUserId)
            ? requestedUserId
            : Number(people[0]?.id || state.boot.user.id);
        let warningsAccepted = false;
        openModal({
            title: adminEditing ? t("Editar pedido de férias") : changing ? t("Pedir alteração de férias") : period ? t("Corrigir pedido de férias") : t("Novo pedido de férias"),
            subtitle: t("Indica a partida e a chegada completas; as horas afetam automaticamente o Welfare Individual."),
            size: "wide",
            body: `<form id="vacation-form" class="form-grid">
                ${management && (!changing || adminEditing) ? `<label class="field field--full"><span class="required">${t("Pessoa")}</span><select name="utilizador_id">${people.map((person) => `<option value="${person.id}" ${userId === person.id ? "selected" : ""}>${esc(person.identificacao)} · ${esc(person.nim)}</option>`).join("")}</select></label>` : ""}
                ${dateTimeField("data_hora_inicio", t("Partida · data e hora"), period?.data_hora_inicio, {required: true, help: t("Momento em que sai da base.")})}
                ${dateTimeField("data_hora_fim", t("Chegada · data e hora"), period?.data_hora_fim, {required: true, help: t("Momento em que regressa à base.")})}
                <label class="field field--full"><span>${t("Companhia aérea / voo")}</span><input name="companhia_aerea" maxlength="120" value="${attr(period?.companhia_aerea || "")}" placeholder="${t("Ex.: TAP TP123")}"></label>
                <label class="field field--full"><span>${t("Observações")}</span><textarea name="observacao" maxlength="1000">${esc(period?.observacao || "")}</textarea></label>
                ${changing ? `<label class="field field--full"><span class="required">${t("Motivo da alteração")}</span><textarea name="reason" maxlength="1000" required></textarea></label>` : ""}
                <div id="vacation-form-warnings" class="field--full"></div>
            </form>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Fechar")}</button><button class="btn btn--primary" type="submit" form="vacation-form">${icon("check")} ${adminEditing ? t("Guardar alterações") : changing ? t("Submeter alteração") : period ? t("Reenviar pedido") : t("Submeter pedido")}</button>`,
            onOpen(modal) {
                const vacationForm = $("#vacation-form", modal);
                vacationForm.addEventListener("input", () => {
                    if (!warningsAccepted) return;
                    warningsAccepted = false;
                    $("#vacation-form-warnings", modal).innerHTML = "";
                });
                vacationForm.addEventListener("submit", async (event) => {
                    event.preventDefault();
                    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
                    if (!management) payload.utilizador_id = state.boot.user.id;
                    if (changing) payload.utilizador_id = period.utilizador_id;
                    payload.accept_warnings = warningsAccepted;
                    const url = adminEditing ? `/api/vacations/${period.id}/admin-edit` : changing ? `/api/vacations/${period.id}/change-request` : period ? `/api/vacations/${period.id}` : "/api/vacations";
                    const method = changing ? "POST" : period ? "PUT" : "POST";
                    setLoading(true);
                    try {
                        const response = await api(url, {method, body: payload});
                        closeModal(); toast(response.message); await refreshVacationPage();
                    } catch (error) {
                        if (error.payload?.warnings?.length && !warningsAccepted) {
                            warningsAccepted = true;
                            $("#vacation-form-warnings", modal).innerHTML = `<div class="vacation-validation"><strong>${icon("alert")} ${t("Confirma estes avisos")}</strong><ul>${error.payload.warnings.map((warning) => `<li>${esc(warning)}</li>`).join("")}</ul><small>${t("Revê os dados ou volta a submeter para aceitar os avisos.")}</small></div>`;
                            toast(t("O pedido contém avisos. Confirma-os e volta a submeter."), "warning");
                        } else if (error.payload?.errors?.length) {
                            $("#vacation-form-warnings", modal).innerHTML = `<div class="vacation-validation vacation-validation--error"><strong>${icon("alert")} ${t("O pedido não pode ser submetido")}</strong><ul>${error.payload.errors.map((message) => `<li>${esc(message)}</li>`).join("")}</ul></div>`;
                        } else toast(error.message, "error");
                    } finally { setLoading(false); }
                });
            },
        });
    }

    function openVacationDetail(item) {
        if (!item) return;
        const summary = item.resumo || {};
        const history = item.historico || [];
        openModal({
            title: t("Pedido de férias #{0}", item.id),
            subtitle: `${item.identificacao} · ${areaLabel(item.area_funcional)}`,
            size: "wide",
            body: `<div class="vacation-detail-head">${vacationStatusBadge(item.estado)}<div class="vacation-route vacation-route--detail"><span class="vacation-route__mark">${icon("plane")}</span><div><small>${t("PARTIDA")}</small><strong>${fmtDateTime(item.data_hora_inicio)}</strong></div><span class="vacation-route__line"></span><div><small>${t("CHEGADA")}</small><strong>${fmtDateTime(item.data_hora_fim)}</strong></div></div></div>
                <div class="vacation-detail-metrics">${vacationMetric(t("Férias"), summary.dias_ferias, t(" dias"))}${vacationMetric(t("Viagem"), summary.dias_viagem, t(" dias"))}${vacationMetric(t("FS / Feriados"), summary.dias_fim_semana_feriado, t(" dias"))}${vacationMetric(t("Ausência"), summary.dias_ausencia, t(" dias"))}</div>
                ${item.companhia_aerea ? `<div class="vacation-detail-row"><strong>${t("Companhia / voo")}</strong><span>${esc(item.companhia_aerea)}</span></div>` : ""}
                ${item.observacao ? `<div class="vacation-detail-row"><strong>${t("Observações")}</strong><span>${esc(item.observacao)}</span></div>` : ""}
                ${item.proposta_data_hora_inicio ? `<div class="vacation-detail-proposal"><p class="eyebrow eyebrow--dark">${t("ALTERAÇÃO PROPOSTA")}</p><strong>${fmtDateTime(item.proposta_data_hora_inicio)} → ${fmtDateTime(item.proposta_data_hora_fim)}</strong>${item.motivo_fluxo ? `<p>${esc(item.motivo_fluxo)}</p>` : ""}</div>` : item.motivo_fluxo ? `<div class="vacation-detail-row"><strong>${t("Motivo do fluxo")}</strong><span>${esc(item.motivo_fluxo)}</span></div>` : ""}
                ${item.nota_decisao ? `<div class="vacation-detail-row"><strong>${t("Nota da decisão")}</strong><span>${esc(item.nota_decisao)}</span></div>` : ""}
                <div class="vacation-history"><h3>${t("Histórico")}</h3>${history.length ? history.map((event) => `<div class="vacation-history-item"><span class="vacation-history-dot"></span><div><strong>${esc(t(event.acao))}</strong><small>${fmtDateTime(event.criado_em)} · ${esc(event.ator || t("Sistema"))}</small>${event.nota ? `<p>${esc(event.nota)}</p>` : ""}</div></div>`).join("") : `<p class="muted">${t("Sem eventos registados.")}</p>`}</div>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Fechar")}</button>`,
        });
    }

    function openVacationReasonModal(item, kind) {
        const config = {
            withdraw: [t("Retirar pedido"), t("Explica, se necessário, por que motivo estás a retirar o pedido."), `/api/vacations/${item.id}/withdraw`, t("Retirar pedido")],
            cancel: [t("Pedir cancelamento"), t("O período aprovado mantém-se no Welfare Individual até o SNR decidir."), `/api/vacations/${item.id}/cancellation-request`, t("Submeter cancelamento")],
            annul: [t("Anular autorização"), t("Esta ação retira imediatamente o período aprovado do Welfare Individual."), `/api/vacations/${item.id}/annul`, t("Anular autorização")],
        }[kind];
        openModal({
            title: config[0], subtitle: config[1],
            body: `<form id="vacation-reason-form"><label class="field"><span class="required">${t("Motivo")}</span><textarea name="reason" maxlength="1000" ${kind === "withdraw" ? "" : "required"}></textarea></label></form>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Fechar")}</button><button class="btn ${kind === "annul" ? "btn--danger" : "btn--primary"}" type="submit" form="vacation-reason-form">${config[3]}</button>`,
            onOpen(modal) { $("#vacation-reason-form", modal).addEventListener("submit", async (event) => { event.preventDefault(); const body = Object.fromEntries(new FormData(event.currentTarget).entries()); setLoading(true); try { const response = await api(config[2], {method: "POST", body}); closeModal(); toast(response.message); await refreshVacationPage(); } catch (error) { toast(error.message, "error"); } finally { setLoading(false); } }); },
        });
    }

    function openVacationDecisionModal(item, workflow, decision) {
        const approving = decision === "approve";
        const returning = decision === "return";
        const labels = workflow === "change" ? t("alteração") : workflow === "cancellation" ? t("cancelamento") : t("pedido");
        const endpoint = workflow === "change" ? "change-decision" : workflow === "cancellation" ? "cancellation-decision" : "decision";
        openModal({
            title: `${approving ? t("Aprovar") : returning ? t("Devolver") : t("Rejeitar")} ${labels}`,
            subtitle: `${item.identificacao} · ${fmtDateTime(item.data_hora_inicio)} → ${fmtDateTime(item.data_hora_fim)}`,
            body: `<form id="vacation-decision-form"><label class="field"><span class="${approving ? "" : "required"}">${t("Nota da decisão")}</span><textarea name="note" maxlength="1000" ${approving ? "" : "required"} placeholder="${approving ? t("Opcional") : t("Obrigatória para justificar a decisão")}"></textarea></label></form>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Fechar")}</button><button class="btn ${approving ? "btn--success" : returning ? "btn--primary" : "btn--danger"}" type="submit" form="vacation-decision-form">${approving ? icon("check") : ""} ${t("Confirmar decisão")}</button>`,
            onOpen(modal) { $("#vacation-decision-form", modal).addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); setLoading(true); try { const response = await api(`/api/vacations/${item.id}/${endpoint}`, {method: "POST", body: {action: decision, note: form.get("note")}}); closeModal(); toast(response.message); await loadVacationManagement(); } catch (error) { toast(error.message, "error"); } finally { setLoading(false); } }); },
        });
    }

    function openVacationHoursModal(item) {
        if (!item) return;
        openModal({
            title: t("Atualizar Horas"),
            subtitle: t("{0} · período aprovado pelo SNR", item.identificacao),
            body: `<form id="vacation-hours-form">
                <div class="info-banner" style="margin-bottom:16px">${icon("info")}<span>${t("Os dias de partida e chegada permanecem inalteráveis. Esta operação não necessita de nova autorização.")}</span></div>
                <div class="form-grid">
                    <label class="field"><span>${t("Dia de partida")}</span><input value="${attr(fmtDate(item.data_hora_inicio))}" disabled></label>
                    <label class="field"><span class="required">${t("Hora de partida")}</span><input name="hora_partida" type="time" value="${attr(String(item.data_hora_inicio).slice(11,16))}" required></label>
                    <label class="field"><span>${t("Dia de chegada")}</span><input value="${attr(fmtDate(item.data_hora_fim))}" disabled></label>
                    <label class="field"><span class="required">${t("Hora de chegada")}</span><input name="hora_chegada" type="time" value="${attr(String(item.data_hora_fim).slice(11,16))}" required></label>
                </div>
            </form>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Fechar")}</button><button class="btn vacation-update-hours-btn" type="submit" form="vacation-hours-form">${icon("clock")} ${t("Atualizar Horas")}</button>`,
            onOpen(modal) { $("#vacation-hours-form", modal).addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); setLoading(true); try { const response = await api(`/api/vacations/${item.id}/hours`, {method: "PUT", body: {hora_partida: form.get("hora_partida"), hora_chegada: form.get("hora_chegada")}}); closeModal(); toast(response.message); await loadVacationManagement(); } catch (error) { toast(error.message, "error"); } finally { setLoading(false); } }); },
        });
    }

    function openVacationPersonModal(person) {
        if (!person) return;
        const canAssignSubstitute = Boolean(state.boot.permissions.snr_substituicao && !person.snr);
        openModal({
            title: t("Dados de férias"), subtitle: person.identificacao, size: "wide",
            body: `<form id="vacation-person-form" class="form-grid">
                <label class="field"><span>${t("Área funcional")}</span><input name="area_funcional" maxlength="120" value="${attr(person.area_funcional === "Não definido" ? "" : person.area_funcional || "")}" placeholder="${attr(t("Não definido"))}"></label>
                <label class="field"><span>${t("Posição N.º")}</span><input name="posicao_numero" maxlength="40" value="${attr(person.posicao_numero || "")}"></label>
                ${dateTimeField("data_chegada", t("Início da missão"), person.data_chegada)}
                ${dateTimeField("data_partida", t("Fim da missão"), person.data_partida)}
                <label class="field"><span>${t("Total de dias Férias (manual)")}</span><input type="number" min="0" max="365" step="0.5" name="ferias_direito_override" value="${attr(person.ferias_direito_override ?? "")}"><small>${t("Vazio mantém o cálculo automático 30/360.")}</small></label>
                <div class="field"><span>${t("Missão")}</span><label class="checkbox vacation-checkbox-line"><input type="checkbox" name="missao_prorrogada" ${person.missao_prorrogada ? "checked" : ""}> ${t("Missão prorrogada")}</label></div>
                <label class="field field--full"><span>${t("Notas")}</span><textarea name="notas_ferias" maxlength="1000">${esc(person.notas_ferias || "")}</textarea></label>
                ${canAssignSubstitute ? snrSubstitutionFields(person) : ""}
            </form>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Fechar")}</button><button class="btn btn--primary" type="submit" form="vacation-person-form">${icon("check")} ${t("Guardar")}</button>`,
            onOpen(modal) { $("#vacation-person-form", modal).addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); const body = Object.fromEntries(form.entries()); body.missao_prorrogada = form.get("missao_prorrogada") === "on"; if (canAssignSubstitute) { body.snr_substituto = form.get("snr_substituto") === "on"; body.snr_substituto_inicio = form.get("snr_substituto_inicio") || ""; body.snr_substituto_fim = form.get("snr_substituto_fim") || ""; } setLoading(true); try { const response = await api(`/api/vacations/people/${person.id}`, {method: "PUT", body}); closeModal(); toast(response.message); await loadVacationManagement(); } catch (error) { toast(error.message, "error"); } finally { setLoading(false); } }); },
        });
    }

    function openVacationHolidayModal(holiday = null) {
        openModal({
            title: holiday ? t("Editar feriado") : t("Novo feriado"), subtitle: t("Classificado como FS no calendário de férias."),
            body: `<form id="vacation-holiday-form" class="form-grid"><label class="field"><span class="required">${t("Data")}</span><input type="date" name="data" value="${attr(holiday?.data || "")}" required></label><label class="field"><span class="required">${t("Descrição")}</span><input name="descricao" maxlength="160" value="${attr(holiday?.descricao || "")}" required></label><label class="checkbox field--full"><input type="checkbox" name="ativo" ${holiday && !Number(holiday.ativo) ? "" : "checked"}> ${t("Ativo no cálculo")}</label></form>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Fechar")}</button><button class="btn btn--primary" type="submit" form="vacation-holiday-form">${icon("check")} ${t("Guardar")}</button>`,
            onOpen(modal) { $("#vacation-holiday-form", modal).addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); const body = Object.fromEntries(form.entries()); body.ativo = form.get("ativo") === "on"; setLoading(true); try { const response = await api(holiday ? `/api/vacations/holidays/${holiday.id}` : "/api/vacations/holidays", {method: holiday ? "PUT" : "POST", body}); closeModal(); toast(response.message); await loadVacationManagement(); } catch (error) { toast(error.message, "error"); } finally { setLoading(false); } }); },
        });
    }

    async function openVacationHolidayImport() {
        setLoading(true);
        try {
            const response = await api(`/api/vacations/holidays/import-preview?ano=${state.vacationHolidayYear}`);
            const preview = response.data;
            state.vacationHolidayPreview = preview;
            const available = preview.feriados.filter((item) => !item.existente).length;
            openModal({
                title: t("Importar feriados nacionais"),
                subtitle: t("Portugal · {0} · Fonte: {1}", preview.ano, preview.fonte),
                size: "wide",
                body: `<form id="vacation-holiday-import-form"><div class="holiday-import-toolbar"><div><strong>${t("Selecione os feriados a importar")}</strong><small>${t("Os que já existem na aplicação aparecem identificados e não serão duplicados.")}</small></div><label class="checkbox"><input type="checkbox" data-holiday-select-all ${available ? "checked" : ""}> ${t("Selecionar disponíveis")}</label></div><div class="holiday-import-list">${preview.feriados.length ? preview.feriados.map((item, index) => `<label class="holiday-import-item ${item.existente ? "holiday-import-item--existing" : ""}"><input type="checkbox" name="holiday" value="${index}" ${item.existente ? "disabled" : "checked"}><span class="holiday-date">${fmtDate(item.data)}</span><span><strong>${esc(item.descricao)}</strong><small>${item.existente ? t("Já existe: {0}", esc(item.descricao_existente || item.descricao)) : t("Feriado nacional disponível")}</small></span><b class="badge ${item.existente ? "" : "badge--green"}">${item.existente ? t("Existente") : t("Importar")}</b></label>`).join("") : `<div class="empty-state empty-state--small"><div><p>${t("O serviço não devolveu feriados nacionais para")} ${preview.ano}.</p></div></div>`}</div></form>`,
                footer: `<button class="btn btn--secondary" data-modal-close>${t("Cancelar")}</button><button class="btn btn--primary" type="submit" form="vacation-holiday-import-form" ${available ? "" : "disabled"}>${icon("download")} ${t("Importar selecionados")}</button>`,
                onOpen(modal) {
                    const form = $("#vacation-holiday-import-form", modal);
                    $("[data-holiday-select-all]", modal)?.addEventListener("change", (event) => {
                        $$('input[name="holiday"]:not(:disabled)', modal).forEach((input) => { input.checked = event.currentTarget.checked; });
                    });
                    form.addEventListener("submit", async (event) => {
                        event.preventDefault();
                        const selected = $$('input[name="holiday"]:checked', form).map((input) => preview.feriados[Number(input.value)]).map((item) => ({data: item.data, descricao: item.descricao}));
                        if (!selected.length) return toast(t("Seleciona pelo menos um feriado para importar."), "error");
                        setLoading(true);
                        try {
                            const result = await api("/api/vacations/holidays/import", {method: "POST", body: {ano: preview.ano, feriados: selected}});
                            closeModal(); toast(result.message); await loadVacationManagement();
                        } catch (error) { toast(error.message, "error"); }
                        finally { setLoading(false); }
                    });
                },
            });
        } catch (error) { toast(error.message, "error"); }
        finally { setLoading(false); }
    }

    function drawVacationNotifications() {
        const items = state.vacationNotifications || [];
        const management = state.vacationNotificationChannel === "gestao";
        openModal({
            title: management ? t("Notificações da Gestão de Férias") : t("Notificações das minhas férias"),
            subtitle: t("{0} por ler", items.filter((item) => !item.lida).length),
            body: `<div class="vacation-notifications">${items.length ? items.map((item) => `<article class="vacation-notification ${item.lida ? "" : "vacation-notification--unread"}"><button type="button" class="vacation-notification__open" data-action="vacation-notification-open" data-id="${item.id}" data-vacation="${item.feria_id || ""}"><span class="vacation-notification__icon">${icon(item.lida ? "info" : "alert")}</span><div><strong>${esc(t(item.titulo))}</strong><p>${esc(t(item.mensagem || ""))}</p><small>${fmtDateTime(item.criado_em)}</small></div></button><button type="button" class="vacation-notification__delete" data-action="vacation-notification-delete" data-id="${item.id}" aria-label="${t("Apagar notificação")}" title="${t("Apagar notificação")}">${icon("x")}</button></article>`).join("") : `<div class="empty-state empty-state--small"><div><p>${t("Sem notificações.")}</p></div></div>`}</div>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Fechar")}</button>${items.some((item) => !item.lida) ? `<button class="btn btn--primary" data-action="vacation-notifications-read">${icon("check")} ${t("Marcar todas como lidas")}</button>` : ""}`,
        });
    }

    async function openVacationNotifications(channel = "pessoal") {
        setLoading(true);
        try {
            const response = await api(`/api/vacations/notifications?canal=${encodeURIComponent(channel)}`);
            state.vacationNotificationChannel = channel;
            state.vacationNotifications = response.data.notificacoes || [];
            if (channel === "pessoal" && state.myVacations) state.myVacations.notificacoes = state.vacationNotifications;
            setVacationNotificationCount(channel, response.data.nao_lidas);
            syncVacationNotificationCount();
            drawVacationNotifications();
        } catch (error) {
            toast(error.message, "error");
        } finally {
            setLoading(false);
        }
    }

    // Administration
    async function renderAdmin() {
        const superadmin = Boolean(state.boot?.permissions?.superadmin);
        setPageHeader(t("Administração"), t("SISTEMA"), `
            ${superadmin ? `<input type="file" accept="application/json,.json" data-database-import hidden>
            <button class="btn btn--secondary" data-action="database-import">${icon("upload")}<span class="hide-mobile">${t("Importar JSON")}</span></button>
            <button class="btn btn--secondary" data-action="database-export">${icon("download")}<span class="hide-mobile">${t("Exportar JSON")}</span></button>` : ""}`);
        els.content.innerHTML = `<section class="page">
            <div class="segmented admin-tabs">
                <button class="${state.adminTab === "settings" ? "active" : ""}" data-action="admin-tab" data-tab="settings">${t("Configuração")}</button>
                <button class="${state.adminTab === "users" ? "active" : ""}" data-action="admin-tab" data-tab="users">${t("Utilizadores")}</button>
                <button class="${state.adminTab === "dayoffs" ? "active" : ""}" data-action="admin-tab" data-tab="dayoffs">Days Off</button>
                <button class="${state.adminTab === "audit" ? "active" : ""}" data-action="admin-tab" data-tab="audit">${t("Auditoria")}</button>
            </div>
            <div id="admin-root"></div>
        </section>`;
        await loadAdminTab();
    }

    async function loadAdminTab() {
        const root = $("#admin-root");
        if (state.adminTab === "settings") await loadSettings(root);
        else if (state.adminTab === "users") await loadAdminUsers(root);
        else if (state.adminTab === "dayoffs") await loadDayOffs(root);
        else await loadAudit(root);
    }

    async function loadSettings(root) {
        setLoading(true);
        try {
            const response = await api("/api/settings");
            const settings = response.settings;
            const superadmin = Boolean(state.boot?.permissions?.superadmin);
            const schedule = settings.horario_dfac;
            root.innerHTML = `<form id="settings-form">
                <div class="settings-grid">
                    ${superadmin ? `<section class="card settings-card" style="grid-column:1/-1"><div class="card-body">
                        <h3>${icon("grid")} ${t("Base de dados")}</h3><p>${t("Escolhe SQLite local/rede ou Supabase online. Depois de alterares esta opção, reinicia a aplicação.")}</p>
                        <label class="field"><span>${t("Tipo de armazenamento")}</span><select name="database_mode"><option value="local" ${settings.database_mode === "local" ? "selected" : ""}>${t("Local / rede")}</option><option value="supabase" ${settings.database_mode === "supabase" ? "selected" : ""}>Online (Supabase)</option></select></label>
                        <label class="field"><span>${t("Caminho completo para database.sqlite3")}</span><input name="database_path" value="${attr(settings.database_path)}" spellcheck="false"></label>
                        <div class="form-grid" style="margin-top:16px"><label class="field"><span>Supabase Project URL</span><input name="supabase_url" value="${attr(settings.supabase_url)}" spellcheck="false"></label><label class="field"><span>Publishable Key</span><input name="supabase_key" value="${attr(settings.supabase_key)}" spellcheck="false"></label></div>
                        <label class="field" style="margin:16px 0 0"><span>${t("Localização do SIGCP.exe das atualizações")}</span><span class="settings-path-picker"><input name="update_folder" value="${attr(settings.update_folder || "")}" spellcheck="false" placeholder="Ex.: \\\\servidor\\SIGCP"><button class="btn btn--secondary" type="button" data-action="select-update-executable">${icon("search")} ${t("Selecionar SIGCP.exe")}</button></span><small data-update-comparison>${t("Seleciona o executável publicado. Versão instalada:")} ${esc(settings.app_version)}.</small></label>
                    </div></section>` : `<section class="card settings-card" style="grid-column:1/-1"><div class="card-body">
                        <h3>${icon("download")} ${t("Atualizações")}</h3><p>${t("Localização partilhada do executável publicado.")}</p>
                        <label class="field"><span>${t("Localização do SIGCP.exe das atualizações")}</span><span class="settings-path-picker"><input name="update_folder" value="${attr(settings.update_folder || "")}" spellcheck="false"><button class="btn btn--secondary" type="button" data-action="select-update-executable">${icon("search")} ${t("Selecionar SIGCP.exe")}</button></span><small data-update-comparison>${t("Versão instalada:")} ${esc(settings.app_version)}.</small></label>
                    </div></section>`}
                    <section class="card settings-card"><div class="card-body">
                        <h3>${icon("coins")} ${t("Valores financeiros")}</h3><p>${t("Valores usados no cálculo de reembolsos e Caixa.")}</p>
                        <div class="form-grid">
                            <label class="field"><span>${t("Valor Welfare (XAF)")}</span><input name="valor_welfare" inputmode="numeric" value="${attr(settings.valor_welfare)}"></label>
                            <label class="field"><span>${t("Valor Caixa (XAF)")}</span><input name="valor_caixa" inputmode="numeric" value="${attr(settings.valor_caixa)}"></label>
                        </div>
                    </div></section>
                    <section class="card settings-card"><div class="card-body">
                        <h3>${icon("user")} ${t("Assinaturas e aplicação")}</h3><p>${t("Informação usada nos documentos e preferências globais.")}</p>
                        <div class="form-grid">
                            <label class="field field--full"><span>${t("Nome do COS")}</span><input name="nome_cos" value="${attr(settings.nome_cos)}"></label>
                            <label class="field"><span>${t("Início da Semana 1")}</span><input name="inicio_semana" type="date" value="${attr(settings.inicio_semana)}"></label>
                            <label class="field"><span>${t("Língua")}</span><select name="lingua"><option value="pt" ${settings.lingua === "pt" ? "selected" : ""}>${t("Português")}</option><option value="en" ${settings.lingua === "en" ? "selected" : ""}>English</option></select></label>
                        </div>
                    </div></section>
                    ${scheduleCard("normal", t("Dias normais"), t("Segunda-feira a sábado"), schedule.normal)}
                    ${scheduleCard("especial", t("Domingo / Day Off"), t("Horário especial DFAC"), schedule.especial)}
                </div>
                <div style="display:flex;justify-content:flex-end;margin-top:16px"><button class="btn btn--primary" type="submit">${icon("check")} ${t("Guardar configuração")}</button></div>
            </form>`;
            $("#settings-form", root).addEventListener("submit", async (event) => {
                event.preventDefault();
                const form = new FormData(event.currentTarget);
                const horario = {normal: {}, especial: {}};
                ["normal", "especial"].forEach((type) => {
                    ["pequeno_almoco", "almoco", "jantar"].forEach((meal) => {
                        horario[type][meal] = {
                            abertura: form.get(`${type}-${meal}-abertura`),
                            fecho: form.get(`${type}-${meal}-fecho`),
                        };
                    });
                });
                setLoading(true);
                try {
                    const body = {
                        valor_welfare: form.get("valor_welfare"), valor_caixa: form.get("valor_caixa"),
                        nome_cos: form.get("nome_cos"), inicio_semana: form.get("inicio_semana"),
                        lingua: form.get("lingua"), horario_dfac: horario,
                        update_folder: form.get("update_folder"),
                    };
                    if (superadmin) Object.assign(body, {
                        database_path: form.get("database_path"), database_mode: form.get("database_mode"),
                        supabase_url: form.get("supabase_url"), supabase_key: form.get("supabase_key"),
                    });
                    const responseSave = await api("/api/settings", {method: "PUT", body});
                    toast(responseSave.message);
                    if (responseSave.restart_required) {
                        toast(t("O novo caminho será usado depois de encerrares e voltares a abrir a aplicação."), "warning", t("Reinício necessário"));
                    }
                    const oldLang = state.boot.language;
                    const boot = await api("/api/bootstrap");
                    state.boot = boot;
                    setupShell();
                    if (oldLang !== boot.language) {
                        await renderAdmin();
                        toast(t("Língua guardada. A interface foi atualizada."), "success");
                    }
                } catch (error) { toast(error.message, "error"); }
                finally { setLoading(false); }
            });
            $("[data-action='select-update-executable']", root)?.addEventListener("click", async () => {
                setLoading(true);
                try {
                    const selected = await api("/api/settings/select-update-executable", {method: "POST", body: {}});
                    if (selected.cancelled) return;
                    $("[name='update_folder']", root).value = selected.update_folder;
                    const comparison = $("[data-update-comparison]", root);
                    if (selected.comparison === "igual") {
                        comparison.textContent = t("O executável selecionado é igual à versão {0} instalada.", settings.app_version);
                    } else if (selected.comparison === "diferente") {
                        comparison.textContent = t("Atualização disponível: versão {0} → {1}.", selected.installed_version, selected.available_version);
                    } else {
                        comparison.textContent = t("Localização selecionada. A comparação será efetuada no próximo arranque.");
                    }
                    toast(selected.message || t("Localização do SIGCP.exe selecionada e guardada."), "success");
                } catch (error) { toast(error.message, "error"); }
                finally { setLoading(false); }
            });
        } finally { setLoading(false); }
    }

    function scheduleCard(type, title, subtitle, data) {
        const labels = {pequeno_almoco: "Pequeno-Almoço", almoco: "Almoço", jantar: "Jantar"};
        return `<section class="card settings-card"><div class="card-body">
            <h3>${icon("calendar")} ${esc(title)}</h3><p>${esc(subtitle)}</p>
            <table class="schedule-table"><thead><tr><th>${t("Refeição")}</th><th>${t("Abertura")}</th><th>${t("Fecho")}</th></tr></thead>
            <tbody>${Object.keys(labels).map((meal) => `<tr><td>${t(labels[meal])}</td>
                <td><input type="time" name="${type}-${meal}-abertura" value="${attr(data[meal].abertura)}"></td>
                <td><input type="time" name="${type}-${meal}-fecho" value="${attr(data[meal].fecho)}"></td>
            </tr>`).join("")}</tbody></table>
        </div></section>`;
    }

    async function loadAdminUsers(root) {
        root.innerHTML = `<div class="page-toolbar">
            <button class="btn btn--primary" data-action="user-new">${icon("plus")} ${t("Novo utilizador")}</button>
            <button class="btn btn--secondary" data-action="users-toggle-all">${state.usersAll ? t("Mostrar só ativos") : t("Mostrar todos")}</button>
            <span class="page-toolbar__spacer"></span>
            <label class="search-box">${icon("search")}<input id="user-search" placeholder="${t("Pesquisar utilizadores…")}" value="${attr(state.userSearch)}"></label>
        </div><div id="users-root" class="card"></div>`;
        await loadUsers();
    }

    function auditDefaultFilters() {
        const today = String(state.boot?.config?.today || new Date().toISOString().slice(0, 10));
        const [year, month] = today.split("-").map(Number);
        const lastDay = new Date(year, month, 0).getDate();
        return {
            search: "",
            method: "",
            dateFrom: `${year}-${String(month).padStart(2, "0")}-01`,
            dateTo: `${year}-${String(month).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`,
        };
    }

    function auditQuery() {
        if (!state.auditFilters) state.auditFilters = auditDefaultFilters();
        const query = new URLSearchParams({limite: "50"});
        if (state.auditFilters.search) query.set("pesquisa", state.auditFilters.search);
        if (state.auditFilters.method) query.set("metodo", state.auditFilters.method);
        if (state.auditFilters.dateFrom) query.set("de", state.auditFilters.dateFrom);
        if (state.auditFilters.dateTo) query.set("ate", state.auditFilters.dateTo);
        if (state.auditCursor) query.set("cursor", state.auditCursor);
        return query.toString();
    }

    function auditDetailSummary(item) {
        const details = item.detalhes || {};
        return details.resultado?.mensagem
            || details.contexto?.pessoa
            || details.contexto?.estado
            || item.entidade_id
            || t("Consultar detalhe");
    }

    function openAuditDetail(item) {
        if (!item) return;
        openModal({
            title: item.acao,
            subtitle: `${fmtDateTime(item.criado_em)} · ${item.utilizador_identificacao || item.utilizador_nim || t("Sistema")}`,
            size: "wide",
            body: `<div class="audit-detail-grid">
                <div><small>${t("Método")}</small><strong>${esc(item.metodo)}</strong></div>
                <div><small>${t("Rota")}</small><strong>${esc(item.rota)}</strong></div>
                <div><small>${t("Identificador")}</small><strong>${esc(item.entidade_id || "—")}</strong></div>
                <div><small>${t("Endereço")}</small><strong>${esc(item.endereco_ip || "—")}</strong></div>
            </div><pre class="audit-json">${esc(JSON.stringify(item.detalhes || {}, null, 2))}</pre>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Fechar")}</button>`,
        });
    }

    async function loadAudit(root) {
        setLoading(true);
        try {
            const response = await api(`/api/audit?${auditQuery()}`);
            state.auditData = response.data;
            const rows = response.data.registos || [];
            root.innerHTML = `<form id="audit-filter-form" class="audit-filterbar card">
                <label class="search-box audit-filterbar__search">${icon("search")}<input id="audit-search" placeholder="${t("Utilizador, ação, rota ou conteúdo…")}" value="${attr(state.auditFilters.search)}"></label>
                <label class="compact-field"><span>${t("Método")}</span><select id="audit-method">
                    <option value="">${t("Todos")}</option>
                    ${["POST", "PUT", "PATCH", "DELETE"].map((method) => `<option value="${method}" ${state.auditFilters.method === method ? "selected" : ""}>${method}</option>`).join("")}
                </select></label>
                <label class="compact-field"><span>${t("De")}</span><input id="audit-date-from" type="date" value="${attr(state.auditFilters.dateFrom)}"></label>
                <label class="compact-field"><span>${t("Até")}</span><input id="audit-date-to" type="date" value="${attr(state.auditFilters.dateTo)}"></label>
                <button class="btn btn--secondary" type="submit">${icon("search")} ${t("Pesquisar")}</button>
                <button class="btn btn--ghost" type="button" data-action="audit-clear">${t("Limpar")}</button>
            </form>
            <section class="card audit-card">
                <div class="card-header"><div><h2>${t("Auditoria da aplicação")}</h2><p>${t("Operações concluídas que alteraram dados. Credenciais e tokens são ocultados.")}</p></div><span class="badge badge--teal">${rows.length}${response.data.tem_mais ? "+" : ""} ${t("registos")}</span></div>
                <div class="table-wrap"><table class="data-table audit-table">
                    <thead><tr><th>${t("Data e hora")}</th><th>${t("Utilizador")}</th><th>${t("Operação")}</th><th>${t("Destino")}</th><th>${t("Detalhe")}</th><th></th></tr></thead>
                    <tbody>${rows.length ? rows.map((item) => `<tr>
                        <td class="audit-date"><strong>${esc(fmtDateTime(item.criado_em))}</strong><small>#${item.id}</small></td>
                        <td><strong>${esc(item.utilizador_identificacao || t("Sistema"))}</strong><small>${esc(item.utilizador_nim || "—")}</small></td>
                        <td><span class="audit-method audit-method--${item.metodo.toLowerCase()}">${esc(item.metodo)}</span><strong class="audit-action">${esc(item.acao)}</strong></td>
                        <td><code>${esc(item.rota)}</code>${item.entidade_id ? `<small>${esc(item.entidade_id)}</small>` : ""}</td>
                        <td class="audit-summary">${esc(auditDetailSummary(item))}</td>
                        <td class="actions-cell"><button class="icon-btn" type="button" data-action="audit-detail" data-id="${item.id}" title="${t("Ver detalhe")}">${icon("info")}</button></td>
                    </tr>`).join("") : `<tr><td colspan="6"><div class="empty-state empty-state--small"><div><p>${t("Não existem registos para estes filtros.")}</p></div></div></td></tr>`}</tbody>
                </table></div>
                <div class="audit-pagination">
                    <button class="btn btn--secondary" type="button" data-action="audit-previous" ${state.auditCursorStack.length ? "" : "disabled"}>${icon("left")} ${t("Mais recentes")}</button>
                    <span>${t("Página de")} ${response.data.limite} ${t("registos")}</span>
                    <button class="btn btn--secondary" type="button" data-action="audit-next" ${response.data.tem_mais ? "" : "disabled"}>${t("Mais antigos")} ${icon("right")}</button>
                </div>
            </section>`;
            $("#audit-filter-form", root).addEventListener("submit", async (event) => {
                event.preventDefault();
                state.auditFilters = {
                    search: $("#audit-search", root).value.trim(),
                    method: $("#audit-method", root).value,
                    dateFrom: $("#audit-date-from", root).value,
                    dateTo: $("#audit-date-to", root).value,
                };
                state.auditCursor = null;
                state.auditCursorStack = [];
                await loadAudit(root);
            });
        } finally { setLoading(false); }
    }

    async function loadDayOffs(root) {
        setLoading(true);
        try {
            const response = await api(`/api/day-offs?todos=${state.dayOffsAll ? 1 : 0}`);
            root.innerHTML = `<div class="page-toolbar">
                <button class="btn btn--primary" data-action="dayoff-new">${icon("plus")} ${t("Novo Day Off")}</button>
                <button class="btn btn--secondary" data-action="dayoffs-toggle-all">${state.dayOffsAll ? t("Mostrar futuros") : t("Mostrar todos")}</button>
                <span class="page-toolbar__spacer"></span><span class="badge badge--teal">${response.day_offs.length} ${t("registos")}</span>
            </div>
            <section class="card"><div class="card-header"><div><h2>Days Off</h2><p>${t("Os dias configurados usam o horário especial DFAC.")}</p></div></div>
                <div class="card-body dayoff-list">${response.day_offs.length ? response.day_offs.map((item) => `<article class="dayoff-item">
                    <span class="dayoff-date">${fmtDate(item.data)}</span><p>${esc(item.observacao || t("Sem observação"))}</p>
                    <span class="dayoff-item__actions">
                        <button class="icon-btn" data-action="dayoff-edit" data-id="${item.id}" data-date="${item.data}" data-note="${attr(item.observacao || "")}">${icon("edit")}</button>
                        <button class="icon-btn icon-btn--danger" data-action="dayoff-delete" data-id="${item.id}" data-date="${item.data}">${icon("trash")}</button>
                    </span>
                </article>`).join("") : `<div class="empty-state"><div>${icon("calendar")}<h3>${t("Sem Days Off")}</h3><p>${t("Não existem registos para mostrar.")}</p></div></div>`}</div>
            </section>`;
        } finally { setLoading(false); }
    }

    function openDayOffModal(item = null) {
        openModal({
            title: item ? t("Editar Day Off") : t("Novo Day Off"),
            body: `<form id="dayoff-form" class="form-grid">
                <label class="field"><span class="required">${t("Data")}</span><input type="date" name="data" value="${attr(item?.data || "")}" required></label>
                <label class="field field--full"><span>${t("Observação")}</span><textarea name="observacao">${esc(item?.observacao || "")}</textarea></label>
            </form>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Fechar")}</button><button class="btn btn--primary" type="submit" form="dayoff-form">${icon("check")} ${t("Guardar")}</button>`,
            onOpen(modal) {
                $("#dayoff-form", modal).addEventListener("submit", async (event) => {
                    event.preventDefault();
                    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
                    setLoading(true);
                    try {
                        const response = await api(item ? `/api/day-offs/${item.id}` : "/api/day-offs", {method: item ? "PUT" : "POST", body: payload});
                        closeModal(); toast(response.message); await loadAdminTab();
                    } catch (error) { toast(error.message, "error"); }
                    finally { setLoading(false); }
                });
            },
        });
    }

    function openProfileModal() {
        const user = state.boot.user;
        openModal({
            title: t("O meu perfil"),
            subtitle: user.identificacao,
            body: `<div class="person-cell" style="margin-bottom:18px"><span class="avatar" style="width:48px;height:48px">${esc(initials(user))}</span><span><strong>${esc(user.identificacao)}</strong><small>${esc(user.acessos.map((access) => t(access)).join(" · "))}</small></span></div>
            <form id="password-form" class="form-grid">
                <label class="field"><span class="required">${t("Nova password")}</span><input type="password" name="password" autocomplete="new-password" required></label>
                <label class="field"><span class="required">${t("Confirmar password")}</span><input type="password" name="confirmar" autocomplete="new-password" required></label>
            </form>`,
            footer: `<button class="btn btn--secondary" data-modal-close>${t("Fechar")}</button><button class="btn btn--primary" type="submit" form="password-form">${icon("check")} ${t("Alterar password")}</button>`,
            onOpen(modal) {
                $("#password-form", modal).addEventListener("submit", async (event) => {
                    event.preventDefault();
                    const body = Object.fromEntries(new FormData(event.currentTarget).entries());
                    setLoading(true);
                    try {
                        const response = await api("/api/profile/password", {method: "PUT", body});
                        closeModal(); toast(response.message);
                    } catch (error) { toast(error.message, "error"); }
                    finally { setLoading(false); }
                });
            },
        });
    }

    async function changePeriod(delta = 0) {
        if (state.pending.size) {
            const yes = await confirmDialog(t("Existem alterações por guardar. Queres anulá-las e mudar de período?"), {title: t("Alterações pendentes"), danger: true, confirmText: t("Anular alterações")});
            if (!yes) {
                syncPeriodPicker();
                return;
            }
            state.pending.clear();
        }
        const previousYear = state.year;
        const previousMonth = state.month;
        const previousSelected = new Set(state.selected);
        if (delta) {
            const dateRef = new Date(state.year, state.month - 1 + delta, 1);
            state.year = dateRef.getFullYear();
            state.month = dateRef.getMonth() + 1;
        } else {
            state.month = Number($("#period-month")?.value || state.month);
            state.year = Number($("#period-year")?.value || state.year);
        }
        syncPeriodPicker();
        try {
            if (state.page === "calendar") {
                await loadCalendar();
            } else if (state.page === "dish-roster") {
                await loadDishRoster();
            } else if (state.page === "individual") {
                state.selected.clear();
                await loadIndividual();
            }
        } catch (error) {
            state.year = previousYear;
            state.month = previousMonth;
            state.selected.clear();
            previousSelected.forEach((userId) => state.selected.add(userId));
            syncPeriodPicker();
            toast(t("Não foi possível carregar o período: {0}", error.message), "error");
        }
    }

    // Global event routing
    els.loginForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        els.loginError.textContent = "";
        setLoading(true);
        try {
            const login = await api("/api/login", {method: "POST", body: {nim: $("#login-nim").value, password: $("#login-password").value}});
            await bootstrap();
            if (login.backup?.ok === false) {
                toast(login.backup.message || t("A sessão foi iniciada, mas não foi possível criar o backup da base de dados."), "warning");
            }
        } catch (error) {
            els.loginError.textContent = error.message;
        } finally { setLoading(false); }
    });

    $("#main-nav").addEventListener("click", (event) => {
        const item = event.target.closest("[data-page]");
        if (item) navigate(item.dataset.page);
    });
    $("#menu-toggle").addEventListener("click", () => {
        els.sidebar.classList.add("open");
        els.sidebarOverlay.classList.add("open");
    });
    els.sidebarOverlay.addEventListener("click", closeSidebar);
    $("#sidebar-profile").addEventListener("click", () => els.profileMenu.classList.toggle("hidden"));
    els.profileMenu.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-action]");
        if (!button) return;
        els.profileMenu.classList.add("hidden");
        if (button.dataset.action === "profile") openProfileModal();
        if (button.dataset.action === "logout") {
            try { await api("/api/logout", {method: "POST"}); } catch {}
            showLogin();
        }
        if (button.dataset.action === "shutdown") {
            const yes = await confirmDialog(t("O servidor local será encerrado e esta página deixará de responder."), {title: t("Encerrar aplicação"), danger: true, confirmText: t("Encerrar")});
            if (!yes) return;
            try { await api("/api/shutdown", {method: "POST"}); } catch {}
            els.content.innerHTML = `<div class="page"><div class="card empty-state"><div>${icon("power")}<h3>${t("Aplicação encerrada")}</h3><p>${t("Podes fechar este separador.")}</p></div></div></div>`;
        }
    });

    document.addEventListener("click", (event) => {
        if (!event.target.closest("#sidebar-profile") && !event.target.closest("#profile-menu")) els.profileMenu.classList.add("hidden");
    });

    els.content.addEventListener("change", async (event) => {
        if (event.target.matches("#period-month, #period-year")) await changePeriod();
        if (event.target.matches("[data-dish-validation]")) {
            const row = event.target.closest("[data-dish-row]");
            try {
                const pending = pendingDishRows([row], true);
                if (pending.length) await saveDishRows(pending);
                const response = await api(`/api/dish-roster/${row.dataset.weekend}/validation`, {method: "PUT", body: {validada: event.target.checked}});
                toast(response.message); await loadDishRoster();
            } catch (error) { toast(error.message, "error"); await loadDishRoster(); }
        }
        if (event.target.matches("[data-dish-signature]")) {
            const row = event.target.closest("[data-dish-row]");
            try {
                const response = await api(`/api/dish-roster/${row.dataset.weekend}/signature/${event.target.dataset.dishSignature}`, {method: "PUT", body: {assinada: event.target.checked}});
                toast(response.message); await loadDishRoster();
            } catch (error) { toast(error.message, "error"); await loadDishRoster(); }
        }
        if (event.target.id === "my-vacation-year") {
            state.vacationYear = Number(event.target.value);
            await loadMyVacations();
        }
        if (event.target.matches("[data-action='individual-select']")) {
            const id = Number(event.target.dataset.user);
            event.target.checked ? state.selected.add(id) : state.selected.delete(id);
            renderIndividualGrid();
        }
        if (event.target.matches("[data-action='individual-select-all']")) {
            if (event.target.checked) state.individual.linhas.forEach((row) => state.selected.add(row.id));
            else state.selected.clear();
            renderIndividualGrid();
        }
    });

    els.content.addEventListener("input", (event) => {
        if (event.target.id === "user-search") {
            state.userSearch = event.target.value;
            drawUsers();
            const input = $("#user-search");
            input?.focus();
            input?.setSelectionRange(input.value.length, input.value.length);
        }
    });

    document.addEventListener("click", async (event) => {
        const target = event.target.closest("[data-action]");
        if (!target) return;
        const action = target.dataset.action;
        if (action === "teams-open") {
            if (!state.boot.permissions.teams) return toast(t("Não tens permissão para gerir Teams."), "warning");
            await navigate("teams");
        }
        else if (action === "cash-consult") await openCashConsultation();
        else if (action === "cash-filter") await loadCash();
        else if (action === "cash-new") openCashMovementModal();
        else if (action === "cash-edit") {
            const item = state.cash?.movimentos.find((movement) => movement.id === Number(target.dataset.cashId));
            if (item) openCashMovementModal(item);
        }
        else if (action === "cash-delete") {
            const item = state.cash?.movimentos.find((movement) => movement.id === Number(target.dataset.cashId));
            if (!item || !await confirmDialog(t("Eliminar o movimento “{0}”?", item.descritivo), {title:t("Eliminar movimento"), danger:true, confirmText:t("Eliminar")})) return;
            try { const response = await api(`/api/cash/${item.id}`, {method:"DELETE"}); toast(response.message); await loadCash(); } catch(error) { toast(error.message,"error"); }
        }
        else if (action === "cash-pdf") {
            const range = state.cash?.range || currentMonthRange();
            await download(`/api/cash.pdf?inicio=${range.inicio}&fim=${range.fim}`, {}, `Balanco_Caixa_${range.inicio}_${range.fim}.pdf`);
        }
        else if (action === "dish-roster-open") await navigate("dish-roster");
        else if (action === "dish-roster-print") await download(`/api/dish-roster.pdf?ano=${state.year}&mes=${state.month}`, {}, "Escala_Loica.pdf");
        else if (action === "dish-roster-generate") {
            try {
                const response = await api("/api/dish-roster/generate", {method: "POST", body: {ano: state.year, mes: state.month}});
                toast(response.message);
                await loadDishRoster();
            }
            catch (error) { toast(error.message, "error"); }
        }
        else if (action === "dish-roster-save") {
            const linhas = pendingDishRows();
            try { const response = await saveDishRows(linhas); toast(response.message); await loadDishRoster(); }
            catch (error) { toast(error.message, "error"); }
        }
        else if (action === "go-calendar") await navigate("calendar");
        else if (action === "teams-pdf") await download("/api/teams.pdf", {}, "Constituicao_Teams.pdf");
        else if (action === "team-create") openTeamNameModal();
        else if (action === "team-edit") {
            const team = state.teamsData?.teams.find((item) => item.id === Number(target.dataset.teamId));
            if (team) openTeamNameModal(team);
        }
        else if (action === "team-add-member") {
            const team = state.teamsData?.teams.find((item) => item.id === Number(target.dataset.teamId));
            if (team) openTeamMembersModal(team);
        }
        else if (action === "team-remove-member") {
            const team = state.teamsData?.teams.find((item) => item.id === Number(target.dataset.teamId));
            const member = team?.membros.find((item) => item.id === Number(target.dataset.memberId));
            if (!team || !member) return;
            const yes = await confirmDialog(t("Queres remover {0} desta Team?", `${member.posto || ""} ${member.nome || ""} ${member.sobrenome || ""}`.trim()), {title: t("Remover elemento"), danger: true, confirmText: t("Remover")});
            if (!yes) return;
            try { const response = await saveTeam(team, team.nome, team.membros.filter((item) => item.id !== member.id).map((item) => item.id)); toast(response.message); await renderTeams(); } catch (error) { toast(error.message, "error"); }
        }
        else if (action === "team-delete") {
            const yes = await confirmDialog(t("Queres eliminar esta Team? Os Welfares associados ficam sem Team definida."), {title: t("Eliminar Team"), danger: true, confirmText: t("Eliminar")});
            if (!yes) return;
            try { const response = await api(`/api/teams/${target.dataset.teamId}`, {method: "DELETE"}); toast(response.message); await renderTeams(); } catch (error) { toast(error.message, "error"); }
        }
        else if (action === "period-prev") await changePeriod(-1);
        else if (action === "period-next") await changePeriod(1);
        else if (action === "calendar-pdf") await download(`/api/export/month.pdf?ano=${state.year}&mes=${state.month}`, {}, "SIGCP.pdf");
        else if (action === "individual-toggle-lock") {
            if (!state.individual?.pode_trancar_mes) return;
            if (state.pending.size) {
                toast(t("Guarda ou anula as alterações pendentes antes de trancar o mês."), "warning");
                return;
            }
            const locking = !state.individual.mes_trancado;
            const yes = await confirmDialog(locking ? t("Depois de trancares, deixam de estar disponíveis alterações aos Welfares Individuais deste mês.") : t("As alterações aos Welfares Individuais voltarão a ficar disponíveis para os perfis autorizados."), {title: locking ? t("Trancar mês") : t("Destrancar mês"), danger: locking, confirmText: locking ? t("Trancar") : t("Destrancar")});
            if (!yes) return;
            try {
                await api("/api/individual/month-lock", {method: "POST", body: {ano: state.year, mes: state.month, trancado: locking}});
                toast(locking ? t("Request efetuado. Alterações indisponíveis.") : t("Mês destrancado."));
                await loadIndividual();
            } catch (error) { toast(error.message, "error"); }
        }
        else if (action === "welfare-add") openWelfareModal(target.dataset.date);
        else if (action === "welfare-edit") {
            const existing = (state.calendar.welfares[target.dataset.date] || []).find((item) => item.refeicao === target.dataset.meal);
            openWelfareModal(target.dataset.date, target.dataset.meal, existing);
        }
        else if (action === "individual-mode") {
            if (target.dataset.mode === state.individualMode) return;
            if (state.pending.size) { toast(t("Guarda ou anula as alterações antes de mudar de modo."), "warning"); return; }
            state.individualMode = target.dataset.mode; await renderIndividual();
        }
        else if (action === "individual-mark") toggleIndividualMark(target);
        else if (action === "pending-save") await savePending();
        else if (action === "pending-cancel") { state.pending.clear(); await loadIndividual(); }
        else if (action === "individual-reset") {
            if (!state.individual?.pode_editar || state.individualMode !== "welfare") return toast(t("A reposição só está disponível no modo Welfare e com permissão de edição."), "warning");
            const yes = await confirmDialog(t("Queres repor os Welfares Individuais deste mês para os Welfares de origem?"), {title: t("Repor marcações"), danger: true, confirmText: t("Repor")});
            if (!yes) return;
            try { const response = await api("/api/individual/reset", {method: "POST", body: {ano: state.year, mes: state.month}}); toast(response.message); await loadIndividual(); }
            catch (error) { toast(error.message, "error"); }
        }
        else if (action === "individual-pdf") openPrintMode();
        else if (action === "week-excel") await exportIndividual("excel_semana", {inicio_semana: target.dataset.start});
        else if (action === "week-pdf") await exportIndividual("pdf_semana", {inicio_semana: target.dataset.start});
        else if (action === "individual-export") await exportIndividual(target.dataset.type);
        else if (action === "xfa-open") openXfaModal();
        else if (action === "user-new") openUserModal();
        else if (action === "user-edit") openUserModal(state.users.find((user) => user.id === Number(target.dataset.id)));
        else if (action === "user-delete") {
            const user = state.users.find((item) => item.id === Number(target.dataset.id));
            const yes = await confirmDialog(t("Queres eliminar o utilizador {0}? Os registos associados também serão eliminados.", user?.nim || ""), {title: t("Eliminar utilizador"), danger: true, confirmText: t("Eliminar")});
            if (!yes) return;
            try { const response = await api(`/api/users/${target.dataset.id}`, {method: "DELETE"}); toast(response.message); await loadUsers(); }
            catch (error) { toast(error.message, "error"); }
        }
        else if (action === "users-toggle-all") { state.usersAll = !state.usersAll; state.page === "admin" ? await loadAdminTab() : await renderUsersPage(); }
        else if (action === "vacation-new") openVacationModal();
        else if (action === "vacation-new-managed") {
            const people = vacationRequestPeople();
            if (!people.length) toast(t("Não existem pessoas que ainda estejam em missão."), "warning");
            else openVacationModal(null, people[0].id);
        }
        else if (action === "vacation-edit") {
            const period = findVacation(target.dataset.id);
            if (period) openVacationModal(period, period.utilizador_id);
        }
        else if (action === "vacation-admin-edit") {
            const period = findVacation(target.dataset.id);
            if (period) openVacationModal(period, period.utilizador_id, "admin-edit");
        }
        else if (action === "vacation-change") {
            const period = findVacation(target.dataset.id);
            if (period) openVacationModal(period, period.utilizador_id, "change");
        }
        else if (action === "vacation-detail") {
            try {
                const period = (await api(`/api/vacations/${target.dataset.id}`)).data;
                openVacationDetail(period);
            } catch (error) { toast(error.message, "error"); }
        }
        else if (action === "vacation-withdraw") {
            const period = findVacation(target.dataset.id); if (period) openVacationReasonModal(period, "withdraw");
        }
        else if (action === "vacation-cancel") {
            const period = findVacation(target.dataset.id); if (period) openVacationReasonModal(period, "cancel");
        }
        else if (action === "vacation-annul") {
            const period = findVacation(target.dataset.id); if (period) openVacationReasonModal(period, "annul");
        }
        else if (action === "vacation-delete") {
            const period = findVacation(target.dataset.id);
            if (!period) return;
            const yes = await confirmDialog(
                t("Apagar definitivamente as férias de {0}, de {1} a {2}? Esta ação não pode ser revertida.", period.identificacao, fmtDateTime(period.data_hora_inicio), fmtDateTime(period.data_hora_fim)),
                {title: t("Apagar período de férias"), danger: true, confirmText: t("Apagar")},
            );
            if (!yes) return;
            try {
                const response = await api(`/api/vacations/${period.id}`, {method: "DELETE"});
                toast(response.message);
                await loadVacationManagement();
            } catch (error) { toast(error.message, "error"); }
        }
        else if (action === "vacation-restore") {
            const period = findVacation(target.dataset.id);
            if (!period) return;
            const yes = await confirmDialog(
                t("Reverter a anulação das férias de {0}, de {1} a {2}?", period.identificacao, fmtDateTime(period.data_hora_inicio), fmtDateTime(period.data_hora_fim)),
                {title: t("Reverter anulação"), confirmText: t("Reverter")},
            );
            if (!yes) return;
            try {
                const response = await api(`/api/vacations/${period.id}/restore`, {method: "POST", body: {}});
                toast(response.message);
                await refreshVacationPage();
            } catch (error) { toast(error.message, "error"); }
        }
        else if (action === "vacation-decision") {
            const period = findVacation(target.dataset.id); if (period) openVacationDecisionModal(period, target.dataset.workflow, target.dataset.decision);
        }
        else if (action === "vacation-update-hours") {
            const period = findVacation(target.dataset.id); if (period) openVacationHoursModal(period);
        }
        else if (action === "my-vacation-tab") {
            state.myVacationTab = target.dataset.tab;
            $$("[data-action='my-vacation-tab']").forEach((button) => button.classList.toggle("active", button.dataset.tab === state.myVacationTab));
            if (state.myVacationTab === "requests" && Number(state.myVacations?.ano) !== Number(state.vacationYear)) await loadMyVacations();
            else await drawMyVacations();
        }
        else if (action === "my-vacations-toggle-all") {
            state.myVacationsAll = !state.myVacationsAll;
            await loadMyVacations();
        }
        else if (action === "vacation-management-tab") {
            state.vacationManagementTab = target.dataset.tab;
            $$("[data-action='vacation-management-tab']").forEach((button) => button.classList.toggle("active", button.dataset.tab === state.vacationManagementTab));
            const expectedYear = state.vacationManagementTab === "rules" ? state.vacationHolidayYear : state.vacationYear;
            if (Number(state.vacationManagement?.ano) !== Number(expectedYear)) await loadVacationManagement();
            else await drawVacationManagement();
        }
        else if (action === "vacation-substitution-people") {
            state.vacationManagementTab = "people";
            await drawVacationManagement();
        }
        else if (action === "vacation-apply-filters") {
            state.vacationYear = Number($("#vacation-year")?.value || state.vacationYear);
            state.vacationFilters = {
                search: $("#vacation-search")?.value.trim() || "",
                statusGroup: state.vacationFilters.statusGroup || "all",
                area: $("#vacation-area")?.value || "",
            };
            await loadVacationManagement();
        }
        else if (action === "vacation-filter-state") {
            state.vacationFilters.statusGroup = target.dataset.state || "all";
            await loadVacationManagement();
        }
        else if (action === "vacation-clear-filters") {
            state.vacationFilters = {search: "", statusGroup: "all", area: ""}; await loadVacationManagement();
        }
        else if (action === "vacations-toggle-all") {
            state.vacationManagementAll = !state.vacationManagementAll;
            await loadVacationManagement();
        }
        else if (action === "vacation-people-toggle-all") {
            state.vacationPeopleAll = !state.vacationPeopleAll;
            await loadVacationManagement();
        }
        else if (action === "vacation-calendar-print") printVacationCalendar();
        else if (action === "vacation-planning-print") printVacationPlanningList();
        else if (action === "vacation-planning-mode") {
            state.vacationPlanningMode = target.dataset.mode || "calendar";
            await renderVacationPlanning();
        }
        else if (action === "vacation-planning-toggle-all") {
            state.vacationPlanningAll = !state.vacationPlanningAll;
            await loadVacationPlanning();
        }
        else if (action === "vacation-planning-filter-state") {
            state.vacationPlanningFilters.statusGroup = target.dataset.state || "all";
            await loadVacationPlanning();
        }
        else if (action === "vacation-planning-apply") {
            state.vacationPlanningFilters.search = $("#planning-vacation-search")?.value.trim() || "";
            state.vacationPlanningFilters.area = $("#planning-vacation-area")?.value || "";
            await loadVacationPlanning();
        }
        else if (action === "vacation-planning-clear") {
            state.vacationPlanningFilters = {search: "", statusGroup: "all", area: ""};
            await loadVacationPlanning();
        }
        else if (action === "vacation-month") {
            const current = new Date(state.vacationYear, state.vacationMonth - 1 + Number(target.dataset.delta || 0), 1);
            state.vacationYear = current.getFullYear(); state.vacationMonth = current.getMonth() + 1;
            await loadVacationCalendar(state.page === "vacations" || state.page === "vacation-planning");
        }
        else if (action === "vacation-person-edit") {
            openVacationPersonModal(state.vacationManagement?.pessoas.find((person) => person.id === Number(target.dataset.id)));
        }
        else if (action === "vacation-holiday-new") openVacationHolidayModal();
        else if (action === "vacation-holiday-import") await openVacationHolidayImport();
        else if (action === "vacation-holiday-year") {
            const year = state.vacationHolidayYear + Number(target.dataset.delta || 0);
            if (year < 1900 || year > 2200) return;
            state.vacationHolidayYear = year;
            await loadVacationManagement();
        }
        else if (action === "vacation-holiday-edit") openVacationHolidayModal(state.vacationManagement?.feriados.find((item) => item.id === Number(target.dataset.id)));
        else if (action === "vacation-holiday-delete") {
            const holiday = state.vacationManagement?.feriados.find((item) => item.id === Number(target.dataset.id));
            const yes = await confirmDialog(t("Eliminar o feriado {0} de {1}?", holiday?.descricao || "", fmtDate(holiday?.data)), {title: t("Eliminar feriado"), danger: true, confirmText: t("Eliminar")});
            if (!yes) return;
            try { const response = await api(`/api/vacations/holidays/${target.dataset.id}`, {method: "DELETE"}); toast(response.message); await loadVacationManagement(); }
            catch (error) { toast(error.message, "error"); }
        }
        else if (action === "vacation-report") await download(`/api/vacations/report.xlsx?${vacationManagementQuery()}`, {}, `SIGCP_Ferias_${state.vacationYear}.xlsx`);
        else if (action === "vacation-print") {
            if (state.vacationManagementTab === "calendar") printVacationCalendar();
            else printVacationList();
        }
        else if (action === "vacation-notifications") await openVacationNotifications(target.dataset.notificationChannel || (state.page === "vacations" ? "gestao" : "pessoal"));
        else if (action === "vacation-notification-open") {
            try {
                const notification = state.vacationNotifications?.find((item) => item.id === Number(target.dataset.id));
                if (notification && !notification.lida) {
                    const channel = state.vacationNotificationChannel || "pessoal";
                    await api("/api/vacations/notifications/read", {method: "POST", body: {id: notification.id, canal: channel}});
                    notification.lida = 1;
                    setVacationNotificationCount(channel, vacationNotificationCount(channel) - 1);
                    syncVacationNotificationCount();
                }
                closeModal();
                const vacationId = Number(target.dataset.vacation || notification?.feria_id || 0);
                if (!vacationId) return;
                const period = (await api(`/api/vacations/${vacationId}`)).data;
                openVacationDetail(period);
            } catch (error) { toast(error.message, "error"); }
        }
        else if (action === "vacation-notification-delete") {
            try {
                const notificationId = Number(target.dataset.id);
                const notification = state.vacationNotifications?.find((item) => item.id === notificationId);
                const channel = state.vacationNotificationChannel || "pessoal";
                const response = await api(`/api/vacations/notifications/${notificationId}?canal=${encodeURIComponent(channel)}`, {method: "DELETE"});
                state.vacationNotifications = (state.vacationNotifications || []).filter((item) => item.id !== notificationId);
                if (channel === "pessoal" && state.myVacations) state.myVacations.notificacoes = state.vacationNotifications;
                if (notification && !notification.lida) {
                    setVacationNotificationCount(channel, vacationNotificationCount(channel) - 1);
                }
                syncVacationNotificationCount();
                drawVacationNotifications();
                toast(response.message);
            } catch (error) { toast(error.message, "error"); }
        }
        else if (action === "vacation-notifications-read") {
            try {
                const channel = state.vacationNotificationChannel || "pessoal";
                await api("/api/vacations/notifications/read", {method: "POST", body: {canal: channel}});
                state.vacationNotifications.forEach((item) => { item.lida = 1; });
                setVacationNotificationCount(channel, 0);
                syncVacationNotificationCount();
                drawVacationNotifications();
            }
            catch (error) { toast(error.message, "error"); }
        }
        else if (action === "audit-detail") {
            openAuditDetail(state.auditData?.registos?.find((item) => item.id === Number(target.dataset.id)));
        }
        else if (action === "audit-clear") {
            state.auditFilters = auditDefaultFilters();
            state.auditCursor = null;
            state.auditCursorStack = [];
            await loadAudit($("#admin-root"));
        }
        else if (action === "audit-next") {
            if (!state.auditData?.proximo_cursor) return;
            state.auditCursorStack.push(state.auditCursor);
            state.auditCursor = state.auditData.proximo_cursor;
            await loadAudit($("#admin-root"));
        }
        else if (action === "audit-previous") {
            if (!state.auditCursorStack.length) return;
            state.auditCursor = state.auditCursorStack.pop();
            await loadAudit($("#admin-root"));
        }
        else if (action === "admin-tab") { state.adminTab = target.dataset.tab; await renderAdmin(); }
        else if (action === "database-import") {
            const input = $("[data-database-import]");
            input.value = "";
            input.onchange = async () => {
                if (!input.files?.[0]) return;
                const yes = await confirmDialog(t("A importação substituirá todos os dados atuais. Quer continuar?"), {title: t("Importar base de dados"), danger: true, confirmText: t("Importar")});
                if (!yes) return;
                setLoading(true);
                try {
                    const data = JSON.parse(await input.files[0].text());
                    const response = await api("/api/import/database.json", {method: "POST", body: data});
                    toast(response.message, "success");
                } catch (error) { toast(error.message || t("Ficheiro JSON inválido."), "error"); }
                finally { setLoading(false); }
            };
            input.click();
        }
        else if (action === "database-export") await download("/api/export/database.json", {}, "sigcp_export.json");
        else if (action === "dayoff-new") openDayOffModal();
        else if (action === "dayoff-edit") openDayOffModal({id: Number(target.dataset.id), data: target.dataset.date, observacao: target.dataset.note});
        else if (action === "dayoff-delete") {
            const yes = await confirmDialog(t("Queres eliminar o Day Off de {0}?", fmtDate(target.dataset.date)), {title: t("Eliminar Day Off"), danger: true, confirmText: t("Eliminar")});
            if (!yes) return;
            try { const response = await api(`/api/day-offs/${target.dataset.id}`, {method: "DELETE"}); toast(response.message); await loadAdminTab(); }
            catch (error) { toast(error.message, "error"); }
        }
        else if (action === "dayoffs-toggle-all") { state.dayOffsAll = !state.dayOffsAll; await loadAdminTab(); }
    });

    window.addEventListener("hashchange", () => {
        const page = location.hash.replace("#", "");
        if (state.boot && page && page !== state.page) navigate(page, false);
    });

    let individualFitFrame = 0;
    window.addEventListener("resize", () => {
        if (state.page !== "individual") return;
        cancelAnimationFrame(individualFitFrame);
        individualFitFrame = requestAnimationFrame(fitIndividualTable);
    });

    setInterval(async () => {
        if (!state.boot || state.loadingCount || els.modalRoot.children.length) return;
        if (document.activeElement?.matches("input, select, textarea")) return;
        try {
            if (state.page === "my-vacations") await loadMyVacations();
            else if (state.page === "vacations") await loadVacationManagement();
        } catch {
            // A próxima atualização ou ação manual volta a tentar sem interromper o trabalho.
        }
    }, 45000);

    startBrowserLifecycle();
    bootstrap();
})();
