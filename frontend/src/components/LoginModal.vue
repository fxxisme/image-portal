<script setup>
import { ref } from "vue";
import { useAuthStore } from "../stores/auth";

defineProps({
  show: { type: Boolean, default: false },
});
const emit = defineEmits(["close", "success"]);
const auth = useAuthStore();
const apiKey = ref("");
const loading = ref(false);
const error = ref("");

const handleSubmit = async () => {
  const key = apiKey.value.trim();
  if (!key) return;
  loading.value = true;
  error.value = "";

  try {
    await auth.loginUser(key);
    emit("success");
    emit("close");
  } catch (e) {
    error.value = e.message || "秘钥输入错误";
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <div v-if="show" class="overlay">
    <div class="panel glass-panel">
      <h3>输入秘钥重新登录</h3>
      <input
        v-model="apiKey"
        placeholder="粘贴你的秘钥..."
        class="api-key-input"
      />
      <button class="primary" @click="handleSubmit" :disabled="loading">
        {{ loading ? "登录中..." : "登录" }}
      </button>
      <p v-if="error" class="error">{{ error }}</p>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(0,0,0,0.7);
  display: grid;
  place-items: center;
  padding: 20px;
}
.panel {
  width: 100%;
  max-width: 420px;
  background: var(--bg);
  border-radius: 16px;
  padding: 32px 24px;
  text-align: center;
}
.api-key-input {
  width: 100%;
  padding: 12px;
  margin: 12px 0;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  font-size: 14px;
}
.error { color: #f56; margin-top: 8px; }
</style>
