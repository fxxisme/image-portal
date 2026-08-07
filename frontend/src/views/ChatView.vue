<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { request } from "../api/http";
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
const error = ref("");
const editImageUrls = ref([]);
const fileInput = ref(null);
const scroller = ref(null);
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
    }
  }
}

function saveBrowserConversations() {
  try {
    saveLocalConversations(conversations.value);
  } catch {
    error.value = "本地对话保存失败，请清理浏览器存储空间后重试";
  }
}

function findLocalConversation(id = currentId.value) {
  return conversations.value.find((conversation) => conversation.id === id) || null;
}

function persistConversation(id, messageList, { touch = true } = {}) {
  const conversation = findLocalConversation(id);
  if (!conversation) return;
  conversation.messages = messageList;
  if (touch) conversation.updated_at = new Date().toISOString();
  conversations.value = [...conversations.value].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );
  saveBrowserConversations();
}

function restoreBrowserConversations() {
  conversations.value = loadLocalConversations().sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );
  const first = conversations.value[0];
  currentId.value = first?.id || null;
  messages.value = first?.messages || [];
}

async function ensureBackendConversation(localConversationId) {
  const conversation = findLocalConversation(localConversationId);
  const apiKeyId = auth.me?.id;
  if (!conversation || !apiKeyId) throw new Error("当前登录状态无效，请重新登录");

  const key = String(apiKeyId);
  const existingId = conversation.backend_conversation_ids[key];
  if (Number.isInteger(existingId)) return existingId;

  const item = await request("/api/conversations", {
    method: "POST",
    token: auth.userToken,
    body: { title: conversation.title || "新对话" },
  });
  conversation.backend_conversation_ids[key] = item.id;
  persistConversation(localConversationId, conversation.messages, { touch: false });
  return item.id;
}

function createConversation() {
  error.value = "";
  const item = createLocalConversation();
  conversations.value.unshift(item);
  currentId.value = item.id;
  messages.value = item.messages;
  saveBrowserConversations();
  clearEditImage();
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
  clearEditImage();
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

async function onFileChange(ev) {
  const files = Array.from(ev.target.files || []);
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

async function send() {
  const text = prompt.value.trim();
  if (!text || sending.value) return;
  if (isEditMode.value && !editImageUrls.value.length) {
    error.value = "图生图请先上传参考图";
    return;
  }
  if (!currentId.value) {
    createConversation();
  }
  if (!currentId.value) return;

  const localConversationId = currentId.value;
  const conversation = findLocalConversation(localConversationId);
  if (!conversation) return;

  sending.value = true;
  error.value = "";
  let localMessages = null;

  try {
    if (conversation.title === "新对话") {
      conversation.title = text.slice(0, 40);
      persistConversation(localConversationId, conversation.messages);
    }
    const backendConversationId = await ensureBackendConversation(localConversationId);
    const apiKeyId = String(auth.me?.id || "unknown");
    const optimisticUserMsg = {
      id: "pending-" + Date.now(),
      role: "user",
      content: text,
      ref_image_url: editImageUrls.value[0] || undefined,
    };
    localMessages = conversation.messages;
    localMessages.push(optimisticUserMsg);
    persistConversation(localConversationId, localMessages);
    prompt.value = "";
    const refImages = [...editImageUrls.value];
    const requestModel = selectedModel.value || undefined;
    clearEditImage();
    await nextTick();
    if (currentId.value === localConversationId) scrollBottom();

    const bodyBase = {
      conversation_id: backendConversationId,
      prompt: text,
      n: 1,
      model: requestModel,
    };
    let data;
    if (refImages.length) {
      data = await request("/api/edit", {
        method: "POST",
        token: auth.userToken,
        body: { ...bodyBase, images: refImages.map((url) => ({ url })) },
      });
    } else {
      data = await request("/api/generate", {
        method: "POST",
        token: auth.userToken,
        body: bodyBase,
      });
    }

    const idx = localMessages.findIndex((m) => m.id === optimisticUserMsg.id);
    if (idx !== -1) {
      localMessages.splice(idx, 1, {
        ...data.user_message,
        id: `${apiKeyId}-${data.user_message.id}`,
      });
    } else {
      localMessages.push({ ...data.user_message, id: `${apiKeyId}-${data.user_message.id}` });
    }
    localMessages.push({
      ...data.assistant_message,
      id: `${apiKeyId}-${data.assistant_message.id}`,
    });
    persistConversation(localConversationId, localMessages);
    auth.setQuotaRemaining(data.quota_remaining);
    if (auth.me) auth.me.quota_used = (auth.me.quota_total || 0) - data.quota_remaining;
    await nextTick();
    if (currentId.value === localConversationId) scrollBottom();
  } catch (e) {
    const detail = e.message || String(e);
    if (localMessages) {
      localMessages.push({
        id: "error-" + Date.now(),
        role: "assistant",
        content: "❌ 生成失败\n\n" + detail,
        cost: 0,
      });
      persistConversation(localConversationId, localMessages);
    }
    error.value = e.message || String(e);
  } finally {
    sending.value = false;
  }
}

function logout() {
  auth.logoutUser();
  router.push({ name: "login" });
}

onMounted(async () => {
  await ensureMe();
  restoreBrowserConversations();
  if (!conversations.value.length) {
    createConversation();
  }
  await nextTick();
  scrollBottom();
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
    <!-- atmosphere blobs -->
    <div class="atmo">
      <div class="blob blob-1" />
      <div class="blob blob-2" />
    </div>

    <!-- ====== sidebar ====== -->
    <aside class="sidebar">
      <div class="side-top">
        <div class="brand">对话生图</div>
      </div>

      <button class="primary new-chat-btn" type="button" @click="createConversation">
        ＋ 新建对话
      </button>

      <div class="conv-list">
        <button
          v-for="c in conversations"
          :key="c.id"
          type="button"
          class="conv-item"
          :class="{ active: c.id === currentId }"
          @click="selectConversation(c.id)"
        >
          <div class="conv-title">{{ c.title || "未命名" }}</div>
          <div class="conv-meta muted">{{ formatChinaDateTime(c.updated_at) }}</div>
          <span class="del" title="删除" @click.stop="removeConversation(c.id)">&times;</span>
        </button>
        <div v-if="!conversations.length" class="muted empty">暂无对话</div>
      </div>
    </aside>

    <!-- ====== main ====== -->
    <main class="main">
      <!-- top bar -->
      <header class="bar glass-bar">
        <div class="bar-title">
          <div class="title">对话生图</div>
          <div class="sub muted">{{ quotaText }}</div>
        </div>
        <div class="bar-actions">
          <button class="ghost" type="button" @click="router.push({ name: 'video' })">视频生成</button>
          <span class="badge">
            剩余 <strong>{{ auth.me?.quota_remaining ?? "-" }}</strong> 张
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
          <span class="badge" v-if="auth.me?.name">{{ auth.me.name }}</span>
        </div>
      </header>

      <LoginModal
        v-if="showLoginModal"
        :show="showLoginModal"
        @close="showLoginModal = false"
        @success="handleLoginSuccess"
      />

      <div v-if="error" class="err ban">{{ error }}</div>

      <!-- messages -->
      <div ref="scroller" class="messages">
        <div v-if="!messages.length" class="center tip">
          输入描述即可生图；上传图片后可改图。成功出图会扣额度。
        </div>

        <div v-for="m in messages" :key="m.id" class="msg" :class="m.role">
          <div class="bubble" :class="m.role">
            <div class="role-tag">{{ m.role === "user" ? "你" : "AI" }}</div>
            <div class="content">{{ m.content }}</div>

            <div v-if="m.ref_image_url && m.role === 'user'" class="ref-thumb">
              <img :src="m.ref_image_url" alt="参考图" />
            </div>

            <div v-if="m.image_urls?.length" class="imgs">
              <div v-for="(url, idx) in m.image_urls" :key="idx" class="img-card">
                <a :href="url" target="_blank" rel="noopener">
                  <img :src="url" :alt="'image-' + idx" loading="lazy" @error="retryImage" />
                </a>
              </div>
            </div>
            <div v-if="m.cost" class="cost muted">消耗 {{ m.cost }} 张</div>
          </div>
        </div>

        <div v-if="sending" class="msg assistant">
          <div class="bubble assistant loading-bubble">
            <span class="dot" />
            <span class="dot" />
            <span class="dot" />
          </div>
        </div>
      </div>

      <!-- ====== composer area (matching risk-1.html style) ====== -->
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
          </div>
          <p class="hint">
            <span class="hint-icon">ⓘ</span>
            生成可能需要一些时间。失败不扣额度。
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
                  : '先上传一张或多张参考图，再描述修改方式…'
                : '描述你想生成的图片…'
            "
            @keydown.enter.exact.prevent="send"
            rows="1"
          />
          <select v-model="selectedModel" class="model-select" aria-label="生图模型">
            <option v-for="modelName in modelOptions" :key="modelName" :value="modelName">
              {{ modelName }}
            </option>
          </select>
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
/* ========= layout ========= */
.shell {
  display: grid;
  grid-template-columns: 280px 1fr;
  height: 100vh;
  position: relative;
  overflow: hidden;
}

/* atmosphere */
.atmo {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  opacity: 0.18;
}
.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(120px);
}
.blob-1 {
  top: 15%;
  right: -5%;
  width: 450px;
  height: 450px;
  background: var(--primary);
}
.blob-2 {
  bottom: 8%;
  left: -10%;
  width: 360px;
  height: 360px;
  background: var(--secondary);
}

/* ========= sidebar ========= */
.sidebar {
  position: relative;
  z-index: 2;
  background: rgba(6, 14, 32, 0.75);
  backdrop-filter: blur(16px);
  border-right: 1px solid rgba(149, 142, 160, 0.15);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.side-top {
  padding: 20px 20px 12px;
}
.brand {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 700;
  background: var(--prismatic);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.new-chat-btn {
  width: calc(100% - 32px);
  margin: 4px 16px 12px;
  padding: 12px 0;
  border-radius: 0.75rem;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.conv-list {
  overflow: auto;
  padding: 4px 10px;
  flex: 1;
}
.conv-item {
  width: 100%;
  text-align: left;
  background: transparent;
  color: var(--text);
  border: 1px solid transparent;
  border-radius: 0.75rem;
  padding: 10px 12px;
  position: relative;
  margin-bottom: 4px;
  transition: all 0.2s;
}
.conv-item:hover {
  background: rgba(255, 255, 255, 0.04);
}
.conv-item.active {
  border-color: rgba(173, 198, 255, 0.35);
  border-right: 3px solid var(--secondary);
  background: rgba(5, 102, 217, 0.12);
}
.conv-title {
  font-size: 13px;
  font-weight: 600;
  padding-right: 20px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-meta {
  font-size: 11px;
  margin-top: 3px;
}
.del {
  position: absolute;
  right: 8px;
  top: 8px;
  color: var(--muted-2);
  font-size: 18px;
  line-height: 1;
  padding: 0 4px;
  border-radius: 4px;
  transition: color 0.15s;
}
.del:hover { color: var(--danger); }
.empty { padding: 20px 12px; font-size: 13px; text-align: center; }

/* ========= main ========= */
.main {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100vh;
}

/* top bar */
.bar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 10px 20px;
  border-bottom: 1px solid rgba(149, 142, 160, 0.12);
}
.glass-bar {
  background: rgba(11, 19, 38, 0.7);
  backdrop-filter: blur(12px);
}
.title {
  font-size: 16px;
  font-weight: 700;
  font-family: var(--font-display);
}
.bar-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.sub {
  font-size: 12px;
  margin-top: 0;
  white-space: nowrap;
}
.bar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: nowrap;
  align-items: center;
  flex-shrink: 0;
}
.ban {
  margin: 10px 18px 0;
}

/* messages */
.messages {
  flex: 1;
  overflow: auto;
  padding: 18px 20px;
}
.center {
  text-align: center;
  padding: 60px 20px;
}
.tip {
  max-width: 480px;
  margin: 40px auto;
  line-height: 1.6;
  font-size: 14px;
}

.msg {
  display: flex;
  margin-bottom: 18px;
}
.msg.user     { justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }

.bubble {
  max-width: min(720px, 88%);
  border-radius: 1rem;
  padding: 14px 16px;
}
.bubble.user {
  background: rgba(160, 120, 255, 0.12);
  border: 1px solid rgba(160, 120, 255, 0.2);
}
.bubble.assistant {
  background: rgba(19, 27, 46, 0.55);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(149, 142, 160, 0.15);
}

.role-tag {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--muted-2);
  margin-bottom: 6px;
}

.content {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.55;
  font-size: 14px;
}

.ref-thumb { margin-top: 10px; }
.ref-thumb img {
  max-width: 140px;
  max-height: 140px;
  object-fit: cover;
  border-radius: 0.625rem;
  border: 1px solid var(--border-light);
}

.imgs {
  margin-top: 14px;
  display: grid;
  gap: 14px;
}
.img-card img {
  width: 100%;
  max-height: 56vh;
  object-fit: contain;
  border-radius: 0.75rem;
  border: 1px solid var(--border-light);
  background: #060e20;
  display: block;
}
.cost {
  margin-top: 8px;
  font-size: 12px;
}

/* ========= composer area (risk-1.html inspired) ========= */
.composer-area {
  padding: 14px 24px 12px;
  background: linear-gradient(to top, var(--bg) 0%, transparent 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.composer-toolbar {
  width: 100%;
  max-width: 56rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 32px;
}
.composer-mode {
  width: auto;
  max-width: none;
  display: flex;
  align-items: center;
}
.mode-switch {
  display: inline-flex;
  padding: 4px;
  border: 1px solid rgba(149, 142, 160, 0.18);
  border-radius: 0.75rem;
  background: rgba(11, 19, 38, 0.58);
}
.mode-option {
  min-width: 88px;
  padding: 8px 14px;
  border: 0;
  border-radius: 0.5rem;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 13px;
  transition: background 0.2s, color 0.2s, box-shadow 0.2s;
}
.mode-option:hover { color: var(--text); }
.mode-option.active {
  background: rgba(208, 188, 255, 0.16);
  color: var(--text);
  box-shadow: inset 0 0 0 1px rgba(208, 188, 255, 0.24);
}
.mode-option:focus-visible {
  outline: 2px solid rgba(208, 188, 255, 0.7);
  outline-offset: 2px;
}

.edit-banner {
  width: 100%;
  max-width: 56rem;
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 0;
  padding: 8px 12px;
  border-radius: 0.75rem;
  border: 1px solid rgba(61, 214, 140, 0.3);
  background: rgba(61, 214, 140, 0.08);
  backdrop-filter: blur(8px);
}
.edit-info {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  font-size: 13px;
  min-width: 0;
}
.edit-thumbs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.edit-thumb-wrap {
  position: relative;
  width: 48px;
  height: 48px;
  flex-shrink: 0;
}
.edit-thumb {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 0.5rem;
  border: 1px solid var(--border-light);
  flex-shrink: 0;
}
.edit-thumb-remove {
  position: absolute;
  top: -5px;
  right: -5px;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 1px solid var(--border-light);
  border-radius: 50%;
  background: #121a2c;
  color: var(--text);
  cursor: pointer;
  font-size: 16px;
  line-height: 14px;
}
.clear-edit-images {
  min-width: 32px;
  padding: 4px 10px;
  font-size: 20px;
  line-height: 1;
}
.tiny { font-size: 12px; margin-top: 2px; }

.input-row {
  width: 100%;
  max-width: 56rem;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px;
  border-radius: 1rem;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.input-row:focus-within {
  box-shadow: 0 0 0 2px rgba(208, 188, 255, 0.25);
  border-color: rgba(208, 188, 255, 0.35);
}

.attach-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 0.75rem;
  background: transparent;
  border: none;
  color: var(--muted);
  cursor: pointer;
  transition: all 0.2s;
}
.attach-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text);
}
.attach-icon {
  font-size: 22px;
  line-height: 1;
  font-weight: 300;
}

.input-row textarea {
  flex: 1;
  min-height: 56px;
  max-height: 160px;
  border: none;
  background: transparent;
  padding: 10px 0;
  font-size: 16px;
  line-height: 1.6;
  font-weight: 400;
  resize: none;
  outline: none;
  box-shadow: none;
}
.model-select {
  flex: 0 0 168px;
  width: 168px;
  padding: 10px;
  font-size: 12px;
}

.send-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 28px;
  border-radius: 0.75rem;
  background: var(--prismatic);
  color: #23005c;
  border: none;
  cursor: pointer;
  font-size: 15px;
  font-family: var(--font-body);
  font-weight: 600;
  box-shadow: 0 4px 20px rgba(160, 120, 255, 0.25);
  transition: all 0.2s;
}
.send-btn:hover:not(:disabled) {
  transform: scale(1.02);
  opacity: 0.93;
}
.send-btn:active:not(:disabled) {
  transform: scale(0.97);
}
.send-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  box-shadow: none;
  background: rgba(149, 142, 160, 0.18);
  color: var(--muted-2);
}
.bolt {
  font-size: 16px;
  line-height: 1;
}

.hidden-file { display: none; }

.hint {
  margin: 0;
  font-size: 12px;
  color: rgba(203, 195, 215, 0.5);
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.hint-icon {
  font-size: 13px;
  opacity: 0.7;
}

/* ---- loading dots ---- */
.loading-bubble {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 16px 22px;
  min-width: 64px;
  justify-content: center;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--muted-2);
  animation: bounce 1.4s ease-in-out infinite both;
}
.dot:nth-child(1) { animation-delay: 0s; }
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.5); opacity: 0.35; }
  40% { transform: scale(1); opacity: 1; }
}

/* ---- responsive ---- */
@media (max-width: 860px) {
  .shell {
    grid-template-columns: 1fr;
  }
  .sidebar {
    max-height: 200px;
  }
  .bar {
    align-items: flex-start;
  }
  .bar-title {
    flex-direction: column;
    align-items: flex-start;
    gap: 0;
  }
  .sub {
    margin-top: 2px;
    white-space: normal;
  }
  .bar-actions {
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .main {
    height: auto;
    min-height: calc(100vh - 200px);
  }
  .input-row {
    flex-wrap: wrap;
  }
  .composer-toolbar {
    align-items: stretch;
    flex-wrap: wrap;
    gap: 8px;
  }
  .composer-mode,
  .mode-switch {
    width: 100%;
  }
  .hint {
    width: 100%;
    white-space: normal;
  }
  .mode-option {
    flex: 1;
  }
  .input-row textarea {
    min-width: calc(100% - 56px);
  }
  .model-select {
    flex: 1;
    width: auto;
  }
}
</style>
