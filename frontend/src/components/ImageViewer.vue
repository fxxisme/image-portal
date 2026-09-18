<script setup>
import { onBeforeUnmount, onMounted } from "vue";

const props = defineProps({
  url: {
    type: String,
    required: true,
  },
  alt: {
    type: String,
    default: "图片预览",
  },
  subtitle: {
    type: String,
    default: "",
  },
  showDownload: {
    type: Boolean,
    default: true,
  },
});

const emit = defineEmits(["close"]);

function handleKeydown(e) {
  if (e.key === "Escape") {
    emit("close");
  }
}

onMounted(() => {
  window.addEventListener("keydown", handleKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleKeydown);
});
</script>

<template>
  <div class="image-viewer-layer" role="dialog" aria-modal="true" :aria-label="alt" @click.self="emit('close')">
    <button class="image-viewer-close" type="button" aria-label="关闭预览" title="关闭预览 (Esc)" @click="emit('close')">
      &times;
    </button>
    
    <div class="image-viewer-body" @click.self="emit('close')">
      <img :src="url" :alt="alt" />
    </div>

    <div v-if="subtitle || showDownload" class="image-viewer-footer">
      <p v-if="subtitle" class="image-viewer-subtitle">{{ subtitle }}</p>
      <div v-if="showDownload" class="image-viewer-actions">
        <a :href="url" target="_blank" rel="noopener" class="action-btn">在新标签打开</a>
        <a :href="url" download="image" class="action-btn primary">下载图片</a>
      </div>
    </div>
  </div>
</template>

<style scoped>
.image-viewer-layer {
  position: fixed;
  z-index: 100;
  inset: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  gap: 16px;
  padding: 32px;
  background: rgba(0, 0, 0, 0.88);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.image-viewer-body {
  min-height: 0;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.image-viewer-body img {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
  border-radius: 6px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
}

.image-viewer-close {
  position: absolute;
  top: 20px;
  right: 24px;
  width: 38px;
  height: 38px;
  padding: 0;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 8px;
  background: rgba(22, 29, 43, 0.85);
  color: #f3f4f6;
  font-size: 24px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;
  z-index: 10;
}

.image-viewer-close:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: scale(1.05);
}

.image-viewer-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  max-width: 100%;
}

.image-viewer-subtitle {
  max-width: 90vw;
  margin: 0;
  overflow: hidden;
  color: #9ca3af;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.image-viewer-actions {
  display: flex;
  gap: 12px;
}

.action-btn {
  padding: 6px 14px;
  font-size: 12px;
  color: #e5e7eb;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 6px;
  text-decoration: none;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.16);
}

.action-btn.primary {
  background: rgba(56, 189, 248, 0.2);
  border-color: rgba(56, 189, 248, 0.4);
  color: #38bdf8;
}

.action-btn.primary:hover {
  background: rgba(56, 189, 248, 0.3);
}

@media (max-width: 640px) {
  .image-viewer-layer {
    padding: 16px;
  }
}
</style>
