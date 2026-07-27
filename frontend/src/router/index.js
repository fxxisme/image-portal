import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../stores/auth";
import LoginView from "../views/LoginView.vue";
import ChatView from "../views/ChatView.vue";
import AdminLoginView from "../views/AdminLoginView.vue";
import AdminView from "../views/AdminView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: LoginView, meta: { guest: true } },
    { path: "/", name: "chat", component: ChatView, meta: { requiresUser: true } },
    { path: "/admin/login", name: "admin-login", component: AdminLoginView },
    { path: "/admin", name: "admin", component: AdminView, meta: { requiresAdmin: true } },
  ],
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.meta.requiresUser && !auth.isUserLoggedIn) return { name: "login" };
  if (to.meta.requiresAdmin && !auth.isAdminLoggedIn) return { name: "admin-login" };
  if (to.name === "login" && auth.isUserLoggedIn) return { name: "chat" };
  if (to.name === "admin-login" && auth.isAdminLoggedIn) return { name: "admin" };
  return true;
});

export default router;
