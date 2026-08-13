<script setup>
import { computed, onBeforeUnmount, ref } from "vue";
import { apiUrl, request } from "../api/http";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const prompt = ref("");
const duration = ref(8);
const aspectRatio = ref("16:9");
const resolution = ref("720p");
const firstFrame = ref("");
const referenceImages = ref([]);
const error = ref("");
const requestId = ref("");
const progress = ref(null);
const status = ref("");
const video = ref(null);
const submitting = ref(false);
const polling = ref(false);
let pollTimer = null;
let pollStartedAt = 0;

const canSubmit = computed(() => !!prompt.value.trim() && !submitting.value && !polling.value);
const progressLabel = computed(() => {
  if (progress.value == null) return "正在创建任务";
  return `生成中 ${Math.min(100, Math.max(0, Number(progress.value) || 0))}%`;
});

function stopPolling() {
  if (pollTimer) window.clearTimeout(pollTimer);
  pollTimer = null;
  polling.value = false;
}

function resetResult() {
  stopPolling();
  error.value = "";
  requestId.value = "";
  progress.value = null;
  status.value = "";
  video.value = null;
}

function videoContentUrl(id, download = false) {
  const params = new URLSearchParams();
  if (download) params.set("download", "true");
  const query = params.toString();
  return apiUrl(`/v1/videos/${encodeURIComponent(id)}/content${query ? `?${query}` : ""}`);
}

function readImage(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("读取图片失败"));
    reader.readAsDataURL(file);
  });
}

async function selectFirstFrame(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  if (!file.type.startsWith("image/") || file.size > 8 * 1024 * 1024) {
    error.value = "首帧图片必须是 8MB 以内的图片文件";
    return;
  }
  try {
    firstFrame.value = await readImage(file);
    error.value = "";
  } catch (e) {
    error.value = e.message || String(e);
  }
}

async function selectReferences(event) {
  const files = Array.from(event.target.files || []).slice(0, 4);
  event.target.value = "";
  if (!files.length) return;
  if (files.some((file) => !file.type.startsWith("image/") || file.size > 8 * 1024 * 1024)) {
    error.value = "参考图片必须是 8MB 以内的图片文件";
    return;
  }
  try {
    referenceImages.value = await Promise.all(files.map(readImage));
    error.value = "";
  } catch (e) {
    error.value = e.message || String(e);
  }
}

async function pollStatus() {
  if (!polling.value || !requestId.value) return;
  const pollingRequestId = requestId.value;
  try {
    const data = await request(`/v1/videos/${encodeURIComponent(pollingRequestId)}`, {
      token: auth.userToken,
    });
    if (!polling.value || requestId.value !== pollingRequestId) return;
    status.value = data.status || "";
    progress.value = data.progress;
    if (data.status === "done" && Number(data.progress) === 100 && data.video?.url) {
      video.value = {
        ...data.video,
        url: videoContentUrl(pollingRequestId),
        downloadUrl: videoContentUrl(pollingRequestId, true),
      };
      stopPolling();
      return;
    }
    if (["failed", "cancelled", "canceled"].includes(String(data.status).toLowerCase())) {
      error.value = "视频生成失败，请调整参数后重试";
      stopPolling();
      return;
    }
    if (Date.now() - pollStartedAt >= 10 * 60 * 1000) {
      error.value = "视频生成等待超时，请稍后重新提交";
      stopPolling();
      return;
    }
    pollTimer = window.setTimeout(pollStatus, 3000);
  } catch (e) {
    error.value = e.message || String(e);
    stopPolling();
  }
}

async function generate() {
  if (!canSubmit.value) return;
  resetResult();
  submitting.value = true;
  try {
    const data = await request("/v1/videos/generations", {
      method: "POST",
      token: auth.userToken,
      body: {
        prompt: prompt.value.trim(),
        duration: Number(duration.value),
        aspect_ratio: aspectRatio.value,
        resolution: resolution.value,
        image: firstFrame.value || undefined,
        reference_images: referenceImages.value.length ? referenceImages.value : undefined,
      },
    });
    requestId.value = data.request_id;
    pollStartedAt = Date.now();
    polling.value = true;
    await pollStatus();
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    submitting.value = false;
  }
}

onBeforeUnmount(stopPolling);
</script>

<template>
  <main class="video-page">
    <header class="video-header">
      <div>
        <h1>视频生成</h1>
        <p class="muted">任务和视频仅在当前页面使用，不保存到历史记录。</p>
      </div>
    </header>

    <section class="video-workspace">
      <div class="video-form">
        <div class="field">
          <label for="video-prompt">视频描述</label>
          <textarea id="video-prompt" v-model="prompt" :disabled="polling" placeholder="描述画面、运动和镜头语言" rows="6" />
        </div>
        <div class="video-options">
          <div class="field">
            <label>时长（秒）</label>
            <select v-model.number="duration" :disabled="polling">
              <option :value="6">6 秒</option>
              <option :value="8">8 秒</option>
              <option :value="10">10 秒</option>
              <option :value="15">15 秒</option>
            </select>
          </div>
          <div class="field">
            <label>画面比例</label>
            <select v-model="aspectRatio" :disabled="polling">
              <option value="16:9">16:9</option>
              <option value="9:16">9:16</option>
              <option value="1:1">1:1</option>
            </select>
          </div>
          <div class="field">
            <label>分辨率</label>
            <select v-model="resolution" :disabled="polling">
              <option value="420p">420p</option>
              <option value="720p">720p</option>
            </select>
          </div>
        </div>
        <div class="upload-row">
          <label class="upload-control">
            <span>首帧图片（可选）</span>
            <input :disabled="polling" type="file" accept="image/*" @change="selectFirstFrame" />
          </label>
          <label class="upload-control">
            <span>参考图片（可选，最多 4 张）</span>
            <input :disabled="polling" type="file" accept="image/*" multiple @change="selectReferences" />
          </label>
        </div>
        <div v-if="firstFrame || referenceImages.length" class="image-previews">
          <img v-if="firstFrame" :src="firstFrame" alt="首帧预览" />
          <img v-for="(image, index) in referenceImages" :key="image" :src="image" :alt="`参考图片 ${index + 1}`" />
        </div>
        <div v-if="error" class="err">{{ error }}</div>
        <div class="video-actions">
          <button class="primary" type="button" :disabled="!canSubmit" @click="generate">
            {{ submitting ? "提交中…" : polling ? progressLabel : "生成视频" }}
          </button>
          <button v-if="video || error" class="ghost" type="button" @click="resetResult">清除结果</button>
        </div>
      </div>

      <div class="video-result" :class="{ active: video }">
        <video v-if="video?.url" :src="video.url" controls playsinline />
        <div v-else class="video-placeholder">
          <strong>{{ polling ? progressLabel : "等待生成" }}</strong>
          <span v-if="requestId" class="mono">任务 {{ requestId }}</span>
          <span v-else class="muted">提交任务后将在此显示视频</span>
        </div>
        <div v-if="video?.url" class="video-tools">
          <a class="primary download-link" :href="video.downloadUrl" :download="`video-${requestId}.mp4`">下载视频</a>
          <a class="ghost download-link" :href="video.url" target="_blank" rel="noopener">打开视频</a>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.video-page { min-height: 100vh; padding: 28px; display: flex; flex-direction: column; background: var(--bg); }
.video-header, .video-workspace { width: 100%; max-width: none; margin: 0; }
.video-header { display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; padding-bottom: 26px; border-bottom: 1px solid var(--border-light); }
.video-header h1 { margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }
.video-header p { margin: 0; }
.video-workspace { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(420px, 0.9fr); gap: 28px; padding-top: 28px; }
.video-form, .video-result { padding: 22px; border: 1px solid var(--border-light); border-radius: 8px; background: var(--glass-bg); box-shadow: var(--shadow); }
.video-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.upload-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 4px 0 16px; }
.upload-control { display: grid; gap: 8px; font-size: 13px; color: var(--muted); }
.upload-control input { padding: 8px; font-size: 12px; }
.image-previews { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 16px; }
.image-previews img { width: 72px; height: 72px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border-light); }
.video-actions { display: flex; align-items: center; gap: 10px; margin-top: 18px; }
.video-result { min-height: 0; display: flex; flex-direction: column; justify-content: center; gap: 16px; }
.video-result video { width: 100%; max-height: 480px; background: #000; border-radius: 4px; }
.video-placeholder { min-height: 250px; display: grid; place-content: center; gap: 10px; text-align: center; border: 1px dashed var(--border-light); color: var(--text); }
.video-tools { display: flex; gap: 10px; align-items: center; }
.download-link { display: inline-flex; align-items: center; text-decoration: none; }
.download-link.primary { background: var(--primary); color: #17200f; border-radius: 6px; padding: 10px 16px; font-family: var(--font-body); font-size: 14px; font-weight: 700; }
@media (max-width: 760px) { .video-page { padding: 18px; } .video-workspace { grid-template-columns: 1fr; } .video-options, .upload-row { grid-template-columns: 1fr; } .video-header { align-items: stretch; flex-direction: column; } }
</style>
