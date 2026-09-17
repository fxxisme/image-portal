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
  background: var(--bg);
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
  margin-bottom: 24px;
}
.brand-text {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
  background: var(--primary-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.badge-ver {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.05em;
  color: var(--secondary);
  background: var(--bg-surface);
  border: 1px solid var(--border-light);
  padding: 2px 8px;
  border-radius: 6px;
}

h1 {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 700;
  font-family: var(--font-display);
}
.sub {
  margin: 0 0 28px;
  font-size: 14px;
  color: var(--muted);
  line-height: 1.5;
}

.input-wrap {
  position: relative;
}
.input-wrap input {
  background: var(--input);
  border: 1px solid var(--border);
  padding: 14px 16px;
  border-radius: 8px;
  font-size: 15px;
}
.input-wrap input:focus {
  border-color: var(--border-focus);
}

.foot {
  margin: 20px 0 0;
  font-size: 13px;
  text-align: center;
}
</style>
