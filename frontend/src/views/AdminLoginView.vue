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
  margin-bottom: 20px;
}
.brand-text {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
}
.badge-admin {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.05em;
  color: var(--tertiary);
  background: #352b1a;
  border: 1px solid #735d32;
  padding: 2px 8px;
  border-radius: 4px;
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
  background: var(--input);
  border: 1px solid var(--border-light);
  padding: 12px 14px;
  border-radius: 6px;
}

.foot {
  margin: 18px 0 0;
  font-size: 13px;
  text-align: center;
}
</style>
