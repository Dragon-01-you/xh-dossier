/*
 * XH-Dossier DOM export (zero extension).
 *
 * Usage in a logged-in conversation page:
 *   1. Paste this file into the browser console (or call it through the
 *      Agent's page-evaluate tool).
 *   2. It reads the visible message rows, builds an AfterChat-compatible
 *      Markdown file, stores it at window.__XH_DOM_EXPORT__, and (by default)
 *      triggers a browser download.
 *   3. To let the Agent write the file itself, set
 *      window.__XH_DOM_EXPORT_NO_DOWNLOAD__ = true before running, then read
 *      window.__XH_DOM_EXPORT__.markdown.
 *
 * Verified selectors for Doubao (2026-11-24):
 *   message row: .v_list_row
 *   role:        [data-message-role="user"|"assistant"]
 *   body:        [data-testid="message_text_content"]
 * The old .send-msg-bubble is kept only as a fallback; on the current page
 * its count is 0, so do not treat it as the primary contract.
 * Other sites are intentionally not guessed; pass an adapter object in
 * window.__XH_DOM_EXPORT_ADAPTER__ only after checking their DOM.
 */
(() => {
  const adapter = Object.assign({
    rowSelector: ".v_list_row",
    roleSelector: "[data-message-role]",
    contentSelector: "[data-testid='message_text_content']",
    userSelector: ".send-msg-bubble",
    filenamePrefix: "豆包 - ",
    titlePrefix: /^\s*豆包\s*[-–—]\s*/,
    titleSuffix: /\s*[-–—]\s*豆包\s*$/,
  }, window.__XH_DOM_EXPORT_ADAPTER__ || {});

  const rows = Array.from(document.querySelectorAll(adapter.rowSelector))
    .filter((row) => {
      const parent = row.parentElement;
      return !(parent && parent.closest(adapter.rowSelector));
    });

  const stripNoise = (node) => {
    const clone = node.cloneNode(true);
    clone.querySelectorAll(
      "button, svg, [role='button'], .anticon, .message-actions, .copy-btn, .msg-action"
    ).forEach((el) => el.remove());
    return clone;
  };

  const messages = [];
  for (const row of rows) {
    const roleNode = row.querySelector(adapter.roleSelector);
    const declaredRole = roleNode && roleNode.getAttribute("data-message-role");
    const isUser = declaredRole
      ? declaredRole === "user"
      : (!!row.querySelector(adapter.userSelector) ||
        !!row.closest(adapter.userSelector) ||
        !!row.querySelector("[data-testid='send_message']"));
    const isAssistant = declaredRole
      ? declaredRole === "assistant"
      : !!row.querySelector("[data-testid='receive_message']");
    if (!isUser && !isAssistant) continue;

    const contentNode = row.querySelector(adapter.contentSelector);
    const clone = stripNoise(contentNode || row);
    const text = (clone.innerText || clone.textContent || "")
      .replace(/\r/g, "")
      .replace(/[ \t]+\n/g, "\n")
      .trim();
    if (!text) continue;

    const role = isUser ? "User" : "Assistant";
    const last = messages[messages.length - 1];
    if (last && last.role === role && last.content === text) continue;
    messages.push({ role, content: text });
  }

  const rawTitle = (document.title || "")
    .replace(adapter.titlePrefix, "")
    .replace(adapter.titleSuffix, "")
    .trim();
  const title = rawTitle || "conversation";
  const safeTitle = title.replace(/[\\/:*?"<>|]/g, "_").slice(0, 80);
  const date = new Date().toISOString().slice(0, 10);
  const source = location.href;

  const lines = [
    "## Metadata",
    `- **Source:** ${source}`,
    `- **Time:** ${date}`,
    "- **Exporter:** XH-Dossier DOM export",
    `- **Message-Count:** ${messages.length}`,
    "",
    "## Conversation",
    "",
  ];
  for (const msg of messages) {
    lines.push(`### ${msg.role === "User" ? "🧑‍💻 User" : "🤖 Assistant"}`, "", msg.content, "");
  }
  const markdown = lines.join("\n");
  const filename = `${adapter.filenamePrefix}${safeTitle}.md`;

  const result = {
    ok: true,
    count: messages.length,
    filename,
    markdown,
    source,
    date,
  };
  window.__XH_DOM_EXPORT__ = result;

  if (!window.__XH_DOM_EXPORT_NO_DOWNLOAD__) {
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  return JSON.stringify({
    ok: true,
    count: messages.length,
    filename,
    chars: markdown.length,
    source,
  });
})();
