const CHINA_TIME_ZONE = "Asia/Shanghai";
const TIME_ZONE_SUFFIX_RE = /(?:Z|[+-]\d{2}:?\d{2})$/i;

export function formatChinaDateTime(value) {
  if (!value) return "-";

  // SQLite 返回的无时区时间是后端写入的 UTC，显式标记后再转换为 UTC+8。
  const raw = String(value);
  const date = new Date(TIME_ZONE_SUFFIX_RE.test(raw) ? raw : `${raw}Z`);
  if (Number.isNaN(date.getTime())) return "-";

  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: CHINA_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(date);
}
