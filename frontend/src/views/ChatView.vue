<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { request } from "../api/http";
import ChatSidebar from "../components/ChatSidebar.vue";
import ImageViewer from "../components/ImageViewer.vue";
import LoginModal from "../components/LoginModal.vue";
import { useAuthStore } from "../stores/auth";
import { formatChinaDateTime } from "../utils/datetime";
import {
  createLocalConversation,
  loadLocalConversations,
  saveLocalConversations,
} from "../utils/local-conversations";

const auth = useAuthStore();
const router = useRouter();
const PREFERENCES_KEY = "image-portal:generation-preferences";

function loadGenerationPreferences() {
  try {
    const value = JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) || "{}");
    return value && typeof value === "object" ? value : {};
  } catch {
    return {};
  }
}

function saveGenerationPreferences(preferences) {
  try {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
  } catch {
    // 本地存储不可用时仍保持当前会话内的选择。
  }
}

const savedPreferences = loadGenerationPreferences();

const conversations = ref([]);
const currentId = ref(null);
const messages = ref([]);
const prompt = ref("");
const sending = ref(false);
const elapsedSeconds = ref(0);
let timer = null;
const lastFailedPrompt = ref("");
const error = ref("");
const editImageUrls = ref([]);
const fileInput = ref(null);
const scroller = ref(null);
const previewImage = ref(null);
const generationMode = ref(
  savedPreferences.mode === "image-to-image" ? "image-to-image" : "text-to-image",
);
const textModel = ref(typeof savedPreferences.textModel === "string" ? savedPreferences.textModel : "");
const editModel = ref(typeof savedPreferences.editModel === "string" ? savedPreferences.editModel : "");
const fallbackTextToImageModels = ["gpt-image-2", "grok-imagine-image"];
const fallbackImageToImageModels = ["gpt-image-2"];

const isEditMode = computed(() => generationMode.value === "image-to-image");
const textToImageModels = computed(() => {
  const models = auth.me?.text_to_image_models;
  return Array.isArray(models) && models.length ? models : fallbackTextToImageModels;
});
const imageToImageModels = computed(() => {
  const models = auth.me?.image_to_image_models;
  return Array.isArray(models) && models.length ? models : fallbackImageToImageModels;
});
const selectedModel = computed({
  get: () => (isEditMode.value ? editModel.value : textModel.value),
  set: (value) => {
    const options = isEditMode.value ? imageToImageModels.value : textToImageModels.value;
    if (!options.includes(value)) return;
    if (isEditMode.value) editModel.value = value;
    else textModel.value = value;
  },
});
const modelOptions = computed(() =>
  isEditMode.value ? imageToImageModels.value : textToImageModels.value,
);
const canSend = computed(
  () =>
    !!prompt.value.trim() &&
    !sending.value &&
    (!isEditMode.value || editImageUrls.value.length > 0),
);

const quotaText = computed(() => {
  const rem = auth.me?.quota_remaining;
  const total = auth.me?.quota_total;
  if (rem == null || total == null) return "额度加载中…";
  return `已用 ${auth.me.quota_used ?? total - rem} / 共 ${total} 张 · 剩余 ${rem} 张`;
});

const showZeroWarning = computed(
  () => auth.me?.quota_remaining != null && Number(auth.me.quota_remaining) === 0,
);

function syncModelSelections() {
  if (!textToImageModels.value.includes(textModel.value)) {
    textModel.value = textToImageModels.value.includes(auth.me?.default_model)
      ? auth.me.default_model
      : textToImageModels.value[0] || "";
  }
  if (!imageToImageModels.value.includes(editModel.value)) {
    editModel.value = imageToImageModels.value[0] || "";
  }
}

watch([generationMode, textModel, editModel], () => {
  saveGenerationPreferences({
    mode: generationMode.value,
    textModel: textModel.value,
    editModel: editModel.value,
  });
});

async function ensureMe() {
  try {
    await auth.fetchMe();
    syncModelSelections();
  } catch (e) {
    if (e.status === 401) {
      auth.logoutUser();
      router.push({ name: "login" });
      return;
    }
    error.value = e.message || String(e);
  }
}

function restoreBrowserConversations() {
  conversations.value = loadLocalConversations();
  if (conversations.value.length) {
    currentId.value = conversations.value[0].id;
    messages.value = conversations.value[0].messages || [];
  }
}

function saveBrowserConversations() {
  saveLocalConversations(conversations.value);
}

function findLocalConversation(id) {
  return conversations.value.find((conversation) => conversation.id === id);
}

function persistConversation(id, nextMessages) {
  const target = findLocalConversation(id);
  if (!target) return;
  target.messages = nextMessages;
  target.updated_at = new Date().toISOString();
  saveBrowserConversations();
}

function createConversation() {
  const item = createLocalConversation();
  conversations.value.unshift(item);
  currentId.value = item.id;
  messages.value = item.messages;
  saveBrowserConversations();
  clearEditImage({ resetMode: false });
}

function removeConversation(id) {
  if (!window.confirm("删除本地对话及历史？后台生成记录会保留。")) return;
  conversations.value = conversations.value.filter((conversation) => conversation.id !== id);
  if (currentId.value === id) {
    const next = conversations.value[0];
    currentId.value = next?.id || null;
    messages.value = next?.messages || [];
  }
  saveBrowserConversations();
}

function selectConversation(id) {
  const conversation = findLocalConversation(id);
  if (!conversation) return;
  currentId.value = conversation.id;
  messages.value = conversation.messages;
  clearEditImage({ resetMode: false });
  nextTick(scrollBottom);
}

function clearEditImage({ resetMode = true } = {}) {
  editImageUrls.value = [];
  if (fileInput.value) fileInput.value.value = "";
  if (resetMode) generationMode.value = "text-to-image";
}

function setGenerationMode(mode) {
  generationMode.value = mode;
  if (mode === "text-to-image") clearEditImage({ resetMode: false });
}

function pickFile() {
  fileInput.value?.click();
}

function readImageAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("读取图片失败"));
    reader.readAsDataURL(file);
  });
}

async function addEditImages(files) {
  if (!files.length) return;
  if (files.some((file) => !file.type.startsWith("image/"))) {
    error.value = "请上传图片文件";
    return;
  }
  if (files.some((file) => file.size > 8 * 1024 * 1024)) {
    error.value = "图片请小于 8MB";
    return;
  }
  const remaining = 4 - editImageUrls.value.length;
  if (remaining <= 0) {
    error.value = "最多上传 4 张图片";
    return;
  }
  error.value = "";
  try {
    const imageUrls = await Promise.all(files.slice(0, remaining).map(readImageAsDataUrl));
    editImageUrls.value.push(...imageUrls);
    generationMode.value = "image-to-image";
    if (files.length > remaining) error.value = "最多上传 4 张图片";
  } catch {
    error.value = "读取图片失败";
  } finally {
    if (fileInput.value) fileInput.value.value = "";
  }
}

function onFileChange(ev) {
  addEditImages(Array.from(ev.target.files || []));
}

function onPromptPaste(ev) {
  if (!isEditMode.value) return;
  const files = Array.from(ev.clipboardData?.items || [])
    .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter(Boolean);
  if (!files.length) return;

  ev.preventDefault();
  addEditImages(files);
}

function removeEditImage(index) {
  editImageUrls.value.splice(index, 1);
}

function scrollBottom() {
  const el = scroller.value;
  if (el) el.scrollTop = el.scrollHeight;
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

function openImagePreview(url, alt) {
  previewImage.value = { url, alt };
}

function closeImagePreview() {
  previewImage.value = null;
}

function onKeydown(event) {
  if (event.key === "Escape" && previewImage.value) {
    closeImagePreview();
  }
}

async function send() {
  const text = prompt.value.trim();
  if (!text || sending.value) return;
  if (isEditMode.value && !editImageUrls.value.length) {
    error.value = "请先上传参考图，再提交改图";
    return;
  }
  if (!currentId.value) createConversation();

  const localConversationId = currentId.value;
  const localMessages = messages.value;
  const backendConversationId =
    findLocalConversation(localConversationId)?.backend_id || localConversationId;
  const apiKeyId = auth.me?.id || "anonymous";

  sending.value = true;
  elapsedSeconds.value = 0;
  if (timer) clearInterval(timer);
  timer = setInterval(() => {
    elapsedSeconds.value++;
  }, 1000);
  error.value = "";
  try {
    const optimisticUserMsg = {
      id: `${apiKeyId}-prompt-${Date.now()}`,
      role: "user",
      content: text,
      ref_image_url: editImageUrls.value[0] || null,
      ref_image_urls: [...editImageUrls.value],
    };
    localMessages.push(optimisticUserMsg);
    persistConversation(localConversationId, localMessages);
    prompt.value = "";
    lastFailedPrompt.value = "";
    const refImages = [...editImageUrls.value];
    const requestModel = selectedModel.value || undefined;
    clearEditImage({ resetMode: false });
    await nextTick();
    if (currentId.value === localConversationId) scrollBottom();

    const bodyBase = {
      prompt: text,
      n: 1,
      model: requestModel,
      response_format: "url",
    };
    const headers = {};
    if (backendConversationId && !isNaN(Number(backendConversationId))) {
      headers["X-Conversation-Id"] = String(backendConversationId);
    }
    let data;
    if (refImages.length) {
      data = await request("/v1/images/edits", {
        method: "POST",
        token: auth.userToken,
        headers,
        body: { ...bodyBase, images: refImages.map((url) => ({ url })) },
      });
    } else {
      data = await request("/v1/images/generations", {
        method: "POST",
        token: auth.userToken,
        headers,
        body: bodyBase,
      });
    }
    localMessages.push({
      id: `${apiKeyId}-image-${Date.now()}`,
      role: "assistant",
      content: `已${refImages.length ? "编辑生成" : "生成"} ${data.data?.length || 0} 张图片`,
      image_urls: (data.data || []).map((item) => item.url).filter(Boolean),
      cost: data.data?.length || 0,
      model: requestModel,
    });
    persistConversation(localConversationId, localMessages);
    await auth.fetchMe();
    await nextTick();
    if (currentId.value === localConversationId) scrollBottom();
  } catch (e) {
    lastFailedPrompt.value = text;
    const detail = e.message || String(e);
    if (localMessages) {
      localMessages.push({
        id: "error-" + Date.now(),
        role: "assistant",
        content: "❌ 生成失败\n\n" + detail,
        cost: 0,
        failedPrompt: text,
      });
      persistConversation(localConversationId, localMessages);
    }
    error.value = e.message || String(e);
  } finally {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
    sending.value = false;
  }
}

function retryPrompt(textToRetry) {
  if (!textToRetry || sending.value) return;
  prompt.value = textToRetry;
  send();
}

function logout() {
  auth.logoutUser();
  router.push({ name: "login" });
}

onMounted(async () => {
  window.addEventListener("keydown", onKeydown);
  await ensureMe();
  restoreBrowserConversations();
  if (!conversations.value.length) {
    createConversation();
  }
  await nextTick();
  scrollBottom();
});

onBeforeUnmount(() => {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
  window.removeEventListener("keydown", onKeydown);
});

const showLoginModal = ref(false);

const handleLoginSuccess = async () => {
  showLoginModal.value = false;
  error.value = "";
  syncModelSelections();
  if (!conversations.value.length) createConversation();
  else selectConversation(currentId.value || conversations.value[0].id);
};
</script>

<template>
  <div class="shell">
    <ChatSidebar
      :conversations="conversations"
      :current-id="currentId"
      @select="selectConversation"
      @create="createConversation"
      @remove="removeConversation"
    />

    <main class="main">
      <header class="bar glass-bar">
        <div class="bar-title">
          <div class="title-kicker">创作空间</div>
          <div class="title">图像生成</div>
        </div>
        <div class="bar-actions">
          <span class="quota-status" :title="quotaText">
            <span class="quota-dot" />
            <span>剩余 <strong>{{ auth.me?.quota_remaining ?? "-" }}</strong> 张</span>
          </span>
          <span v-if="showZeroWarning" class="badge warn">剩余 0 张</span>
          <button
            v-if="showZeroWarning"
            class="ghost"
            type="button"
            @click="showLoginModal = true"
          >
            重新输入秘钥
          </button>
          <span class="user-name" v-if="auth.me?.name">{{ auth.me.name }}</span>
        </div>
      </header>

      <LoginModal
        v-if="showLoginModal"
        :show="showLoginModal"
        @close="showLoginModal = false"
        @success="handleLoginSuccess"
      />

      <div v-if="error" class="err ban">{{ error }}</div>

      <div ref="scroller" class="messages">
        <div v-if="!messages.length" class="center tip">
          <span class="empty-mark" aria-hidden="true"><i /><i /><i /></span>
          <strong>从一个画面开始</strong>
          <span>输入描述，或切换到图生图继续创作。</span>
        </div>

        <div v-for="m in messages" :key="m.id" class="msg" :class="m.role">
          <div class="bubble" :class="m.role">
            <div class="role-tag">{{ m.role === "user" ? "你" : "AI" }}</div>
            <div class="content">{{ m.content }}</div>
            <div v-if="m.failedPrompt" class="retry-action-box">
              <button class="retry-btn" type="button" :disabled="sending" @click="retryPrompt(m.failedPrompt)">
                🔄 重新尝试此生图
              </button>
            </div>

            <div v-if="m.ref_image_url && m.role === 'user'" class="ref-thumb">
              <img :src="m.ref_image_url" alt="参考图" />
            </div>

            <div v-if="m.image_urls?.length" class="imgs" :class="{ 'multiple-images': m.image_urls.length > 1 }">
              <div v-for="(url, idx) in m.image_urls" :key="url" class="img-card group">
                <button
                  class="image-preview-trigger"
                  type="button"
                  :title="`预览图片 ${idx + 1}`"
                  @click="openImagePreview(url, `生成图片 ${idx + 1}`)"
                >
                  <img :src="url" :alt="`生成图片 ${idx + 1}`" loading="lazy" @error="retryImage" />
                  <div class="image-overlay-action">
                    <span class="view-pill">点击全屏查看</span>
                  </div>
                </button>
                <div class="image-tools">
                  <span class="index-chip">{{ idx + 1 }} / {{ m.image_urls.length }}</span>
                  <div class="action-links">
                    <a :href="url" target="_blank" rel="noopener">新窗口</a>
                    <a :href="url" :download="`generated-image-${idx + 1}`" class="dl-badge">下载</a>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="m.cost" class="cost muted">消耗 {{ m.cost }} 张</div>
          </div>
        </div>

        <div v-if="sending" class="msg assistant">
          <div class="bubble assistant studio-generating-card">
            <div class="generating-header">
              <span class="pulsing-orbit"></span>
              <span class="generating-title">AI 正在绘制画面...</span>
              <span class="generating-timer">已等待 {{ elapsedSeconds }}s</span>
            </div>
            <div class="generating-skeleton shimmer"></div>
          </div>
        </div>
      </div>

      <ImageViewer
        v-if="previewImage"
        :url="previewImage.url"
        :alt="previewImage.alt"
        @close="closeImagePreview"
      />

      <div class="composer-area">
        <div class="composer-toolbar">
          <div class="composer-mode">
            <div class="mode-switch" role="group" aria-label="生成类型">
              <button
                type="button"
                class="mode-option"
                :class="{ active: generationMode === 'text-to-image' }"
                :aria-pressed="generationMode === 'text-to-image'"
                @click="setGenerationMode('text-to-image')"
              >
                文生图
              </button>
              <button
                type="button"
                class="mode-option"
                :class="{ active: generationMode === 'image-to-image' }"
                :aria-pressed="generationMode === 'image-to-image'"
                @click="setGenerationMode('image-to-image')"
              >
                图生图
              </button>
            </div>
            <label class="model-field toolbar-model">
              <span>模型</span>
              <select v-model="selectedModel" class="model-select" aria-label="生图模型">
                <option v-for="modelName in modelOptions" :key="modelName" :value="modelName">
                  {{ modelName }}
                </option>
              </select>
            </label>
          </div>
          <p class="hint">
            <span class="hint-icon">●</span>
            成功生成后扣除额度
          </p>
        </div>

        <div v-if="isEditMode && editImageUrls.length" class="edit-banner">
          <div class="edit-info">
            <div class="edit-thumbs">
              <div v-for="(imageUrl, index) in editImageUrls" :key="index" class="edit-thumb-wrap">
                <img class="edit-thumb" :src="imageUrl" :alt="`参考图 ${index + 1}`" />
                <button
                  class="edit-thumb-remove"
                  type="button"
                  title="移除图片"
                  :aria-label="`移除参考图 ${index + 1}`"
                  @click="removeEditImage(index)"
                >
                  &times;
                </button>
              </div>
            </div>
            <div>
              <strong>图生图</strong>
              <div class="muted tiny">已选择 {{ editImageUrls.length }} 张参考图</div>
            </div>
          </div>
          <button
            class="ghost clear-edit-images"
            type="button"
            title="清空参考图"
            aria-label="清空参考图"
            @click="clearEditImage"
          >
            &times;
          </button>
        </div>

        <div class="input-row glass-panel">
          <button
            v-if="isEditMode"
            class="attach-btn"
            type="button"
            :title="isEditMode ? '上传参考图' : '上传参考图并切换到图生图'"
            @click="pickFile"
          >
            <span class="attach-icon">＋</span>
          </button>
          <input
            ref="fileInput"
            type="file"
            accept="image/*"
            multiple
            class="hidden-file"
            @change="onFileChange"
          />
          <textarea
            v-model="prompt"
            :placeholder="
              isEditMode
                ? editImageUrls.length
                  ? '描述如何修改这张图…'
                  : '上传或粘贴一张或多张参考图，再描述修改方式…'
                : '描述你想生成的图片…'
            "
            @keydown.enter.exact.prevent="send"
            @paste="onPromptPaste"
            rows="1"
          />
          <button
            class="send-btn"
            type="button"
            :disabled="!canSend"
            @click="send"
          >
            <span>{{ sending ? "生成中…" : isEditMode ? "提交改图" : "生成" }}</span>
            <span class="bolt">⚡</span>
          </button>
        </div>

      </div>
    </main>
  </div>
</template>

<style scoped>
/* ========= shell & sidebar ========= */
.shell {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  width: 100%;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
  letter-spacing: 0;
}

.sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  z-index: 10;
  background: var(--sidebar);
  border-right: 1px solid var(--border);
}

.side-top {
  padding: 16px 16px 12px;
  flex-shrink: 0;
}
.brand-lockup {
  display: flex;
  align-items: center;
  gap: 11px;
}
.brand-mark,
.empty-mark {
  display: inline-grid;
  grid-template-columns: repeat(3, 5px);
  gap: 3px;
}
.brand-mark i,
.empty-mark i {
  display: block;
  width: 5px;
  height: 18px;
  background: var(--primary);
}
.brand-mark i:nth-child(2),
.empty-mark i:nth-child(2) { background: var(--secondary); height: 12px; align-self: end; }
.brand-mark i:nth-child(3),
.empty-mark i:nth-child(3) { background: var(--tertiary); height: 8px; align-self: end; }
.brand {
  background: none;
  color: var(--text);
  font-family: var(--font-body);
  font-size: 16px;
  font-weight: 700;
  -webkit-text-fill-color: currentColor;
}
.brand-caption {
  margin-top: 3px;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 9px;
  line-height: 1;
}

.new-chat-btn {
  width: calc(100% - 32px);
  min-height: 36px;
  margin: 0 16px 12px;
  padding: 7px 10px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-surface);
  color: var(--text);
  font-family: var(--font-body);
  font-size: 13px;
  font-weight: 500;
  flex-shrink: 0;
}
.new-chat-btn:hover:not(:disabled) {
  background: var(--card-hover);
  border-color: var(--border-focus);
}
.new-chat-btn:active:not(:disabled) { transform: translateY(0); }
.new-chat-icon {
  font-size: 16px;
  line-height: 1;
}

.conv-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 8px 8px;
}
.section-label {
  padding: 0 6px 6px;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 10px;
  text-transform: uppercase;
}
.conv-item {
  width: 100%;
  text-align: left;
  background: transparent;
  color: var(--text-soft);
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 8px 28px 8px 10px;
  position: relative;
  margin-bottom: 4px;
  min-height: 44px;
  transition: all 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}
.conv-item:hover {
  background: rgba(255, 255, 255, 0.03);
  color: var(--text);
}
.conv-item.active {
  background: linear-gradient(90deg, rgba(167, 139, 250, 0.08) 0%, transparent 100%);
  border-color: rgba(255, 255, 255, 0.05);
  color: var(--text);
  box-shadow: 0 1px 2px rgba(0,0,0,0.2);
}
.conv-item.active::before {
  position: absolute;
  top: 10px;
  bottom: 10px;
  left: 0;
  width: 3px;
  background: var(--primary-gradient);
  content: "";
  border-radius: 0 4px 4px 0;
}
.conv-title {
  font-size: 13px;
  font-weight: 500;
  padding-right: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-meta {
  font-size: 11px;
  color: var(--muted);
  margin-top: 3px;
}
.del {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--muted);
  font-size: 18px;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 4px;
  transition: color 0.15s;
}
.del:hover {
  background: transparent;
  color: var(--danger);
}
.empty {
  padding: 20px 8px;
  font-size: 13px;
  text-align: center;
  color: var(--muted);
}

/* ========= main ========= */
.main {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  background: var(--bg);
}

/* top bar */
.bar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  min-height: 60px;
  padding: 9px 24px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
  flex-shrink: 0;
}
.glass-bar {
  background: var(--bg);
  backdrop-filter: none;
}
.bar-title {
  display: block;
  min-width: 0;
}
.title-kicker {
  margin-bottom: 2px;
  color: var(--secondary);
  font-family: var(--font-mono);
  font-size: 10px;
}
.title {
  color: var(--text);
  font-family: var(--font-body);
  font-size: 18px;
  font-weight: 600;
}
.bar-actions {
  display: flex;
  gap: 10px;
  flex-wrap: nowrap;
  align-items: center;
  flex-shrink: 0;
}
.quota-status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--text-soft);
  font-size: 12px;
  white-space: nowrap;
}
.quota-status strong {
  color: var(--primary);
  font-family: var(--font-mono);
  font-size: 13px;
}
.quota-dot {
  width: 6px;
  height: 6px;
  background: var(--success);
  border-radius: 50%;
}
.bar-actions .badge {
  padding: 5px 10px;
  border-radius: 6px;
}
.bar-actions .ghost {
  min-height: 32px;
  padding: 6px 12px;
  border-radius: 8px;
  border-color: var(--border);
  color: var(--text-soft);
  font-size: 12px;
}
.bar-actions .ghost:hover:not(:disabled) {
  border-color: var(--border-focus);
  background: var(--bg-surface);
  color: var(--text);
}
.user-name {
  max-width: 120px;
  overflow: hidden;
  color: var(--muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ban {
  margin: 12px 24px 0;
  border-radius: 8px;
  background: var(--danger-bg);
  border-color: var(--danger-border);
  color: var(--danger);
  flex-shrink: 0;
}

/* messages */
.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px clamp(16px, 3vw, 48px);
}
.center {
  text-align: center;
  padding: 44px 16px;
}
.tip {
  display: grid;
  justify-items: center;
  max-width: 360px;
  margin: 40px auto;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
}
.tip .empty-mark { margin-bottom: 12px; }
.tip strong {
  margin-bottom: 4px;
  color: var(--text);
  font-size: 16px;
  font-weight: 600;
}

.msg {
  display: flex;
  margin-bottom: 16px;
}
.msg.user { justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }

.bubble {
  max-width: min(760px, 88%);
  border-radius: 12px;
  padding: 12px 16px;
  box-shadow: none;
}
.bubble.user {
  background: var(--bg-surface);
  border: 1px solid var(--border-light);
  border-bottom-right-radius: 4px;
}
.bubble.assistant {
  background: var(--card);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}

.role-tag {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0;
  font-weight: 500;
  color: var(--secondary);
  margin-bottom: 6px;
}
.bubble.user .role-tag { color: var(--primary); }

.content {
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  font-size: 14px;
}

.ref-thumb { margin-top: 10px; }
.ref-thumb img {
  max-width: 140px;
  max-height: 140px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--border);
}

.imgs {
  margin-top: 14px;
  display: grid;
  gap: 12px;
}
.imgs.multiple-images {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.img-card {
  position: relative;
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-2);
}
.image-preview-trigger {
  position: relative;
  display: block;
  width: 100%;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  overflow: hidden;
}
.image-overlay-action {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.4);
  opacity: 0;
  transition: opacity 0.2s ease;
}
.image-preview-trigger:hover .image-overlay-action {
  opacity: 1;
}
.view-pill {
  padding: 6px 14px;
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 9999px;
  color: #fff;
  font-size: 12px;
  font-weight: 500;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  transform: translateY(4px);
  transition: transform 0.2s ease;
}
.image-preview-trigger:hover .view-pill {
  transform: translateY(0);
}
.img-card img {
  width: 100%;
  aspect-ratio: 1 / 1;
  max-height: 56vh;
  object-fit: contain;
  background: #070a10;
  display: block;
  transition: transform 0.35s ease;
  border-radius: 8px 8px 0 0;
}
.img-card:hover img {
  transform: scale(1.015);
}
.imgs:not(.multiple-images) .img-card img { aspect-ratio: auto; }
.image-tools {
  min-height: 38px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  background: var(--bg-surface);
  border-top: 1px solid var(--border);
}
.index-chip {
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--muted);
}
.action-links { display: flex; gap: 10px; align-items: center; }
.action-links a {
  color: var(--muted);
  text-decoration: none;
  transition: color 0.15s ease;
}
.action-links a:hover { color: #fff; }
.dl-badge {
  color: var(--secondary) !important;
  background: rgba(167, 139, 250, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid rgba(167, 139, 250, 0.2);
}
.dl-badge:hover {
  background: rgba(167, 139, 250, 0.2);
}

/* Studio Generating Animation Card */
.studio-generating-card {
  width: min(420px, 100%);
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px !important;
  box-shadow: 0 4px 20px rgba(167, 139, 250, 0.08);
  border: 1px solid rgba(167, 139, 250, 0.15);
  background: linear-gradient(145deg, var(--card) 0%, rgba(167, 139, 250, 0.03) 100%);
}
.generating-header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pulsing-orbit {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--secondary);
  box-shadow: 0 0 12px var(--secondary);
  animation: pulse-ring 1.8s infinite ease-in-out;
}
@keyframes pulse-ring {
  0% { transform: scale(0.85); opacity: 0.6; }
  50% { transform: scale(1.2); opacity: 1; }
  100% { transform: scale(0.85); opacity: 0.6; }
}
.generating-title {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--text-soft);
}
.generating-timer {
  margin-left: auto;
  font-size: 12px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.retry-action-box {
  margin-top: 10px;
}
.retry-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12px;
  background: rgba(239, 68, 68, 0.12);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.retry-btn:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.4);
}
.retry-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.generating-skeleton {
  width: 100%;
  aspect-ratio: 16 / 10;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-surface);
  position: relative;
  overflow: hidden;
}
.generating-skeleton::after {
  content: "";
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0) 0%,
    rgba(255, 255, 255, 0.05) 50%,
    rgba(255, 255, 255, 0) 100%
  );
  transform: translateX(-100%);
  animation: shimmer 1.5s infinite;
}
@keyframes shimmer {
  100% { transform: translateX(100%); }
}

.cost {
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--tertiary);
}

/* ========= composer area ========= */
.composer-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 12px 24px 16px;
  border-top: 1px solid var(--border);
  background: var(--bg);
  flex-shrink: 0;
}

.composer-toolbar,
.edit-banner,
.input-row {
  width: 100%;
  max-width: 920px;
}

.composer-toolbar {
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}
.composer-mode {
  display: flex;
  align-items: center;
  gap: 12px;
}
.mode-switch {
  display: inline-flex;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--input);
}
.mode-option {
  min-width: 82px;
  padding: 7px 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.mode-option:hover { color: var(--text-soft); }
.mode-option.active {
  background: var(--bg-surface);
  color: var(--text);
  border: 1px solid var(--border-light);
}

.toolbar-model {
  display: flex;
  align-items: center;
  flex: 0 0 184px;
}
.toolbar-model > span { display: none; }
.toolbar-model .model-select {
  width: 184px;
  min-height: 38px;
  padding: 8px 26px 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-surface);
  color: var(--text-soft);
  font-family: var(--font-mono);
  font-size: 12px;
}
.toolbar-model .model-select:focus { border-color: var(--border-focus); }

.hint {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.hint-icon {
  color: var(--primary);
  font-size: 8px;
  opacity: 1;
}

.edit-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-surface);
}
.edit-info {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  color: var(--text-soft);
  font-size: 13px;
  min-width: 0;
}
.edit-info strong { color: var(--text); }
.edit-thumbs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.edit-thumb-wrap {
  position: relative;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
}
.edit-thumb {
  width: 44px;
  height: 44px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--border);
  flex-shrink: 0;
}
.edit-thumb-remove {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 20px;
  height: 20px;
  padding: 0;
  border: 1px solid var(--border-light);
  border-radius: 50%;
  background: var(--bg);
  color: var(--text);
  cursor: pointer;
  font-size: 16px;
  line-height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.clear-edit-images {
  min-width: 28px;
  padding: 2px 7px;
  border-color: transparent;
  color: var(--muted);
  font-size: 18px;
  line-height: 1;
}
.clear-edit-images:hover:not(:disabled) {
  background: transparent;
  color: var(--danger);
}
.tiny { color: var(--muted); font-size: 12px; }

.input-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 64px;
  padding: 8px 10px 8px 12px;
  border: 1px solid var(--border-light);
  border-radius: 16px;
  background: var(--input);
  box-shadow: var(--shadow-sm), var(--shadow-inner);
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.input-row:focus-within {
  border-color: rgba(167, 139, 250, 0.4);
  box-shadow: 0 0 0 1px rgba(167, 139, 250, 0.4), var(--shadow-inner);
  background: var(--bg-surface);
}

.attach-btn {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-soft);
  background: var(--bg-surface);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}
.attach-btn:hover {
  background: var(--card-hover);
  border-color: var(--border-light);
  color: var(--text);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}
.attach-btn:active { transform: translateY(0); box-shadow: none; }
.attach-icon { font-size: 18px; }

.hidden-file { display: none; }

.input-row textarea {
  flex: 1;
  min-height: 42px;
  max-height: 160px;
  padding: 8px 2px;
  border: 0;
  border-radius: 0;
  color: var(--text);
  font-size: 14px;
  line-height: 1.6;
  background: transparent;
  resize: none;
  outline: none;
}
.input-row textarea:focus {
  box-shadow: none;
  border-color: transparent;
}

.send-btn {
  flex-shrink: 0;
  min-width: 108px;
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: var(--text);
  color: var(--bg);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}
.send-btn:hover:not(:disabled) {
  background: var(--text-soft);
  opacity: 1;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(255, 255, 255, 0.15);
}
.send-btn:active:not(:disabled) { transform: translateY(0); box-shadow: none; }
.send-btn:disabled {
  background: var(--bg-surface);
  border-color: var(--border);
  color: var(--muted);
  cursor: not-allowed;
  transform: none;
}
.bolt { font-size: 14px; }

.mode-option:focus-visible,
.attach-btn:focus-visible,
.send-btn:focus-visible,
.edit-thumb-remove:focus-visible,
.clear-edit-images:focus-visible,
.new-chat-btn:focus-visible,
.conv-item:focus-visible {
  outline: 2px solid var(--border-focus);
  outline-offset: 2px;
}

/* responsive */
@media (max-width: 860px) {
  .shell {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 100dvh;
  }
  .sidebar {
    display: grid;
    grid-template-columns: 36px minmax(0, 1fr);
    gap: 8px;
    height: auto;
    max-height: none;
    padding: 6px 12px;
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }
  .side-top { display: none; }
  .new-chat-btn {
    width: 36px;
    height: 36px;
    min-height: 36px;
    margin: 0;
    padding: 0;
    border-radius: 5px;
  }
  .new-chat-icon { font-size: 22px; line-height: 1; font-weight: 400; }
  .new-chat-label { display: none; }
  .conv-list {
    display: flex;
    align-items: center;
    gap: 6px;
    height: 36px;
    overflow-x: auto;
    padding: 0;
  }
  .section-label, .conv-meta, .del { display: none; }
  .conv-item {
    flex: 0 0 auto;
    max-width: 148px;
    min-height: 32px;
    margin: 0;
    padding: 6px 10px;
  }
  .conv-title { font-size: 12px; line-height: 1.2; padding: 0; }
  .conv-item.active::before { top: auto; right: 10px; bottom: 0; left: 10px; width: auto; height: 2px; }
  .main { height: auto; min-height: calc(100dvh - 49px); }
  .bar { min-height: 54px; padding: 8px 14px; }
  .title { font-size: 17px; }
  .bar-actions { gap: 6px; }
  .user-name { display: none; }
  .messages { min-height: 42dvh; padding: 12px 14px; }
  .composer-area { padding: 8px 12px 10px; }
  .composer-toolbar {
    gap: 8px;
    flex-wrap: wrap;
  }
  .mode-switch { width: auto; }
  .composer-mode {
    width: auto;
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .hint { width: auto; }
  .input-row { gap: 8px; flex-wrap: wrap; }
  .input-row textarea { min-width: calc(100% - 50px); order: 0; }
  .toolbar-model {
    display: grid;
    flex: 1 1 170px;
    min-width: 0;
    max-width: 240px;
  }
  .toolbar-model .model-select { width: 100%; }
  .send-btn { order: 3; min-width: 94px; min-height: 40px; }
}

@media (max-width: 480px) {
  .quota-status { font-size: 11px; }
  .bar-actions .ghost { display: none; }
  .composer-toolbar { align-items: center; }
  .mode-option { min-width: 72px; }
  .edit-banner { align-items: center; }
  .imgs.multiple-images { grid-template-columns: 1fr; }
}

@media (max-width: 360px) {
  .composer-toolbar { align-items: stretch; }
  .composer-mode { flex-wrap: wrap; }
  .toolbar-model {
    flex-basis: 100%;
    max-width: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .new-chat-btn,
  .send-btn,
  .conv-item,
  .attach-btn { transition: none; }
  .pulsing-orbit { animation: none; }
}
</style>
