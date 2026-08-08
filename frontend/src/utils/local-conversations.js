const STORAGE_KEY = "image-portal:local-conversations";

function newId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `local-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function normalizeConversation(value) {
  if (!value || typeof value !== "object" || typeof value.id !== "string") return null;
  const now = new Date().toISOString();
  return {
    id: value.id,
    title: typeof value.title === "string" ? value.title : "新对话",
    created_at: typeof value.created_at === "string" ? value.created_at : now,
    updated_at: typeof value.updated_at === "string" ? value.updated_at : now,
    messages: Array.isArray(value.messages) ? value.messages : [],
    backend_conversation_ids:
      value.backend_conversation_ids && typeof value.backend_conversation_ids === "object"
        ? value.backend_conversation_ids
        : {},
  };
}

function isInlineImage(value) {
  return typeof value === "string" && value.startsWith("data:image/");
}

function toStoredConversation(conversation) {
  return {
    ...conversation,
    messages: (conversation.messages || []).map((message) => {
      const storedMessage = { ...message };
      if (isInlineImage(storedMessage.ref_image_url)) delete storedMessage.ref_image_url;
      if (Array.isArray(storedMessage.image_urls)) {
        storedMessage.image_urls = storedMessage.image_urls.filter((url) => !isInlineImage(url));
      }
      return storedMessage;
    }),
  };
}

export function loadLocalConversations() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
    if (!Array.isArray(parsed)) return [];
    const conversations = parsed.map(normalizeConversation).filter(Boolean);
    const storedConversations = conversations.map(toStoredConversation);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(storedConversations));
    return storedConversations;
  } catch {
    return [];
  }
}

export function saveLocalConversations(conversations) {
  const storedConversations = conversations.map(toStoredConversation);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(storedConversations));
}

export function createLocalConversation() {
  const now = new Date().toISOString();
  return {
    id: newId(),
    title: "新对话",
    created_at: now,
    updated_at: now,
    messages: [],
    backend_conversation_ids: {},
  };
}
