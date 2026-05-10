// ============ CHART RENDERER ============

function renderTrendChart(values, labels, opts = {}) {
  const W = 520, H = 220, P = { l: 36, r: 12, t: 14, b: 26 };
  const innerW = W - P.l - P.r;
  const innerH = H - P.t - P.b;

  const max = Math.max(...values) * 1.05;
  const min = 0;

  const x = i => P.l + (i / (values.length - 1)) * innerW;
  const y = v => P.t + innerH - ((v - min) / (max - min)) * innerH;

  // Gridlines
  const gridLines = [];
  const ticks = 4;
  for (let i = 0; i <= ticks; i++) {
    const yy = P.t + (i / ticks) * innerH;
    const val = Math.round(max - (i / ticks) * (max - min));
    gridLines.push(`
      <line x1="${P.l}" x2="${W - P.r}" y1="${yy}" y2="${yy}"
            stroke="#E9ECF1" stroke-width="1" />
      <text x="${P.l - 8}" y="${yy + 3}" font-size="9" fill="#8B92A0"
            font-family="JetBrains Mono, monospace" text-anchor="end">${val.toLocaleString('ru-RU')}</text>
    `);
  }

  // X labels (every 4th)
  const xLabels = labels.map((l, i) => {
    if (i % 4 !== 0 && i !== labels.length - 1) return '';
    return `<text x="${x(i)}" y="${H - 8}" font-size="9" fill="#8B92A0"
                  font-family="JetBrains Mono, monospace" text-anchor="middle">${l}</text>`;
  }).join('');

  // Bars (every 2nd quarter as accent)
  const bars = values.map((v, i) => {
    const bw = innerW / values.length * 0.55;
    const bx = x(i) - bw / 2;
    const by = y(v);
    const bh = (P.t + innerH) - by;
    const isAccent = i === values.length - 1;
    return `<rect x="${bx}" y="${by}" width="${bw}" height="${bh}"
                  fill="${isAccent ? '#FFC58D' : '#FFE0BD'}"
                  stroke="${isAccent ? '#E89A4D' : 'none'}" stroke-width="${isAccent ? 1 : 0}"
                  rx="2"/>`;
  }).join('');

  // Trend line
  const linePath = values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`).join(' ');
  const areaPath = `${linePath} L${x(values.length - 1)},${P.t + innerH} L${x(0)},${P.t + innerH} Z`;

  // Dots
  const dots = values.map((v, i) =>
    `<circle cx="${x(i)}" cy="${y(v)}" r="${i === values.length - 1 ? 4 : 2.5}"
             fill="${i === values.length - 1 ? '#B6FF00' : '#2684FF'}"
             stroke="${i === values.length - 1 ? '#0B0B0B' : '#FFFFFF'}"
             stroke-width="${i === values.length - 1 ? 1.5 : 1.5}"/>`
  ).join('');

  // Last value annotation
  const last = values[values.length - 1];
  const lastX = x(values.length - 1);
  const lastY = y(last);

  return `
  <svg class="chart-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <defs>
      <linearGradient id="gradFill" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%"  stop-color="#2684FF" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="#2684FF" stop-opacity="0"/>
      </linearGradient>
    </defs>
    ${gridLines.join('')}
    ${bars}
    <path d="${areaPath}" fill="url(#gradFill)"/>
    <path d="${linePath}" stroke="#2684FF" stroke-width="2" fill="none" stroke-linejoin="round"/>
    ${dots}
    <g transform="translate(${lastX - 64}, ${lastY - 30})">
      <rect width="58" height="22" rx="4" fill="#0B0B0B"/>
      <text x="29" y="14" font-size="10" fill="#B6FF00" font-family="JetBrains Mono, monospace"
            text-anchor="middle" font-weight="600">${last.toLocaleString('ru-RU')}</text>
    </g>
    ${xLabels}
  </svg>
  `;
}
