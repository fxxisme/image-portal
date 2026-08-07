<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { apiUrl, request } from "../api/http";
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
const copyingKey = ref(false);
const copiedKey = ref(false);
const images = ref([]);
const imagesTotal = ref(0);
const loadingImages = ref(false);
const availableModels = ref([]);
const loadingModels = ref(false);
const activeTab = ref("settings");
const previewImage = ref(null);
const downloadingImage = ref(false);

const form = ref({ name: "", quota_total: 20, api_key: "" });
const settingsForm = ref({
  upstream_base_url: "",
  upstream_api_key: "",
  default_model: "gpt-image-2",
  text_to_image_models: ["gpt-image-2", "grok-imagine-image"],
  image_to_image_models: ["gpt-image-2"],
  response_format: "url",
  webdav_url: "",
  webdav_username: "",
  webdav_password: "",
  webdav_path: "",
  webdav_public_base_url: "",
});
const settingsMeta = ref({
  has_upstream_api_key: false,
  upstream_api_key_masked: "",
  updated_at: null,
  has_webdav_password: false,
  webdav_password_masked: "",
});

function uniqueModels(...groups) {
  const result = [];
  for (const group of groups) {
    for (const raw of group || []) {
      const name = String(raw || "").trim();
      if (name && !result.includes(name)) result.push(name);
    }
  }
  return result;
}

const textModelChoices = computed(() => {
  if (availableModels.value.length) {
    return uniqueModels(
      availableModels.value,
      settingsForm.value.text_to_image_models,
      [settingsForm.value.default_model],
    );
  }
  return uniqueModels(
    settingsForm.value.text_to_image_models,
    [settingsForm.value.default_model],
    ["gpt-image-2", "grok-imagine-image"],
  );
});

const imageModelChoices = computed(() => {
  if (availableModels.value.length) {
    return uniqueModels(
      availableModels.value,
      settingsForm.value.image_to_image_models,
    );
  }
  return uniqueModels(
    settingsForm.value.image_to_image_models,
    ["gpt-image-2"],
  );
});

function imagesPath(offset = 0) {
  const params = new URLSearchParams({ limit: "48", offset: String(offset) });
  return `/api/admin/images?${params}`;
}

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
      text_to_image_models: Array.isArray(s.text_to_image_models)
        ? s.text_to_image_models
        : ["gpt-image-2", "grok-imagine-image"],
      image_to_image_models: Array.isArray(s.image_to_image_models)
        ? s.image_to_image_models
        : ["gpt-image-2"],
      response_format: s.response_format || "url",
      webdav_url: s.webdav_url || "",
      webdav_username: s.webdav_username || "",
      webdav_password: "",
      webdav_path: s.webdav_path || "",
      webdav_public_base_url: s.webdav_public_base_url || "",
    };
    settingsMeta.value = {
      has_upstream_api_key: s.has_upstream_api_key,
      upstream_api_key_masked: s.upstream_api_key_masked || "",
      updated_at: s.updated_at,
      has_webdav_password: s.has_webdav_password,
      webdav_password_masked: s.webdav_password_masked || "",
    };
    if (activeTab.value === "images") await loadImages();
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

function selectTab(tab) {
  activeTab.value = tab;
  if (tab === "images" && !images.value.length) loadImages();
}

async function fetchUpstreamModels() {
  loadingModels.value = true;
  error.value = "";
  try {
    const data = await request("/api/admin/upstream-models", { token: auth.adminToken });
    availableModels.value = Array.isArray(data.models) ? data.models : [];
    settingsMsg.value = `已获取 ${availableModels.value.length} 个模型，请勾选后保存`;
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    loadingModels.value = false;
  }
}

function openPreview(image) {
  previewImage.value = image;
}

function closePreview() {
  if (!downloadingImage.value) previewImage.value = null;
}

async function downloadPreview() {
  const image = previewImage.value;
  if (!image || downloadingImage.value) return;
  downloadingImage.value = true;
  try {
    const response = await fetch(apiUrl(`/api/admin/images/${image.id}/download`), {
      headers: { Authorization: `Bearer ${auth.adminToken}` },
    });
    if (!response.ok) throw new Error(`下载失败（HTTP ${response.status}）`);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `image-${image.id}`;
    link.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    downloadingImage.value = false;
  }
}

async function loadImages(append = false) {
  loadingImages.value = true;
  try {
    const offset = append ? images.value.length : 0;
    const data = await request(imagesPath(offset), { token: auth.adminToken });
    images.value = append ? [...images.value, ...(data.items || [])] : (data.items || []);
    imagesTotal.value = data.total || 0;
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    loadingImages.value = false;
  }
}

async function saveSettings() {
  if (
    !settingsForm.value.text_to_image_models.length ||
    !settingsForm.value.image_to_image_models.length
  ) {
    error.value = "文生图和图生图至少各选择一个模型";
    return;
  }
  savingSettings.value = true;
  error.value = "";
  settingsMsg.value = "";
  try {
    const body = {
      upstream_base_url: settingsForm.value.upstream_base_url.trim(),
      default_model: settingsForm.value.default_model.trim() || "gpt-image-2",
      text_to_image_models: settingsForm.value.text_to_image_models,
      image_to_image_models: settingsForm.value.image_to_image_models,
      response_format: settingsForm.value.response_format || "url",
      webdav_url: settingsForm.value.webdav_url.trim(),
      webdav_username: settingsForm.value.webdav_username.trim(),
      webdav_path: settingsForm.value.webdav_path.trim(),
      webdav_public_base_url: settingsForm.value.webdav_public_base_url.trim(),
    };
    const keyInput = settingsForm.value.upstream_api_key.trim();
    if (keyInput) body.upstream_api_key = keyInput;
    const webdavPassword = settingsForm.value.webdav_password.trim();
    if (webdavPassword) body.webdav_password = webdavPassword;

    const s = await request("/api/admin/settings", {
      method: "PUT",
      token: auth.adminToken,
      body,
    });
    settingsForm.value.upstream_api_key = "";
    settingsForm.value.webdav_password = "";
    settingsMeta.value = {
      has_upstream_api_key: s.has_upstream_api_key,
      upstream_api_key_masked: s.upstream_api_key_masked || "",
      updated_at: s.updated_at,
      has_webdav_password: s.has_webdav_password,
      webdav_password_masked: s.webdav_password_masked || "",
    };
    settingsForm.value.upstream_base_url = s.upstream_base_url || "";
    settingsForm.value.default_model = s.default_model || "gpt-image-2";
    settingsForm.value.text_to_image_models = Array.isArray(s.text_to_image_models)
      ? s.text_to_image_models
      : ["gpt-image-2", "grok-imagine-image"];
    settingsForm.value.image_to_image_models = Array.isArray(s.image_to_image_models)
      ? s.image_to_image_models
      : ["gpt-image-2"];
    settingsForm.value.response_format = s.response_format || "url";
    settingsForm.value.webdav_url = s.webdav_url || "";
    settingsForm.value.webdav_username = s.webdav_username || "";
    settingsForm.value.webdav_path = s.webdav_path || "";
    settingsForm.value.webdav_public_base_url = s.webdav_public_base_url || "";
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
  copiedKey.value = false;
  try {
    const item = await request("/api/admin/keys", {
      method: "POST",
      token: auth.adminToken,
      body: {
        name: form.value.name || "未命名",
        quota_total: Number(form.value.quota_total) || 0,
        api_key: form.value.api_key.trim() || undefined,
      },
    });
    createdKey.value = item.api_key;
    form.value = { name: "", quota_total: 20, api_key: "" };
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

async function copyCreated() {
  if (!createdKey.value || copyingKey.value) return;
  copyingKey.value = true;
  error.value = "";
  try {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(createdKey.value);
        copiedKey.value = true;
        return;
      } catch {
        // Clipboard API may be unavailable on non-secure origins or without permission.
      }
    }

    const textarea = document.createElement("textarea");
    textarea.value = createdKey.value;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    let copied = false;
    try {
      textarea.select();
      copied = document.execCommand("copy");
    } finally {
      textarea.remove();
    }
    if (!copied) throw new Error("copy failed");
    copiedKey.value = true;
  } catch {
    copiedKey.value = false;
    error.value = "复制失败，请手动选择秘钥复制";
  } finally {
    copyingKey.value = false;
  }
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

    <nav class="admin-tabs" aria-label="后台页面">
      <button
        type="button"
        :class="{ active: activeTab === 'settings' }"
        @click="selectTab('settings')"
      >
        系统配置
      </button>
      <button
        type="button"
        :class="{ active: activeTab === 'images' }"
        @click="selectTab('images')"
      >
        全部图片
      </button>
    </nav>

    <!-- 上游配置 -->
    <section v-if="activeTab === 'settings'" class="glass-panel section-card">
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
          <select v-model="settingsForm.default_model">
            <option v-for="modelName in textModelChoices" :key="modelName" :value="modelName">
              {{ modelName }}
            </option>
          </select>
        </div>
        <div class="field">
          <label>response_format</label>
          <select v-model="settingsForm.response_format">
            <option value="url">url</option>
            <option value="b64_json">b64_json</option>
          </select>
        </div>
      </div>

      <h2 class="subsection-title">可用模型</h2>
      <p class="muted tip">
        先保存上游连接，再从 <span class="mono">/v1/models</span> 获取模型；勾选后保存到文生图和图生图配置。
      </p>
      <div class="model-config-head">
        <button class="ghost" type="button" :disabled="loadingModels" @click="fetchUpstreamModels">
          {{ loadingModels ? "获取中…" : "从上游获取模型" }}
        </button>
        <span v-if="availableModels.length" class="muted">
          已获取 {{ availableModels.length }} 个模型
        </span>
      </div>
      <div class="model-config-grid">
        <div class="model-config-group">
          <h3>文生图可用模型</h3>
          <label v-for="modelName in textModelChoices" :key="`text-${modelName}`" class="model-option">
            <input v-model="settingsForm.text_to_image_models" type="checkbox" :value="modelName" />
            <span>{{ modelName }}</span>
          </label>
        </div>
        <div class="model-config-group">
          <h3>图生图可用模型</h3>
          <label v-for="modelName in imageModelChoices" :key="`edit-${modelName}`" class="model-option">
            <input v-model="settingsForm.image_to_image_models" type="checkbox" :value="modelName" />
            <span>{{ modelName }}</span>
          </label>
        </div>
      </div>

      <h2 class="subsection-title">WebDAV 存储</h2>
      <p class="muted tip">
        新图按日期保存；远端目录留空时使用 image-portal。公开访问基址留空时将使用 WebDAV 地址。
      </p>
      <div class="settings-grid">
        <div class="field">
          <label>WebDAV URL</label>
          <input v-model="settingsForm.webdav_url" type="url" placeholder="https://dav.example.com/remote.php/dav/files/user" />
        </div>
        <div class="field">
          <label>WebDAV 用户名</label>
          <input v-model="settingsForm.webdav_username" autocomplete="username" placeholder="用户名" />
        </div>
        <div class="field">
          <label>
            WebDAV 密码
            <span v-if="settingsMeta.has_webdav_password" class="muted">（当前 {{ settingsMeta.webdav_password_masked }}）</span>
            <span v-else class="muted">（未配置）</span>
          </label>
          <input v-model="settingsForm.webdav_password" type="password" autocomplete="new-password" placeholder="留空则不修改" />
        </div>
        <div class="field">
          <label>远端目录</label>
          <input v-model="settingsForm.webdav_path" placeholder="留空使用 image-portal" />
        </div>
        <div class="field settings-wide">
          <label>公开访问基址</label>
          <input v-model="settingsForm.webdav_public_base_url" type="url" placeholder="https://cdn.example.com/image-portal（留空使用 WebDAV URL）" />
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

    <section v-else class="glass-panel section-card">
      <div class="gallery-heading">
        <div>
          <h2>全部生成图片</h2>
          <p class="muted tip">共 {{ imagesTotal }} 张，按生成时间倒序展示。</p>
        </div>
        <div class="gallery-tools">
          <button class="ghost" type="button" :disabled="loadingImages" @click="loadImages()">
            刷新图片
          </button>
        </div>
      </div>
      <div v-if="images.length" class="image-grid">
        <button
          v-for="image in images"
          :key="image.id"
          type="button"
          class="image-item"
          @click="openPreview(image)"
        >
          <img :src="image.public_url" :alt="image.prompt || '生成图片'" loading="lazy" />
          <div class="image-meta">
            <span>#{{ image.api_key_id }} · {{ image.api_key_name }}</span>
            <span>{{ image.action === 'edit' ? '改图' : '生成' }}</span>
          </div>
          <div class="image-prompt">{{ image.prompt || '无提示词' }}</div>
          <time>{{ new Date(image.created_at).toLocaleString() }}</time>
        </button>
      </div>
      <div v-else class="muted gallery-empty">{{ loadingImages ? "图片加载中…" : "暂无生成图片" }}</div>
      <div v-if="images.length < imagesTotal" class="gallery-more">
        <button class="ghost" type="button" :disabled="loadingImages" @click="loadImages(true)">
          {{ loadingImages ? "加载中…" : "加载更多" }}
        </button>
      </div>
    </section>

    <div v-if="previewImage" class="preview-backdrop" role="presentation" @click.self="closePreview">
      <section class="preview-dialog" role="dialog" aria-modal="true" aria-label="图片预览">
        <div class="preview-bar">
          <div class="preview-title">图片预览</div>
          <div class="preview-actions">
            <button class="primary" type="button" :disabled="downloadingImage" @click="downloadPreview">
              {{ downloadingImage ? "下载中…" : "下载原图" }}
            </button>
            <button class="ghost preview-close" type="button" aria-label="关闭预览" @click="closePreview">×</button>
          </div>
        </div>
        <img :src="previewImage.public_url" :alt="previewImage.prompt || '生成图片'" />
        <p v-if="previewImage.prompt" class="preview-prompt">{{ previewImage.prompt }}</p>
      </section>
    </div>

    <!-- 新建秘钥 -->
    <section v-if="activeTab === 'settings'" class="glass-panel section-card">
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
        <div class="field" style="margin:0">
          <label>自定义秘钥（可选）</label>
          <input
            v-model="form.api_key"
            type="text"
            maxlength="128"
            placeholder="留空自动生成；8-128 位字母、数字、_、-"
            autocomplete="off"
            spellcheck="false"
          />
        </div>
        <div class="actions">
          <button class="primary" type="button" @click="createKey">创建</button>
        </div>
      </div>
      <div v-if="createdKey" class="created">
        <div class="ok">创建成功。明文秘钥仅显示一次，请立即复制发给用户：</div>
        <div class="mono keyline">{{ createdKey }}</div>
        <button class="ghost" type="button" :disabled="copyingKey" @click="copyCreated">
          {{ copyingKey ? "复制中…" : copiedKey ? "已复制" : "复制" }}
        </button>
      </div>
    </section>

    <!-- 秘钥列表 -->
    <section v-if="activeTab === 'settings'" class="glass-panel section-card">
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
    <section v-if="activeTab === 'settings'" class="glass-panel section-card">
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
.admin-tabs {
  position: relative;
  z-index: 1;
  display: inline-flex;
  gap: 2px;
  margin-bottom: 20px;
  padding: 3px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: rgba(6, 14, 32, 0.5);
}
.admin-tabs button {
  padding: 8px 14px;
  border-radius: 5px;
  background: transparent;
  color: var(--muted);
}
.admin-tabs button:hover { color: var(--text); }
.admin-tabs button.active {
  background: rgba(160, 120, 255, 0.18);
  color: var(--text);
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
.settings-wide { grid-column: span 2; }
.model-config-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.model-config-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.model-config-group {
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-light);
  border-radius: 0.75rem;
  background: rgba(12, 18, 36, 0.35);
}
.model-config-group h3 {
  margin: 0 0 10px;
  font-size: 14px;
}
.model-option {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  margin: 0;
  color: var(--text);
  cursor: pointer;
  word-break: break-word;
}
.model-option input {
  flex: 0 0 auto;
  width: 16px;
  height: 16px;
  margin: 0;
  accent-color: var(--primary-2);
}
.subsection-title {
  margin-top: 26px;
  padding-top: 20px;
  border-top: 1px solid var(--border-light);
}

.form-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 2fr auto;
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
.gallery-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}
.gallery-heading h2 { margin-bottom: 4px; }
.gallery-heading .tip { margin: 0; }
.gallery-tools {
  display: flex;
  gap: 8px;
  align-items: center;
}
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}
.image-item {
  display: block;
  padding: 0;
  text-align: left;
  font-weight: 400;
  font-family: var(--font-body);
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: rgba(6, 14, 32, 0.72);
  color: var(--text);
}
.image-item:hover { border-color: var(--primary-2); color: var(--text); }
.image-item:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}
.image-item img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  background: var(--bg-2);
}
.image-meta, .image-prompt, .image-item time { display: block; padding: 0 10px; }
.image-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding-top: 9px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--primary);
}
.image-prompt {
  margin-top: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.image-item time { padding-bottom: 10px; margin-top: 5px; font-size: 10px; color: var(--muted-2); }
.gallery-empty { padding: 30px 0; text-align: center; }
.gallery-more { display: flex; justify-content: center; margin-top: 16px; }
.preview-backdrop {
  position: fixed;
  z-index: 20;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(2, 5, 13, 0.78);
}
.preview-dialog {
  width: min(1100px, 100%);
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-2);
  box-shadow: var(--shadow);
}
.preview-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-light);
}
.preview-title { font-weight: 700; font-size: 14px; }
.preview-actions { display: flex; gap: 8px; align-items: center; }
.preview-close {
  width: 36px;
  height: 36px;
  padding: 0;
  font-size: 22px;
  line-height: 1;
}
.preview-dialog > img {
  display: block;
  width: 100%;
  min-height: 0;
  flex: 1;
  object-fit: contain;
  background: #050814;
}
.preview-prompt {
  max-height: 96px;
  margin: 0;
  padding: 12px 14px;
  overflow: auto;
  border-top: 1px solid var(--border-light);
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
}
.status-pill {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
}

@media (max-width: 720px) {
  .form-grid,
  .settings-grid,
  .model-config-grid {
    grid-template-columns: 1fr;
  }
  .settings-wide { grid-column: auto; }
  .gallery-heading { flex-direction: column; }
  .gallery-tools { width: 100%; }
  .preview-backdrop { padding: 12px; }
  .preview-dialog { max-height: calc(100vh - 24px); }
}
</style>
