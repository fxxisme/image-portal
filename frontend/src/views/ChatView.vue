<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { request } from "../api/http";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();

const conversations = ref([]);
const currentId = ref(null);
const messages = ref([]);
const prompt = ref("");
const n = ref(1);
const model = ref("");
const loadingList = ref(false);
const loadingChat = ref(false);
const sending = ref(false);
const error = ref("");
const editTargetUrl = ref("");
const scroller = ref(null);

const currentTitle = computed(() => {
  const c = conversations.value.find((x) => x.id === currentId.value);
  return c?.title || "对话生图";
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
  loadingList.value = true;
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
  } finally {
    loadingList.value = false;
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
    editTargetUrl.value = "";
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
  editTargetUrl.value = "";
}

function useAsEditRef(url) {
  editTargetUrl.value = url;
}

function clearEditRef() {
  editTargetUrl.value = "";
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
  if (model.value.trim()) bodyBase.model = model.value.trim();

  try {
    let data;
    if (editTargetUrl.value) {
      data = await request("/api/edit", {
        method: "POST",
        token: auth.userToken,
        body: { ...bodyBase, image_url: editTargetUrl.value },
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
    // 多轮默认以上一轮结果为下一轮参考
    const lastUrls = data.assistant_message?.image_urls || [];
    editTargetUrl.value = lastUrls[0] || "";
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
          <div class="muted sub">
            文生图 / 多轮改图 · 上游
            <span class="mono">/v1/images/generations|edits</span>
          </div>
        </div>
        <div class="row">
          <span class="badge">
            剩余
            <strong>{{ auth.me?.quota_remaining ?? "-" }}</strong>
            / {{ auth.me?.quota_total ?? "-" }} 张
          </span>
          <span class="badge" v-if="auth.me?.name">{{ auth.me.name }}</span>
          <button class="ghost" type="button" @click="logout">退出</button>
        </div>
      </header>

      <div v-if="error" class="err ban">{{ error }}</div>

      <div ref="scroller" class="messages">
        <div v-if="loadingChat" class="muted center">加载中…</div>
        <div v-else-if="!messages.length" class="muted center tip">
          输入描述生成图片。点「基于此图修改」可进入多轮改图，每张成功出图都会扣额度。
        </div>

        <div v-for="m in messages" :key="m.id" class="msg" :class="m.role">
          <div class="bubble">
            <div class="role">{{ m.role === "user" ? "你" : "助手" }}</div>
            <div class="content">{{ m.content }}</div>
            <div v-if="m.ref_image_url && m.role === 'user'" class="ref muted">
              参考图：
              <a :href="m.ref_image_url" target="_blank" rel="noopener">打开</a>
            </div>
            <div v-if="m.image_urls?.length" class="imgs">
              <div v-for="(url, idx) in m.image_urls" :key="idx" class="img-card">
                <a :href="url" target="_blank" rel="noopener">
                  <img :src="url" :alt="'image-' + idx" loading="lazy" />
                </a>
                <div class="img-actions">
                  <button class="success" type="button" @click="useAsEditRef(url)">基于此图修改</button>
                  <a class="link" :href="url" target="_blank" rel="noopener">原图</a>
                </div>
              </div>
            </div>
            <div v-if="m.cost" class="meta muted">消耗 {{ m.cost }} 张 · {{ m.model || "" }}</div>
          </div>
        </div>
      </div>

      <footer class="composer card">
        <div v-if="editTargetUrl" class="edit-banner">
          <div class="edit-info">
            <strong>改图模式</strong>
            <span class="muted">将调用 /v1/images/edits</span>
            <a :href="editTargetUrl" target="_blank" rel="noopener">查看参考图</a>
          </div>
          <button class="ghost" type="button" @click="clearEditRef">取消改图</button>
        </div>

        <textarea
          v-model="prompt"
          :placeholder="editTargetUrl ? '描述如何修改这张图…' : '描述你想生成的图片…'"
          @keydown.enter.exact.prevent="send"
        />

        <div class="composer-bar">
          <div class="row controls">
            <label class="mini">
              张数
              <select v-model.number="n">
                <option :value="1">1</option>
                <option :value="2">2</option>
                <option :value="3">3</option>
                <option :value="4">4</option>
              </select>
            </label>
            <label class="mini grow">
              模型（可空=默认）
              <input v-model="model" placeholder="gpt-image-2" />
            </label>
          </div>
          <button
            class="primary"
            type="button"
            :disabled="sending || !prompt.trim()"
            @click="send"
          >
            {{ sending ? "生成中…" : editTargetUrl ? "提交改图" : "生成" }}
          </button>
        </div>
        <div class="muted hint">生图可能需要 30 秒～数分钟。失败不扣额度。</div>
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
.ref {
  margin-top: 8px;
  font-size: 12px;
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
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  font-size: 13px;
}
.composer-bar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: end;
  margin-top: 10px;
}
.controls {
  flex: 1;
}
.mini {
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}
.mini.grow {
  flex: 1;
  min-width: 160px;
}
.mini select,
.mini input {
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
