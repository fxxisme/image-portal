<script setup>
import { computed, onMounted, ref } from "vue";
import { apiUrl, request } from "../api/http";

const loading = ref(false);
const error = ref("");
const items = ref([]);
const nextCursor = ref(null);
const selected = ref(null);

const groups = computed(() => {
  const byDate = new Map();
  for (const item of items.value) {
    const group = byDate.get(item.date) || { date: item.date, items: [] };
    group.items.push(item);
    byDate.set(item.date, group);
  }
  return [...byDate.values()];
});

function imageUrl(item) {
  return apiUrl(item.url);
}

async function loadGallery(append = false) {
  if (loading.value || (append && !nextCursor.value)) return;
  loading.value = true;
  error.value = "";
  try {
    const query = append ? `?cursor=${encodeURIComponent(nextCursor.value)}` : "";
    const data = await request(`/api/external-gallery/${query}`);
    items.value = append ? [...items.value, ...(data.items || [])] : (data.items || []);
    nextCursor.value = data.next_cursor || null;
  } catch (err) {
    error.value = err.message || String(err);
  } finally {
    loading.value = false;
  }
}

function openImage(item) {
  selected.value = item;
}

function closeImage() {
  selected.value = null;
}

onMounted(loadGallery);
</script>

<template>
  <main class="external-gallery-page">
    <header class="gallery-header">
      <div>
        <h1>外部图库</h1>
        <p v-if="!loading" class="muted">已加载 {{ items.length }} 张图片</p>
      </div>
      <button class="ghost" type="button" :disabled="loading" @click="loadGallery">
        {{ loading ? "读取中…" : "刷新" }}
      </button>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <section v-if="!loading && !error && !groups.length" class="gallery-empty">
      未找到符合年/月/日目录结构的图片。
    </section>

    <section v-for="group in groups" :key="group.date" class="directory-group">
      <h2>{{ group.date }}</h2>
      <div class="image-grid">
        <button
          v-for="item in group.items"
          :key="item.path"
          class="image-tile"
          type="button"
          :title="item.name"
          @click="openImage(item)"
        >
          <img :src="imageUrl(item)" :alt="item.name" loading="lazy" />
          <span>{{ item.name }}</span>
        </button>
      </div>
    </section>

    <div v-if="nextCursor && !error" class="gallery-more">
      <button class="ghost" type="button" :disabled="loading" @click="loadGallery(true)">
        {{ loading ? "读取中…" : "加载更早图片" }}
      </button>
    </div>

    <div v-if="selected" class="preview-layer" role="dialog" aria-modal="true" :aria-label="selected.name" @click.self="closeImage">
      <button class="preview-close" type="button" aria-label="关闭预览" @click="closeImage">×</button>
      <img :src="imageUrl(selected)" :alt="selected.name" />
      <p>{{ selected.path }}</p>
    </div>
  </main>
</template>

<style scoped>
.external-gallery-page { min-height: 100vh; padding: 28px; background: var(--bg); }
.gallery-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding-bottom: 20px; border-bottom: 1px solid var(--border-light); }
.gallery-header h1 { margin: 0 0 6px; font-size: 28px; letter-spacing: 0; }
.gallery-header p { margin: 0; }
.gallery-empty { display: grid; min-height: 42vh; place-items: center; color: var(--muted); border-bottom: 1px solid var(--border-light); }
.directory-group { margin-top: 28px; }
.directory-group h2 { margin: 0 0 12px; color: var(--muted); font-size: 14px; font-weight: 600; }
.image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
.image-tile { display: grid; min-width: 0; padding: 0; overflow: hidden; border: 1px solid var(--border-light); border-radius: 5px; background: var(--card); text-align: left; }
.image-tile:hover { border-color: var(--secondary); background: var(--card); transform: none; }
.image-tile:focus-visible { outline: 2px solid var(--secondary); outline-offset: 2px; }
.image-tile img { width: 100%; aspect-ratio: 1 / 1; display: block; object-fit: cover; background: #0b0e0b; }
.image-tile span { overflow: hidden; padding: 8px 9px; color: var(--muted); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.gallery-more { display: flex; justify-content: center; margin: 28px 0 12px; }
.preview-layer { position: fixed; z-index: 10; inset: 0; display: grid; grid-template-rows: minmax(0, 1fr) auto; gap: 10px; padding: 28px; background: rgba(0, 0, 0, 0.88); }
.preview-layer img { min-width: 0; min-height: 0; width: 100%; height: 100%; object-fit: contain; }
.preview-layer p { max-width: 100%; margin: 0; overflow: hidden; color: var(--muted); font-family: var(--font-mono); font-size: 12px; text-align: center; text-overflow: ellipsis; white-space: nowrap; }
.preview-close { position: absolute; top: 14px; right: 16px; width: 36px; height: 36px; padding: 0; border: 1px solid var(--border-light); border-radius: 5px; background: var(--card); color: var(--text); font-size: 26px; line-height: 1; }
.preview-close:hover { background: var(--bg-2); transform: none; }
@media (max-width: 640px) { .external-gallery-page { padding: 18px; } .image-grid { grid-template-columns: repeat(auto-fill, minmax(124px, 1fr)); gap: 8px; } .preview-layer { padding: 18px; } }
</style>
