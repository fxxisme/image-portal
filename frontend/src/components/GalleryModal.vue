<script setup>
import { onMounted, ref, watch } from "vue";
import { request } from "../api/http";
import { useAuthStore } from "../stores/auth";

const props = defineProps({
  open: { type: Boolean, default: false },
});
const emit = defineEmits(["close", "use-edit"]);

const auth = useAuthStore();
const items = ref([]);
const total = ref(0);
const loading = ref(false);
const loadingMore = ref(false);
const error = ref("");
const limit = 48;

async function load(reset = true) {
  if (!props.open) return;
  if (reset) {
    loading.value = true;
    items.value = [];
  } else {
    loadingMore.value = true;
  }
  error.value = "";
  try {
    const offset = reset ? 0 : items.value.length;
    const data = await request(`/api/gallery/?offset=${offset}&limit=${limit}`, {
      token: auth.userToken,
    });
    total.value = data.total;
    items.value = reset ? data.items : items.value.concat(data.items);
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    loading.value = false;
    loadingMore.value = false;
  }
}

async function removeItem(it) {
  if (!window.confirm("从我的图库删除这张图？（不影响对话历史）")) return;
  try {
    await request(`/api/gallery/${it.id}`, {
      method: "DELETE",
      token: auth.userToken,
    });
    items.value = items.value.filter((x) => x.id !== it.id);
    total.value = Math.max(0, total.value - 1);
  } catch (e) {
    error.value = e.message || String(e);
  }
}

function onBackdrop(e) {
  if (e.target === e.currentTarget) emit("close");
}

function onKey(e) {
  if (e.key === "Escape") emit("close");
}

function retryImage(event) {
  const image = event.currentTarget;
  const retries = Number(image.dataset.retries || "0");
  if (retries >= 1) return;
  image.dataset.retries = String(retries + 1);
  window.setTimeout(() => {
    const separator = image.src.includes("?") ? "&" : "?";
    image.src = `${image.src}${separator}retry=${Date.now()}`;
  }, 800);
}

watch(
  () => props.open,
  (v) => {
    if (v) {
      load(true);
      window.addEventListener("keydown", onKey);
    } else {
      window.removeEventListener("keydown", onKey);
    }
  }
);

onMounted(() => {
  if (props.open) load(true);
});
</script>

<template>
  <div v-if="open" class="overlay" @click="onBackdrop">
    <div class="panel glass-panel" role="dialog" aria-modal="true" aria-label="我的图库">
      <header class="head">
        <div>
          <div class="h-title">我的图库</div>
          <div class="muted tiny">共 {{ total }} 张 · 已持久化保存</div>
        </div>
        <div class="head-btns">
          <button class="ghost" type="button" :disabled="loading" @click="load(true)">刷新</button>
          <button class="ghost" type="button" @click="emit('close')">关闭</button>
        </div>
      </header>

      <div v-if="error" class="err" style="margin:10px 16px 0">{{ error }}</div>

      <div class="body">
        <div v-if="loading" class="center muted">加载中…</div>
        <div v-else-if="!items.length" class="center muted">还没有生成过的图片</div>
        <div v-else class="grid">
          <div v-for="it in items" :key="it.id" class="cell">
            <a :href="it.public_url" target="_blank" rel="noopener">
              <img :src="it.public_url" :alt="it.prompt || 'image'" loading="lazy" @error="retryImage" />
            </a>
            <div class="cap">
              <div class="prompt" :title="it.prompt">{{ it.prompt || "（无描述）" }}</div>
              <div class="muted tiny">
                {{ it.action === "edit" ? "改图" : "生图" }} ·
                {{ new Date(it.created_at).toLocaleString() }}
              </div>
              <div class="acts">
                <button class="success" type="button" @click="emit('use-edit', it.public_url)">
                  改图
                </button>
                <button class="ghost" type="button" @click="removeItem(it)">删除</button>
              </div>
            </div>
          </div>
        </div>
        <div v-if="items.length < total" class="more">
          <button class="ghost" type="button" :disabled="loadingMore" @click="load(false)">
            {{ loadingMore ? "加载中…" : "加载更多" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(6, 14, 32, 0.65);
  backdrop-filter: blur(6px);
  display: grid;
  place-items: center;
  padding: 16px;
}
.panel {
  width: min(960px, 100%);
  max-height: min(88vh, 900px);
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
  border-radius: 1.25rem;
}
.head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light);
}
.head-btns {
  display: flex;
  gap: 8px;
}
.h-title {
  font-weight: 700;
  font-size: 17px;
  font-family: var(--font-display);
}
.tiny {
  font-size: 12px;
  margin-top: 2px;
}
.body {
  overflow: auto;
  padding: 18px;
  flex: 1;
}
.center {
  text-align: center;
  padding: 48px 16px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 14px;
}
.cell {
  border: 1px solid var(--border-light);
  border-radius: 0.75rem;
  overflow: hidden;
  background: rgba(12, 18, 36, 0.5);
  transition: border-color 0.2s;
}
.cell:hover {
  border-color: var(--primary-2);
}
.cell img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  background: #060e20;
}
.cap {
  padding: 10px 12px 12px;
}
.prompt {
  font-size: 12px;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 2.7em;
}
.acts {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.acts button {
  padding: 6px 10px;
  font-size: 12px;
}
.more {
  text-align: center;
  margin-top: 18px;
}
</style>
