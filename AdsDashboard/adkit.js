// 구글·메타 대시보드 공통 함수. 빌드할 때 template.html의 /*__COMMON_JS__*/ 자리에 들어간다.

// ---- 숫자 표기
const num = n => Math.round(n || 0).toLocaleString('ko-KR');
const pct = (a, b) => b ? (a / b * 100).toFixed(2) + '%' : '-';
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// 통화에 맞는 금액 표기 함수를 만든다 (구글=원, 메타=달러)
const moneyFmt = cur => cur === 'USD' ? n => '$' + (n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : n => Math.round(n || 0).toLocaleString('ko-KR') + '원';
// 나눗셈 지표(CPC·CPA 등). 분모가 0이면 '-'
const ratio = (fmt, a, b) => b ? fmt(a / b) : '-';

// ---- 날짜: 'YYYY-MM-DD' 문자열을 UTC 자정으로 다뤄 시간대 때문에 하루 밀리는 일을 막는다
const addDays = (ymd, n) => { const d = new Date(ymd + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const TODAY = (() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; })();
const LAST_DAY = addDays(TODAY, -1);  // 광고 데이터는 어제까지가 완성본
// 최근 n일 구간. shift=1이면 바로 앞 같은 길이 구간(전기 비교용)
const lastNDays = (n, shift = 0) => { const e = addDays(LAST_DAY, -shift * n); return [addDays(e, -n + 1), e]; };
const inRange = ([s, e]) => r => r.date >= s && r.date <= e;

// ---- 합계·묶기
function sumBy(rows, keys) {
  const a = Object.fromEntries(keys.map(k => [k, 0]));
  rows.forEach(r => keys.forEach(k => { a[k] += r[k] || 0; }));
  return a;
}
// keyOf(r)가 같은 행끼리 묶어 { r: 대표 행, s: 합계, list } 목록으로
function groupRows(rows, keyOf, keys) {
  const m = new Map();
  rows.forEach(r => { const k = keyOf(r); if (!m.has(k)) m.set(k, []); m.get(k).push(r); });
  return [...m.values()].map(list => ({ r: list[0], last: list.at(-1), list, s: sumBy(list, keys) }));
}

// ---- 전기 대비 증감. better='up'이면 오를 때 초록, 'down'이면 내릴 때 초록, 생략하면 색 없음
function delta(cur, prev, fmt, better) {
  if (!prev) return '전기 데이터 없음';
  const d = (cur - prev) / prev * 100;
  const dir = d >= 0 ? 'up' : 'down';
  const cls = !better || Math.abs(d) < 0.5 ? '' : (dir === better ? `${dir}-good` : `${dir}-bad`);
  return `전기 ${fmt(prev)} · <span class="${cls}">${d >= 0 ? '+' : ''}${d.toFixed(0)}%</span>`;
}

// ---- 화면 조각
const bar = (v, max, color) => `<span class="bar" style="width:${Math.max(2, v / max * 60)}px;background:${color}"></span>`;
const emptyTable = (id, msg) => { document.getElementById(id).innerHTML = `<tr><td class="empty">${esc(msg)}</td></tr>`; };
// 라벨 사전 {이름: [표시명, 색]}에서 표시명·색을 꺼내는 함수 쌍
const labeler = dict => ({
  name: k => (dict[k] || [k])[0],
  color: k => (dict[k] || [, '#9ca3af'])[1],
  rank: k => { const i = Object.keys(dict).indexOf(k); return i < 0 ? 99 : i; },
});
// 표 머리글. [글자, 풀이] 쌍이면 풀이를 마우스 올림 설명으로 단다. 'l'로 시작하는 글자는 왼쪽 정렬
const head = cols => '<thead><tr>' + cols.map(c => {
  const [t, tip] = Array.isArray(c) ? c : [c, ''];
  const left = t.startsWith('l:');
  return `<th${left ? ' class="l"' : ''}${tip ? ` title="${esc(tip)}"` : ''}>${esc(left ? t.slice(2) : t)}</th>`;
}).join('') + '</tr></thead>';

// KPI 묶음 그리기. groups = [{ title, items: [[지표명, 풀이, 값, 증감HTML]] }]
function renderKpis(id, groups) {
  document.getElementById(id).innerHTML = groups.map(g =>
    `<div class="kpi-group"><h3>${esc(g.title)}</h3>` + g.items.map(([label, def, value, d]) =>
      `<div class="kpi"><div class="label">${esc(label)}<small>${esc(def)}</small></div>` +
      `<div class="right"><div class="value">${value}</div><div class="delta">${d || '&nbsp;'}</div></div></div>`).join('') +
    '</div>').join('');
}

// 일별 막대(항목별 비용 누적) + 선(클릭) 그래프. 두 대시보드가 같은 모양을 쓴다
function stackedDailyChart(canvas, old, { rows, seriesOf, order, label, color, lineKey, lineLabel, valueKey, money }) {
  const dates = [...new Set(rows.map(r => r.date))].sort();
  const series = [...new Set(rows.map(seriesOf))].sort((x, y) => order(x) - order(y));
  const cell = {}, line = {};
  rows.forEach(r => {
    const k = seriesOf(r) + '|' + r.date;
    cell[k] = (cell[k] || 0) + r[valueKey];
    line[r.date] = (line[r.date] || 0) + r[lineKey];
  });
  old?.destroy();
  return new Chart(canvas, {
    type: 'bar',
    data: {
      labels: dates.map(d => d.slice(5)),
      datasets: [
        { type: 'line', label: lineLabel, data: dates.map(d => line[d] || 0), borderColor: '#111827', backgroundColor: '#111827',
          borderWidth: 2, tension: .25, yAxisID: 'y1', order: 0 },
        ...series.map(s => ({ label: label(s), data: dates.map(d => cell[s + '|' + d] || 0), backgroundColor: color(s) + 'cc',
          stack: 'cost', yAxisID: 'y', order: 1 })),
      ],
    },
    options: {
      maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      scales: {
        x: { stacked: true },
        y: { stacked: true, beginAtZero: true, title: { display: true, text: '광고비' }, ticks: { callback: v => money(v) } },
        y1: { position: 'right', grid: { drawOnChartArea: false }, beginAtZero: true, title: { display: true, text: lineLabel }, ticks: { precision: 0 } },
      },
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, font: { family: 'Pretendard' } } },
        tooltip: { callbacks: { label: c => c.dataset.label + ' ' + (c.dataset.type === 'line' ? num(c.raw) + '회' : money(c.raw)) } },
      },
    },
  });
}
