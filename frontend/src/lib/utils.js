// pieni utility-luokkien yhdistäjä
export function cn(...args) {
  return args.filter(Boolean).join(" ");
}

export const fmtPrice = (v, digits = 3) => {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return Number(v).toFixed(digits);
};

export const fmtDateFi = (isoDate) => {
  if (!isoDate) return "—";
  const [y, m, d] = isoDate.split("T")[0].split("-");
  return `${parseInt(d, 10)}.${parseInt(m, 10)}.${y}`;
};

export const fmtDateTimeFi = (iso) => {
  if (!iso) return "—";
  const dt = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(dt.getDate())}.${pad(dt.getMonth() + 1)}.${dt.getFullYear()} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
};
