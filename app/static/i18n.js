/* Source-language keys keep the Portuguese interface readable at call sites.
 * Translate presentation strings only: database codes and user content stay intact. */
(() => {
    "use strict";
    let language = document.documentElement.lang === "en" ? "en" : "pt";
    const catalog = {};
    const patterns = [];
    const t = (source, ...values) => {
        let text = language === "en" ? (catalog[source] ?? source) : source;
        if (language === "en" && !values.length && !Object.hasOwn(catalog, source)) {
            for (const [pattern, target] of patterns) {
                const match = pattern.exec(source);
                if (match) {
                    text = target;
                    values = match.slice(1);
                    break;
                }
            }
        }
        return text.replace(/\{(\d+)\}/g, (_, index) => String(values[Number(index)] ?? `{${index}}`));
    };
    window.SIGCPI18n = {
        t,
        locale: () => language === "en" ? "en-GB" : "pt-PT",
        setLanguage(value) {
            language = value === "en" ? "en" : "pt";
            document.documentElement.lang = language;
            document.title = `SIGCP · ${t("Sistema Integrado de Gestão do Contingente Português")}`;
            document.querySelectorAll("[data-i18n]").forEach((element) => {
                element.textContent = t(element.dataset.i18n);
            });
            for (const attribute of ["title", "placeholder", "aria-label", "alt"]) {
                document.querySelectorAll(`[data-i18n-${attribute}]`).forEach((element) => {
                    element.setAttribute(attribute, t(element.getAttribute(`data-i18n-${attribute}`)));
                });
            }
        },
    };
    Object.assign(catalog, JSON.parse(document.getElementById("i18n-catalog").textContent));
    for (const [source, target] of Object.entries(catalog)) {
        if (!/\{\d+\}/.test(source)) continue;
        const pattern = source.split(/\{\d+\}/).map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("(.*?)");
        patterns.push([new RegExp(`^${pattern}$`, "s"), target]);
    }
})();
