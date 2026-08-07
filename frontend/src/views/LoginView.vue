<script setup>
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const apiKey = ref("");
const loading = ref(false);
const error = ref("");

async function login({ replace = false } = {}) {
  error.value = "";
  loading.value = true;
  try {
    await auth.loginUser(apiKey.value.trim());
    await router[replace ? "replace" : "push"]({ name: "chat" });
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    loading.value = false;
  }
}

async function onSubmit() {
  await login();
}

onMounted(async () => {
  const queryApiKey = typeof route.query.apikey === "string" ? route.query.apikey.trim() : "";
  if (!queryApiKey) return;

  apiKey.value = queryApiKey;
  await login({ replace: true });
});
</script>

<template>
  <div class="page">
    <!-- atmosphere blobs -->
    <div class="atmo">
      <div class="blob blob-1" />
      <div class="blob blob-2" />
    </div>

    <div class="glass-panel login-card">
      <div class="brand-row">
        <span class="brand-text">VisionaryAI</span>
        <span class="badge-ver">V2.5</span>
      </div>

      <h1>对话生图</h1>
      <p class="sub">输入访问秘钥登录，使用对应额度</p>

      <form @submit.prevent="onSubmit">
        <div class="field">
          <label for="key">访问秘钥</label>
          <div class="input-wrap">
            <input
              id="key"
              v-model="apiKey"
              type="password"
              placeholder="请输入秘钥…"
              autocomplete="off"
            />
          </div>
        </div>

        <div v-if="error" class="err" style="margin-bottom: 16px">{{ error }}</div>

        <button
          class="primary"
          type="submit"
          :disabled="loading || !apiKey.trim()"
          style="width:100%"
        >
          {{ loading ? "登录中…" : "登录" }}
        </button>
      </form>

    </div>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px 16px;
  position: relative;
  overflow: hidden;
}

/* atmosphere blobs */
.atmo {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  opacity: 0.25;
}
.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
}
.blob-1 {
  top: 15%;
  right: -5%;
  width: 420px;
  height: 420px;
  background: var(--primary);
}
.blob-2 {
  bottom: 5%;
  left: -8%;
  width: 340px;
  height: 340px;
  background: var(--secondary);
}

.login-card {
  position: relative;
  z-index: 1;
  width: min(420px, 100%);
  padding: 32px 28px 28px;
}

.brand-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
}
.brand-text {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  background: var(--prismatic);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.badge-ver {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.05em;
  color: var(--primary);
  background: rgba(208, 188, 255, 0.1);
  border: 1px solid rgba(208, 188, 255, 0.2);
  padding: 2px 8px;
  border-radius: 999px;
}

h1 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 700;
  font-family: var(--font-display);
}
.sub {
  margin: 0 0 24px;
  font-size: 14px;
  color: var(--muted);
  line-height: 1.5;
}

.input-wrap {
  position: relative;
}
.input-wrap input {
  background: rgba(12, 18, 36, 0.6);
  border: 1px solid var(--border-light);
  padding: 12px 14px;
  border-radius: 0.75rem;
}
.input-wrap input:focus {
  border-color: var(--primary-2);
  box-shadow: 0 0 0 3px rgba(160, 120, 255, 0.12);
}

.foot {
  margin: 18px 0 0;
  font-size: 13px;
  text-align: center;
}
</style>
