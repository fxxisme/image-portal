<script setup>
import { formatChinaDateTime } from "../utils/datetime";

defineProps({
  conversations: {
    type: Array,
    default: () => [],
  },
  currentId: {
    type: String,
    default: null,
  },
});

defineEmits(["select", "create", "remove"]);
</script>

<template>
  <aside class="sidebar">
    <div class="side-top">
      <div class="brand-lockup">
        <span class="brand-mark" aria-hidden="true"><i /><i /><i /></span>
        <div>
          <div class="brand">VisionaryAI</div>
          <div class="brand-caption">IMAGE WORKSPACE</div>
        </div>
      </div>
    </div>

    <button
      class="primary new-chat-btn"
      type="button"
      title="新建对话"
      aria-label="新建对话"
      @click="$emit('create')"
    >
      <span class="new-chat-icon" aria-hidden="true">+</span>
      <span class="new-chat-label">新建对话</span>
    </button>

    <div class="conv-list">
      <div class="section-label">最近创作</div>
      <button
        v-for="c in conversations"
        :key="c.id"
        type="button"
        class="conv-item"
        :class="{ active: c.id === currentId }"
        @click="$emit('select', c.id)"
      >
        <div class="conv-title">{{ c.title || "未命名" }}</div>
        <div class="conv-meta muted">{{ formatChinaDateTime(c.updated_at) }}</div>
        <span class="del" title="删除" @click.stop="$emit('remove', c.id)">&times;</span>
      </button>
      <div v-if="!conversations.length" class="muted empty">暂无对话</div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 280px;
  min-width: 280px;
  background: var(--bg-surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 16px;
  gap: 16px;
}

.side-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand-lockup {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-mark {
  display: inline-flex;
  gap: 3px;
  padding: 4px;
}

.brand-mark i {
  width: 4px;
  height: 12px;
  background: var(--primary);
  border-radius: 2px;
}

.brand {
  font-weight: 700;
  font-size: 15px;
  letter-spacing: -0.02em;
}

.brand-caption {
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.08em;
}

.new-chat-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 8px;
  font-weight: 500;
  cursor: pointer;
}

.conv-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-label {
  font-size: 11px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 4px;
  padding: 0 4px;
}

.conv-item {
  position: relative;
  width: 100%;
  text-align: left;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.conv-item:hover {
  background: var(--card-hover);
  border-color: var(--border-light);
}

.conv-item.active {
  background: var(--card);
  border-color: var(--primary);
}

.conv-title {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 20px;
}

.conv-meta {
  font-size: 11px;
}

.del {
  position: absolute;
  right: 8px;
  top: 8px;
  font-size: 16px;
  line-height: 1;
  color: var(--muted);
  opacity: 0;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.15s ease;
}

.conv-item:hover .del {
  opacity: 0.7;
}

.del:hover {
  opacity: 1 !important;
  color: #ef4444;
  background: rgba(239, 68, 68, 0.15);
}

.empty {
  text-align: center;
  padding: 24px 0;
  font-size: 12px;
}

@media (max-width: 768px) {
  .sidebar {
    display: none;
  }
}
</style>
