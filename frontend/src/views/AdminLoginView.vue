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
    <div class="card box">
      <h1>管理后台</h1>
      <p class="muted sub">单管理员口令登录，用于分配秘钥与额度。</p>
      <form @submit.prevent="onSubmit">
        <div class="field">
          <label for="pwd">管理员口令</label>
          <input id="pwd" v-model="password" type="password" autocomplete="current-password" />
        </div>
        <div v-if="error" class="err" style="margin-bottom: 12px">{{ error }}</div>
        <button class="primary" type="submit" :disabled="loading || !password" style="width: 100%">
          {{ loading ? "登录中…" : "登录" }}
        </button>
      </form>
      <p class="muted foot"><router-link to="/login">返回用户登录</router-link></p>
    </div>
  </div>
</template>

<style scoped>
.page {
  min-height: 100%;
  display: grid;
  place-items: center;
  padding: 24px 16px;
}
.box {
  width: min(420px, 100%);
}
h1 {
  margin: 0 0 6px;
  font-size: 22px;
}
.sub {
  margin: 0 0 18px;
  font-size: 13px;
}
.foot {
  margin: 16px 0 0;
  font-size: 12px;
}
</style>
