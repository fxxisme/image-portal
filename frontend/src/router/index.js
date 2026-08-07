import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../stores/auth";
import LoginView from "../views/LoginView.vue";
import ChatView from "../views/ChatView.vue";
import VideoView from "../views/VideoView.vue";
import AdminLoginView from "../views/AdminLoginView.vue";
import AdminView from "../views/AdminView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: LoginView },
    { path: "/", name: "chat", component: ChatView, meta: { requiresUser: true } },
    { path: "/video", name: "video", component: VideoView, meta: { requiresUser: true } },
    { path: "/admin/login", name: "admin-login", component: AdminLoginView },
    { path: "/admin", name: "admin", component: AdminView, meta: { requiresAdmin: true } },
  ],
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  const apiKey = typeof to.query.apikey === "string" ? to.query.apikey.trim() : "";

  if (to.meta.requiresAdmin && !auth.isAdminLoggedIn) return { name: "admin-login" };
  if (to.name === "admin-login" && auth.isAdminLoggedIn) return { name: "admin" };
  if (apiKey && to.name !== "login") {
    return { name: "login", query: { apikey: apiKey }, replace: true };
  }
  if (to.name === "login" && auth.isUserLoggedIn && !apiKey) return { name: "chat" };

  if (to.meta.requiresUser && !auth.isUserLoggedIn) return { name: "login", query: to.query };

  return true;
});

export default router;
