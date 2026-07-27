<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const apiKey = ref("");
const loading = ref(false);
const error = ref("");

async function onSubmit() {
  error.value = "";
  loading.value = true;
  try {
    await auth.loginUser(apiKey.value.trim());
    router.push({ name: "chat" });
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
      <h1>对话生图</h1>
      <p class="muted sub">使用分配的秘钥登录。成功出图后按张数扣减额度。</p>

      <form @submit.prevent="onSubmit">
        <div class="field">
          <label for="key">访问秘钥</label>
          <input id="key" v-model="apiKey" type="password" placeholder="请输入秘钥" autocomplete="off" />
        </div>
        <div v-if="error" class="err" style="margin-bottom: 12px">{{ error }}</div>
        <button class="primary" type="submit" :disabled="loading || !apiKey.trim()" style="width: 100%">
          {{ loading ? "登录中…" : "登录" }}
        </button>
      </form>
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
</style>
