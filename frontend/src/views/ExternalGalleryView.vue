<script setup>
import { computed, onMounted, ref } from "vue";
import { apiUrl, request } from "../api/http";

const loading = ref(false);
const error = ref("");
const gallery = ref({ total: 0, truncated: false, directories: [] });
const selected = ref(null);

const groups = computed(() => gallery.value.directories || []);

function imageUrl(item) {
  return apiUrl(item.url);
}

async function loadGallery() {
  loading.value = true;
  error.value = "";
  try {
    gallery.value = await request("/api/external-gallery/");
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
        <p v-if="!loading" class="muted">{{ gallery.total }} 张图片</p>
      </div>
      <button class="ghost" type="button" :disabled="loading" @click="loadGallery">
        {{ loading ? "读取中…" : "刷新" }}
      </button>
    </header>

    <p v-if="error" class="err">{{ error }}</p>
    <p v-else-if="gallery.truncated" class="notice">图片数量达到配置上限，当前仅展示部分内容。</p>

    <section v-if="!loading && !error && !groups.length" class="gallery-empty">
      目标目录及其子目录中没有可展示的图片。
    </section>

    <section v-for="group in groups" :key="group.path || '__root__'" class="directory-group">
      <h2>{{ group.path || "根目录" }}</h2>
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
.notice { margin: 18px 0 0; color: var(--warn); font-size: 13px; }
.gallery-empty { display: grid; min-height: 42vh; place-items: center; color: var(--muted); border-bottom: 1px solid var(--border-light); }
.directory-group { margin-top: 28px; }
.directory-group h2 { margin: 0 0 12px; color: var(--muted); font-size: 14px; font-weight: 600; }
.image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
.image-tile { display: grid; min-width: 0; padding: 0; overflow: hidden; border: 1px solid var(--border-light); border-radius: 5px; background: var(--card); text-align: left; }
.image-tile:hover { border-color: var(--secondary); background: var(--card); transform: none; }
.image-tile:focus-visible { outline: 2px solid var(--secondary); outline-offset: 2px; }
.image-tile img { width: 100%; aspect-ratio: 1 / 1; display: block; object-fit: cover; background: #0b0e0b; }
.image-tile span { overflow: hidden; padding: 8px 9px; color: var(--muted); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.preview-layer { position: fixed; z-index: 10; inset: 0; display: grid; grid-template-rows: minmax(0, 1fr) auto; gap: 10px; padding: 28px; background: rgba(0, 0, 0, 0.88); }
.preview-layer img { min-width: 0; min-height: 0; width: 100%; height: 100%; object-fit: contain; }
.preview-layer p { max-width: 100%; margin: 0; overflow: hidden; color: var(--muted); font-family: var(--font-mono); font-size: 12px; text-align: center; text-overflow: ellipsis; white-space: nowrap; }
.preview-close { position: absolute; top: 14px; right: 16px; width: 36px; height: 36px; padding: 0; border: 1px solid var(--border-light); border-radius: 5px; background: var(--card); color: var(--text); font-size: 26px; line-height: 1; }
.preview-close:hover { background: var(--bg-2); transform: none; }
@media (max-width: 640px) { .external-gallery-page { padding: 18px; } .image-grid { grid-template-columns: repeat(auto-fill, minmax(124px, 1fr)); gap: 8px; } .preview-layer { padding: 18px; } }
</style>
