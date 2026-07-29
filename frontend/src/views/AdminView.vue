<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { request } from "../api/http";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();

const keys = ref([]);
const usage = ref([]);
const loading = ref(false);
const savingSettings = ref(false);
const error = ref("");
const settingsMsg = ref("");
const createdKey = ref("");

const form = ref({ name: "", quota_total: 20 });
const settingsForm = ref({
  upstream_base_url: "",
  upstream_api_key: "",
  default_model: "gpt-image-2",
  response_format: "url",
});
const settingsMeta = ref({
  has_upstream_api_key: false,
  upstream_api_key_masked: "",
  updated_at: null,
});

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [k, u, s] = await Promise.all([
      request("/api/admin/keys", { token: auth.adminToken }),
      request("/api/admin/usage?limit=50", { token: auth.adminToken }),
      request("/api/admin/settings", { token: auth.adminToken }),
    ]);
    keys.value = k;
    usage.value = u;
    settingsForm.value = {
      upstream_base_url: s.upstream_base_url || "",
      upstream_api_key: "",
      default_model: s.default_model || "gpt-image-2",
      response_format: s.response_format || "url",
    };
    settingsMeta.value = {
      has_upstream_api_key: s.has_upstream_api_key,
      upstream_api_key_masked: s.upstream_api_key_masked || "",
      updated_at: s.updated_at,
    };
  } catch (e) {
    error.value = e.message || String(e);
    if (e.status === 401 || e.status === 403) {
      auth.logoutAdmin();
      router.push({ name: "admin-login" });
    }
  } finally {
    loading.value = false;
  }
}

async function saveSettings() {
  savingSettings.value = true;
  error.value = "";
  settingsMsg.value = "";
  try {
    const body = {
      upstream_base_url: settingsForm.value.upstream_base_url.trim(),
      default_model: settingsForm.value.default_model.trim() || "gpt-image-2",
      response_format: settingsForm.value.response_format || "url",
    };
    const keyInput = settingsForm.value.upstream_api_key.trim();
    if (keyInput) body.upstream_api_key = keyInput;

    const s = await request("/api/admin/settings", {
      method: "PUT",
      token: auth.adminToken,
      body,
    });
    settingsForm.value.upstream_api_key = "";
    settingsMeta.value = {
      has_upstream_api_key: s.has_upstream_api_key,
      upstream_api_key_masked: s.upstream_api_key_masked || "",
      updated_at: s.updated_at,
    };
    settingsForm.value.upstream_base_url = s.upstream_base_url || "";
    settingsForm.value.default_model = s.default_model || "gpt-image-2";
    settingsForm.value.response_format = s.response_format || "url";
    settingsMsg.value = "上游配置已保存";
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    savingSettings.value = false;
  }
}

async function createKey() {
  error.value = "";
  createdKey.value = "";
  try {
    const item = await request("/api/admin/keys", {
      method: "POST",
      token: auth.adminToken,
      body: {
        name: form.value.name || "未命名",
        quota_total: Number(form.value.quota_total) || 0,
      },
    });
    createdKey.value = item.api_key;
    form.value = { name: "", quota_total: 20 };
    await load();
  } catch (e) {
    error.value = e.message || String(e);
  }
}

async function toggleEnabled(row) {
  try {
    await request(`/api/admin/keys/${row.id}`, {
      method: "PATCH",
      token: auth.adminToken,
      body: { enabled: !row.enabled },
    });
    await load();
  } catch (e) {
    error.value = e.message || String(e);
  }
}

async function adjustQuota(row) {
  const raw = window.prompt("设置总额度（张）", String(row.quota_total));
  if (raw == null) return;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0) {
    error.value = "额度必须是非负数字";
    return;
  }
  try {
    await request(`/api/admin/keys/${row.id}`, {
      method: "PATCH",
      token: auth.adminToken,
      body: { quota_total: n },
    });
    await load();
  } catch (e) {
    error.value = e.message || String(e);
  }
}

async function removeKey(row) {
  if (!window.confirm(`确认删除秘钥 ${row.key_prefix}… / ${row.name}？`)) return;
  try {
    await request(`/api/admin/keys/${row.id}`, {
      method: "DELETE",
      token: auth.adminToken,
    });
    await load();
  } catch (e) {
    error.value = e.message || String(e);
  }
}

function logout() {
  auth.logoutAdmin();
  router.push({ name: "admin-login" });
}

function copyCreated() {
  if (!createdKey.value) return;
  navigator.clipboard?.writeText(createdKey.value);
}

onMounted(load);
</script>

<template>
  <div class="layout">
    <!-- atmosphere -->
    <div class="atmo">
      <div class="blob blob-1" />
      <div class="blob blob-2" />
    </div>

    <header class="top">
      <div>
        <h1>
          <span class="brand-text">VisionaryAI</span>
          <span class="admin-chip">Admin</span>
        </h1>
        <p class="muted">上游配置 · 秘钥额度 · 用量</p>
      </div>
      <div class="top-btns">
        <button class="ghost" type="button" :disabled="loading" @click="load">刷新</button>
        <button class="ghost" type="button" @click="logout">退出</button>
      </div>
    </header>

    <div v-if="error" class="err" style="margin-bottom: 16px">{{ error }}</div>

    <!-- 上游配置 -->
    <section class="glass-panel section-card">
      <h2>上游连接</h2>
      <p class="muted tip">
        配置 chatgpt2api / New API。API Key 仅在填写时更新；留空表示保持原值。
      </p>
      <div class="settings-grid">
        <div class="field">
          <label>Upstream Base URL</label>
          <input v-model="settingsForm.upstream_base_url" type="url" placeholder="https://xx.xx.com" />
        </div>
        <div class="field">
          <label>
            Upstream API Key
            <span v-if="settingsMeta.has_upstream_api_key" class="muted">（当前 {{ settingsMeta.upstream_api_key_masked }}）</span>
            <span v-else class="muted">（未配置）</span>
          </label>
          <input v-model="settingsForm.upstream_api_key" type="password" placeholder="留空则不修改" autocomplete="off" />
        </div>
        <div class="field">
          <label>默认模型</label>
          <input v-model="settingsForm.default_model" placeholder="gpt-image-2" />
        </div>
        <div class="field">
          <label>response_format</label>
          <select v-model="settingsForm.response_format">
            <option value="url">url</option>
            <option value="b64_json">b64_json</option>
          </select>
        </div>
      </div>
      <div class="settings-foot">
        <button class="primary" type="button" :disabled="savingSettings" @click="saveSettings">
          {{ savingSettings ? "保存中…" : "保存上游配置" }}
        </button>
        <span v-if="settingsMsg" class="ok">{{ settingsMsg }}</span>
        <span v-if="settingsMeta.updated_at" class="muted mono">
          更新于 {{ new Date(settingsMeta.updated_at).toLocaleString() }}
        </span>
      </div>
    </section>

    <!-- 新建秘钥 -->
    <section class="glass-panel section-card">
      <h2>新建秘钥</h2>
      <div class="form-grid">
        <div class="field" style="margin:0">
          <label>名称</label>
          <input v-model="form.name" placeholder="例如：张三 / 测试" />
        </div>
        <div class="field" style="margin:0">
          <label>额度（张）</label>
          <input v-model.number="form.quota_total" type="number" min="0" />
        </div>
        <div class="actions">
          <button class="primary" type="button" @click="createKey">创建</button>
        </div>
      </div>
      <div v-if="createdKey" class="created">
        <div class="ok">创建成功。明文秘钥仅显示一次，请立即复制发给用户：</div>
        <div class="mono keyline">{{ createdKey }}</div>
        <button class="ghost" type="button" @click="copyCreated">复制</button>
      </div>
    </section>

    <!-- 秘钥列表 -->
    <section class="glass-panel section-card">
      <h2>秘钥列表</h2>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>名称</th>
              <th>前缀</th>
              <th>额度</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="k in keys" :key="k.id">
              <td class="mono">{{ k.id }}</td>
              <td>{{ k.name }}</td>
              <td class="mono">{{ k.key_prefix }}…</td>
              <td>
                已用 {{ k.quota_used }} / 共 {{ k.quota_total }}
                <div class="muted">剩余 {{ k.quota_remaining }}</div>
              </td>
              <td>
                <span :class="k.enabled ? 'ok' : 'err'" class="status-pill">
                  {{ k.enabled ? "启用" : "禁用" }}
                </span>
              </td>
              <td class="row">
                <button class="ghost" type="button" @click="adjustQuota(k)">改额度</button>
                <button class="ghost" type="button" @click="toggleEnabled(k)">
                  {{ k.enabled ? "禁用" : "启用" }}
                </button>
                <button class="danger" type="button" @click="removeKey(k)">删除</button>
              </td>
            </tr>
            <tr v-if="!keys.length">
              <td colspan="6" class="muted">暂无秘钥</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 用量 -->
    <section class="glass-panel section-card">
      <h2>最近用量</h2>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>时间</th>
              <th>Key</th>
              <th>动作</th>
              <th>张数</th>
              <th>模型</th>
              <th>结果</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in usage" :key="u.id">
              <td class="mono">{{ new Date(u.created_at).toLocaleString() }}</td>
              <td>#{{ u.api_key_id }}</td>
              <td>{{ u.action }}</td>
              <td>{{ u.cost }}</td>
              <td class="mono">{{ u.model || "-" }}</td>
              <td>
                <span :class="u.success ? 'ok' : 'err'" class="status-pill">
                  {{ u.success ? "成功" : "失败" }}
                </span>
                <div v-if="u.detail" class="muted mono">{{ u.detail }}</div>
              </td>
            </tr>
            <tr v-if="!usage.length">
              <td colspan="6" class="muted">暂无记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.layout {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 16px 48px;
  position: relative;
}

/* atmosphere */
.atmo {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  opacity: 0.16;
}
.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(120px);
}
.blob-1 {
  top: 10%;
  right: -5%;
  width: 400px;
  height: 400px;
  background: var(--primary);
}
.blob-2 {
  bottom: 5%;
  left: -8%;
  width: 320px;
  height: 320px;
  background: var(--secondary);
}

/* top */
.top {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 20px;
}
.top-btns {
  display: flex;
  gap: 8px;
}
h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-text {
  font-family: var(--font-display);
  background: var(--prismatic);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.admin-chip {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--tertiary);
  background: rgba(255, 175, 211, 0.1);
  border: 1px solid rgba(255, 175, 211, 0.2);
  padding: 2px 8px;
  border-radius: 999px;
}
.top p {
  margin: 4px 0 0;
  font-size: 13px;
}

/* section card */
.section-card {
  position: relative;
  z-index: 1;
  margin-bottom: 20px;
  padding: 24px;
}
h2 {
  margin: 0 0 10px;
  font-size: 17px;
  font-weight: 700;
  font-family: var(--font-display);
}
.tip {
  margin: -2px 0 18px;
  font-size: 13px;
  line-height: 1.55;
}

.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.settings-foot {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: 14px;
  flex-wrap: wrap;
}

.form-grid {
  display: grid;
  grid-template-columns: 2fr 1fr auto;
  gap: 14px;
  align-items: end;
}
.actions {
  display: flex;
  align-items: end;
}

.created {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-light);
}
.keyline {
  margin: 10px 0;
  padding: 12px 14px;
  border-radius: 0.75rem;
  background: rgba(12, 18, 36, 0.6);
  border: 1px solid var(--border-light);
  word-break: break-all;
  font-size: 13px;
}

.table-wrap { overflow: auto; }
.status-pill {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
}

@media (max-width: 720px) {
  .form-grid,
  .settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>
