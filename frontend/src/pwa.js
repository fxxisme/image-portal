import { ref } from "vue";
import { registerSW } from "virtual:pwa-register";

const deferredInstallPrompt = ref(null);
const canInstall = ref(false);
const updateAvailable = ref(false);
const isOffline = ref(false);
let updateServiceWorker = null;

export function registerPwa() {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;

  updateServiceWorker = registerSW({
    onNeedRefresh() {
      updateAvailable.value = true;
    },
  });

  const syncOnlineStatus = () => {
    isOffline.value = !navigator.onLine;
  };
  syncOnlineStatus();
  window.addEventListener("online", syncOnlineStatus);
  window.addEventListener("offline", syncOnlineStatus);

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstallPrompt.value = event;
    canInstall.value = true;
  });

  window.addEventListener("appinstalled", () => {
    deferredInstallPrompt.value = null;
    canInstall.value = false;
  });
}

export function usePwa() {
  async function install() {
    if (!deferredInstallPrompt.value) return;
    await deferredInstallPrompt.value.prompt();
    deferredInstallPrompt.value = null;
    canInstall.value = false;
  }

  function update() {
    updateServiceWorker?.(true);
  }

  return { canInstall, updateAvailable, isOffline, install, update };
}
