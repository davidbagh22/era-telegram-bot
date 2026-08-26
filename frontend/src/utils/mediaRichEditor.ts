const ALLOWED_TAGS = new Set(["B", "STRONG", "I", "EM", "U", "S", "STRIKE", "DEL", "CODE", "PRE", "BLOCKQUOTE", "A"]);
const SAFE_SCHEMES = new Set(["http:", "https:", "tg:"]);

function safeHref(value: string): string | null {
  try {
    const url = new URL(value, window.location.origin);
    if (!SAFE_SCHEMES.has(url.protocol)) return null;
    return value.trim();
  } catch {
    return null;
  }
}

export function sanitizeMediaPreviewHtml(value: string): string {
  const template = document.createElement("template");
  template.innerHTML = value;
  const output = document.createElement("div");

  const copyNode = (node: Node, parent: Node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      parent.appendChild(document.createTextNode(node.textContent ?? ""));
      return;
    }
    if (!(node instanceof HTMLElement)) return;

    const tag = node.tagName.toUpperCase();
    if (!ALLOWED_TAGS.has(tag)) {
      node.childNodes.forEach((child) => copyNode(child, parent));
      return;
    }

    const canonical = tag === "STRONG" ? "b" : tag === "EM" ? "i" : ["STRIKE", "DEL"].includes(tag) ? "s" : tag.toLowerCase();
    const element = document.createElement(canonical);
    if (canonical === "a") {
      const href = safeHref(node.getAttribute("href") ?? "");
      if (!href) {
        node.childNodes.forEach((child) => copyNode(child, parent));
        return;
      }
      element.setAttribute("href", href);
      element.setAttribute("target", "_blank");
      element.setAttribute("rel", "noopener noreferrer");
    }
    node.childNodes.forEach((child) => copyNode(child, element));
    parent.appendChild(element);
  };

  template.content.childNodes.forEach((node) => copyNode(node, output));
  return output.innerHTML;
}

function applyAroundSelection(textarea: HTMLTextAreaElement, open: string, close: string): void {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const selected = textarea.value.slice(start, end) || "текст";
  textarea.setRangeText(`${open}${selected}${close}`, start, end, "select");
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
  textarea.focus();
}

function applyLinePrefix(textarea: HTMLTextAreaElement, prefix: string): void {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const selected = textarea.value.slice(start, end) || "Пункт";
  const formatted = selected.split("\n").map((line) => `${prefix}${line}`).join("\n");
  textarea.setRangeText(formatted, start, end, "select");
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
  textarea.focus();
}

export function openMediaRichEditor(initialValue: string): Promise<string | null> {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Предпросмотр публикации");
    Object.assign(overlay.style, {
      position: "fixed",
      inset: "0",
      zIndex: "10000",
      background: "rgba(0,0,0,.58)",
      padding: "max(18px, env(safe-area-inset-top)) 14px max(18px, env(safe-area-inset-bottom))",
      display: "grid",
      placeItems: "center",
      overflow: "auto",
    });

    const card = document.createElement("div");
    Object.assign(card.style, {
      width: "min(620px, 100%)",
      maxHeight: "92vh",
      overflow: "auto",
      borderRadius: "22px",
      background: "var(--era-surface, #fff)",
      color: "var(--era-text, #111)",
      padding: "18px",
      boxShadow: "0 24px 70px rgba(0,0,0,.28)",
      display: "grid",
      gap: "12px",
    });

    const heading = document.createElement("div");
    heading.innerHTML = '<div style="font-size:12px;font-weight:800;opacity:.58;text-transform:uppercase">Media Desk</div><div style="font-size:22px;font-weight:900;margin-top:2px">Публикация в Telegram</div><div style="font-size:13px;opacity:.65;margin-top:5px;line-height:1.4">Отредактируйте текст и сразу проверьте, как он будет читаться в канале.</div>';

    const toolbar = document.createElement("div");
    Object.assign(toolbar.style, { display: "flex", flexWrap: "wrap", gap: "7px" });

    const textarea = document.createElement("textarea");
    textarea.value = initialValue;
    textarea.placeholder = "Текст публикации";
    Object.assign(textarea.style, {
      width: "100%",
      minHeight: "190px",
      resize: "vertical",
      boxSizing: "border-box",
      border: "1px solid var(--era-border, #ddd)",
      borderRadius: "14px",
      padding: "13px",
      background: "var(--era-surface-2, #f7f7f8)",
      color: "inherit",
      font: "inherit",
      lineHeight: "1.5",
    });

    const previewLabel = document.createElement("strong");
    previewLabel.textContent = "Предпросмотр Telegram";
    const preview = document.createElement("div");
    Object.assign(preview.style, {
      whiteSpace: "pre-wrap",
      overflowWrap: "anywhere",
      lineHeight: "1.55",
      borderRadius: "16px",
      padding: "14px",
      background: "var(--era-surface-2, #f7f7f8)",
      border: "1px solid var(--era-border, #e7e7e9)",
      minHeight: "70px",
    });

    const updatePreview = () => {
      preview.innerHTML = sanitizeMediaPreviewHtml(textarea.value);
    };
    textarea.addEventListener("input", updatePreview);
    updatePreview();

    const tool = (label: string, title: string, action: () => void) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.title = title;
      Object.assign(button.style, {
        border: "1px solid var(--era-border, #ddd)",
        background: "var(--era-surface-2, #f7f7f8)",
        color: "inherit",
        borderRadius: "10px",
        minWidth: "42px",
        minHeight: "38px",
        padding: "7px 10px",
        fontWeight: "800",
        cursor: "pointer",
      });
      button.addEventListener("click", action);
      toolbar.appendChild(button);
    };

    tool("B", "Жирный", () => applyAroundSelection(textarea, "<b>", "</b>"));
    tool("I", "Курсив", () => applyAroundSelection(textarea, "<i>", "</i>"));
    tool("↗", "Ссылка", () => {
      const href = window.prompt("Ссылка (https://…)");
      if (!href) return;
      if (!safeHref(href)) {
        window.alert("Разрешены только http, https и tg ссылки.");
        return;
      }
      applyAroundSelection(textarea, `<a href="${href.replace(/"/g, "&quot;")}">`, "</a>");
    });
    tool("•", "Список", () => applyLinePrefix(textarea, "• "));
    tool("❝", "Цитата", () => applyAroundSelection(textarea, "<blockquote>", "</blockquote>"));

    const actions = document.createElement("div");
    Object.assign(actions.style, { display: "grid", gridTemplateColumns: "1fr 1.4fr", gap: "8px", marginTop: "4px" });
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "Отмена";
    const publish = document.createElement("button");
    publish.type = "button";
    publish.textContent = "Сохранить и опубликовать";
    [cancel, publish].forEach((button) => Object.assign(button.style, {
      border: "0",
      borderRadius: "13px",
      minHeight: "46px",
      padding: "10px 12px",
      fontWeight: "850",
      cursor: "pointer",
    }));
    Object.assign(cancel.style, { background: "var(--era-surface-2, #eee)", color: "inherit" });
    Object.assign(publish.style, { background: "var(--era-violet, #6d4aff)", color: "#fff" });
    actions.append(cancel, publish);

    const finish = (value: string | null) => {
      document.removeEventListener("keydown", onKeyDown);
      overlay.remove();
      resolve(value);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") finish(null);
    };
    document.addEventListener("keydown", onKeyDown);
    cancel.addEventListener("click", () => finish(null));
    overlay.addEventListener("click", (event) => { if (event.target === overlay) finish(null); });
    publish.addEventListener("click", () => {
      const value = textarea.value.trim();
      if (!value) {
        textarea.focus();
        return;
      }
      finish(value);
    });

    card.append(heading, toolbar, textarea, previewLabel, preview, actions);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    window.setTimeout(() => textarea.focus(), 0);
  });
}
