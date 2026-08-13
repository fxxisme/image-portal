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
    clearEditImage({ resetMode: false });
    await nextTick();
    if (currentId.value === localConversationId) scrollBottom();

    const bodyBase = {
      prompt: text,
      n: 1,
      model: requestModel,
      response_format: "url",
    };
    const headers = { "X-Conversation-Id": String(backendConversationId) };
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
    <aside class="sidebar">
      <div class="side-top">
        <div class="brand-lockup">
          <span class="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <div>
            <div class="brand">对话生图</div>
            <div class="brand-caption">IMAGE WORKSPACE</div>
          </div>
        </div>
      </div>

      <button
        class="primary new-chat-btn"
        type="button"
        title="新建对话"
        aria-label="新建对话"
        @click="createConversation"
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
          @click="selectConversation(c.id)"
        >
          <div class="conv-title">{{ c.title || "未命名" }}</div>
          <div class="conv-meta muted">{{ formatChinaDateTime(c.updated_at) }}</div>
          <span class="del" title="删除" @click.stop="removeConversation(c.id)">&times;</span>
        </button>
        <div v-if="!conversations.length" class="muted empty">暂无对话</div>
      </div>
    </aside>

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
/* ========= layout ========= */
.shell {
  display: grid;
  grid-template-columns: 280px 1fr;
  height: 100vh;
  position: relative;
  overflow: hidden;
}

/* ========= sidebar ========= */
.sidebar {
  position: relative;
  z-index: 2;
  background: #171b17;
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
  background: #273023;
  border: 1px solid #455440;
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
  background: #344229;
  color: var(--text);
  box-shadow: inset 0 0 0 1px #4f6738;
}
.mode-option:focus-visible {
  outline: 2px solid var(--secondary);
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
  box-shadow: 0 0 0 2px rgba(145, 211, 203, 0.12);
  border-color: var(--secondary);
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
  box-shadow: none;
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

<style scoped>
.shell {
  --canvas: #101310;
  --rail: #171b17;
  --surface: #1b201b;
  --surface-raised: #222922;
  --line: #343c34;
  --line-strong: #4a574a;
  --ink: #edf2e9;
  --subtle: #aab5a9;
  --quiet: #748074;
  --signal: #a7d85a;
  --signal-deep: #18220e;
  --aqua: #91d3cb;
  --amber: #e9b65a;
  --danger-soft: #ffb4a9;
  background: var(--canvas);
  color: var(--ink);
  grid-template-columns: 224px minmax(0, 1fr);
  letter-spacing: 0;
}

.sidebar {
  z-index: 1;
  background: var(--rail);
  border-right: 1px solid var(--line);
  backdrop-filter: none;
}

.side-top { padding: 16px 16px 12px; }
.brand-lockup { display: flex; align-items: center; gap: 11px; }
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
  background: var(--signal);
}
.brand-mark i:nth-child(2),
.empty-mark i:nth-child(2) { background: var(--aqua); height: 12px; align-self: end; }
.brand-mark i:nth-child(3),
.empty-mark i:nth-child(3) { background: var(--amber); height: 8px; align-self: end; }
.brand {
  background: none;
  color: var(--ink);
  font-family: var(--font-body);
  font-size: 16px;
  font-weight: 700;
  -webkit-text-fill-color: currentColor;
}
.brand-caption {
  margin-top: 3px;
  color: var(--quiet);
  font-family: var(--font-mono);
  font-size: 9px;
  line-height: 1;
}

.new-chat-btn {
  width: calc(100% - 32px);
  min-height: 36px;
  margin: 0 16px 12px;
  padding: 7px 10px;
  border: 1px solid #bbeb70;
  border-radius: 6px;
  background: var(--signal);
  box-shadow: none;
  color: var(--signal-deep);
  font-family: var(--font-body);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0;
}
.new-chat-btn:hover:not(:disabled) {
  background: #b8e867;
  opacity: 1;
  transform: translateY(-1px);
}
.new-chat-btn:active:not(:disabled) { transform: translateY(0); }
.conv-list { padding: 0 8px 8px; }
.section-label {
  padding: 0 6px 6px;
  color: var(--quiet);
  font-family: var(--font-mono);
  font-size: 10px;
  text-transform: uppercase;
}
.conv-item {
  min-height: 48px;
  margin-bottom: 2px;
  padding: 7px 26px 7px 10px;
  border: 1px solid transparent;
  border-radius: 5px;
  color: var(--subtle);
}
.conv-item:hover { background: #202620; }
.conv-item.active {
  border-color: #3d4d3c;
  border-right: 1px solid #3d4d3c;
  background: #262f24;
  color: var(--ink);
}
.conv-item.active::before {
  position: absolute;
  top: 10px;
  bottom: 10px;
  left: 0;
  width: 3px;
  background: var(--signal);
  content: "";
}
.conv-title { font-size: 13px; font-weight: 600; padding: 0; }
.conv-meta { margin-top: 2px; color: var(--quiet); font-size: 10px; }
.del { top: 50%; right: 5px; padding: 3px 5px; transform: translateY(-50%); color: var(--quiet); }
.del:hover { background: #352521; color: var(--danger-soft); }
.empty { padding: 20px 8px; color: var(--quiet); }

.main { z-index: 1; height: 100dvh; background: var(--canvas); }
.bar {
  min-height: 60px;
  padding: 9px 22px;
  border-bottom: 1px solid var(--line);
  background: var(--canvas);
}
.glass-bar { background: var(--canvas); backdrop-filter: none; }
.bar-title { display: block; }
.title-kicker {
  margin-bottom: 2px;
  color: var(--aqua);
  font-family: var(--font-mono);
  font-size: 10px;
}
.title { color: var(--ink); font-family: var(--font-body); font-size: 20px; font-weight: 700; }
.bar-actions { gap: 10px; }
.quota-status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--subtle);
  font-size: 12px;
  white-space: nowrap;
}
.quota-status strong { color: var(--signal); font-family: var(--font-mono); font-size: 13px; }
.quota-dot { width: 7px; height: 7px; background: var(--signal); border-radius: 50%; }
.bar-actions .badge {
  padding: 5px 8px;
  border-radius: 4px;
  border-color: #755839;
  background: #30261a;
  color: #f1c778;
}
.bar-actions .ghost {
  min-height: 32px;
  padding: 6px 10px;
  border-radius: 5px;
  border-color: var(--line-strong);
  color: var(--subtle);
  font-size: 12px;
}
.bar-actions .ghost:hover:not(:disabled) { border-color: var(--aqua); background: #1d2725; color: var(--ink); }
.user-name {
  max-width: 120px;
  overflow: hidden;
  color: var(--quiet);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ban {
  margin: 12px 28px 0;
  border-radius: 5px;
  background: #38221f;
  border-color: #7c4039;
  color: #ffd7d1;
}

.messages { padding: 18px clamp(16px, 3vw, 48px); }
.center { padding: 44px 16px; }
.tip {
  display: grid;
  justify-items: center;
  max-width: 360px;
  color: var(--quiet);
  font-size: 13px;
  line-height: 1.7;
}
.tip .empty-mark { margin-bottom: 12px; }
.tip strong { margin-bottom: 4px; color: var(--ink); font-size: 17px; }
.msg { margin-bottom: 12px; }
.bubble {
  max-width: min(760px, 88%);
  padding: 10px 12px;
  border-radius: 6px;
  box-shadow: none;
}
.bubble.user { background: #273023; border: 1px solid #455440; }
.bubble.assistant { background: var(--surface); border: 1px solid var(--line); backdrop-filter: none; }
.role-tag { margin-bottom: 4px; color: var(--aqua); font-size: 10px; letter-spacing: 0; }
.bubble.user .role-tag { color: var(--signal); }
.content { color: var(--ink); font-size: 14px; line-height: 1.65; }
.ref-thumb img { border-radius: 5px; border-color: var(--line-strong); }
.imgs { gap: 6px; }
.img-card img { border-radius: 5px; border-color: var(--line); background: #0b0e0b; }
.cost { color: var(--amber); font-family: var(--font-mono); font-size: 11px; }
.loading-bubble { min-width: 70px; background: var(--surface); }
.dot { width: 6px; height: 6px; background: var(--signal); }

.composer-area {
  gap: 9px;
  padding: 8px 22px 10px;
  border-top: 1px solid var(--line);
  background: var(--rail);
}
.composer-toolbar,
.edit-banner,
.input-row { max-width: 920px; }
.composer-toolbar {
  min-height: 44px;
  align-items: center;
  gap: 20px;
}
.composer-mode {
  align-items: center;
  gap: 10px;
}
.mode-switch {
  padding: 3px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #121712;
}
.mode-option {
  min-width: 82px;
  padding: 7px 12px;
  border-radius: 4px;
  color: var(--quiet);
  font-size: 12px;
}
.mode-option:hover { color: var(--ink); }
.mode-option.active {
  background: #344229;
  box-shadow: none;
  color: #ddf7b2;
}
.mode-option:focus-visible,
.attach-btn:focus-visible,
.send-btn:focus-visible,
.edit-thumb-remove:focus-visible,
.clear-edit-images:focus-visible,
.new-chat-btn:focus-visible,
.conv-item:focus-visible { outline: 2px solid var(--aqua); outline-offset: 2px; }
.hint { color: var(--quiet); font-size: 11px; }
.hint-icon { color: var(--signal); font-size: 8px; opacity: 1; }
.edit-banner {
  padding: 9px 10px;
  border: 1px solid #485c3d;
  border-radius: 6px;
  background: #202a1d;
  backdrop-filter: none;
}
.edit-info { color: var(--subtle); font-size: 12px; }
.edit-info strong { color: var(--ink); }
.edit-thumb-wrap, .edit-thumb { width: 44px; height: 44px; }
.edit-thumb { border-radius: 4px; border-color: #596851; }
.edit-thumb-remove {
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  border: 1px solid var(--line-strong);
  border-radius: 50%;
  background: #172017;
  color: var(--ink);
}
.clear-edit-images { min-width: 28px; padding: 2px 7px; border-color: transparent; color: var(--subtle); }
.clear-edit-images:hover:not(:disabled) { background: #352521; color: var(--danger-soft); }
.tiny { color: var(--quiet); }

.input-row {
  gap: 10px;
  min-height: 64px;
  padding: 7px 8px 7px 10px;
  border: 1px solid var(--line-strong);
  border-radius: 7px;
  background: var(--surface-raised);
  backdrop-filter: none;
}
.input-row:focus-within { border-color: var(--aqua); box-shadow: 0 0 0 2px rgba(145, 211, 203, 0.12); }
.attach-btn {
  width: 38px;
  height: 38px;
  border: 1px solid var(--line-strong);
  border-radius: 5px;
  color: var(--subtle);
}
.attach-btn:hover { background: #2e3a2c; border-color: var(--signal); color: var(--signal); }
.attach-icon { font-size: 20px; }
.input-row textarea {
  min-height: 42px;
  padding: 6px 2px;
  border: 0;
  border-radius: 0;
  color: var(--ink);
  font-size: 14px;
}
.input-row textarea:focus { box-shadow: none; }
.model-field {
  display: grid;
  flex: 0 0 166px;
  gap: 3px;
  color: var(--quiet);
  font-family: var(--font-mono);
  font-size: 9px;
}
.model-select {
  width: 166px;
  min-height: 38px;
  padding: 7px 26px 7px 9px;
  border-color: var(--line-strong);
  border-radius: 5px;
  background: #171d17;
  color: var(--subtle);
  font-family: var(--font-mono);
  font-size: 11px;
}
.model-select:focus { border-color: var(--aqua); box-shadow: none; }
.toolbar-model {
  flex: 0 0 184px;
  align-self: center;
}
.toolbar-model > span { display: none; }
.toolbar-model .model-select {
  width: 184px;
  min-height: 36px;
  font-size: 12px;
}
.send-btn {
  min-width: 108px;
  min-height: 48px;
  justify-content: center;
  padding: 10px 15px;
  border: 1px solid #bbeb70;
  border-radius: 5px;
  background: var(--signal);
  box-shadow: none;
  color: var(--signal-deep);
  font-size: 13px;
}
.send-btn:hover:not(:disabled) { background: #b8e867; opacity: 1; transform: translateY(-1px); }
.send-btn:active:not(:disabled) { transform: translateY(0); }
.send-btn:disabled { background: #303830; border-color: #3c453c; color: #7e897e; }
.bolt { color: #52623a; font-size: 13px; }

@media (max-width: 860px) {
  .shell { grid-template-columns: 1fr; height: auto; min-height: 100dvh; }
  .sidebar {
    display: grid;
    grid-template-columns: 36px minmax(0, 1fr);
    gap: 8px;
    max-height: none;
    padding: 6px 12px;
    border-right: 0;
    border-bottom: 1px solid var(--line);
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
  .conv-title { font-size: 12px; line-height: 1.2; }
  .conv-item.active::before { top: auto; right: 10px; bottom: 0; left: 10px; width: auto; height: 2px; }
  .main { height: auto; min-height: calc(100dvh - 49px); }
  .bar { min-height: 54px; padding: 8px 14px; }
  .title { font-size: 17px; }
  .bar-actions { gap: 6px; }
  .user-name { display: none; }
  .messages { min-height: 42dvh; padding: 12px 14px; }
  .composer-area { padding: 8px 12px 10px; }
  .composer-toolbar { gap: 8px; }
  .mode-switch { width: auto; }
  .composer-mode {
    width: auto;
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .hint { width: auto; }
  .input-row { gap: 8px; }
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
  .dot { animation: none; }
}
</style>
