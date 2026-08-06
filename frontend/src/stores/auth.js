import { defineStore } from "pinia";
import { request } from "../api/http";

const USER_TOKEN_KEY = "image_portal_user_token";
const ADMIN_TOKEN_KEY = "image_portal_admin_token";
const LEGACY_GUEST_KEY = "image_portal_is_guest";

function getStoredUserToken() {
  if (localStorage.getItem(LEGACY_GUEST_KEY) === "1") {
    localStorage.removeItem(USER_TOKEN_KEY);
    localStorage.removeItem(LEGACY_GUEST_KEY);
    return "";
  }
  return localStorage.getItem(USER_TOKEN_KEY) || "";
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    userToken: getStoredUserToken(),
    adminToken: localStorage.getItem(ADMIN_TOKEN_KEY) || "",
    me: null,
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
      localStorage.setItem(USER_TOKEN_KEY, this.userToken);
      localStorage.removeItem(LEGACY_GUEST_KEY);
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
      localStorage.removeItem(USER_TOKEN_KEY);
      localStorage.removeItem(LEGACY_GUEST_KEY);
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
