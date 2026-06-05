/**
 * CRM Chat Center — load smoke (staging / local).
 *
 * Flow per VU: login → list chats → send one outbound message (when chat exists).
 * Default: 20 VUs, 5 minutes. Target envelope: ~10k messages/hour cluster-wide
 * (this script is a smoke skeleton, not a full soak).
 *
 * Run: see scripts/load/README.md
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const API = `${BASE_URL}/api/v1`;
const EMAIL = __ENV.LOAD_EMAIL || "operator.chats.a@crm.local";
const PASSWORD = __ENV.LOAD_PASSWORD || "TestPass!234567";
const CHAT_ID = __ENV.LOAD_CHAT_ID || "";

const messagesSent = new Counter("crm_messages_sent");
const loginFailures = new Rate("crm_login_failures");

export const options = {
  scenarios: {
    smoke: {
      executor: "constant-vus",
      vus: Number(__ENV.K6_VUS || 20),
      duration: __ENV.K6_DURATION || "5m",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    crm_login_failures: ["rate<0.01"],
  },
};

function login() {
  const res = http.post(
    `${API}/auth/login`,
    JSON.stringify({ email: EMAIL, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" }, tags: { name: "auth_login" } },
  );
  const ok = check(res, {
    "login status 200": (r) => r.status === 200,
    "login has token": (r) => r.json("access_token") !== undefined,
  });
  if (!ok) {
    loginFailures.add(1);
    return null;
  }
  loginFailures.add(0);
  return res.json("access_token");
}

function pickChatId(token) {
  if (CHAT_ID) {
    return CHAT_ID;
  }
  const res = http.get(`${API}/chats?limit=1`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    tags: { name: "chats_list" },
  });
  check(res, { "list chats 200": (r) => r.status === 200 });
  const items = res.json("items");
  if (!items || items.length === 0) {
    return null;
  }
  return String(items[0].id);
}

export default function () {
  const token = login();
  if (!token) {
    sleep(1);
    return;
  }

  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  const listRes = http.get(`${API}/chats?limit=20`, {
    headers,
    tags: { name: "chats_list" },
  });
  check(listRes, { "list chats 200": (r) => r.status === 200 });

  const chatId = pickChatId(token);
  if (!chatId) {
    sleep(1);
    return;
  }

  const clientMessageId = `k6-${__VU}-${__ITER}-${Date.now()}`;
  const sendRes = http.post(
    `${API}/chats/${chatId}/messages`,
    JSON.stringify({
      body: `k6 smoke ${clientMessageId}`,
      client_message_id: clientMessageId,
    }),
    { headers, tags: { name: "chats_send_message" } },
  );
  const sent = check(sendRes, {
    "send accepted": (r) => r.status === 202 || r.status === 200,
  });
  if (sent) {
    messagesSent.add(1);
  }

  sleep(Number(__ENV.K6_SLEEP || 3));
}
