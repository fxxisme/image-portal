<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { request } from "../api/http";
import GalleryModal from "../components/GalleryModal.vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();

const conversations = ref([]);
const currentId = ref(null);
const messages = ref([]);
const prompt = ref("");
const n = ref(1);
const loadingChat = ref(false);
const sending = ref(false);
const error = ref("");
/** 改图参考：远程 URL 或 data URL */
const editImageSrc = ref("");
const editPreview = ref("");
const fileInput = ref(null);
const scroller = ref(null);
const galleryOpen = ref(false);

const currentTitle = computed(() => {
  const c = conversations.value.find((x) => x.id === currentId.value);
  return c?.title || "对话生图";
});

const isEditMode = computed(() => !!editImageSrc.value);

const quotaText = computed(() => {
  const rem = auth.me?.quota_remaining;
  const total = auth.me?.quota_total;
  if (rem == null || total == null) return "额度加载中…";
  return `已用 ${auth.me.quota_used ?? total - rem} / 共 ${total} 张 · 剩余 ${rem} 张`;
});

async function ensureMe() {
  try {
    await auth.fetchMe();
  } catch (e) {
    if (e.status === 401) {
      auth.logoutUser();
      router.push({ name: "login" });
    }
  }
}

async function loadConversations() {
  try {
    conversations.value = await request("/api/conversations", { token: auth.userToken });
    if (!currentId.value && conversations.value.length) {
      currentId.value = conversations.value[0].id;
    }
  } catch (e) {
    error.value = e.message || String(e);
    if (e.status === 401) {
      auth.logoutUser();
      router.push({ name: "login" });
    }
  }
}

async function loadMessages() {
  if (!currentId.value) {
    messages.value = [];
    return;
  }
  loadingChat.value = true;
  error.value = "";
  try {
    const detail = await request(`/api/conversations/${currentId.value}`, {
      token: auth.userToken,
    });
    messages.value = detail.messages || [];
    await nextTick();
    scrollBottom();
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    loadingChat.value = false;
  }
}

async function createConversation() {
  error.value = "";
  try {
    const item = await request("/api/conversations", {
      method: "POST",
      token: auth.userToken,
      body: { title: "新对话" },
    });
    conversations.value.unshift(item);
    currentId.value = item.id;
    messages.value = [];
    clearEditImage();
  } catch (e) {
    error.value = e.message || String(e);
  }
}

async function removeConversation(id) {
  if (!window.confirm("删除该对话及历史？")) return;
  try {
    await request(`/api/conversations/${id}`, {
      method: "DELETE",
      token: auth.userToken,
    });
    conversations.value = conversations.value.filter((c) => c.id !== id);
    if (currentId.value === id) {
      currentId.value = conversations.value[0]?.id || null;
    }
  } catch (e) {
    error.value = e.message || String(e);
  }
}

function selectConversation(id) {
  currentId.value = id;
  clearEditImage();
}

function useAsEditRef(url) {
  editImageSrc.value = url;
  editPreview.value = url;
  galleryOpen.value = false;
}

function clearEditImage() {
  editImageSrc.value = "";
  editPreview.value = "";
  if (fileInput.value) fileInput.value.value = "";
}

function pickFile() {
  fileInput.value?.click();
}

function onFileChange(ev) {
  const file = ev.target.files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    error.value = "请上传图片文件";
    return;
  }
  // 约 8MB 限制，避免 body 过大
  if (file.size > 8 * 1024 * 1024) {
    error.value = "图片请小于 8MB";
    return;
  }
  error.value = "";
  const reader = new FileReader();
  reader.onload = () => {
    const dataUrl = String(reader.result || "");
    editImageSrc.value = dataUrl;
    editPreview.value = dataUrl;
  };
  reader.onerror = () => {
    error.value = "读取图片失败";
  };
  reader.readAsDataURL(file);
}

function scrollBottom() {
  const el = scroller.value;
  if (el) el.scrollTop = el.scrollHeight;
}

async function send() {
  const text = prompt.value.trim();
  if (!text || sending.value) return;
  if (!currentId.value) {
    await createConversation();
  }
  if (!currentId.value) return;

  sending.value = true;
  error.value = "";
  const bodyBase = {
    conversation_id: currentId.value,
    prompt: text,
    n: Number(n.value) || 1,
  };

  try {
    let data;
    if (editImageSrc.value) {
      data = await request("/api/edit", {
        method: "POST",
        token: auth.userToken,
        body: { ...bodyBase, image_url: editImageSrc.value },
      });
    } else {
      data = await request("/api/generate", {
        method: "POST",
        token: auth.userToken,
        body: bodyBase,
      });
    }

    messages.value.push(data.user_message, data.assistant_message);
    auth.setQuotaRemaining(data.quota_remaining);
    if (auth.me) auth.me.quota_used = (auth.me.quota_total || 0) - data.quota_remaining;
    prompt.value = "";
    // 提交后退出改图附件，避免误连发；可再点「基于此图修改」
    clearEditImage();
    await loadConversations();
    await nextTick();
    scrollBottom();
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    sending.value = false;
  }
}

function logout() {
  auth.logoutUser();
  router.push({ name: "login" });
}

watch(currentId, () => {
  loadMessages();
});

onMounted(async () => {
  await ensureMe();
  await loadConversations();
  if (!conversations.value.length) {
    await createConversation();
  } else {
    await loadMessages();
  }
});
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="side-top">
        <div class="brand">对话生图</div>
        <button class="primary" type="button" style="width: 100%" @click="createConversation">
          新建对话
        </button>
      </div>
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
          <div class="conv-meta muted">{{ new Date(c.updated_at).toLocaleString() }}</div>
          <span class="del" title="删除" @click.stop="removeConversation(c.id)">×</span>
        </button>
        <div v-if="!conversations.length" class="muted empty">暂无对话</div>
      </div>
    </aside>

    <main class="main">
      <header class="bar">
        <div>
          <div class="title">{{ currentTitle }}</div>
          <div class="muted sub">{{ quotaText }}</div>
        </div>
        <div class="row">
          <button class="ghost" type="button" @click="galleryOpen = true">我的图库</button>
          <span class="badge remain">
            剩余 <strong>{{ auth.me?.quota_remaining ?? "-" }}</strong> 张
          </span>
          <span class="badge" v-if="auth.me?.name">{{ auth.me.name }}</span>
          <button class="ghost" type="button" @click="logout">退出</button>
        </div>
      </header>

      <GalleryModal
        :open="galleryOpen"
        @close="galleryOpen = false"
        @use-edit="useAsEditRef"
      />

      <div v-if="error" class="err ban">{{ error }}</div>

      <div ref="scroller" class="messages">
        <div v-if="loadingChat" class="muted center">加载中…</div>
        <div v-else-if="!messages.length" class="muted center tip">
          输入描述即可生图；上传图片或点「基于此图修改」可改图。成功出图会扣额度。
        </div>

        <div v-for="m in messages" :key="m.id" class="msg" :class="m.role">
          <div class="bubble">
            <div class="role">{{ m.role === "user" ? "你" : "助手" }}</div>
            <div class="content">{{ m.content }}</div>
            <div v-if="m.ref_image_url && m.role === 'user'" class="ref-thumb">
              <img :src="m.ref_image_url" alt="参考图" />
            </div>
            <div v-if="m.image_urls?.length" class="imgs">
              <div v-for="(url, idx) in m.image_urls" :key="idx" class="img-card">
                <a :href="url" target="_blank" rel="noopener">
                  <img :src="url" :alt="'image-' + idx" loading="lazy" />
                </a>
                <div class="img-actions">
                  <button class="success" type="button" @click="useAsEditRef(url)">基于此图修改</button>
                  <a class="link" :href="url" target="_blank" rel="noopener">查看原图</a>
                </div>
              </div>
            </div>
            <div v-if="m.cost" class="meta muted">消耗 {{ m.cost }} 张</div>
          </div>
        </div>
      </div>

      <footer class="composer card">
        <div v-if="isEditMode" class="edit-banner">
          <div class="edit-info">
            <img v-if="editPreview" class="edit-thumb" :src="editPreview" alt="参考" />
            <div>
              <strong>改图模式</strong>
              <div class="muted tiny">将根据参考图与文字说明生成</div>
            </div>
          </div>
          <button class="ghost" type="button" @click="clearEditImage">移除图片</button>
        </div>

        <div class="input-row">
          <button class="ghost attach" type="button" title="上传参考图" @click="pickFile">
            图片
          </button>
          <input
            ref="fileInput"
            type="file"
            accept="image/*"
            class="hidden-file"
            @change="onFileChange"
          />
          <textarea
            v-model="prompt"
            :placeholder="isEditMode ? '描述如何修改这张图…' : '描述你想生成的图片…'"
            @keydown.enter.exact.prevent="send"
          />
        </div>

        <div class="composer-bar">
          <label class="mini">
            张数
            <select v-model.number="n">
              <option :value="1">1</option>
              <option :value="2">2</option>
              <option :value="3">3</option>
              <option :value="4">4</option>
            </select>
          </label>
          <button
            class="primary"
            type="button"
            :disabled="sending || !prompt.trim()"
            @click="send"
          >
            {{ sending ? "处理中…" : isEditMode ? "提交改图" : "生成" }}
          </button>
        </div>
        <div class="muted hint">生成可能需要一些时间。失败不扣额度。</div>
      </footer>
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 280px 1fr;
  height: 100%;
  min-height: 100vh;
}
.sidebar {
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--sidebar) 92%, transparent);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.side-top {
  padding: 16px;
  border-bottom: 1px solid var(--border);
}
.brand {
  font-weight: 700;
  margin-bottom: 12px;
}
.conv-list {
  overflow: auto;
  padding: 8px;
  flex: 1;
}
.conv-item {
  width: 100%;
  text-align: left;
  background: transparent;
  color: var(--text);
  border: 1px solid transparent;
  border-radius: 12px;
  padding: 10px 12px;
  position: relative;
  margin-bottom: 6px;
}
.conv-item:hover {
  background: color-mix(in srgb, var(--card) 80%, transparent);
}
.conv-item.active {
  border-color: color-mix(in srgb, var(--accent) 50%, var(--border));
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}
.conv-title {
  font-size: 13px;
  font-weight: 600;
  padding-right: 18px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-meta {
  font-size: 11px;
  margin-top: 4px;
}
.del {
  position: absolute;
  right: 8px;
  top: 8px;
  color: var(--muted);
  font-size: 16px;
  line-height: 1;
  padding: 2px 6px;
}
.del:hover {
  color: var(--danger);
}
.empty {
  padding: 16px;
  font-size: 13px;
}
.main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  height: 100vh;
}
.bar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 70%, transparent);
  backdrop-filter: blur(8px);
}
.title {
  font-size: 16px;
  font-weight: 700;
}
.sub {
  font-size: 12px;
  margin-top: 2px;
}
.remain strong {
  color: var(--accent-2);
}
.ban {
  margin: 12px 18px 0;
}
.messages {
  flex: 1;
  overflow: auto;
  padding: 18px;
}
.center {
  text-align: center;
  padding: 40px 12px;
}
.tip {
  max-width: 520px;
  margin: 40px auto;
  line-height: 1.6;
}
.msg {
  display: flex;
  margin-bottom: 14px;
}
.msg.user {
  justify-content: flex-end;
}
.msg.assistant {
  justify-content: flex-start;
}
.bubble {
  max-width: min(720px, 92%);
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 12px 14px;
}
.msg.user .bubble {
  background: color-mix(in srgb, var(--accent) 12%, var(--card));
}
.role {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 6px;
}
.content {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}
.ref-thumb {
  margin-top: 8px;
}
.ref-thumb img {
  max-width: 120px;
  max-height: 120px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--border);
}
.imgs {
  margin-top: 12px;
  display: grid;
  gap: 12px;
}
.img-card img {
  width: 100%;
  max-height: 56vh;
  object-fit: contain;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: #0a0c10;
  display: block;
}
.img-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-top: 8px;
}
.link {
  font-size: 13px;
}
.meta {
  margin-top: 8px;
  font-size: 12px;
}
.composer {
  margin: 0 18px 18px;
  padding: 14px;
}
.edit-banner {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--accent-2) 35%, var(--border));
  background: color-mix(in srgb, var(--accent-2) 10%, transparent);
}
.edit-info {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 13px;
  min-width: 0;
}
.edit-thumb {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--border);
  flex-shrink: 0;
}
.tiny {
  font-size: 12px;
  margin-top: 2px;
}
.input-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
}
.attach {
  flex-shrink: 0;
  align-self: flex-end;
  min-width: 56px;
}
.input-row textarea {
  flex: 1;
  min-height: 72px;
}
.hidden-file {
  display: none;
}
.composer-bar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: end;
  margin-top: 10px;
}
.mini {
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}
.mini select {
  min-width: 72px;
}
.hint {
  margin-top: 8px;
  font-size: 12px;
}
@media (max-width: 860px) {
  .shell {
    grid-template-columns: 1fr;
  }
  .sidebar {
    max-height: 220px;
  }
  .main {
    height: auto;
    min-height: calc(100vh - 220px);
  }
  .composer-bar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
