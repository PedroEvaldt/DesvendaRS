const menuButton = document.querySelector(".menu-toggle");
const mainMenu = document.querySelector(".main-nav");

if (menuButton && mainMenu) {
  menuButton.addEventListener("click", () => {
    const isOpen = menuButton.getAttribute("aria-expanded") === "true";
    menuButton.setAttribute("aria-expanded", String(!isOpen));
    mainMenu.classList.toggle("is-open", !isOpen);
  });

  mainMenu.addEventListener("click", (event) => {
    if (event.target.closest("a")) {
      menuButton.setAttribute("aria-expanded", "false");
      mainMenu.classList.remove("is-open");
    }
  });
}

document.querySelectorAll("[data-auto-submit]").forEach((field) => {
  field.addEventListener("change", () => field.form?.requestSubmit());
});

document.querySelectorAll("[data-href]").forEach((element) => {
  element.addEventListener("click", (event) => {
    if (event.target.closest("a, button, input, select")) return;
    window.location.href = element.dataset.href;
  });
});

const canvasToBlob = (canvas) =>
  new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) {
        resolve(blob);
        return;
      }
      reject(new Error("PNG export failed"));
    }, "image/png");
  });

const cleanFilename = (filename) => {
  const cleaned = (filename || "desvendars.png")
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, "-")
    .toLowerCase();
  return cleaned.endsWith(".png") ? cleaned : `${cleaned}.png`;
};

const downloadBlob = (blob, filename) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = cleanFilename(filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
};

const readText = (root, selector) => root.querySelector(selector)?.textContent.trim() || "";

const readMetric = (node) => ({
  label: readText(node, "span"),
  value: readText(node, "strong"),
  note: readText(node, "small"),
});

const wrapLines = (context, text, maxWidth, maxLines = Infinity) => {
  const words = String(text || "").replace(/\s+/g, " ").trim().split(" ").filter(Boolean);
  const lines = [];
  let current = "";

  words.forEach((word) => {
    const test = current ? `${current} ${word}` : word;
    if (context.measureText(test).width <= maxWidth) {
      current = test;
      return;
    }
    if (current) lines.push(current);
    current = word;
  });

  if (current) lines.push(current);
  if (!lines.length) lines.push("");

  if (lines.length > maxLines) {
    const visible = lines.slice(0, maxLines);
    let last = visible[visible.length - 1];
    while (last.length > 1 && context.measureText(`${last}...`).width > maxWidth) {
      last = last.slice(0, -1).trimEnd();
    }
    visible[visible.length - 1] = `${last}...`;
    return visible;
  }

  return lines;
};

const drawRoundRect = (context, x, y, width, height, radius) => {
  const r = Math.min(radius, width / 2, height / 2);
  context.beginPath();
  context.moveTo(x + r, y);
  context.arcTo(x + width, y, x + width, y + height, r);
  context.arcTo(x + width, y + height, x, y + height, r);
  context.arcTo(x, y + height, x, y, r);
  context.arcTo(x, y, x + width, y, r);
  context.closePath();
};

const drawTextLines = (context, lines, x, y, lineHeight) => {
  lines.forEach((line, index) => {
    context.fillText(line, x, y + index * lineHeight);
  });
};

const drawChipRows = (context, labels, x, y, maxWidth) => {
  const gap = 10;
  const rowHeight = 34;
  let cursorX = x;
  let cursorY = y;

  context.font = "700 14px Inter, system-ui, sans-serif";
  labels.forEach((label) => {
    const width = Math.min(context.measureText(label).width + 24, maxWidth);
    if (cursorX > x && cursorX + width > x + maxWidth) {
      cursorX = x;
      cursorY += rowHeight + gap;
    }

    context.fillStyle = "#f6f7f3";
    drawRoundRect(context, cursorX, cursorY, width, rowHeight, 17);
    context.fill();
    context.strokeStyle = "#eaf0f2";
    context.stroke();
    context.fillStyle = "#486581";
    context.fillText(label, cursorX + 12, cursorY + 22);
    cursorX += width + gap;
  });

  return cursorY + rowHeight - y;
};

const severityColors = (label) => {
  const normalized = label.toLowerCase();
  if (normalized.includes("alto") || normalized.includes("forte")) {
    return { fg: "#982d3d", bg: "#fdecef" };
  }
  if (normalized.includes("baixo")) {
    return { fg: "#256347", bg: "#e8f5ee" };
  }
  return { fg: "#875b0f", bg: "#fff3d2" };
};

const renderElementToPng = async (target) => {
  const card = target.querySelector(".share-card") || target;
  const headerTitle = readText(card, ".share-card__header strong");
  const headerSubtitle = readText(card, ".share-card__header div span");
  const headerAside = readText(card, ".share-card__header > span");
  const title = readText(card, "h2");
  const metas = Array.from(card.querySelectorAll(".share-card__meta span")).map((item) => item.textContent.trim());
  const metrics = Array.from(card.querySelectorAll(".share-card__metrics > div")).map(readMetric);
  const sectionTitle = readText(card, ".share-card__section h3");
  const items = Array.from(card.querySelectorAll(".share-card__section li")).map((item) => ({
    severity: readText(item, ".share-card__severity"),
    text: readText(item, "p"),
  }));
  const more = readText(card, ".share-card__more") || readText(card, ".share-card__empty");
  const footer = readText(card, "footer");
  const measure = document.createElement("canvas").getContext("2d");

  const width = 960;
  const margin = 44;
  const inner = width - margin * 2;
  let y = margin;

  measure.font = "700 36px Inter, system-ui, sans-serif";
  const titleLines = wrapLines(measure, title, inner, 3);
  y += 64;
  y += 28 + titleLines.length * 42 + 16;
  const metaHeight = drawChipRows(measure, metas, 0, 0, inner);
  y += metaHeight + 28;
  y += 118 + 28;

  measure.font = "400 15px Inter, system-ui, sans-serif";
  const itemLayouts = items.slice(0, 3).map((item) => ({
    ...item,
    lines: wrapLines(measure, item.text, inner - 112, 2),
  }));
  const itemHeights = itemLayouts.map((item) => Math.max(28, item.lines.length * 22));
  const sectionItemsHeight = itemHeights.reduce((sum, height) => sum + height, 0);
  const sectionGaps = itemHeights.length ? (itemHeights.length - 1) * 12 : 0;
  const moreHeight = more ? 28 : 0;
  const sectionHeight = 22 + 22 + 14 + sectionItemsHeight + sectionGaps + moreHeight + 22;
  y += sectionHeight + 20 + 18 + margin;

  const scale = Math.min(window.devicePixelRatio || 2, 2);
  const canvas = document.createElement("canvas");
  canvas.width = width * scale;
  canvas.height = y * scale;

  const context = canvas.getContext("2d");
  context.scale(scale, scale);
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, width, y);

  context.strokeStyle = "#dce4e8";
  context.strokeRect(0.5, 0.5, width - 1, y - 1);

  context.fillStyle = "#087f6d";
  context.font = "700 24px Inter, system-ui, sans-serif";
  context.fillText(headerTitle, margin, margin + 22);
  context.fillStyle = "#6b7c8f";
  context.font = "700 15px Inter, system-ui, sans-serif";
  context.fillText(headerSubtitle, margin, margin + 48);
  context.textAlign = "right";
  context.fillText(headerAside, width - margin, margin + 24);
  context.textAlign = "left";
  context.strokeStyle = "#dce4e8";
  context.beginPath();
  context.moveTo(margin, margin + 68);
  context.lineTo(width - margin, margin + 68);
  context.stroke();

  y = margin + 98;
  context.fillStyle = "#102a43";
  context.font = "700 36px Inter, system-ui, sans-serif";
  drawTextLines(context, titleLines, margin, y, 42);
  y += titleLines.length * 42 + 22;

  const usedMetaHeight = drawChipRows(context, metas, margin, y, inner);
  y += usedMetaHeight + 28;

  const gap = 12;
  const metricWidth = (inner - gap * 3) / 4;
  metrics.slice(0, 4).forEach((metric, index) => {
    const x = margin + index * (metricWidth + gap);
    context.fillStyle = "#f8faf9";
    drawRoundRect(context, x, y, metricWidth, 118, 12);
    context.fill();
    context.strokeStyle = "#dce4e8";
    context.stroke();

    context.fillStyle = "#6b7c8f";
    context.font = "800 12px Inter, system-ui, sans-serif";
    wrapLines(context, metric.label.toUpperCase(), metricWidth - 36, 2).forEach((line, lineIndex) => {
      context.fillText(line, x + 18, y + 20 + lineIndex * 15);
    });

    context.fillStyle = "#102a43";
    context.font = "700 26px Inter, system-ui, sans-serif";
    drawTextLines(context, wrapLines(context, metric.value, metricWidth - 36, 2), x + 18, y + 72, 30);
    if (metric.note) {
      context.fillStyle = "#6b7c8f";
      context.font = "700 14px Inter, system-ui, sans-serif";
      context.fillText(metric.note, x + 18, y + 101);
    }
  });
  y += 146;

  context.fillStyle = "#fffdf6";
  drawRoundRect(context, margin, y, inner, sectionHeight, 14);
  context.fill();
  context.strokeStyle = "#f0e4c2";
  context.stroke();

  let sectionY = y + 22;
  context.fillStyle = "#102a43";
  context.font = "700 18px Inter, system-ui, sans-serif";
  context.fillText(sectionTitle, margin + 22, sectionY + 18);
  sectionY += 36;

  context.font = "400 15px Inter, system-ui, sans-serif";
  itemLayouts.forEach((item, index) => {
    const colors = severityColors(item.severity);
    context.fillStyle = colors.bg;
    drawRoundRect(context, margin + 22, sectionY, 84, 28, 14);
    context.fill();
    context.fillStyle = colors.fg;
    context.font = "800 11px Inter, system-ui, sans-serif";
    context.textAlign = "center";
    context.fillText(item.severity.toUpperCase(), margin + 64, sectionY + 18);
    context.textAlign = "left";

    context.fillStyle = "#486581";
    context.font = "400 15px Inter, system-ui, sans-serif";
    drawTextLines(context, item.lines, margin + 118, sectionY + 17, 22);
    sectionY += itemHeights[index] + 12;
  });

  if (more) {
    context.fillStyle = "#6b7c8f";
    context.font = "700 13px Inter, system-ui, sans-serif";
    context.fillText(more, margin + 22, sectionY + 18);
  }

  y += sectionHeight + 20;
  context.fillStyle = "#6b7c8f";
  context.font = "600 13px Inter, system-ui, sans-serif";
  context.fillText(footer, margin, y + 14);

  return canvasToBlob(canvas);
};

document.querySelectorAll("[data-export-trigger]").forEach((button) => {
  button.addEventListener("click", async () => {
    const target = document.querySelector(button.dataset.exportTarget);
    if (!target) return;

    const originalHtml = button.innerHTML;
    button.classList.add("is-busy");
    button.disabled = true;
    button.innerHTML = "Gerando...";

    try {
      const blob = await renderElementToPng(target);
      downloadBlob(blob, button.dataset.exportFilename);
    } catch (error) {
      console.error(error);
      window.alert("Nao foi possivel gerar a imagem agora.");
    } finally {
      button.innerHTML = originalHtml;
      button.disabled = false;
      button.classList.remove("is-busy");
    }
  });
});
