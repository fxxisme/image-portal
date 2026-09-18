<script setup>
import { computed, onMounted, ref } from "vue";
import { apiUrl, request } from "../api/http";
import ImageViewer from "../components/ImageViewer.vue";

const loading = ref(false);
const error = ref("");
const items = ref([]);
const nextCursor = ref(null);
const selected = ref(null);
const loadedMap = ref(new Map());
const errorMap = ref(new Map());

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

function handleImageLoad(path) {
  loadedMap.value.set(path, true);
}

function handleImageError(path) {
  errorMap.value.set(path, true);
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

onMounted(() => {
  loadGallery();
});
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
          <div class="image-wrapper">
            <div v-if="!loadedMap.get(item.path) && !errorMap.get(item.path)" class="skeleton-placeholder"></div>
            <div v-if="errorMap.get(item.path)" class="error-placeholder">加载失败</div>
            <img
              v-show="!errorMap.get(item.path)"
              :src="imageUrl(item)"
              :alt="item.name"
              loading="lazy"
              :class="{ loaded: loadedMap.get(item.path) }"
              @load="handleImageLoad(item.path)"
              @error="handleImageError(item.path)"
            />
          </div>
          <span>{{ item.name }}</span>
        </button>
      </div>
    </section>

    <div v-if="nextCursor && !error" class="gallery-more">
      <button class="ghost" type="button" :disabled="loading" @click="loadGallery(true)">
        {{ loading ? "读取中…" : "加载更早图片" }}
      </button>
    </div>

    <ImageViewer
      v-if="selected"
      :url="imageUrl(selected)"
      :alt="selected.name"
      :subtitle="selected.path"
      @close="closeImage"
    />
  </main>
</template>

<style scoped>
.external-gallery-page { min-height: 100vh; padding: 28px 36px; background: var(--bg); max-width: 1600px; margin: 0 auto; }
.gallery-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding-bottom: 20px; border-bottom: 1px solid var(--border); }
.gallery-header h1 { margin: 0 0 6px; font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }
.gallery-header p { margin: 0; color: var(--muted); }
.gallery-empty { display: grid; min-height: 42vh; place-items: center; color: var(--muted); border-bottom: 1px solid var(--border); }
.directory-group { margin-top: 32px; }
.directory-group h2 { margin: 0 0 14px; color: var(--muted); font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; font-family: var(--font-mono); }
.image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); gap: 14px; }
.image-tile { display: grid; min-width: 0; padding: 0; overflow: hidden; border: 1px solid var(--border); border-radius: 10px; background: var(--card); text-align: left; transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1); box-shadow: var(--shadow-sm); cursor: pointer; }
.image-tile:hover { border-color: rgba(56, 189, 248, 0.4); background: var(--card-hover); transform: translateY(-2px); box-shadow: var(--shadow); }
.image-tile:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.image-wrapper { position: relative; width: 100%; aspect-ratio: 1 / 1; overflow: hidden; background: #070a10; }
.skeleton-placeholder { position: absolute; inset: 0; background: linear-gradient(90deg, #111827 25%, #1f2937 50%, #111827 75%); background-size: 200% 100%; animation: shimmer 1.5s infinite; }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
.error-placeholder { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 11px; color: var(--muted); background: #111827; }
.image-tile img { width: 100%; height: 100%; display: block; object-fit: cover; opacity: 0; transition: opacity 0.3s ease; }
.image-tile img.loaded { opacity: 1; }
.image-tile span { overflow: hidden; padding: 9px 12px; color: var(--muted); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.gallery-more { display: flex; justify-content: center; margin: 32px 0 16px; }
@media (max-width: 640px) { .external-gallery-page { padding: 18px; } .image-grid { grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 10px; } }
</style>
