<script setup>
import { computed } from "vue";
import { usePwa } from "../pwa";

const { canInstall, updateAvailable, isOffline, install, update } = usePwa();
const message = computed(() => {
  if (updateAvailable.value) return "发现新版本";
  if (isOffline.value) return "当前离线";
  return "可安装到主屏幕";
});
</script>

<template>
  <aside v-if="canInstall || updateAvailable || isOffline" class="pwa-controls" aria-live="polite">
    <span>{{ message }}</span>
    <button v-if="canInstall" type="button" @click="install">安装</button>
    <button v-if="updateAvailable" type="button" @click="update">更新</button>
  </aside>
</template>

<style scoped>
.pwa-controls {
  position: fixed;
  z-index: 100;
  right: max(16px, env(safe-area-inset-right));
  bottom: max(16px, env(safe-area-inset-bottom));
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: calc(100vw - 32px);
  padding: 10px 12px;
  color: #f7f5ef;
  background: #14332a;
  border: 1px solid rgba(247, 245, 239, 0.25);
  border-radius: 6px;
  box-shadow: 0 8px 24px rgba(18, 36, 29, 0.2);
  font-size: 13px;
}

button {
  min-height: 32px;
  padding: 0 10px;
  color: #14332a;
  background: #dcecc8;
  border: 0;
  border-radius: 4px;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

@media (min-width: 861px) {
  .pwa-controls { display: none; }
}
</style>
