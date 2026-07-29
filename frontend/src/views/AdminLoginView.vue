<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const password = ref("");
const loading = ref(false);
const error = ref("");

async function onSubmit() {
  error.value = "";
  loading.value = true;
  try {
    await auth.loginAdmin(password.value);
    router.push({ name: "admin" });
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    loading.value = false;
  }
}
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
        <span class="badge-admin">Admin</span>
      </div>

      <h1>管理后台</h1>
      <p class="sub">单管理员口令登录，用于分配秘钥与额度</p>

      <form @submit.prevent="onSubmit">
        <div class="field">
          <label for="pwd">管理员口令</label>
          <input
            id="pwd"
            v-model="password"
            type="password"
            placeholder="请输入口令…"
            autocomplete="current-password"
          />
        </div>

        <div v-if="error" class="err" style="margin-bottom: 16px">{{ error }}</div>

        <button
          class="primary"
          type="submit"
          :disabled="loading || !password"
          style="width:100%"
        >
          {{ loading ? "登录中…" : "登录" }}
        </button>
      </form>

      <p class="foot">
        <router-link to="/login">返回用户登录</router-link>
      </p>
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
.badge-admin {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.05em;
  color: var(--tertiary);
  background: rgba(255, 175, 211, 0.1);
  border: 1px solid rgba(255, 175, 211, 0.2);
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

input {
  background: rgba(12, 18, 36, 0.6);
  border: 1px solid var(--border-light);
  padding: 12px 14px;
  border-radius: 0.75rem;
}

.foot {
  margin: 18px 0 0;
  font-size: 13px;
  text-align: center;
}
</style>
