const TASK_TYPE_LABELS = {
  minimax_h3: "高级图生视频 Pro",
  minimax_h3_t2v: "高级图生视频 Pro · 文生视频",
  minimax_h3_i2v: "高级图生视频 Pro · 首帧图生视频",
  minimax_h3_flf2v: "高级图生视频 Pro · 首尾帧视频",
  minimax_h3_ref2v: "高级图生视频 Pro · 参考图生视频",
};

export function taskTypeLabel(taskType) {
  const normalized = String(taskType || "").trim();
  return TASK_TYPE_LABELS[normalized] || normalized;
}

export function taskTypeListLabel(taskTypes, fallback = "-") {
  const labels = (Array.isArray(taskTypes) ? taskTypes : [])
    .map(taskTypeLabel)
    .filter(Boolean);
  return labels.join(" / ") || fallback;
}
