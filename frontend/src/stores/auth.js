import { defineStore } from "pinia";
import { request } from "../api/http";

const USER_TOKEN_KEY = "image_portal_user_token";
const ADMIN_TOKEN_KEY = "image_portal_admin_token";
const GUEST_DEVICE_KEY = "image_portal_guest_device";
const IS_GUEST_KEY = "image_portal_is_guest";

function getDeviceId() {
  let id = localStorage.getItem(GUEST_DEVICE_KEY);
  if (!id) {
    id = crypto.randomUUID?.() || Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(GUEST_DEVICE_KEY, id);
  }
  return id;
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    userToken: localStorage.getItem(USER_TOKEN_KEY) || "",
    adminToken: localStorage.getItem(ADMIN_TOKEN_KEY) || "",
    me: null,
    isGuest: localStorage.getItem(IS_GUEST_KEY) === "1",
  }),
  getters: {
    isUserLoggedIn: (s) => !!s.userToken,
    isAdminLoggedIn: (s) => !!s.adminToken,
  },
  actions: {
    async loginUser(apiKey) {
      const data = await request("/api/auth/login", {
        method: "POST",
        body: { api_key: apiKey },
      });
      this.userToken = data.access_token;
      this.isGuest = false;
      localStorage.setItem(USER_TOKEN_KEY, this.userToken);
      localStorage.removeItem(IS_GUEST_KEY);
      await this.fetchMe();
    },
    async guestRegister() {
      const data = await request("/api/auth/guest-register", {
        method: "POST",
        body: { device_id: getDeviceId() },
      });
      this.userToken = data.access_token;
      this.isGuest = true;
      localStorage.setItem(USER_TOKEN_KEY, this.userToken);
      localStorage.setItem(IS_GUEST_KEY, "1");
      await this.fetchMe();
    },
    async fetchMe() {
      if (!this.userToken) {
        this.me = null;
        return null;
      }
      this.me = await request("/api/auth/me", { token: this.userToken });
      return this.me;
    },
    logoutUser() {
      this.userToken = "";
      this.me = null;
      this.isGuest = false;
      localStorage.removeItem(USER_TOKEN_KEY);
      localStorage.removeItem(IS_GUEST_KEY);
    },
    async loginAdmin(password) {
      const data = await request("/api/admin/login", {
        method: "POST",
        body: { password },
      });
      this.adminToken = data.access_token;
      localStorage.setItem(ADMIN_TOKEN_KEY, this.adminToken);
    },
    logoutAdmin() {
      this.adminToken = "";
      localStorage.removeItem(ADMIN_TOKEN_KEY);
    },
    setQuotaRemaining(n) {
      if (this.me) this.me.quota_remaining = n;
    },
  },
});
